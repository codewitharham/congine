"""Unit tests for :mod:`congine_core.adapters.guard`."""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Dict, List, Tuple

from congine_core.adapters.guard import congine_guard
from congine_core.domain.models import ValidationResult


class _FakeUseCase:
    def __init__(self) -> None:
        self.calls: List[Tuple[Any, str, str]] = []

    def execute(
        self, payload: Any, contract_id: str, contract_version: str
    ) -> ValidationResult:
        self.calls.append((payload, contract_id, contract_version))
        return ValidationResult(status="pass")


class _FakeContainer:
    def __init__(self) -> None:
        self.validate_contract_usecase = _FakeUseCase()


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
