"""Unit tests for :mod:`congine_core.adapters.langchain_handler` (P2-03a1).

The handler may evaluate a LangChain output only after it has established that
the output is completely represented under supported semantics; everything
else must be refused before the use case runs. Tests are named after the
P2-03a1 unit matrix (``test_uNN_*``, see
``docs/_suite/hardening/P2_03A1_IMPLEMENTATION_SPEC.md`` §34) plus the
additional witnesses the approved plan requires.

The real ``langchain-core`` objects are used wherever LangChain can construct
the shape; ``SimpleNamespace`` stands in only for shapes LangChain itself
refuses to build (malformed hosts, disagreeing text/message fields).
"""

from __future__ import annotations

import enum
import subprocess
import sys
import threading
import traceback
import types
from typing import Any, Callable, List, Optional, Tuple

import pytest

pytest.importorskip("langchain_core")

from langchain_core.messages import AIMessage, AIMessageChunk  # noqa: E402
from langchain_core.outputs import (  # noqa: E402
    ChatGeneration,
    ChatGenerationChunk,
    Generation,
    GenerationChunk,
    LLMResult,
)

from congine_core.adapters.langchain_handler import (  # noqa: E402
    CongineCallbackHandler,
    _extract_complete_text,
    _Refusal,
    _RefusalReason,
    _RunStatus,
)
from congine_core.domain.models import ValidationResult  # noqa: E402
from congine_core.exceptions import (  # noqa: E402
    CongineBaseException,
    CongineContractNotFoundError,
    CongineLifecycleError,
    CongineUnsupportedRepresentationError,
    CongineValidationError,
)
from tests.conftest import FakeLogger  # noqa: E402

SECRET = "SECRET-SENTINEL-p2-03a1"
_DEFAULT_LIMIT = 500_000


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
    def __init__(self, max_buffer: Optional[int] = None) -> None:
        self.validate_contract_usecase = _UseCase()
        self.logger = FakeLogger()
        self.closed = False
        self.ensure_open_calls = 0
        if max_buffer is not None:
            self.config = types.SimpleNamespace(max_stream_buffer_chars=max_buffer)

    def ensure_open(self) -> None:
        self.ensure_open_calls += 1
        if self.closed:
            raise CongineLifecycleError("container is closed")


def _handler(
    max_buffer: Optional[int] = None, **kw: Any
) -> tuple[CongineCallbackHandler, _Container]:
    container = _Container(max_buffer)
    handler = CongineCallbackHandler(contract_id="c1", container=container, **kw)
    return handler, container


def _final(text: str, **generation_kwargs: Any) -> LLMResult:
    return LLMResult(generations=[[Generation(text=text, **generation_kwargs)]])


def _chat_final(message: Any, llm_output: Any = None) -> LLMResult:
    return LLMResult(
        generations=[[ChatGeneration(message=message)]], llm_output=llm_output
    )


def _tool_call(**args: Any) -> dict[str, Any]:
    return {"name": "delete_customer_record", "args": args, "id": "call_1"}


def _refuse(call: Callable[[], Any], reason: str) -> BaseException:
    """Run *call*, require a refusal with exactly *reason*, return the error."""
    with pytest.raises(
        CongineUnsupportedRepresentationError, match=rf"\({reason}\)$"
    ) as info:
        call()
    return info.value


def _assert_not_evaluated(
    handler: CongineCallbackHandler, container: _Container, rid: Any
) -> None:
    assert container.validate_contract_usecase.calls == []
    assert handler.result_for(rid) is None
    assert handler.last_result is None


def _assert_sanitized(exc: BaseException, secret: str = SECRET) -> None:
    """The public boundary exposes a fixed reason code and nothing else."""
    assert type(exc) is CongineUnsupportedRepresentationError
    assert exc.__cause__ is None
    assert exc.__context__ is None
    assert "_Refusal" not in repr(exc)
    rendered = "".join(traceback.format_exception(exc))
    assert "direct cause" not in rendered
    assert "During handling" not in rendered
    for text in (str(exc), repr(exc), rendered):
        assert secret not in text


class _RaisingLen:
    """A host value whose ``__len__`` is hostile."""

    def __len__(self) -> int:
        raise RuntimeError(SECRET)


class _Unclassifiable:
    """A termination value of a type the adapter cannot interpret."""


class _ProtoFinishReason(enum.IntEnum):
    """Mimics a provider protobuf enum: the textual form is ``.name``."""

    STOP = 1
    MAX_TOKENS = 2


# --------------------------------------------------------------------------- #
# Supported representations are evaluated exactly once
# --------------------------------------------------------------------------- #
def test_u01_plain_final_text_is_evaluated_once() -> None:
    handler, container = _handler()

    result = handler.on_llm_end(_final("plain result"), run_id="r")

    assert result is not None and result.is_pass()
    assert handler.result_for("r") is result
    assert handler.last_result is result
    assert container.validate_contract_usecase.calls == [
        ({"text": "plain result"}, "c1", "latest")
    ]
    assert "r" not in handler._runs


def test_u02_plain_chat_message_is_evaluated_once() -> None:
    handler, container = _handler()

    result = handler.on_llm_end(
        _chat_final(AIMessage(content="Deploy completed.")), run_id="r"
    )

    assert result is not None and result.is_pass()
    assert container.validate_contract_usecase.calls == [
        ({"text": "Deploy completed."}, "c1", "latest")
    ]


