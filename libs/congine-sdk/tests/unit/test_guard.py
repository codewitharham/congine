"""Unit tests for :mod:`congine_core.adapters.guard`."""

from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
import types
from typing import Any, Dict, List, Tuple

import pytest

from congine_core.adapters.guard import congine_guard
from congine_core.domain.models import BreachDetail, ValidationResult
from congine_core.exceptions import CongineLifecycleError, CongineValidationError


class _FakeUseCase:
    def __init__(self, status: str = "pass") -> None:
        self.calls: List[Tuple[Any, str, str]] = []
        self._status = status

    def execute(
        self, payload: Any, contract_id: str, contract_version: str
    ) -> ValidationResult:
        self.calls.append((payload, contract_id, contract_version))
        breaches = () if self._status == "pass" else (BreachDetail("X", "y"),)
        return ValidationResult(status=self._status, breaches=breaches)

    async def execute_async(
        self, payload: Any, contract_id: str, contract_version: str
    ) -> ValidationResult:
        # The async guard now routes through execute_async (bounded + timed).
        return self.execute(payload, contract_id, contract_version)


class _FakeContainer:
    def __init__(self) -> None:
        self._closed = False
        self.validate_contract_usecase = _FakeUseCase()
        # The async guard offloads execute() onto this pool (H2).
        self.validation_executor = types.SimpleNamespace(
            thread_pool=concurrent.futures.ThreadPoolExecutor(max_workers=2)
        )

    def ensure_open(self) -> None:
        if self._closed:
            raise CongineLifecycleError("ServiceContainer is closed")


def test_sync_wrapper_returns_output_and_result() -> None:
    container = _FakeContainer()

    @congine_guard("sentiment-v1", version="1.0", container=container)
    def analyze(text: str) -> Dict[str, Any]:
        return {"score": 0.8, "text": text}

    result = analyze("great")
    assert result["output"] == {"score": 0.8, "text": "great"}
    assert isinstance(result["validation_result"], ValidationResult)
    assert result["validation_result"].is_pass()
    assert container.validate_contract_usecase.calls == [
        ({"score": 0.8, "text": "great"}, "sentiment-v1", "1.0")
    ]


def test_async_wrapper_returns_output_and_result() -> None:
    container = _FakeContainer()

    @congine_guard("sentiment-v1", container=container)
    async def analyze(text: str) -> Dict[str, Any]:
        return {"score": 0.5, "text": text}

    assert inspect.iscoroutinefunction(analyze)
    result = asyncio.run(analyze("ok"))
    assert result["output"] == {"score": 0.5, "text": "ok"}
    assert result["validation_result"].is_pass()


def test_functools_wraps_preserves_metadata() -> None:
    container = _FakeContainer()

    @congine_guard("c", container=container)
    def documented() -> dict:
        """Original docstring."""
        return {}

    assert documented.__name__ == "documented"
    assert documented.__doc__ == "Original docstring."


def test_default_version_is_latest() -> None:
    container = _FakeContainer()

    @congine_guard("c", container=container)
    def f() -> dict:
        return {"a": 1}

    f()
    assert container.validate_contract_usecase.calls[0][2] == "latest"


# --- M5: return modes + extractor ------------------------------------------ #


def test_mode_output_returns_raw_output() -> None:
    container = _FakeContainer()

    @congine_guard("c", container=container, mode="output")
    def f() -> dict:
        return {"a": 1}

    assert f() == {"a": 1}  # no envelope
    assert container.validate_contract_usecase.calls  # validation still ran


def test_mode_raise_raises_on_failure() -> None:
    container = _FakeContainer()
    container.validate_contract_usecase = _FakeUseCase(status="fail")

    @congine_guard("c", container=container, mode="raise")
    def f() -> dict:
        return {"a": 1}

    with pytest.raises(CongineValidationError):
        f()


def test_mode_raise_returns_output_on_pass() -> None:
    container = _FakeContainer()

    @congine_guard("c", container=container, mode="raise")
    def f() -> dict:
        return {"a": 1}

    assert f() == {"a": 1}


def test_extractor_wraps_non_dict_output() -> None:
    container = _FakeContainer()

    @congine_guard(
        "c", container=container, mode="output", extractor=lambda s: {"text": s}
    )
    def f() -> str:
        return "hello"

    assert f() == "hello"  # original output preserved
    assert container.validate_contract_usecase.calls[0][0] == {"text": "hello"}


def test_invalid_mode_rejected() -> None:
    with pytest.raises(ValueError):
        congine_guard("c", mode="bogus")


def test_sync_guard_rejects_closed_container_before_host_call() -> None:
    container = _FakeContainer()
    container._closed = True
    called = False

    @congine_guard("c", container=container)
    def f() -> dict:
        nonlocal called
        called = True
        return {"a": 1}

    with pytest.raises(CongineLifecycleError, match="closed"):
        f()
    assert called is False


def test_async_guard_rejects_closed_container_before_host_call() -> None:
    container = _FakeContainer()
    container._closed = True
    called = False

    @congine_guard("c", container=container)
    async def f() -> dict:
        nonlocal called
        called = True
        return {"a": 1}

    with pytest.raises(CongineLifecycleError, match="closed"):
        asyncio.run(f())
    assert called is False
