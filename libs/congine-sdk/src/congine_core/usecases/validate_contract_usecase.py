"""Validate-contract workflow (Layer 3)."""

from __future__ import annotations

import json
import time
from dataclasses import replace
from typing import Any, Callable, Optional

from congine_core.config import DEFAULT_VALIDATION_TIMEOUT_MS, FailMode
from congine_core.models import (
    BreachDetail,
    EvaluationStage,
    DegradedReason,
    TelemetryEvent,
    ValidationResult,
)
from congine_core.domain.validator import CompositeValidator, IValidator
from congine_core.exceptions import (
    CongineBaseException,
    CongineConfigurationError,
    CongineContractNotFoundError,
    CongineValidationError,
    LoadShedError,
)
from congine_core.pii_sanitize import sanitize_breach_message
from congine_core.ports.event_bus import IEventBus
from congine_core.ports.logger import ILogger
from congine_core.ports.schema_storage import ISchemaStorage
from congine_core.ports.semantic_validator import ISemanticValidator
from congine_core.ports.validation_runner import IValidationRunner


def _require_protocol(role: str, implementation: object, protocol: type[Any]) -> None:
    """Fail fast when a constructor-injected role misses its declared port."""
    if not isinstance(implementation, protocol):
        raise CongineConfigurationError(
            f"Invalid {role}: expected an implementation of {protocol.__name__}"
        )