def test_u03_complete_stream_with_matching_final_is_evaluated_once() -> None:
    handler, container = _handler()
    rid = "run-1"
    for tok in ["Hel", "lo ", "world"]:
        handler.on_llm_new_token(tok, run_id=rid)

    result = handler.on_llm_end(_final("Hello world"), run_id=rid)

    assert result is not None and result.is_pass()
    assert handler.last_result is result
    assert container.validate_contract_usecase.calls == [
        ({"text": "Hello world"}, "c1", "latest")
    ]
    assert container.ensure_open_calls == 4
    assert rid not in handler._runs


def test_u04_explicit_empty_text_is_a_complete_output() -> None:
    handler, container = _handler()

    result = handler.on_llm_end(_final(""), run_id="r")

    assert result is not None and result.is_pass()
    assert container.validate_contract_usecase.calls == [({"text": ""}, "c1", "latest")]


def test_u05_custom_payload_key() -> None:
    handler, container = _handler(payload_key="output")
    handler.on_llm_new_token("hi", run_id="r")
    handler.on_llm_end(_final("hi"), run_id="r")
    assert container.validate_contract_usecase.calls[0][0] == {"output": "hi"}


def test_u06_concurrent_runs_are_isolated() -> None:
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

    handler.on_llm_end(_final("a" * 300), run_id="A")
    handler.on_llm_end(_final("b" * 500), run_id="B")
    texts = [c[0]["text"] for c in container.validate_contract_usecase.calls]
    assert texts == ["a" * 300, "b" * 500]


def test_u06_high_throughput_concurrent_tokens_same_run() -> None:
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

    # No appends lost under lock contention: the stream reconciles exactly.
    handler.on_llm_end(_final("x" * (n_threads * per_thread)), run_id=rid)
    assert len(container.validate_contract_usecase.calls) == 1


