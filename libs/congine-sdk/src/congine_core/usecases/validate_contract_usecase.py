"""Validate-contract workflow (Layer 3).

:class:`ValidateContractUseCase` orchestrates the validation hot path: fetch the
schema from storage, validate under a timeout, then publish a telemetry event.
It depends only on Layer 1 abstractions (injected via the constructor); the
sole concrete collaborator is the cross-platform :class:`ValidationTimer`
utility, typed under ``TYPE_CHECKING`` to keep this layer decoupled from Layer 4.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from congine_core.config import FailMode
from congine_core.domain.models import TelemetryEvent, ValidationResult
from congine_core.domain.validator import IValidator
from congine_core.exceptions import (
    CongineContractNotFoundError,
    CongineValidationError,
)
from congine_core.repositories.event_bus import IEventBus
from congine_core.repositories.logger import ILogger
from congine_core.repositories.schema_storage import ISchemaStorage

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.infrastructure.timer import ValidationTimer


class ValidateContractUseCase:
    """Validate an output payload against a contract (orchestration only)."""

    def __init__(
        self,
        schema_storage: ISchemaStorage,
        validator: IValidator,
        event_bus: IEventBus,
        logger: ILogger,
        timer: "ValidationTimer",
        timeout_ms: int = 15,
        fail_mode: FailMode = FailMode.DEGRADE,
    ) -> None:
        """Constructor injection of all collaborators.

        Args:
            schema_storage: Schema cache abstraction.
            validator: Validation strategy abstraction.
            event_bus: Telemetry event publisher abstraction.
            logger: Structured logger abstraction.
            timer: Cross-platform timeout runner.
            timeout_ms: Per-validation wall-clock budget in milliseconds.
            fail_mode: Behaviour on a failing validation —
                :attr:`FailMode.STRICT` raises,
                :attr:`FailMode.DEGRADE` logs and returns,
                :attr:`FailMode.SILENT` returns without error logging.
        """
        self.schema_storage = schema_storage
        self.validator = validator
        self.event_bus = event_bus
        self.logger = logger
        self.timer = timer
        self.timeout_ms = timeout_ms
        self.fail_mode = fail_mode

    def execute(
        self,
        payload: dict,
        contract_id: str,
        contract_version: str,
    ) -> ValidationResult:
        """Run the validation workflow.

        Steps:
            1. Resolve the schema from storage (abstraction).
            2. Validate under a timeout (domain logic), degrading on
               timeout/error.
            3. Publish a telemetry event (fire-and-forget).

        Args:
            payload: The output to validate.
            contract_id: Identifier of the contract to validate against.
            contract_version: Version string recorded in telemetry.

        Returns:
            The :class:`ValidationResult` (possibly ``degraded``).

        Raises:
            CongineContractNotFoundError: If no schema is cached for
                *contract_id*.
            CongineValidationError: If the result is a failure and the
                configured :class:`FailMode` is :attr:`FailMode.STRICT`.
        """
        # Step 1: Fetch schema.
        schema = self.schema_storage.get(contract_id)
        if schema is None:
            self.logger.error("Schema not found", contract_id=contract_id)
            raise CongineContractNotFoundError(f"Schema {contract_id} not found")

        # Step 2: Validate with timeout.
        def do_validate() -> ValidationResult:
            return self.validator.validate(payload, schema)

        try:
            result = self.timer.run_with_timeout(do_validate, self.timeout_ms)
        except TimeoutError:
            self.logger.warning(
                "Validation timeout",
                contract_id=contract_id,
                timeout_ms=self.timeout_ms,
            )
            result = ValidationResult(status="fail", degraded=True)
        except Exception as exc:  # noqa: BLE001 - degrade on any validation error
            self.logger.error(
                "Validation error",
                contract_id=contract_id,
                error=str(exc),
            )
            result = ValidationResult(status="fail", degraded=True)

        # Step 3: Publish telemetry (fire-and-forget). Published BEFORE any
        # fail-mode escalation so a STRICT raise never loses the event.
        event = TelemetryEvent(
            contract_id=contract_id,
            contract_version=contract_version,
            status=result.status,
            duration_ms=result.duration_ms,
            breach_details=[
                {"rule": b.rule, "field": b.field, "message": b.message}
                for b in result.breaches
            ],
        )
        self.event_bus.publish(event)

        # Step 4: Enforce fail mode on a failing result.
        if not result.is_pass():
            self._handle_failure(result, contract_id, contract_version)

        return result

    def _handle_failure(
        self,
        result: ValidationResult,
        contract_id: str,
        contract_version: str,
    ) -> None:
        """Apply the configured :class:`FailMode` to a failing *result*.

        Args:
            result: The failing validation result.
            contract_id: Identifier of the validated contract.
            contract_version: Version of the validated contract.

        Raises:
            CongineValidationError: When :attr:`FailMode.STRICT` is configured.
        """
        if self.fail_mode is FailMode.SILENT:
            # Swallow: no error logging, no raise — caller inspects the result.
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

        # FailMode.DEGRADE (default): log and continue.
        self.logger.warning(
            "Validation failed (degrade)",
            contract_id=contract_id,
            contract_version=contract_version,
            breaches=len(result.breaches),
            degraded=result.degraded,
        )