class _StageBudget:
    """Absolute monotonic deadlines for one governed validation.

    Two deadlines are tracked, not one, and that distinction is the whole point.
    An aggregate deadline alone cannot enforce a stage cap: with a 100 ms
    aggregate and a 20 ms native cap, a runner that returns normally at 30 ms has
    blown its stage cap while the aggregate still has 70 ms left. Accepting that
    result would make the configured cap decorative.

    All arithmetic uses :func:`time.monotonic_ns`. Wall-clock time is unusable
    here: an NTP step could move a deadline backwards mid-validation.
    """

    __slots__ = ("aggregate_deadline_ns", "_stage_deadline_ns")

    def __init__(self, aggregate_timeout_ms: int) -> None:
        self.aggregate_deadline_ns = (
            time.monotonic_ns() + aggregate_timeout_ms * 1_000_000
        )
        self._stage_deadline_ns = self.aggregate_deadline_ns

    def aggregate_remaining_ns(self) -> int:
        """Nanoseconds left in the aggregate budget; may be negative."""
        return self.aggregate_deadline_ns - time.monotonic_ns()

    def open_stage(self, stage_cap_ms: Optional[int]) -> int:
        """Begin a stage and return its wait budget in whole milliseconds.

        The stage deadline is the earlier of its own cap and the aggregate
        deadline, so a stage can never extend the aggregate budget.

        Returns ``0`` when there is not enough time left to express a positive
        millisecond wait. Callers treat that as "exhausted" rather than rounding
        up, because rounding up is precisely how a budget silently grows.
        """
        now = time.monotonic_ns()
        self._stage_deadline_ns = self.aggregate_deadline_ns
        if stage_cap_ms is not None:
            self._stage_deadline_ns = min(
                self.aggregate_deadline_ns, now + stage_cap_ms * 1_000_000
            )
        # Floor division: never round upward past the logical deadline.
        return max(0, (self._stage_deadline_ns - now) // 1_000_000)

    def stage_expired(self) -> bool:
        """Whether the current stage's deadline has passed.

        ``>=`` because a deadline names the instant at which the budget is no
        longer valid, not the last instant it is.
        """
        return time.monotonic_ns() >= self._stage_deadline_ns

    def aggregate_expired(self) -> bool:
        """Whether the aggregate deadline has passed."""
        return time.monotonic_ns() >= self.aggregate_deadline_ns

    def exhausted(self) -> bool:
        """Whether either applicable deadline has passed.

        Used for the mandatory post-stage check: a normal stage result is
        discarded if *either* deadline expired while it was running.
        """
        return self.stage_expired() or self.aggregate_expired()


class ValidateContractUseCase:
    """Validate an output payload against a contract (orchestration only)."""

    def __init__(
        self,
        schema_storage: ISchemaStorage,
        validator: IValidator,
        event_bus: IEventBus,
        logger: ILogger,
        timer: IValidationRunner,
        # Single source of truth (audit P0-07 / Q17): this used to default to 15
        # while configuration defaulted to 100, so direct construction silently
        # ran a budget almost 7x tighter than the documented one.
        timeout_ms: int = DEFAULT_VALIDATION_TIMEOUT_MS,
        semantic_validator: "Optional[ISemanticValidator]" = None,
        native_timeout_ms: "Optional[int]" = None,
        semantic_timeout_ms: "Optional[int]" = None,
        fail_mode: FailMode = FailMode.DEGRADE,
        max_payload_bytes: int = 1_048_576,
        max_schema_bytes: int = 1_048_576,
    ) -> None:
        _require_protocol("schema_storage", schema_storage, ISchemaStorage)
        _require_protocol("validator", validator, IValidator)
        if semantic_validator is not None:
            _require_protocol(
                "semantic_validator", semantic_validator, ISemanticValidator
            )
            # A CompositeValidator already runs semantic evaluation internally,
            # so pairing one with a separate semantic validator would evaluate
            # semantics twice and make the stage budgets meaningless. Refused at
            # construction rather than left as a latent wiring trap.
            if isinstance(validator, CompositeValidator):
                raise CongineConfigurationError(
                    "Invalid validator: a CompositeValidator already performs "
                    "semantic validation, so it cannot be combined with a "
                    "separate semantic_validator. Pass the native validator "
                    "(e.g. LocalValidator) instead; staged budgets require the "
                    "use case to schedule each stage itself."
                )
        _require_protocol("event_bus", event_bus, IEventBus)
        _require_protocol("logger", logger, ILogger)
        _require_protocol("validation_runner", timer, IValidationRunner)

        self.schema_storage = schema_storage
        self.validator = validator
        self.event_bus = event_bus
        self.logger = logger
        self.timer = timer
        self.timeout_ms = timeout_ms
        self.semantic_validator = semantic_validator
        self.native_timeout_ms = native_timeout_ms
        self.semantic_timeout_ms = semantic_timeout_ms
        self.fail_mode = fail_mode
        self.max_payload_bytes = max_payload_bytes
        self.max_schema_bytes = max_schema_bytes

    def execute(
        self,
        payload: dict[str, Any],
        contract_id: str,
        contract_version: str,
    ) -> ValidationResult:
        """Run the governed validation workflow under staged budgets.

        The aggregate deadline starts **here**, after contract resolution and the
        size preflight, so repository/storage I/O is not silently charged to a
        validation budget.
        """
        oversize = self._check_payload_size(payload)
        if oversize is not None:
            return self._finalize(oversize, contract_id, contract_version)

        schema = self._resolve_schema(contract_id)
        schema_oversize = self._check_schema_size(schema)
        if schema_oversize is not None:
            return self._finalize(schema_oversize, contract_id, contract_version)

        budget = _StageBudget(self.timeout_ms)
        started = time.perf_counter()

        native = self._run_stage(
            lambda: self.validator.validate(payload, schema),
            budget=budget,
            stage=EvaluationStage.NATIVE,
            stage_cap_ms=self.native_timeout_ms,
            contract_id=contract_id,
            started=started,
        )
        if isinstance(native, ValidationResult) and native.degraded:
            return self._finalize(native, contract_id, contract_version)

        if self.semantic_validator is None:
            return self._finalize(
                self._staged(native, EvaluationStage.NATIVE),
                contract_id,
                contract_version,
            )

        # Native completed, but the aggregate budget may already be gone. The
        # required semantic stage is then the one that cannot be completed, so
        # the truthful outcome is a semantic timeout — never the native PASS.
        if budget.aggregate_expired():
            return self._finalize(
                self._degraded(
                    contract_id,
                    started,
                    DegradedReason.SEMANTIC_TIMEOUT,
                    EvaluationStage.SEMANTIC,
                    "Aggregate validation budget exhausted before semantic evaluation",
                ),
                contract_id,
                contract_version,
            )

        semantic = self._run_stage(
            lambda: self.semantic_validator.validate(payload, schema),  # type: ignore[union-attr]
            budget=budget,
            stage=EvaluationStage.SEMANTIC,
            stage_cap_ms=self.semantic_timeout_ms,
            contract_id=contract_id,
            started=started,
        )
        if isinstance(semantic, ValidationResult) and semantic.degraded:
            return self._finalize(semantic, contract_id, contract_version)

        return self._finalize(
            self._merge(native, semantic, started),
            contract_id,
            contract_version,
        )

    def _run_stage(
        self,
        work: "Callable[[], Any]",
        *,
        budget: _StageBudget,
        stage: EvaluationStage,
        stage_cap_ms: "Optional[int]",
        contract_id: str,
        started: float,
    ) -> Any:
        """Execute one stage under its deadline, or return a degraded result.

        Returns either the stage's own value or a degraded
        :class:`ValidationResult`; the caller distinguishes them by type.

        The post-stage check is the part that cannot be dropped. A runner may
        return normally just after its deadline — through scheduler latency, a
        ``Future.result`` race, or the reentrant inline path, which is not
        preemptible at all. Accepting such a result would let a late PASS become
        an enforced PASS, which is exactly the false safety this phase exists to
        prevent.
        """
        timeout_reason = (
            DegradedReason.TIMEOUT
            if stage is EvaluationStage.NATIVE
            else DegradedReason.SEMANTIC_TIMEOUT
        )

        wait_ms = budget.open_stage(stage_cap_ms)
        if wait_ms <= 0:
            return self._degraded(
                contract_id,
                started,
                timeout_reason,
                stage,
                f"No budget remained for the {stage} stage",
            )

        try:
            value = self.timer.run_with_timeout(work, wait_ms)
        except LoadShedError:
            # MUST precede TimeoutError: LoadShedError subclasses it (P0-06), so
            # reversing these two would report every load shed as a timeout.
            return self._degraded(
                contract_id,
                started,
                DegradedReason.LOAD_SHED,
                stage,
                f"Capacity exhausted before the {stage} stage could run",
            )
        except TimeoutError:
            return self._degraded(
                contract_id, started, timeout_reason, stage, f"{stage} stage timed out"
            )
        except (MemoryError, RecursionError) as exc:
            return self._degraded_on_error(
                contract_id, started, exc, DegradedReason.RESOURCE_ERROR, stage
            )
        except CongineBaseException:
            raise
        except Exception as exc:  # noqa: BLE001 - unexpected evaluator failure
            return self._degraded_on_error(
                contract_id, started, exc, DegradedReason.INTERNAL_ERROR, stage
            )

        if budget.exhausted():
            return self._degraded(
                contract_id,
                started,
                timeout_reason,
                stage,
                f"{stage} stage returned after its deadline had expired",
            )
        return value

    @staticmethod
    def _staged(result: ValidationResult, stage: EvaluationStage) -> ValidationResult:
        """Tag a normal result with the stage that produced it."""
        return replace(result, evaluation_stage=stage)

    def _merge(
        self,
        native: ValidationResult,
        semantic_breaches: "list[BreachDetail]",
        started: float,
    ) -> ValidationResult:
        """Combine both stages, preserving current breach behaviour.

        Native breaches first, then semantic — the same order and the same
        duplicate handling ``CompositeValidator`` has always produced, so moving
        scheduling into the use case does not change what a caller sees.
        """
        breaches = list(native.breaches) + list(semantic_breaches)
        return ValidationResult(
            status="pass" if not breaches else "fail",
            breaches=tuple(breaches),
            duration_ms=(time.perf_counter() - started) * 1000.0,
            degraded=native.degraded,
            degraded_reason=native.degraded_reason,
            evaluation_stage=EvaluationStage.SEMANTIC,
        )

    def _degraded(
        self,
        contract_id: str,
        started: float,
        reason: DegradedReason,
        stage: EvaluationStage,
        message: str,
    ) -> ValidationResult:
        """Build a non-enforced result naming both the reason and the stage."""
        level = (
            self.logger.warning
            if reason
            in (
                DegradedReason.TIMEOUT,
                DegradedReason.SEMANTIC_TIMEOUT,
                DegradedReason.LOAD_SHED,
            )
            else self.logger.error
        )
        level(
            message,
            contract_id=contract_id,
            timeout_ms=self.timeout_ms,
            degraded_reason=reason,
            evaluation_stage=stage,
        )
        return ValidationResult(
            status="fail",
            degraded=True,
            degraded_reason=reason,
            duration_ms=(time.perf_counter() - started) * 1000.0,
            evaluation_stage=stage,
        )

    async def execute_async(
        self,
        payload: dict[str, Any],
        contract_id: str,
        contract_version: str,
    ) -> ValidationResult:
        """Async twin of :meth:`execute`, with identical budget semantics.

        Deliberately mirrors the synchronous staging step for step. An async
        caller must not get weaker enforcement than a sync one, so the aggregate
        deadline, the stage caps and both post-stage checks all behave the same;
        only the awaiting primitive differs.
        """
        oversize = self._check_payload_size(payload)
        if oversize is not None:
            return self._finalize(oversize, contract_id, contract_version)

        schema = self._resolve_schema(contract_id)
        schema_oversize = self._check_schema_size(schema)
        if schema_oversize is not None:
            return self._finalize(schema_oversize, contract_id, contract_version)

        budget = _StageBudget(self.timeout_ms)
        started = time.perf_counter()

        native = await self._run_stage_async(
            lambda: self.validator.validate(payload, schema),
            budget=budget,
            stage=EvaluationStage.NATIVE,
            stage_cap_ms=self.native_timeout_ms,
            contract_id=contract_id,
            started=started,
        )
        if isinstance(native, ValidationResult) and native.degraded:
            return self._finalize(native, contract_id, contract_version)

        if self.semantic_validator is None:
            return self._finalize(
                self._staged(native, EvaluationStage.NATIVE),
                contract_id,
                contract_version,
            )

        if budget.aggregate_expired():
            return self._finalize(
                self._degraded(
                    contract_id,
                    started,
                    DegradedReason.SEMANTIC_TIMEOUT,
                    EvaluationStage.SEMANTIC,
                    "Aggregate validation budget exhausted before semantic evaluation",
                ),
                contract_id,
                contract_version,
            )

        semantic = await self._run_stage_async(
            lambda: self.semantic_validator.validate(payload, schema),  # type: ignore[union-attr]
            budget=budget,
            stage=EvaluationStage.SEMANTIC,
            stage_cap_ms=self.semantic_timeout_ms,
            contract_id=contract_id,
            started=started,
        )
        if isinstance(semantic, ValidationResult) and semantic.degraded:
            return self._finalize(semantic, contract_id, contract_version)

        return self._finalize(
            self._merge(native, semantic, started),
            contract_id,
            contract_version,
        )

    async def _run_stage_async(
        self,
        work: "Callable[[], Any]",
        *,
        budget: _StageBudget,
        stage: EvaluationStage,
        stage_cap_ms: "Optional[int]",
        contract_id: str,
        started: float,
    ) -> Any:
        """Async twin of :meth:`_run_stage`, including the post-stage check."""
        timeout_reason = (
            DegradedReason.TIMEOUT
            if stage is EvaluationStage.NATIVE
            else DegradedReason.SEMANTIC_TIMEOUT
        )

        wait_ms = budget.open_stage(stage_cap_ms)
        if wait_ms <= 0:
            return self._degraded(
                contract_id,
                started,
                timeout_reason,
                stage,
                f"No budget remained for the {stage} stage",
            )

        try:
            value = await self.timer.run_with_timeout_async(work, wait_ms)
        except LoadShedError:
            # MUST precede TimeoutError: LoadShedError subclasses it (audit P0-06).
            return self._degraded(
                contract_id,
                started,
                DegradedReason.LOAD_SHED,
                stage,
                f"Capacity exhausted before the {stage} stage could run",
            )
        except TimeoutError:
            return self._degraded(
                contract_id, started, timeout_reason, stage, f"{stage} stage timed out"
            )
        except (MemoryError, RecursionError) as exc:
            return self._degraded_on_error(
                contract_id, started, exc, DegradedReason.RESOURCE_ERROR, stage
            )
        except CongineBaseException:
            raise
        except Exception as exc:  # noqa: BLE001 - unexpected evaluator failure
            return self._degraded_on_error(
                contract_id, started, exc, DegradedReason.INTERNAL_ERROR, stage
            )

        if budget.exhausted():
            return self._degraded(
                contract_id,
                started,
                timeout_reason,
                stage,
                f"{stage} stage returned after its deadline had expired",
            )
        return value

    def _check_payload_size(self, payload: dict[str, Any]) -> ValidationResult | None:
        """Enforce the payload size bound, failing **closed** if unmeasurable.

        A payload that cannot be serialised used to be recorded as ``size = 0``
        and sailed straight past the bound (audit P0-02) — an input could evade
        a security control precisely by being malformed.

        The replacement is a *degradation*, not a breach: we never measured the
        payload, so we cannot claim it exceeded a limit. Saying "policy violated"
        here would fabricate a verdict we never reached. The caller sees
        ``is_enforced() is False`` with reason ``INVALID_PAYLOAD``.

        The catch is deliberately broad. Because ``default=str`` already absorbs
        ordinary unserialisable values, what actually reaches here are hostile or
        pathological payloads — a circular reference (``ValueError``), a non-string
        mapping key (``TypeError``), or an object whose own ``__str__``/``__repr__``
        raises something else entirely. Narrow catching let that last class escape
        uncaught into the host, bypassing telemetry and the fail-mode policy. A
        size guard must fail closed for *every* reason it cannot measure, not for
        an enumerated subset.
        """
        try:
            size = len(json.dumps(payload, default=str))
        except Exception:
            return self._degraded_unmeasurable(
                field="<root>",
                reason=DegradedReason.INVALID_PAYLOAD,
                message="Payload could not be serialised for size measurement",
            )
        if size > self.max_payload_bytes:
            return ValidationResult(
                status="fail",
                breaches=(
                    BreachDetail(
                        rule="INPUT_BOUNDS",
                        field="<root>",
                        message="Payload exceeds max_payload_bytes budget",
                    ),
                ),
            )
        return None

    def _check_schema_size(self, schema: dict[str, Any]) -> ValidationResult | None:
        """Enforce the schema size bound, failing **closed** if unmeasurable.

        See :meth:`_check_payload_size`, including why the catch is broad. An
        unmeasurable *schema* is a defective contract rather than a defective
        payload, so it degrades with ``INVALID_CONTRACT``.
        """
        try:
            size = len(json.dumps(schema, default=str))
        except Exception:
            return self._degraded_unmeasurable(
                field="<schema>",
                reason=DegradedReason.INVALID_CONTRACT,
                message="Schema could not be serialised for size measurement",
            )
        if size > self.max_schema_bytes:
            return ValidationResult(
                status="fail",
                breaches=(
                    BreachDetail(
                        rule="INPUT_BOUNDS",
                        field="<schema>",
                        message="Schema exceeds max_schema_bytes budget",
                    ),
                ),
            )
        return None

    def _degraded_unmeasurable(
        self, *, field: str, reason: DegradedReason, message: str
    ) -> ValidationResult:
        """Build the fail-closed result for an input we could not measure.

        Carries **no breaches** by design: evaluation inability is not a policy
        violation. ``degraded=True`` is what makes the difference legible to the
        caller via :meth:`ValidationResult.is_enforced`.
        """
        self.logger.error(message, field=field, degraded_reason=reason)
        return ValidationResult(
            status="fail",
            degraded=True,
            degraded_reason=reason,
        )

    def _resolve_schema(self, contract_id: str) -> dict[str, Any]:
        schema = self.schema_storage.get(contract_id)
        if schema is None:
            self.logger.error("Schema not found", contract_id=contract_id)
            raise CongineContractNotFoundError(f"Schema {contract_id} not found")
        return schema

    def _degraded_on_timeout(
        self, contract_id: str, started: float
    ) -> ValidationResult:
        """The validation ran but overran its deadline."""
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.logger.warning(
            "Validation timeout",
            contract_id=contract_id,
            timeout_ms=self.timeout_ms,
            degraded_reason=DegradedReason.TIMEOUT,
        )
        return ValidationResult(
            status="fail",
            degraded=True,
            degraded_reason=DegradedReason.TIMEOUT,
            duration_ms=elapsed_ms,
        )

    def _degraded_on_capacity(
        self, contract_id: str, started: float
    ) -> ValidationResult:
        """Capacity was exhausted, so the validation never ran (audit P0-06).

        Distinct from :meth:`_degraded_on_timeout` in both reason and log
        message: an operator seeing this needs to scale or shed upstream, not to
        investigate a slow contract.
        """
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.logger.warning(
            "Validation load shed (capacity exhausted)",
            contract_id=contract_id,
            timeout_ms=self.timeout_ms,
            degraded_reason=DegradedReason.LOAD_SHED,
        )
        return ValidationResult(
            status="fail",
            degraded=True,
            degraded_reason=DegradedReason.LOAD_SHED,
            duration_ms=elapsed_ms,
        )

    def _degraded_on_error(
        self,
        contract_id: str,
        started: float,
        exc: Exception,
        reason: DegradedReason,
        stage: "Optional[EvaluationStage]" = None,
    ) -> ValidationResult:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.logger.error(
            "Validation error",
            contract_id=contract_id,
            error_type=type(exc).__name__,
            degraded_reason=reason,
            evaluation_stage=stage,
        )
        return ValidationResult(
            status="fail",
            degraded=True,
            degraded_reason=reason,
            duration_ms=elapsed_ms,
            evaluation_stage=stage,
        )

    def _finalize(
        self,
        result: ValidationResult,
        contract_id: str,
        contract_version: str,
    ) -> ValidationResult:
        event = TelemetryEvent(
            contract_id=contract_id,
            contract_version=contract_version,
            status=result.status,
            duration_ms=result.duration_ms,
            breach_details=[
                {
                    "rule": b.rule,
                    "field": b.field,
                    "message": sanitize_breach_message(b.message or ""),
                }
                for b in result.breaches
            ],
            # Carried only when enforcement did not complete. Together these two
            # make the four degraded outcomes machine-distinguishable — native
            # timeout, semantic timeout, native load shed, semantic load shed —
            # which a single `degraded_reason` could not do.
            # Gated on `degraded` so a successful event keeps its exact previous
            # wire shape: the stage that produced a PASS is not information any
            # consumer asked for, and emitting it would change every event on the
            # happy path to buy nothing.
            degraded_reason=(
                str(result.degraded_reason)
                if result.degraded and result.degraded_reason
                else None
            ),
            evaluation_stage=(
                str(result.evaluation_stage)
                if result.degraded and result.evaluation_stage
                else None
            ),
        )
        self.event_bus.publish(event)

        if not result.is_pass():
            self._handle_failure(result, contract_id, contract_version)

        return result

    def _handle_failure(
        self,
        result: ValidationResult,
        contract_id: str,
        contract_version: str,
    ) -> None:
        if self.fail_mode is FailMode.SILENT:
            return

        if self.fail_mode is FailMode.STRICT:
            self.logger.error(
                "Validation failed (strict)",
                contract_id=contract_id,
                contract_version=contract_version,
                breaches=len(result.breaches),
                degraded=result.degraded,
            )
            raise CongineValidationError(
                f"Contract {contract_id} validation failed "
                f"with {len(result.breaches)} breach(es)"
            )

        self.logger.warning(
            "Validation failed (degrade)",
            contract_id=contract_id,
            contract_version=contract_version,
            breaches=len(result.breaches),
            degraded=result.degraded,
        )