def test_refusing_one_run_does_not_touch_concurrent_runs() -> None:
    handler, container = _handler()
    refused: List[BaseException] = []

    def stream(rid: str, count: int) -> None:
        for _ in range(count):
            handler.on_llm_new_token("t", run_id=rid)

    def refuse() -> None:
        handler.on_llm_new_token("ok", run_id="C")
        try:
            handler.on_llm_new_token([{"type": "image"}], run_id="C")  # type: ignore[arg-type]
        except CongineUnsupportedRepresentationError as exc:
            refused.append(exc)

    threads = [
        threading.Thread(target=stream, args=("A", 400)),
        threading.Thread(target=stream, args=("B", 400)),
        threading.Thread(target=refuse),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(refused) == 1
    assert handler._runs["C"].status is _RunStatus.REFUSED
    assert handler.on_llm_end(_final("t" * 400), run_id="A") is not None
    assert handler.on_llm_end(_final("t" * 400), run_id="B") is not None
    assert len(container.validate_contract_usecase.calls) == 2


def test_completed_results_are_consistent_under_concurrency() -> None:
    handler, _ = _handler()
    completed: dict[str, ValidationResult] = {}
    completed_lock = threading.Lock()

    def validate(rid: str) -> None:
        handler.on_llm_new_token(rid, run_id=rid)
        result = handler.on_llm_end(_final(rid), run_id=rid)
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


# --------------------------------------------------------------------------- #
# Stream bound: refuse, never clip
# --------------------------------------------------------------------------- #
def test_u07_exactly_the_default_buffer_limit_is_supported() -> None:
    handler, container = _handler()
    text = "x" * _DEFAULT_LIMIT

    handler.on_llm_new_token(text, run_id="r")
    result = handler.on_llm_end(_final(text), run_id="r")

    assert result is not None and result.is_pass()
    assert len(container.validate_contract_usecase.calls) == 1


def test_u07_exactly_a_configured_limit_is_supported() -> None:
    handler, container = _handler(max_buffer=10)
    handler.on_llm_new_token("12345", run_id="r")
    handler.on_llm_new_token("67890", run_id="r")

    assert handler.on_llm_end(_final("1234567890"), run_id="r") is not None
    assert len(container.validate_contract_usecase.calls) == 1


def test_u08_one_character_over_the_default_limit_refuses() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("x" * _DEFAULT_LIMIT, run_id="r")

    _refuse(lambda: handler.on_llm_new_token("y", run_id="r"), "stream_buffer_exceeded")
    # Sticky through the end: a matching final never revives the run.
    _refuse(
        lambda: handler.on_llm_end(_final("x" * _DEFAULT_LIMIT + "y"), run_id="r"),
        "stream_buffer_exceeded",
    )
    _assert_not_evaluated(handler, container, "r")


def test_u09_overflowing_token_is_not_clipped() -> None:
    handler, container = _handler(max_buffer=10)
    handler.on_llm_new_token("123456789", run_id="r")

    # "ab" would partly fit; the old handler kept "a" and validated a prefix.
    _refuse(
        lambda: handler.on_llm_new_token("ab", run_id="r"), "stream_buffer_exceeded"
    )

    state = handler._runs["r"]
    assert state.status is _RunStatus.REFUSED
    assert state.parts == [] and state.length == 0
    _refuse(
        lambda: handler.on_llm_end(_final("1234567890"), run_id="r"),
        "stream_buffer_exceeded",
    )
    _assert_not_evaluated(handler, container, "r")


@pytest.mark.parametrize(
    "token", ["12345", 42], ids=["overflow-under-lock", "inspection-refusal"]
)
def test_refusal_paths_release_the_state_lock(token: Any) -> None:
    """Regression guard: ``self._lock`` is a plain Lock and is never re-entered."""
    handler, _ = _handler(max_buffer=4)
    outcome: List[BaseException] = []

    def refuse() -> None:
        try:
            handler.on_llm_new_token(token, run_id="big")
        except BaseException as exc:  # noqa: BLE001 - recorded for the assertion
            outcome.append(exc)

    worker = threading.Thread(target=refuse, daemon=True)
    worker.start()
    worker.join(timeout=5)

    assert not worker.is_alive(), "refusal deadlocked on the handler state lock"
    assert isinstance(outcome[0], CongineUnsupportedRepresentationError)
    handler.on_llm_new_token("ok", run_id="other")
    assert handler._runs["other"].parts == ["ok"]


# --------------------------------------------------------------------------- #
# Unsupported stream observations are sticky
# --------------------------------------------------------------------------- #
def test_u10_non_string_token_refuses_stickily() -> None:
    handler, container = _handler()

    _refuse(
        lambda: handler.on_llm_new_token(42, run_id="r"),  # type: ignore[arg-type]
        "non_text_stream_token",
    )

    assert handler._runs["r"].status is _RunStatus.REFUSED
    _refuse(lambda: handler.on_llm_new_token("ok", run_id="r"), "non_text_stream_token")
    _assert_not_evaluated(handler, container, "r")


def test_u11_text_then_unsupported_then_text_remains_refused() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("text A", run_id="r")
    _refuse(
        lambda: handler.on_llm_new_token(
            [{"type": "text", "text": "x"}],  # type: ignore[arg-type]
            run_id="r",
        ),
        "non_text_stream_token",
    )
    # A later, different refusal must not overwrite the first reason.
    _refuse(
        lambda: handler.on_llm_new_token(
            "b", chunk=GenerationChunk(text="c"), run_id="r"
        ),
        "non_text_stream_token",
    )
    _refuse(
        lambda: handler.on_llm_new_token("text B", run_id="r"), "non_text_stream_token"
    )

    assert handler._runs["r"].parts == []
    _refuse(
        lambda: handler.on_llm_end(_final("text Atext B"), run_id="r"),
        "non_text_stream_token",
    )
    _assert_not_evaluated(handler, container, "r")


def test_u11a_direct_caller_that_catches_a_refusal_keeps_the_run_refused() -> None:
    """Direct callers own cleanup: the run stays refused until it ends.

    Contrast with real LangChain dispatch (``LC09`` in
    ``tests/integration/test_langchain_callback_manager.py``), where LangChain
    itself calls ``on_llm_error`` and clears the state before re-raising.
    """
    handler, container = _handler()
    handler.on_llm_new_token("partial", run_id="r")
    try:
        handler.on_llm_new_token(None, run_id="r")  # type: ignore[arg-type]
    except CongineUnsupportedRepresentationError:
        pass

    state = handler._runs["r"]
    assert state.status is _RunStatus.REFUSED
    assert state.refusal_reason is _RefusalReason.NON_TEXT_STREAM_TOKEN
    assert state.parts == [] and state.length == 0

    _refuse(
        lambda: handler.on_llm_new_token("more", run_id="r"), "non_text_stream_token"
    )
    _refuse(
        lambda: handler.on_llm_end(_final("partialmore"), run_id="r"),
        "non_text_stream_token",
    )
    assert "r" not in handler._runs
    _assert_not_evaluated(handler, container, "r")


def test_list_token_from_block_content_refuses() -> None:
    handler, _ = _handler()
    chunk = ChatGenerationChunk(
        message=AIMessageChunk(content=[{"type": "text", "text": "hi"}])
    )
    _refuse(
        lambda: handler.on_llm_new_token(
            chunk.message.content,  # type: ignore[arg-type]
            chunk=chunk,
            run_id="r",
        ),
        "non_text_stream_token",
    )


def test_stream_chunk_tool_call_keeps_its_specific_reason() -> None:
    handler, _ = _handler()
    chunk = ChatGenerationChunk(
        message=AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "delete", "args": '{"id": 42}', "id": "c1", "index": 0}
            ],
        )
    )
    exc = _refuse(
        lambda: handler.on_llm_new_token("", chunk=chunk, run_id="r"),
        "tool_or_action_content",
    )
    assert "unsupported_stream_chunk" not in str(exc)


def test_stream_chunk_truncation_refuses() -> None:
    handler, _ = _handler()
    chunk = GenerationChunk(text="cut", generation_info={"finish_reason": "length"})
    _refuse(
        lambda: handler.on_llm_new_token("cut", chunk=chunk, run_id="r"),
        "output_truncated",
    )


def test_stream_chunk_with_none_valued_kwargs_is_not_refused() -> None:
    handler, container = _handler()
    chunk = ChatGenerationChunk(
        message=AIMessageChunk(content="hi", additional_kwargs={"refusal": None})
    )
    handler.on_llm_new_token("hi", chunk=chunk, run_id="r")
    assert handler.on_llm_end(_final("hi"), run_id="r") is not None
    assert len(container.validate_contract_usecase.calls) == 1


