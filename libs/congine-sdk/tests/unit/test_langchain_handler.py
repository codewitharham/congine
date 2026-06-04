"""Unit tests for :mod:`congine_core.adapters.langchain_handler`.

The real ``langchain-core`` base class is required so the concurrency tests
exercise genuine LangChain wiring; the module is skipped if it is absent.
"""

from __future__ import annotations

import threading
import types
from typing import Any, List, Tuple

import pytest

pytest.importorskip("langchain_core")

from congine_core.adapters.langchain_handler import (  # noqa: E402
    CongineCallbackHandler,
)
from congine_core.domain.models import ValidationResult  # noqa: E402
from congine_core.exceptions import CongineContractNotFoundError  # noqa: E402
from tests.conftest import FakeLogger  # noqa: E402


class _UseCase:
    def __init__(self) -> None:
        self.calls: List[Tuple[Any, str, str]] = []
        self.raise_exc: BaseException | None = None

    def execute(
        self, payload: Any, contract_id: str, contract_version: str
    ) -> ValidationResult:
        self.calls.append((payload, contract_id, contract_version))
        if self.raise_exc is not None:
            raise self.raise_exc
        return ValidationResult(status="pass")


class _Container:
    def __init__(self) -> None:
        self.validate_contract_usecase = _UseCase()
        self.logger = FakeLogger()


def _handler(**kw: Any) -> tuple[CongineCallbackHandler, _Container]:
    container = _Container()
    handler = CongineCallbackHandler(contract_id="c1", container=container, **kw)
    return handler, container


def test_on_llm_end_validates_joined_completion() -> None:
    handler, container = _handler()
    rid = "run-1"
    for tok in ["Hel", "lo ", "world"]:
        handler.on_llm_new_token(tok, run_id=rid)
    result = handler.on_llm_end(run_id=rid)

    assert result.is_pass()
    assert handler.last_result is result
    assert container.validate_contract_usecase.calls == [
        ({"text": "Hello world"}, "c1", "latest")
    ]


def test_high_throughput_concurrent_tokens_same_run() -> None:
    handler, container = _handler()
    rid = "run-hot"
    n_threads, per_thread = 50, 200

    def worker() -> None:
        for _ in range(per_thread):
            handler.on_llm_new_token("x", run_id=rid)

    threads = [threading.Thread(target=worker) for _ in range(n_threads)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    handler.on_llm_end(run_id=rid)
    payload = container.validate_contract_usecase.calls[0][0]
    # No appends lost under lock contention.
    assert len(payload["text"]) == n_threads * per_thread


def test_concurrent_runs_are_isolated() -> None:
    handler, container = _handler()

    def stream(rid: str, token: str, count: int) -> None:
        for _ in range(count):
            handler.on_llm_new_token(token, run_id=rid)

    t_a = threading.Thread(target=stream, args=("A", "a", 300))
    t_b = threading.Thread(target=stream, args=("B", "b", 500))
    t_a.start()
    t_b.start()
    t_a.join()
    t_b.join()

    handler.on_llm_end(run_id="A")
    handler.on_llm_end(run_id="B")
    texts = [c[0]["text"] for c in container.validate_contract_usecase.calls]
    assert "a" * 300 in texts
    assert "b" * 500 in texts
    # No cross-run leakage.
    assert all(set(t) <= {"a"} or set(t) <= {"b"} for t in texts)


def test_buffer_cleared_after_end() -> None:
    handler, _ = _handler()
    handler.on_llm_new_token("x", run_id="r")
    handler.on_llm_end(run_id="r")
    assert "r" not in handler._buffers


def test_degradation_swallows_usecase_error() -> None:
    handler, container = _handler()
    container.validate_contract_usecase.raise_exc = CongineContractNotFoundError(
        "missing"
    )
    handler.on_llm_new_token("hi", run_id="r")
    result = handler.on_llm_end(run_id="r")  # must NOT raise
    assert result is None
    assert handler.last_result is None
    assert "ERROR" in container.logger.levels()


def test_custom_payload_key() -> None:
    handler, container = _handler(payload_key="output")
    handler.on_llm_new_token("hi", run_id="r")
    handler.on_llm_end(run_id="r")
    assert container.validate_contract_usecase.calls[0][0] == {"output": "hi"}


def test_non_streaming_extracts_text_from_response() -> None:
    handler, container = _handler()
    gen = types.SimpleNamespace(text="non-streamed result", message=None)
    response = types.SimpleNamespace(generations=[[gen]])
    handler.on_llm_end(response=response, run_id="r")
    assert container.validate_contract_usecase.calls[0][0] == {
        "text": "non-streamed result"
    }


def test_on_llm_error_discards_partial_buffer() -> None:
    handler, _ = _handler()
    handler.on_llm_new_token("partial", run_id="r")
    handler.on_llm_error(RuntimeError("llm failed"), run_id="r")
    assert "r" not in handler._buffers


def test_lazy_adapter_export() -> None:
    import congine_core
    from congine_core import adapters

    # Reachable lazily from the adapters package...
    assert adapters.CongineCallbackHandler is CongineCallbackHandler
    # ...but deliberately NOT in the root public API (avoids forcing the import).
    assert "CongineCallbackHandler" not in congine_core.__all__


def test_unknown_adapter_attr_raises() -> None:
    from congine_core import adapters

    with pytest.raises(AttributeError):
        _ = adapters.DoesNotExist
