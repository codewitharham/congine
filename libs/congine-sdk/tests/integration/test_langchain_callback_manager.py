"""P2-03a1: the LangChain handler through LangChain's *real* callback dispatch.

Calling ``handler.on_llm_end(...)`` directly proves nothing about what a host
sees: LangChain's ``CallbackManager`` logs and swallows handler exceptions
unless ``raise_error`` is set. These tests drive the real
``langchain_core.callbacks.manager.CallbackManager`` (LC01–LC05) and real
LangChain models (LC06–LC09) against a real ``ServiceContainer`` whose
telemetry is captured by ``FakeEventBus``. Each ``execute()`` publishes
exactly one event, so the event count is the policy-evaluation witness.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator, List

import pytest

pytest.importorskip("langchain_core")

from langchain_core.callbacks.manager import CallbackManager  # noqa: E402
from langchain_core.language_models.fake import FakeListLLM  # noqa: E402
from langchain_core.language_models.fake_chat_models import (  # noqa: E402
    GenericFakeChatModel,
)
from langchain_core.messages import AIMessage, AIMessageChunk  # noqa: E402
from langchain_core.outputs import (  # noqa: E402
    ChatGeneration,
    ChatGenerationChunk,
    Generation,
    LLMResult,
)

from congine_core.adapters.dependency_injection import ServiceContainer  # noqa: E402
from congine_core.adapters.langchain_handler import (  # noqa: E402
    CongineCallbackHandler,
)
from congine_core.config import CongineConfig, FailMode, Region  # noqa: E402
from congine_core.exceptions import (  # noqa: E402
    CongineUnsupportedRepresentationError,
    CongineValidationError,
)
from tests.conftest import FakeEventBus  # noqa: E402

SECRET = "SECRET-SENTINEL-p2-03a1-lc"
_CONTRACT = "lc-text"
_TEXT_SCHEMA = {"required": ["text"], "properties": {"text": {"type": "string"}}}
_LANGCHAIN_LOGGER = "langchain_core.callbacks.manager"


def _container(fail_mode: FailMode = FailMode.DEGRADE) -> ServiceContainer:
    """Real container with telemetry captured by a fake bus (no network)."""
    container = ServiceContainer(
        CongineConfig(
            base_url="http://control-plane.invalid",
            api_key="k",
            project_id="p",
            tenant_id="t",
            region=Region.US,
            allow_cleartext=True,  # cleartext test control plane (declared)
            validation_timeout_ms=1000,
            fail_mode=fail_mode,
        )
    )
    container.event_bus.stop(drain=False)
    fake_bus = FakeEventBus()
    container.event_bus = fake_bus
    container.validate_contract_usecase.event_bus = fake_bus
    return container


@pytest.fixture
def container() -> Iterator[ServiceContainer]:
    container = _container()
    container.schema_storage.put(_CONTRACT, _TEXT_SCHEMA, 300)
    try:
        yield container
    finally:
        container.close()


def _published(container: ServiceContainer) -> List[Any]:
    return container.event_bus.published  # type: ignore[attr-defined, no-any-return]


def _run_manager(handler: CongineCallbackHandler) -> Any:
    return CallbackManager([handler]).on_llm_start(
        {"name": "p2-03a1-test"}, ["prompt"]
    )[0]


def _tool_message() -> AIMessage:
    return AIMessage(
        content="The request looks safe.",
        tool_calls=[
            {"name": "delete_customer_record", "args": {"id": 42}, "id": "call_1"}
        ],
    )


# --------------------------------------------------------------------------- #
# LC01–LC05: the real CallbackManager
# --------------------------------------------------------------------------- #
def test_lc01_supported_final_response_completes_through_the_manager(
    container: ServiceContainer,
) -> None:
    handler = CongineCallbackHandler(_CONTRACT, container=container)
    run = _run_manager(handler)

    run.on_llm_end(LLMResult(generations=[[Generation(text="Deploy completed.")]]))

    result = handler.result_for(run.run_id)
    assert result is not None and result.is_pass()
    assert len(_published(container)) == 1


def test_lc02_representation_refusal_escapes_the_manager(
    container: ServiceContainer, caplog: pytest.LogCaptureFixture
) -> None:
    handler = CongineCallbackHandler(_CONTRACT, container=container)
    run = _run_manager(handler)
    response = LLMResult(
        generations=[[Generation(text=SECRET), Generation(text="candidate 2")]]
    )

    with caplog.at_level(logging.WARNING, logger=_LANGCHAIN_LOGGER):
        with pytest.raises(
            CongineUnsupportedRepresentationError, match=r"\(multiple_generations\)$"
        ):
            run.on_llm_end(response)

    assert _published(container) == []
    assert handler.result_for(run.run_id) is None
    # LangChain logs ``repr(exc)`` for every handler error: the refusal must be
    # content-free by construction.
    assert "CongineCallbackHandler.on_llm_end" in caplog.text
    assert SECRET not in caplog.text


def test_lc03_strict_policy_block_escapes_the_manager() -> None:
    container = _container(FailMode.STRICT)
    try:
        container.schema_storage.put(
            "strict-text",
            {
                "required": ["text"],
                "properties": {"text": {"type": "string", "enum": ["approved"]}},
            },
            300,
        )
        handler = CongineCallbackHandler("strict-text", container=container)
        run = _run_manager(handler)

        with pytest.raises(CongineValidationError):
            run.on_llm_end(LLMResult(generations=[[Generation(text="denied")]]))

        # The policy genuinely ran (one event) and then blocked.
        assert len(_published(container)) == 1
        assert handler.result_for(run.run_id) is None
    finally:
        container.close()


def test_lc04_unsupported_stream_observation_escapes_the_manager(
    container: ServiceContainer,
) -> None:
    handler = CongineCallbackHandler(_CONTRACT, container=container)
    run = _run_manager(handler)
    chunk = ChatGenerationChunk(
        message=AIMessageChunk(
            content="",
            tool_call_chunks=[
                {"name": "delete", "args": '{"id": 42}', "id": "c1", "index": 0}
            ],
        )
    )

    with pytest.raises(
        CongineUnsupportedRepresentationError, match=r"\(tool_or_action_content\)$"
    ):
        run.on_llm_new_token("", chunk=chunk)
    # The manager does not call on_llm_error here, so the run stays refused.
    with pytest.raises(
        CongineUnsupportedRepresentationError, match=r"\(tool_or_action_content\)$"
    ):
        run.on_llm_end(LLMResult(generations=[[Generation(text="")]]))

    assert _published(container) == []


def test_lc05_handler_raises_through_langchain_dispatch(
    container: ServiceContainer,
) -> None:
    handler = CongineCallbackHandler(_CONTRACT, container=container)
    assert CongineCallbackHandler.raise_error is True
    assert handler.raise_error is True


# --------------------------------------------------------------------------- #
# LC06–LC09: real LangChain models
# --------------------------------------------------------------------------- #
def test_lc06_real_chat_model_stream_reconciles_with_its_final_result(
    container: ServiceContainer,
) -> None:
    handler = CongineCallbackHandler(_CONTRACT, container=container)
    model = GenericFakeChatModel(
        messages=iter(["Deploy completed on all nodes."]), callbacks=[handler]
    )

    streamed = "".join(str(chunk.content) for chunk in model.stream("deploy?"))

    assert streamed == "Deploy completed on all nodes."
    assert handler.last_result is not None and handler.last_result.is_pass()
    assert len(_published(container)) == 1
    assert handler._runs == {}


def test_lc06b_real_text_llm_invoke_is_evaluated_once(
    container: ServiceContainer,
) -> None:
    handler = CongineCallbackHandler(_CONTRACT, container=container)
    model = FakeListLLM(responses=["Claim approved."], callbacks=[handler])

    assert model.invoke("status?") == "Claim approved."
    assert handler.last_result is not None and handler.last_result.is_pass()
    assert len(_published(container)) == 1


def test_lc07_real_chat_model_tool_call_is_refused_from_invoke(
    container: ServiceContainer,
) -> None:
    handler = CongineCallbackHandler(_CONTRACT, container=container)
    model = GenericFakeChatModel(messages=iter([_tool_message()]), callbacks=[handler])

    with pytest.raises(
        CongineUnsupportedRepresentationError, match=r"\(tool_or_action_content\)$"
    ):
        model.invoke("is this safe?")

    assert _published(container) == []
    assert handler.last_result is None


async def test_lc08_async_tool_call_refusal_escapes_ainvoke(
    container: ServiceContainer,
) -> None:
    handler = CongineCallbackHandler(_CONTRACT, container=container)
    model = GenericFakeChatModel(messages=iter([_tool_message()]), callbacks=[handler])

    with pytest.raises(
        CongineUnsupportedRepresentationError, match=r"\(tool_or_action_content\)$"
    ):
        await model.ainvoke("is this safe?")

    assert _published(container) == []


def test_lc09_real_stream_refusal_is_cleaned_up_by_on_llm_error(
    container: ServiceContainer,
) -> None:
    """Real-LangChain counterpart of unit test U11a.

    LangChain calls ``on_llm_error`` with the handler's own refusal before
    re-raising it, so the run's sticky state is cleared by the framework.
    """
    handler = CongineCallbackHandler(_CONTRACT, container=container)
    seen: List[BaseException] = []
    original = handler.on_llm_error

    def spy(error: BaseException, **kwargs: Any) -> None:
        seen.append(error)
        original(error, **kwargs)

    handler.on_llm_error = spy  # type: ignore[method-assign]
    message = AIMessage(
        content="looks safe",
        additional_kwargs={
            "function_call": {"name": "delete", "arguments": f'{{"q": "{SECRET}"}}'}
        },
    )
    model = GenericFakeChatModel(messages=iter([message]), callbacks=[handler])

    with pytest.raises(
        CongineUnsupportedRepresentationError, match=r"\(tool_or_action_content\)$"
    ) as info:
        list(model.stream("is this safe?"))

    assert len(seen) == 1 and seen[0] is info.value
    assert handler._runs == {}
    assert _published(container) == []
    assert SECRET not in str(info.value)


def test_refused_chat_generation_has_no_validation_result(
    container: ServiceContainer,
) -> None:
    handler = CongineCallbackHandler(_CONTRACT, container=container)
    run = _run_manager(handler)
    message = AIMessage(content=[{"type": "text", "text": "Deploy completed."}])

    with pytest.raises(
        CongineUnsupportedRepresentationError, match=r"\(non_text_content\)$"
    ):
        run.on_llm_end(LLMResult(generations=[[ChatGeneration(message=message)]]))

    assert handler.result_for(run.run_id) is None
    assert handler.last_result is None
    assert _published(container) == []