@pytest.mark.parametrize(
    "chunk",
    [
        ChatGenerationChunk(message=AIMessageChunk(content="delete production data")),
        GenerationChunk(text="delete production data"),
    ],
    ids=["chat-chunk", "text-chunk"],
)
def test_stream_token_must_agree_with_its_chunk(chunk: Any) -> None:
    handler, container = _handler()

    _refuse(
        lambda: handler.on_llm_new_token("looks safe", chunk=chunk, run_id="r"),
        "stream_token_chunk_mismatch",
    )

    assert handler._runs["r"].status is _RunStatus.REFUSED
    _refuse(
        lambda: handler.on_llm_end(_final("looks safe"), run_id="r"),
        "stream_token_chunk_mismatch",
    )
    _assert_not_evaluated(handler, container, "r")


def test_stream_token_matching_its_chunk_is_collected() -> None:
    handler, _ = _handler()
    handler.on_llm_new_token(
        "looks ",
        chunk=ChatGenerationChunk(message=AIMessageChunk(content="looks ")),
        run_id="r",
    )
    handler.on_llm_new_token("safe", chunk=GenerationChunk(text="safe"), run_id="r")
    assert handler._runs["r"].parts == ["looks ", "safe"]


def test_unrecognized_stream_chunk_refuses() -> None:
    handler, _ = _handler()
    _refuse(
        lambda: handler.on_llm_new_token("x", chunk=object(), run_id="r"),
        "unsupported_stream_chunk",
    )


def test_hostile_stream_chunk_is_classified_and_sanitized() -> None:
    handler, container = _handler()

    class _HostileChunk:
        @property
        def message(self) -> Any:
            raise RuntimeError(SECRET)

    exc = _refuse(
        lambda: handler.on_llm_new_token("x", chunk=_HostileChunk(), run_id="r"),
        "unsupported_stream_chunk",
    )
    _assert_sanitized(exc)
    assert SECRET not in repr(container.logger.records)


# --------------------------------------------------------------------------- #
# Run identity
# --------------------------------------------------------------------------- #
def test_u12_missing_run_id_refuses_without_aliasing_state() -> None:
    handler, container = _handler()

    _refuse(lambda: handler.on_llm_new_token("x"), "missing_run_id")
    _refuse(lambda: handler.on_llm_end(_final("x")), "missing_run_id")

    assert handler._runs == {}
    _assert_not_evaluated(handler, container, None)


def test_u13_unhashable_run_id_refuses() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("seed", run_id="seed")

    _refuse(lambda: handler.on_llm_new_token("x", run_id=[]), "unhashable_run_id")
    _refuse(lambda: handler.on_llm_end(_final("x"), run_id=[]), "unhashable_run_id")

    assert list(handler._runs) == ["seed"]
    assert container.validate_contract_usecase.calls == []
    assert handler.last_result is None


class _HostileId:
    def __hash__(self) -> int:
        raise RuntimeError(SECRET)


class _FlakyId:
    """Hashes once (admission), then fails when used as a dictionary key."""

    def __init__(self) -> None:
        self.calls = 0

    def __hash__(self) -> int:
        self.calls += 1
        if self.calls > 1:
            raise RuntimeError(SECRET)
        return 7


@pytest.mark.parametrize("make_id", [_HostileId, _FlakyId], ids=["hash", "late-hash"])
@pytest.mark.parametrize("callback", ["token", "end"])
def test_hostile_run_identity_is_a_sanitized_refusal(
    make_id: Callable[[], Any], callback: str
) -> None:
    handler, container = _handler()
    # Another active run makes every ``_runs`` lookup hash the key (CPython
    # skips hashing when popping from an empty dict).
    handler.on_llm_new_token("seed", run_id="seed")
    run_id = make_id()

    if callback == "token":
        exc = _refuse(
            lambda: handler.on_llm_new_token("x", run_id=run_id), "unhashable_run_id"
        )
    else:
        exc = _refuse(
            lambda: handler.on_llm_end(_final("x"), run_id=run_id), "unhashable_run_id"
        )

    _assert_sanitized(exc)
    assert list(handler._runs) == ["seed"]
    assert container.validate_contract_usecase.calls == []
    assert SECRET not in repr(container.logger.records)


def test_private_refusal_signal_is_never_exported() -> None:
    import congine_core
    from congine_core import adapters

    assert "_Refusal" not in congine_core.__all__
    assert "_Refusal" not in adapters.__all__
    assert not issubclass(_Refusal, CongineBaseException)


# --------------------------------------------------------------------------- #
# Final-response cardinality and content
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("generations", [[], [[]]], ids=["no-groups", "empty-group"])
def test_u14_no_generation_refuses(generations: Any) -> None:
    handler, container = _handler()
    _refuse(
        lambda: handler.on_llm_end(LLMResult(generations=generations), run_id="r"),
        "no_generation",
    )
    _assert_not_evaluated(handler, container, "r")


def test_u15_multiple_generation_groups_refuse() -> None:
    handler, container = _handler()
    response = LLMResult(
        generations=[[Generation(text="prompt 1")], [Generation(text="prompt 2")]]
    )
    _refuse(
        lambda: handler.on_llm_end(response, run_id="r"),
        "multiple_generation_groups",
    )
    _assert_not_evaluated(handler, container, "r")


