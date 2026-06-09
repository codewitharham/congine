"""Validate-contract workflow (Layer 3)."""

from __future__ import annotations

import json
import time

from congine_core.config import FailMode
from congine_core.domain.models import BreachDetail, TelemetryEvent, ValidationResult
from congine_core.domain.validator import IValidator
from congine_core.exceptions import (
    CongineBaseException,
    CongineContractNotFoundError,
    CongineValidationError,
)
from congine_core.pii_sanitize import sanitize_breach_message
from congine_core.ports.event_bus import IEventBus
from congine_core.ports.logger import ILogger
from congine_core.ports.schema_storage import ISchemaStorage
from congine_core.ports.validation_runner import IValidationRunner


class ValidateContractUseCase:
    """Validate an output payload against a contract (orchestration only)."""

    def __init__(
        self,
        schema_storage: ISchemaStorage,
        validator: IValidator,
        event_bus: IEventBus,
        logger: ILogger,
        timer: IValidationRunner,
        timeout_ms: int = 15,
        fail_mode: FailMode = FailMode.DEGRADE,
        max_payload_bytes: int = 1_048_576,
        max_schema_bytes: int = 1_048_576,
    ) -> None:
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
        payload: dict,
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
        except TimeoutError:
            result = self._degraded_on_timeout(contract_id, started)
        except (MemoryError, RecursionError) as exc:
            result = self._degraded_on_error(contract_id, started, exc, "resource_error")
        except CongineBaseException:
            raise
        except Exception as exc:
            result = self._degraded_on_error(contract_id, started, exc, "internal_error")

        return self._finalize(result, contract_id, contract_version)

    async def execute_async(
        self,
        payload: dict,
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
        except TimeoutError:
            result = self._degraded_on_timeout(contract_id, started)
        except (MemoryError, RecursionError) as exc:
            result = self._degraded_on_error(contract_id, started, exc, "resource_error")
        except CongineBaseException:
            raise
        except Exception as exc:
            result = self._degraded_on_error(contract_id, started, exc, "internal_error")

        return self._finalize(result, contract_id, contract_version)

    def _check_payload_size(self, payload: dict) -> ValidationResult | None:
        try:
            size = len(json.dumps(payload, default=str))
        except (TypeError, ValueError):
            size = 0
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

    def _check_schema_size(self, schema: dict) -> ValidationResult | None:
        try:
            size = len(json.dumps(schema, default=str))
        except (TypeError, ValueError):
            size = 0
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

    def _resolve_schema(self, contract_id: str) -> dict:
        schema = self.schema_storage.get(contract_id)
        if schema is None:
            self.logger.error("Schema not found", contract_id=contract_id)
            raise CongineContractNotFoundError(f"Schema {contract_id} not found")
        return schema

    def _degraded_on_timeout(
        self, contract_id: str, started: float
    ) -> ValidationResult:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        self.logger.warning(
            "Validation timeout",
            contract_id=contract_id,
            timeout_ms=self.timeout_ms,
        )
        return ValidationResult(
            status="fail",
            degraded=True,
            degraded_reason="timeout",
            duration_ms=elapsed_ms,
        )

    def _degraded_on_error(
        self,
        contract_id: str,
        started: float,
        exc: Exception,
        reason: str,
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
