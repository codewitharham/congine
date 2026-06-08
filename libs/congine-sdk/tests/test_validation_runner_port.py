"""Conformance tests for :class:`IValidationRunner` (the L1 port).

Validates that:
1. A custom fake implementing the port can be injected into
   :class:`ValidateContractUseCase` without using any L4 concrete.
2. Both the sync and async entry points route through the port — closing
   the audit-D-4 architecture gap and removing the getattr shim.
"""

from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict

import pytest

from congine_core.domain.models import ValidationResult
from congine_core.domain.validator import IValidator
from congine_core.ports.validation_runner import IValidationRunner
from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase
from tests.conftest import FakeEventBus, FakeLogger, FakeSchemaStorage


class FakeRunner:
    """A minimal :class:`IValidationRunner` that runs callables inline."""

    def __init__(self) -> None:
        self.capacity = 1
        self.sync_calls = 0
        self.async_calls = 0

    def run_with_timeout(self, func: Callable[[], Any], timeout_ms: int) -> Any:
        self.sync_calls += 1
        return func()

    async def run_with_timeout_async(
        self, func: Callable[[], Any], timeout_ms: int
    ) -> Any:
        self.async_calls += 1
        return func()

    def health(self) -> Dict[str, Any]:
        return {"in_flight": 0, "rejected_total": 0, "capacity": self.capacity}


class _StubValidator(IValidator):
    """An :class:`IValidator` that always returns a pass result."""

    def validate(self, payload: dict, schema: dict) -> ValidationResult:
        return ValidationResult(status="pass", duration_ms=0.0)


def test_fake_runner_satisfies_protocol() -> None:
    """The fake conforms structurally to the port (runtime_checkable)."""
    runner = FakeRunner()
    assert isinstance(runner, IValidationRunner)


def test_bounded_executor_satisfies_protocol() -> None:
    """The production executor conforms structurally to the port."""
    from congine_core.infrastructure.bounded_executor import BoundedValidationExecutor

    executor = BoundedValidationExecutor(
        max_workers=1, max_pending=0, register_atexit=False
    )
    try:
        assert isinstance(executor, IValidationRunner)
        assert executor.capacity == 1
        assert executor.health() == {"in_flight": 0, "rejected_total": 0, "capacity": 1}
    finally:
        executor.shutdown(wait=False)


def test_execute_routes_through_sync_port() -> None:
    runner = FakeRunner()
    storage = FakeSchemaStorage({"c": {"type": "object"}})
    use_case = ValidateContractUseCase(
        schema_storage=storage,
        validator=_StubValidator(),
        event_bus=FakeEventBus(),
        logger=FakeLogger(),
        timer=runner,
        timeout_ms=100,
    )
    result = use_case.execute({"x": 1}, "c", "v1")
    assert result.is_pass()
    assert runner.sync_calls == 1
    assert runner.async_calls == 0


def test_execute_async_routes_through_async_port() -> None:
    runner = FakeRunner()
    storage = FakeSchemaStorage({"c": {"type": "object"}})
    use_case = ValidateContractUseCase(
        schema_storage=storage,
        validator=_StubValidator(),
        event_bus=FakeEventBus(),
        logger=FakeLogger(),
        timer=runner,
        timeout_ms=100,
    )
    result = asyncio.run(use_case.execute_async({"x": 1}, "c", "v1"))
    assert result.is_pass()
    assert runner.async_calls == 1
    assert runner.sync_calls == 0


def test_execute_async_propagates_runner_timeout() -> None:
    """Demonstrates that async TimeoutError from the runner degrades, not raises."""

    class TimeoutRunner(FakeRunner):
        async def run_with_timeout_async(
            self, func: Callable[[], Any], timeout_ms: int
        ) -> Any:
            self.async_calls += 1
            raise TimeoutError("synthetic")

    runner = TimeoutRunner()
    storage = FakeSchemaStorage({"c": {"type": "object"}})
    use_case = ValidateContractUseCase(
        schema_storage=storage,
        validator=_StubValidator(),
        event_bus=FakeEventBus(),
        logger=FakeLogger(),
        timer=runner,
        timeout_ms=1,
    )
    result = asyncio.run(use_case.execute_async({"x": 1}, "c", "v1"))
    assert result.degraded is True
    assert result.status == "fail"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