def test_u16_multiple_candidates_refuse() -> None:
    handler, container = _handler()
    response = LLMResult(
        generations=[[Generation(text="candidate 1"), Generation(text="candidate 2")]]
    )
    _refuse(lambda: handler.on_llm_end(response, run_id="r"), "multiple_generations")
    _assert_not_evaluated(handler, container, "r")


def test_u17_structured_list_content_is_not_flattened() -> None:
    handler, container = _handler()
    message = AIMessage(content=[{"type": "text", "text": "Deploy completed."}])
    # LangChain itself flattens this to ``.text``; the adapter must not trust it.
    assert ChatGeneration(message=message).text == "Deploy completed."

    _refuse(
        lambda: handler.on_llm_end(_chat_final(message), run_id="r"),
        "non_text_content",
    )
    _assert_not_evaluated(handler, container, "r")


def test_u18_image_only_content_refuses() -> None:
    handler, container = _handler()
    message = AIMessage(
        content=[{"type": "image_url", "image_url": {"url": "data:image/png;base64,"}}]
    )
    _refuse(
        lambda: handler.on_llm_end(_chat_final(message), run_id="r"),
        "non_text_content",
    )
    _assert_not_evaluated(handler, container, "r")


def test_u19_tool_calls_refuse_even_with_benign_text() -> None:
    handler, container = _handler()
    message = AIMessage(
        content="The request looks safe.", tool_calls=[_tool_call(id=42)]
    )
    _refuse(
        lambda: handler.on_llm_end(_chat_final(message), run_id="r"),
        "tool_or_action_content",
    )
    _assert_not_evaluated(handler, container, "r")


def test_u20_function_call_in_additional_kwargs_refuses() -> None:
    handler, container = _handler()
    message = AIMessage(
        content="ok",
        additional_kwargs={"function_call": {"name": "delete", "arguments": "{}"}},
    )
    _refuse(
        lambda: handler.on_llm_end(_chat_final(message), run_id="r"),
        "tool_or_action_content",
    )
    _assert_not_evaluated(handler, container, "r")


def test_unaccounted_additional_kwargs_refuse() -> None:
    handler, _ = _handler()
    message = AIMessage(content="ok", additional_kwargs={"reasoning_content": "hidden"})
    _refuse(
        lambda: handler.on_llm_end(_chat_final(message), run_id="r"),
        "unsupported_message_metadata",
    )


def test_none_valued_additional_kwargs_are_absent_not_refused() -> None:
    handler, container = _handler()
    message = AIMessage(content="ok", additional_kwargs={"refusal": None, "x": []})
    assert handler.on_llm_end(_chat_final(message), run_id="r") is not None
    assert len(container.validate_contract_usecase.calls) == 1


def test_u21_text_stream_with_final_tool_call_refuses() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("The request ", run_id="r")
    handler.on_llm_new_token("looks safe.", run_id="r")
    message = AIMessage(
        content="The request looks safe.", tool_calls=[_tool_call(id=42)]
    )
    _refuse(
        lambda: handler.on_llm_end(_chat_final(message), run_id="r"),
        "tool_or_action_content",
    )
    _assert_not_evaluated(handler, container, "r")


def test_u22_stream_final_mismatch_refuses() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("hello", run_id="r")
    _refuse(
        lambda: handler.on_llm_end(_final("goodbye"), run_id="r"),
        "stream_final_mismatch",
    )
    _assert_not_evaluated(handler, container, "r")


def test_u23_stream_without_final_response_refuses() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("hello", run_id="r")
    _refuse(lambda: handler.on_llm_end(run_id="r"), "missing_final_response")
    _assert_not_evaluated(handler, container, "r")


def test_missing_final_response_refuses_without_stream() -> None:
    handler, container = _handler()
    _refuse(lambda: handler.on_llm_end(None, run_id="r"), "missing_final_response")
    _assert_not_evaluated(handler, container, "r")


def test_u24_observable_finish_reason_length_refuses() -> None:
    handler, container = _handler()
    response = _final("cut", generation_info={"finish_reason": "length"})
    exc = _refuse(lambda: handler.on_llm_end(response, run_id="r"), "output_truncated")
    # The specific reason survives the extraction boundary's fallback.
    assert "malformed_final_response" not in str(exc)
    _assert_not_evaluated(handler, container, "r")


def test_u25_observable_max_token_truncation_refuses() -> None:
    handler, container = _handler()
    message = AIMessage(content="cut", response_metadata={"stop_reason": "max_tokens"})
    _refuse(
        lambda: handler.on_llm_end(_chat_final(message), run_id="r"),
        "output_truncated",
    )
    _assert_not_evaluated(handler, container, "r")


def test_u26_malformed_generations_property_is_a_sanitized_refusal() -> None:
    handler, container = _handler()

    class _MalformedResponse:
        @property
        def generations(self) -> Any:
            raise RuntimeError(f"failed parsing {SECRET}")

    exc = _refuse(
        lambda: handler.on_llm_end(response=_MalformedResponse(), run_id="r"),
        "malformed_final_response",
    )
    _assert_sanitized(exc)
    _assert_not_evaluated(handler, container, "r")


