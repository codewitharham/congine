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
from congine_core.exceptions import (  # noqa: E402
    CongineContractNotFoundError,
    CongineLifecycleError,
    CongineValidationError,
)
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
        self.closed = False
        self.ensure_open_calls = 0

    def ensure_open(self) -> None:
        self.ensure_open_calls += 1
        if self.closed:
            raise CongineLifecycleError("container is closed")


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
    assert container.ensure_open_calls == 4


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


def test_sdk_usecase_error_is_rethrown() -> None:
    handler, container = _handler()
    container.validate_contract_usecase.raise_exc = CongineContractNotFoundError(
        "missing"
    )
    handler.on_llm_new_token("hi", run_id="r")
    with pytest.raises(CongineContractNotFoundError, match="missing"):
        handler.on_llm_end(run_id="r")
    assert handler.last_result is None
    assert "ERROR" in container.logger.levels()


def test_strict_validation_error_is_rethrown() -> None:
    handler, container = _handler()
    container.validate_contract_usecase.raise_exc = CongineValidationError(
        "strict contract breach"
    )

    with pytest.raises(CongineValidationError, match="strict contract breach"):
        handler.on_llm_end(run_id="r")

    assert handler.last_result is None
    assert "ERROR" in container.logger.levels()


def test_unexpected_usecase_error_is_logged_and_contained() -> None:
    handler, container = _handler()
    container.validate_contract_usecase.raise_exc = RuntimeError("internal")
    handler.on_llm_new_token("hi", run_id="r")
    assert handler.on_llm_end(run_id="r") is None
    assert handler.result_for("r") is None
    assert handler.last_result is None
    assert "ERROR" in container.logger.levels()


def test_malformed_token_is_logged_and_contained() -> None:
    handler, container = _handler()

    assert handler.on_llm_new_token(42, run_id="r") is None  # type: ignore[arg-type]

    assert "r" not in handler._buffers
    assert "ERROR" in container.logger.levels()


def test_unexpected_response_extraction_error_is_logged_and_contained() -> None:
    handler, container = _handler()

    class _MalformedResponse:
        @property
        def generations(self) -> Any:
            raise RuntimeError("malformed host response")

    assert handler.on_llm_end(response=_MalformedResponse(), run_id="r") is None
    assert handler.last_result is None
    assert not container.validate_contract_usecase.calls
    assert "ERROR" in container.logger.levels()


def test_unhashable_host_run_id_is_contained() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("seed", run_id="seed")

    assert handler.on_llm_end(run_id=[]) is None

    assert not container.validate_contract_usecase.calls
    assert "ERROR" in container.logger.levels()


def test_logger_failure_does_not_replace_sdk_or_host_error_policy() -> None:
    handler, container = _handler()

    class _RaisingLogger:
        def error(self, *_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("logger unavailable")

    container.logger = _RaisingLogger()  # type: ignore[assignment]
    handler._logger = container.logger
    container.validate_contract_usecase.raise_exc = CongineValidationError("strict")

    with pytest.raises(CongineValidationError, match="strict"):
        handler.on_llm_end(run_id="sdk")

    container.validate_contract_usecase.raise_exc = RuntimeError("host")
    assert handler.on_llm_end(run_id="host") is None


def test_closed_container_is_rejected_before_callback_state_mutation() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("partial", run_id="r")
    container.closed = True

    with pytest.raises(CongineLifecycleError, match="closed"):
        handler.on_llm_end(run_id="r")

    assert handler._buffers["r"] == ["partial"]
    assert handler.result_for("r") is None
    assert handler.last_result is None
    assert not container.validate_contract_usecase.calls


def test_closed_container_rejects_token_before_buffer_mutation() -> None:
    handler, container = _handler()
    container.closed = True

    with pytest.raises(CongineLifecycleError, match="closed"):
        handler.on_llm_new_token("must-not-buffer", run_id="r")

    assert "r" not in handler._buffers
    assert "r" not in handler._buffer_lengths
    assert handler.result_for("r") is None


def test_closed_container_rejects_error_callback_before_state_mutation() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("partial", run_id="r")
    container.closed = True

    with pytest.raises(CongineLifecycleError, match="closed"):
        handler.on_llm_error(RuntimeError("host failure"), run_id="r")

    assert handler._buffers["r"] == ["partial"]


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
    assert handler.result_for("r") is None
    assert handler.last_result is None


def test_completed_results_are_consistent_under_concurrency() -> None:
    handler, _ = _handler()
    completed: dict[str, ValidationResult] = {}
    completed_lock = threading.Lock()

    def validate(rid: str) -> None:
        handler.on_llm_new_token(rid, run_id=rid)
        result = handler.on_llm_end(run_id=rid)
        assert result is not None
        with completed_lock:
            completed[rid] = result

    threads = [
        threading.Thread(target=validate, args=(f"run-{index}",))
        for index in range(100)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(completed) == len(threads)
    assert all(handler.result_for(rid) is result for rid, result in completed.items())
    assert any(handler.last_result is result for result in completed.values())


def test_last_result_assignment_remains_lock_backed_and_compatible() -> None:
    handler, _ = _handler()
    result = ValidationResult(status="pass")
    handler.last_result = result
    assert handler.last_result is result


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
