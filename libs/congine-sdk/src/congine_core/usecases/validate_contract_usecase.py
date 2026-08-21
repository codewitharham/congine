"""Validate-contract workflow (Layer 3)."""

from __future__ import annotations

import json
import time
from typing import Any

from congine_core.config import DEFAULT_VALIDATION_TIMEOUT_MS, FailMode
from congine_core.models import (
    BreachDetail,
    DegradedReason,
    TelemetryEvent,
    ValidationResult,
)
from congine_core.domain.validator import IValidator
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
from congine_core.ports.validation_runner import IValidationRunner


def _require_protocol(role: str, implementation: object, protocol: type[Any]) -> None:
    """Fail fast when a constructor-injected role misses its declared port."""
    if not isinstance(implementation, protocol):
        raise CongineConfigurationError(
            f"Invalid {role}: expected an implementation of {protocol.__name__}"
        )


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
        fail_mode: FailMode = FailMode.DEGRADE,
        max_payload_bytes: int = 1_048_576,
        max_schema_bytes: int = 1_048_576,
    ) -> None:
        _require_protocol("schema_storage", schema_storage, ISchemaStorage)
        _require_protocol("validator", validator, IValidator)
        _require_protocol("event_bus", event_bus, IEventBus)
        _require_protocol("logger", logger, ILogger)
        _require_protocol("validation_runner", timer, IValidationRunner)

        self.schema_storage = schema_storage
        self.validator = validator
        self.event_bus = event_bus
        self.logger = logger
        self.timer = timer
        self.timeout_ms = timeout_ms
        self.fail_mode = fail_mode
        self.max_payload_bytes = max_payload_bytes
        self.max_schema_bytes = max_schema_bytes

    def execute(
        self,
        payload: dict[str, Any],
        contract_id: str,
        contract_version: str,
    ) -> ValidationResult:
        """Run the validation workflow."""
        oversize = self._check_payload_size(payload)
        if oversize is not None:
            return self._finalize(oversize, contract_id, contract_version)

        schema = self._resolve_schema(contract_id)
        schema_oversize = self._check_schema_size(schema)
        if schema_oversize is not None:
            return self._finalize(schema_oversize, contract_id, contract_version)

        def do_validate() -> ValidationResult:
            return self.validator.validate(payload, schema)

        started = time.perf_counter()
        try:
            result = self.timer.run_with_timeout(do_validate, self.timeout_ms)
        except LoadShedError:
            # MUST precede TimeoutError: LoadShedError subclasses it (audit P0-06).
            result = self._degraded_on_capacity(contract_id, started)
        except TimeoutError:
            result = self._degraded_on_timeout(contract_id, started)
        except (MemoryError, RecursionError) as exc:
            result = self._degraded_on_error(
                contract_id, started, exc, DegradedReason.RESOURCE_ERROR
            )
        except CongineBaseException:
            raise
        except Exception as exc:
            result = self._degraded_on_error(
                contract_id, started, exc, DegradedReason.INTERNAL_ERROR
            )

        return self._finalize(result, contract_id, contract_version)

    async def execute_async(
        self,
        payload: dict[str, Any],
        contract_id: str,
        contract_version: str,
    ) -> ValidationResult:
        """Async twin of :meth:`execute`."""
        oversize = self._check_payload_size(payload)
        if oversize is not None:
            return self._finalize(oversize, contract_id, contract_version)

        schema = self._resolve_schema(contract_id)
        schema_oversize = self._check_schema_size(schema)
        if schema_oversize is not None:
            return self._finalize(schema_oversize, contract_id, contract_version)

        def do_validate() -> ValidationResult:
            return self.validator.validate(payload, schema)

        started = time.perf_counter()
        try:
            result = await self.timer.run_with_timeout_async(
                do_validate, self.timeout_ms
            )
        except LoadShedError:
            # MUST precede TimeoutError: LoadShedError subclasses it (audit P0-06).
            result = self._degraded_on_capacity(contract_id, started)
        except TimeoutError:
            result = self._degraded_on_timeout(contract_id, started)
        except (MemoryError, RecursionError) as exc:
            result = self._degraded_on_error(
                contract_id, started, exc, DegradedReason.RESOURCE_ERROR
            )
        except CongineBaseException:
            raise
        except Exception as exc:
            result = self._degraded_on_error(
                contract_id, started, exc, DegradedReason.INTERNAL_ERROR
            )

        return self._finalize(result, contract_id, contract_version)

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
    ) -> ValidationResult:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.logger.error(
            "Validation error",
            contract_id=contract_id,
            error_type=type(exc).__name__,
            degraded_reason=reason,
        )
        return ValidationResult(
            status="fail",
            degraded=True,
            degraded_reason=reason,
            duration_ms=elapsed_ms,
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