def test_private_extraction_keeps_host_causality_internally() -> None:
    """Implementation detail: the private signal keeps the host cause."""

    class _MalformedResponse:
        @property
        def generations(self) -> Any:
            raise RuntimeError("host failure")

    with pytest.raises(_Refusal) as info:
        _extract_complete_text(_MalformedResponse())

    assert info.value.reason is _RefusalReason.MALFORMED_FINAL_RESPONSE
    assert isinstance(info.value.__cause__, RuntimeError)


def test_u27_text_and_message_content_must_agree() -> None:
    handler, container = _handler()
    # A real ChatGeneration always overwrites ``.text``; only a host can disagree.
    generation = types.SimpleNamespace(
        text="looks safe", message=AIMessage(content="delete production data")
    )
    response = types.SimpleNamespace(generations=[[generation]], llm_output=None)
    _refuse(lambda: handler.on_llm_end(response, run_id="r"), "text_message_mismatch")
    _assert_not_evaluated(handler, container, "r")


def test_non_string_plain_generation_text_refuses() -> None:
    handler, _ = _handler()
    response = types.SimpleNamespace(
        generations=[[types.SimpleNamespace(text=None)]], llm_output=None
    )
    _refuse(lambda: handler.on_llm_end(response, run_id="r"), "non_text_content")


@pytest.mark.parametrize(
    "response",
    [
        types.SimpleNamespace(),
        types.SimpleNamespace(generations="text"),
        types.SimpleNamespace(generations=["not-a-group"]),
    ],
    ids=["no-generations", "string-generations", "string-group"],
)
def test_malformed_response_shapes_refuse(response: Any) -> None:
    handler, container = _handler()
    _refuse(
        lambda: handler.on_llm_end(response, run_id="r"), "malformed_final_response"
    )
    _assert_not_evaluated(handler, container, "r")


# --------------------------------------------------------------------------- #
# Termination classification and llm_output
# --------------------------------------------------------------------------- #
_TERMINATION_LOCATIONS = ["generation_info", "response_metadata", "llm_output", "chunk"]


def _end_with_termination(
    handler: CongineCallbackHandler, location: str, meta: dict[str, Any]
) -> Optional[ValidationResult]:
    if location == "generation_info":
        return handler.on_llm_end(_final("ok", generation_info=meta), run_id="r")
    if location == "response_metadata":
        message = AIMessage(content="ok", response_metadata=meta)
        return handler.on_llm_end(_chat_final(message), run_id="r")
    if location == "llm_output":
        response = LLMResult(generations=[[Generation(text="ok")]], llm_output=meta)
        return handler.on_llm_end(response, run_id="r")
    chunk = GenerationChunk(text="ok", generation_info=meta)
    handler.on_llm_new_token("ok", chunk=chunk, run_id="r")
    return handler.on_llm_end(_final("ok"), run_id="r")


@pytest.mark.parametrize("location", _TERMINATION_LOCATIONS)
@pytest.mark.parametrize("key", ["finish_reason", "stop_reason"])
@pytest.mark.parametrize(
    "value",
    ["stop", "STOP", " end_turn ", "stop_sequence", "", None, _ProtoFinishReason.STOP],
)
def test_known_complete_termination_is_accepted(
    location: str, key: str, value: Any
) -> None:
    handler, container = _handler()
    assert _end_with_termination(handler, location, {key: value}) is not None
    assert len(container.validate_contract_usecase.calls) == 1


@pytest.mark.parametrize("location", _TERMINATION_LOCATIONS)
@pytest.mark.parametrize("key", ["finish_reason", "stop_reason"])
@pytest.mark.parametrize(
    ("value", "reason"),
    [
        ("length", "output_truncated"),
        ("MAX_TOKENS", "output_truncated"),
        ("max_output_tokens", "output_truncated"),
        (_ProtoFinishReason.MAX_TOKENS, "output_truncated"),
        ("content_filter", "output_incomplete"),
        ("SAFETY", "output_incomplete"),
        ("refusal", "output_incomplete"),
        ("new_provider_reason", "unknown_termination"),
    ],
)
def test_incomplete_or_unknown_termination_refuses(
    location: str, key: str, value: Any, reason: str
) -> None:
    handler, container = _handler()
    _refuse(lambda: _end_with_termination(handler, location, {key: value}), reason)
    _assert_not_evaluated(handler, container, "r")


def test_unclassifiable_termination_type_refuses() -> None:
    handler, _ = _handler()
    _refuse(
        lambda: _end_with_termination(
            handler, "generation_info", {"finish_reason": _Unclassifiable()}
        ),
        "malformed_final_response",
    )
    handler, _ = _handler()
    _refuse(
        lambda: _end_with_termination(
            handler, "chunk", {"finish_reason": _Unclassifiable()}
        ),
        "unsupported_stream_chunk",
    )


def test_llm_output_action_key_refuses() -> None:
    handler, container = _handler()
    response = LLMResult(
        generations=[[Generation(text="ok")]],
        llm_output={"tool_calls": [_tool_call(id=42)]},
    )
    _refuse(lambda: handler.on_llm_end(response, run_id="r"), "tool_or_action_content")
    _assert_not_evaluated(handler, container, "r")


def test_non_mapping_llm_output_refuses() -> None:
    handler, _ = _handler()
    response = types.SimpleNamespace(
        generations=[[Generation(text="ok")]], llm_output="not-a-mapping"
    )
    _refuse(
        lambda: handler.on_llm_end(response, run_id="r"), "malformed_final_response"
    )


def test_ordinary_provider_metadata_is_outside_the_governed_subject() -> None:
    handler, container = _handler()
    response = LLMResult(
        generations=[[Generation(text="ok", generation_info={"logprobs": None})]],
        llm_output={
            "token_usage": {"prompt_tokens": 3, "completion_tokens": 1},
            "model_name": "m",
            "system_fingerprint": "fp",
        },
    )
    assert handler.on_llm_end(response, run_id="r") is not None
    assert len(container.validate_contract_usecase.calls) == 1


def _duck_response(message: Any = None, **generation_fields: Any) -> Any:
    generation = types.SimpleNamespace(text="ok", message=message, **generation_fields)
    return types.SimpleNamespace(generations=[[generation]], llm_output=None)


@pytest.mark.parametrize(
    "response",
    [
        _duck_response(generation_info="finish_reason=length"),
        _duck_response(
            types.SimpleNamespace(content="ok", additional_kwargs=["function_call"])
        ),
        _duck_response(types.SimpleNamespace(content="ok", response_metadata="length")),
    ],
    ids=["generation-info", "additional-kwargs", "response-metadata"],
)
def test_non_mapping_metadata_is_malformed_not_ignored(response: Any) -> None:
    handler, container = _handler()
    _refuse(
        lambda: handler.on_llm_end(response, run_id="r"), "malformed_final_response"
    )
    _assert_not_evaluated(handler, container, "r")


def test_message_without_side_channel_fields_is_plain_text() -> None:
    """A duck-typed message that has no action or metadata fields at all."""
    handler, container = _handler()
    response = _duck_response(types.SimpleNamespace(content="ok"))
    assert handler.on_llm_end(response, run_id="r") is not None
    assert container.validate_contract_usecase.calls[0][0] == {"text": "ok"}


@pytest.mark.parametrize("field", ["additional_kwargs", "tool_calls"])
def test_hostile_len_in_side_channel_is_a_sanitized_refusal(field: str) -> None:
    handler, container = _handler()
    extras: dict[str, Any] = {"additional_kwargs": {}, "tool_calls": []}
    if field == "additional_kwargs":
        extras["additional_kwargs"] = {"x": _RaisingLen()}
    else:
        extras["tool_calls"] = _RaisingLen()
    message = types.SimpleNamespace(content="ok", response_metadata={}, **extras)
    response = types.SimpleNamespace(
        generations=[[types.SimpleNamespace(text="ok", message=message)]],
        llm_output=None,
    )

    exc = _refuse(
        lambda: handler.on_llm_end(response, run_id="r"), "malformed_final_response"
    )
    _assert_sanitized(exc)
    _assert_not_evaluated(handler, container, "r")


# --------------------------------------------------------------------------- #
# Cleanup, existing exception policy, lifecycle
# --------------------------------------------------------------------------- #
def test_u28_refusal_clears_retained_text() -> None:
    handler, _ = _handler()
    handler.on_llm_new_token("abc", run_id="r")
    handler.on_llm_new_token("def", run_id="r")
    _refuse(
        lambda: handler.on_llm_new_token(b"raw", run_id="r"),  # type: ignore[arg-type]
        "non_text_stream_token",
    )

    state = handler._runs["r"]
    assert (state.parts, state.length) == ([], 0)


def test_u29_refusal_leaves_no_result_for_the_run() -> None:
    handler, container = _handler()
    first = handler.on_llm_end(_final("ok"), run_id="r")
    assert handler.result_for("r") is first

    _refuse(lambda: handler.on_llm_end(None, run_id="r"), "missing_final_response")

    assert handler.result_for("r") is None
    assert handler.last_result is None
    assert len(container.validate_contract_usecase.calls) == 1


def test_u30_contract_not_found_is_rethrown() -> None:
    handler, container = _handler()
    container.validate_contract_usecase.raise_exc = CongineContractNotFoundError(
        "missing"
    )
    handler.on_llm_new_token("hi", run_id="r")
    with pytest.raises(CongineContractNotFoundError, match="missing"):
        handler.on_llm_end(_final("hi"), run_id="r")
    assert len(container.validate_contract_usecase.calls) == 1
    assert handler.last_result is None
    assert "ERROR" in container.logger.levels()


def test_u31_strict_validation_error_is_rethrown() -> None:
    handler, container = _handler()
    container.validate_contract_usecase.raise_exc = CongineValidationError(
        "strict contract breach"
    )

    with pytest.raises(CongineValidationError, match="strict contract breach"):
        handler.on_llm_end(_final("breach"), run_id="r")

    assert len(container.validate_contract_usecase.calls) == 1
    assert handler.last_result is None
    assert "ERROR" in container.logger.levels()


def test_unexpected_usecase_error_is_still_logged_and_contained() -> None:
    """Spec §27: the use-case containment policy is out of P2-03a1's scope."""
    handler, container = _handler()
    container.validate_contract_usecase.raise_exc = RuntimeError("internal")
    handler.on_llm_new_token("hi", run_id="r")
    assert handler.on_llm_end(_final("hi"), run_id="r") is None
    assert handler.result_for("r") is None
    assert handler.last_result is None
    assert "ERROR" in container.logger.levels()


class _RaisingLogger:
    def error(self, *_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("logger unavailable")


def test_u32_logger_failure_does_not_replace_a_refusal() -> None:
    handler, container = _handler()
    container.logger = _RaisingLogger()  # type: ignore[assignment]
    handler._logger = container.logger

    exc = _refuse(
        lambda: handler.on_llm_end(_final("a"), run_id=None), "missing_run_id"
    )
    assert type(exc) is CongineUnsupportedRepresentationError


def test_logger_failure_does_not_replace_sdk_or_host_error_policy() -> None:
    handler, container = _handler()
    container.logger = _RaisingLogger()  # type: ignore[assignment]
    handler._logger = container.logger
    container.validate_contract_usecase.raise_exc = CongineValidationError("strict")

    with pytest.raises(CongineValidationError, match="strict"):
        handler.on_llm_end(_final("x"), run_id="sdk")

    container.validate_contract_usecase.raise_exc = RuntimeError("host")
    assert handler.on_llm_end(_final("x"), run_id="host") is None


def test_u33_closed_container_rejects_token_before_state_mutation() -> None:
    handler, container = _handler()
    container.closed = True

    with pytest.raises(CongineLifecycleError, match="closed"):
        handler.on_llm_new_token("must-not-buffer", run_id="r")

    assert "r" not in handler._runs
    assert handler.result_for("r") is None


def test_u34_closed_container_is_rejected_before_callback_state_mutation() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("partial", run_id="r")
    container.closed = True

    with pytest.raises(CongineLifecycleError, match="closed"):
        handler.on_llm_end(_final("partial"), run_id="r")

    assert handler._runs["r"].parts == ["partial"]
    assert handler.result_for("r") is None
    assert handler.last_result is None
    assert not container.validate_contract_usecase.calls


def test_closed_container_rejects_error_callback_before_state_mutation() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("partial", run_id="r")
    container.closed = True

    with pytest.raises(CongineLifecycleError, match="closed"):
        handler.on_llm_error(RuntimeError("host failure"), run_id="r")

    assert handler._runs["r"].parts == ["partial"]


def test_u35_llm_error_discards_partial_stream() -> None:
    handler, container = _handler()
    handler.on_llm_new_token("partial", run_id="r")
    handler.on_llm_error(RuntimeError("llm failed"), run_id="r")
    assert "r" not in handler._runs
    _assert_not_evaluated(handler, container, "r")


def test_u36_raw_unsupported_content_never_reaches_logs_or_errors() -> None:
    handler, container = _handler()
    errors: List[BaseException] = [
        _refuse(
            lambda: handler.on_llm_new_token(
                [{"type": "text", "text": SECRET}],  # type: ignore[arg-type]
                run_id="token",
            ),
            "non_text_stream_token",
        ),
        _refuse(
            lambda: handler.on_llm_end(
                _chat_final(AIMessage(content=[{"type": "text", "text": SECRET}])),
                run_id="content",
            ),
            "non_text_content",
        ),
        _refuse(
            lambda: handler.on_llm_end(
                _chat_final(AIMessage(content="ok", tool_calls=[_tool_call(q=SECRET)])),
                run_id="tool",
            ),
            "tool_or_action_content",
        ),
        _refuse(
            lambda: handler.on_llm_end(
                _chat_final(
                    AIMessage(content="ok", additional_kwargs={"reasoning": SECRET})
                ),
                run_id="metadata",
            ),
            "unsupported_message_metadata",
        ),
        _refuse(
            lambda: handler.on_llm_end(
                _final("ok", generation_info={"finish_reason": SECRET}),
                run_id="termination",
            ),
            "unknown_termination",
        ),
        # Sticky: ending the refused "token" run with a final carrying the
        # secret still refuses by the first reason, before reading the final.
        _refuse(
            lambda: handler.on_llm_end(_final(SECRET), run_id="token"),
            "non_text_stream_token",
        ),
    ]

    for exc in errors:
        _assert_sanitized(exc)
    assert container.validate_contract_usecase.calls == []
    assert container.logger.records, "refusals are logged (by reason code only)"
    assert SECRET not in repr(container.logger.records)
    assert {kw["reason"] for _lvl, _msg, kw in container.logger.records} >= {
        "non_text_stream_token",
        "tool_or_action_content",
    }


# --------------------------------------------------------------------------- #
# Public surface and optional dependency
# --------------------------------------------------------------------------- #
def test_handler_raises_through_langchain_dispatch_by_default() -> None:
    handler, _ = _handler()
    assert CongineCallbackHandler.raise_error is True
    assert handler.raise_error is True


def test_representation_error_is_canonical_not_an_alias() -> None:
    import congine_core
    from congine_core import exceptions

    assert issubclass(CongineUnsupportedRepresentationError, CongineBaseException)
    assert not issubclass(CongineUnsupportedRepresentationError, CongineValidationError)
    assert "CongineUnsupportedRepresentationError" in exceptions.__all__
    assert "CongineUnsupportedRepresentationError" in congine_core.__all__
    assert (
        congine_core.CongineUnsupportedRepresentationError
        is CongineUnsupportedRepresentationError
    )


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


def test_importing_the_sdk_does_not_import_langchain() -> None:
    probe = (
        "import sys, congine_core, congine_core.adapters; "
        "assert 'langchain_core' not in sys.modules, 'langchain_core imported'"
    )
    completed = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stderr


def test_unknown_adapter_attr_raises() -> None:
    from congine_core import adapters

    with pytest.raises(AttributeError):
        _ = adapters.DoesNotExist
