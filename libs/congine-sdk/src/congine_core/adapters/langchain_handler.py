"""LangChain callback handler (Layer 5).

The handler evaluates a LangChain output only once it has established that the
output is completely represented under supported semantics (P2-03a1): exactly
one generation of plain text, with any token stream reconciled against the
final response. Anything partial, ambiguous or unsupported is refused *before*
the use case runs, with :class:`CongineUnsupportedRepresentationError`, and
``raise_error = True`` makes both that refusal and a strict BLOCK survive
LangChain's own callback dispatch.

This adapter does not make Congine understand more kinds of agent output. It
makes Congine stop claiming governance over output it does not fully see.
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Hashable, Mapping, Sized
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    ParamSpec,
    TypeVar,
)

from congine_core.exceptions import (
    CongineBaseException,
    CongineUnsupportedRepresentationError,
)

try:
    from langchain_core.callbacks.base import (
        BaseCallbackHandler as _BaseCallbackHandler,
    )

    _LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover
    _BaseCallbackHandler = object  # type: ignore[assignment,misc]
    _LANGCHAIN_AVAILABLE = False

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.adapters.dependency_injection import ServiceContainer
    from congine_core.models import ValidationResult


# --------------------------------------------------------------------------- #
# Representation vocabulary (P2-03a1) — private to this adapter
# --------------------------------------------------------------------------- #
class _RunStatus(Enum):
    """State of an active run; an absent ``_runs`` entry means no active run."""

    COLLECTING_TEXT = "collecting_text"
    REFUSED = "refused"


class _RefusalReason(Enum):
    """Fixed, content-free reason codes; the only detail a refusal exposes."""

    MISSING_RUN_ID = "missing_run_id"
    UNHASHABLE_RUN_ID = "unhashable_run_id"

    NON_TEXT_STREAM_TOKEN = "non_text_stream_token"
    UNSUPPORTED_STREAM_CHUNK = "unsupported_stream_chunk"
    STREAM_TOKEN_CHUNK_MISMATCH = "stream_token_chunk_mismatch"
    STREAM_BUFFER_EXCEEDED = "stream_buffer_exceeded"

    MISSING_FINAL_RESPONSE = "missing_final_response"
    MALFORMED_FINAL_RESPONSE = "malformed_final_response"
    NO_GENERATION = "no_generation"
    MULTIPLE_GENERATION_GROUPS = "multiple_generation_groups"
    MULTIPLE_GENERATIONS = "multiple_generations"

    NON_TEXT_CONTENT = "non_text_content"
    TEXT_MESSAGE_MISMATCH = "text_message_mismatch"
    TOOL_OR_ACTION_CONTENT = "tool_or_action_content"
    UNSUPPORTED_MESSAGE_METADATA = "unsupported_message_metadata"

    OUTPUT_TRUNCATED = "output_truncated"
    OUTPUT_INCOMPLETE = "output_incomplete"
    UNKNOWN_TERMINATION = "unknown_termination"
    STREAM_FINAL_MISMATCH = "stream_final_mismatch"


@dataclass
class _RunState:
    """One active run. A refused run keeps only its status and first reason."""

    parts: List[str] = field(default_factory=list)
    length: int = 0
    status: _RunStatus = _RunStatus.COLLECTING_TEXT
    refusal_reason: Optional[_RefusalReason] = None


class _Refusal(Exception):
    """Internal control-flow signal carrying a reason code.

    It may hold a host exception as ``__cause__`` for in-module diagnostics,
    but neither it nor that cause ever crosses the public callback boundary.
    """

    def __init__(self, reason: _RefusalReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


# Message fields and ``additional_kwargs`` keys that carry agent actions.
_ACTION_FIELDS = ("tool_calls", "invalid_tool_calls", "tool_call_chunks")
_ACTION_KWARGS = ("function_call", "tool_calls")

# Termination metadata. Unknown termination semantics are not evidence of
# completion, so only the "complete" set is accepted; every other non-empty
# value refuses. The allowlist is deliberately small (P2-03a1).
_TERMINATION_KEYS = ("finish_reason", "stop_reason")
_COMPLETE_TERMINATIONS = frozenset({"stop", "end_turn", "stop_sequence"})
_TRUNCATED_TERMINATIONS = frozenset({"length", "max_tokens", "max_output_tokens"})
_INCOMPLETE_TERMINATIONS = frozenset({"content_filter", "safety", "refusal"})

_MISSING = object()

_P = ParamSpec("_P")
_R = TypeVar("_R")


def _guarded(
    fallback: _RefusalReason,
) -> Callable[[Callable[_P, _R]], Callable[_P, _R]]:
    """Apply the representation boundary rule to a host-inspecting helper.

    A specific :class:`_Refusal` raised inside passes through unchanged; only
    an unexpected host-object failure is classified as *fallback*.
    """

    def decorate(inspect: Callable[_P, _R]) -> Callable[_P, _R]:
        @functools.wraps(inspect)
        def guarded(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            try:
                return inspect(*args, **kwargs)
            except _Refusal:
                raise
            except Exception as exc:
                raise _Refusal(fallback) from exc

        return guarded

    return decorate


def _require_run_key(run_id: Any) -> Hashable:
    """Refuse stateful governance without a usable run identity."""
    if run_id is None:
        raise _Refusal(_RefusalReason.MISSING_RUN_ID)
    try:
        hash(run_id)
    except Exception as exc:
        raise _Refusal(_RefusalReason.UNHASHABLE_RUN_ID) from exc
    key: Hashable = run_id
    return key


def _is_present(value: Any, malformed: _RefusalReason) -> bool:
    """Whether a side-channel value carries anything (``None``/empty is absent)."""
    try:
        return value is not None and not (isinstance(value, Sized) and len(value) == 0)
    except Exception as exc:  # host ``__len__`` is untrusted
        raise _Refusal(malformed) from exc


def _normalize_termination(value: Any, malformed: _RefusalReason) -> Optional[str]:
    """Normalise one termination value; an unknown value *type* refuses."""
    if value is None:
        return None
    if isinstance(value, Enum) and not isinstance(value, str):
        value = value.value if isinstance(value.value, str) else value.name
    if not isinstance(value, str):
        raise _Refusal(malformed)
    return value.strip().lower() or None


def _check_termination(metadata: Any, malformed: _RefusalReason) -> None:
    """Refuse when termination metadata does not establish a complete output."""
    if metadata is None:
        return
    if not isinstance(metadata, Mapping):
        raise _Refusal(malformed)
    for key in _TERMINATION_KEYS:
        termination = _normalize_termination(metadata.get(key), malformed)
        if termination is None or termination in _COMPLETE_TERMINATIONS:
            continue
        if termination in _TRUNCATED_TERMINATIONS:
            raise _Refusal(_RefusalReason.OUTPUT_TRUNCATED)
        if termination in _INCOMPLETE_TERMINATIONS:
            raise _Refusal(_RefusalReason.OUTPUT_INCOMPLETE)
        raise _Refusal(_RefusalReason.UNKNOWN_TERMINATION)


def _inspect_message(message: Any, malformed: _RefusalReason) -> str:
    """Return a message's text only if nothing else rides alongside it."""
    for name in _ACTION_FIELDS:
        if _is_present(getattr(message, name, None), malformed):
            raise _Refusal(_RefusalReason.TOOL_OR_ACTION_CONTENT)
    extra = getattr(message, "additional_kwargs", None)
    if extra is not None:
        if not isinstance(extra, Mapping):
            raise _Refusal(malformed)
        for key in _ACTION_KWARGS:
            if _is_present(extra.get(key), malformed):
                raise _Refusal(_RefusalReason.TOOL_OR_ACTION_CONTENT)
        # Unaccounted side-channel output is refused, not ignored.
        for value in extra.values():
            if _is_present(value, malformed):
                raise _Refusal(_RefusalReason.UNSUPPORTED_MESSAGE_METADATA)
    content = getattr(message, "content", _MISSING)
    if not isinstance(content, str):
        # Content blocks are never flattened: a list with a text part is not text.
        raise _Refusal(_RefusalReason.NON_TEXT_CONTENT)
    _check_termination(getattr(message, "response_metadata", None), malformed)
    return content


@_guarded(_RefusalReason.UNSUPPORTED_STREAM_CHUNK)
def _inspect_stream_observation(token: Any, chunk: Any) -> None:
    """Accept one stream observation only if token and chunk are one text."""
    if not isinstance(token, str):
        raise _Refusal(_RefusalReason.NON_TEXT_STREAM_TOKEN)
    if chunk is None:
        return
    message = getattr(chunk, "message", None)
    if message is not None:
        chunk_text = _inspect_message(message, _RefusalReason.UNSUPPORTED_STREAM_CHUNK)
    else:
        text = getattr(chunk, "text", _MISSING)
        if not isinstance(text, str):
            raise _Refusal(_RefusalReason.UNSUPPORTED_STREAM_CHUNK)
        chunk_text = text
    if chunk_text != token:
        raise _Refusal(_RefusalReason.STREAM_TOKEN_CHUNK_MISMATCH)
    _check_termination(
        getattr(chunk, "generation_info", None),
        _RefusalReason.UNSUPPORTED_STREAM_CHUNK,
    )


@_guarded(_RefusalReason.MALFORMED_FINAL_RESPONSE)
def _inspect_llm_output(llm_output: Any) -> None:
    """Read ``LLMResult.llm_output`` for signals that change completeness.

    Only top-level action and termination keys are interpreted. Everything
    else (token usage, model name, fingerprints, ids) is provider metadata
    outside the governed text subject.
    """
    if llm_output is None:
        return
    if not isinstance(llm_output, Mapping):
        raise _Refusal(_RefusalReason.MALFORMED_FINAL_RESPONSE)
    for key in (*_ACTION_FIELDS, *_ACTION_KWARGS):
        if _is_present(llm_output.get(key), _RefusalReason.MALFORMED_FINAL_RESPONSE):
            raise _Refusal(_RefusalReason.TOOL_OR_ACTION_CONTENT)
    _check_termination(llm_output, _RefusalReason.MALFORMED_FINAL_RESPONSE)


@_guarded(_RefusalReason.MALFORMED_FINAL_RESPONSE)
def _extract_complete_text(response: Any) -> str:
    """Return the complete final text, or refuse.

    An explicit ``""`` is a valid complete output; *failing* to extract text is
    a refusal and is never converted to ``""``.
    """
    if response is None:
        raise _Refusal(_RefusalReason.MISSING_FINAL_RESPONSE)
    generations = getattr(response, "generations", _MISSING)
    if not isinstance(generations, (list, tuple)):
        raise _Refusal(_RefusalReason.MALFORMED_FINAL_RESPONSE)
    if not generations:
        raise _Refusal(_RefusalReason.NO_GENERATION)
    if len(generations) > 1:
        raise _Refusal(_RefusalReason.MULTIPLE_GENERATION_GROUPS)
    group = generations[0]
    if not isinstance(group, (list, tuple)):
        raise _Refusal(_RefusalReason.MALFORMED_FINAL_RESPONSE)
    if not group:
        raise _Refusal(_RefusalReason.NO_GENERATION)
    if len(group) > 1:
        raise _Refusal(_RefusalReason.MULTIPLE_GENERATIONS)

    generation = group[0]
    text = getattr(generation, "text", _MISSING)
    message = getattr(generation, "message", None)
    if message is not None:
        complete = _inspect_message(message, _RefusalReason.MALFORMED_FINAL_RESPONSE)
        # Neither representation is preferred: when both exist they must agree.
        if isinstance(text, str) and text != complete:
            raise _Refusal(_RefusalReason.TEXT_MESSAGE_MISMATCH)
    elif isinstance(text, str):
        complete = text
    else:
        raise _Refusal(_RefusalReason.NON_TEXT_CONTENT)

    _check_termination(
        getattr(generation, "generation_info", None),
        _RefusalReason.MALFORMED_FINAL_RESPONSE,
    )
    _inspect_llm_output(getattr(response, "llm_output", None))
    return complete


class CongineCallbackHandler(_BaseCallbackHandler):
    """Validate completely represented LLM completions against a contract."""

    #: LangChain's default (``False``) makes its dispatcher log and swallow any
    #: exception a handler raises, so neither a strict BLOCK nor a
    #: representation refusal would reach the host (P2-03a1).
    raise_error: bool = True

    def __init__(
        self,
        contract_id: str,
        version: str = "latest",
        container: Optional["ServiceContainer"] = None,
        payload_key: str = "text",
    ) -> None:
        if not _LANGCHAIN_AVAILABLE:
            raise ImportError(
                "CongineCallbackHandler requires 'langchain-core'. "
                "Install it with: pip install congine-sdk[langchain]"
            )
        from congine_core.adapters.dependency_injection import ServiceContainer
        from congine_core.config import DeploymentMode
        from congine_core.exceptions import CongineConfigurationError

        if container is None:
            config = __import__(
                "congine_core.config", fromlist=["CongineConfig"]
            ).CongineConfig.from_env()
            if config.deployment_mode is DeploymentMode.MULTI_TENANT:
                raise CongineConfigurationError(
                    "CongineCallbackHandler requires an explicit container= "
                    "in multi_tenant deployment mode."
                )
            container = ServiceContainer.get_default()
        self._container = container
        self._logger = getattr(self._container, "logger", None)
        self._contract_id = contract_id
        self._version = version
        self._payload_key = payload_key
        from congine_core.security_limits import DEFAULT_MAX_STREAM_BUFFER_CHARS

        container_config = getattr(self._container, "config", None)
        self._max_buffer_chars = (
            container_config.max_stream_buffer_chars
            if container_config is not None
            else DEFAULT_MAX_STREAM_BUFFER_CHARS
        )

        self._lock = threading.Lock()
        self._runs: Dict[Hashable, _RunState] = {}
        self._results: Dict[Any, "ValidationResult"] = {}
        self._last_result: Optional["ValidationResult"] = None

    @property
    def last_result(self) -> Optional["ValidationResult"]:
        """Most recently completed result, read through the state lock."""
        with self._lock:
            return self._last_result

    @last_result.setter
    def last_result(self, result: Optional["ValidationResult"]) -> None:
        """Preserve the historical assignment API behind the state lock."""
        with self._lock:
            self._last_result = result

    def on_llm_new_token(
        self, token: str, *, run_id: Any = None, **kwargs: Any
    ) -> None:
        if not self._ensure_open():
            return
        try:
            key = _require_run_key(run_id)
            standing = self._collect_token(key, token, kwargs.get("chunk"))
        except _Refusal as caught:
            standing = caught.reason
        except Exception:
            # Inspection is guarded, so only the run identity's own hashing or
            # equality can fail here after admission: the identity is unusable.
            standing = _RefusalReason.UNHASHABLE_RUN_ID
        if standing is None:
            return
        # The one public raise: outside the ``except`` block and ``from None``,
        # so neither the private refusal nor any host exception is chained.
        raise self._refusal_error(standing) from None

    def on_llm_end(
        self, response: Any = None, *, run_id: Any = None, **kwargs: Any
    ) -> Optional["ValidationResult"]:
        # A callback can outlive its host container. Refuse a new callback
        # completion before mutating state or touching torn-down resources.
        if not self._ensure_open():
            return None

        key: Optional[Hashable] = None
        try:
            key = _require_run_key(run_id)
            completion = self._establish_completion(key, response)
        except _Refusal as caught:
            reason = caught.reason
        except Exception:
            # As in ``on_llm_new_token``: only the admitted run identity can fail
            # here, so it is unusable for result bookkeeping as well.
            reason, key = _RefusalReason.UNHASHABLE_RUN_ID, None
        else:
            return self._evaluate(key, completion)
        self._best_effort_record_failure(key)
        raise self._refusal_error(reason) from None

    def on_llm_error(
        self, error: BaseException, *, run_id: Any = None, **kwargs: Any
    ) -> None:
        if not self._ensure_open():
            return
        try:
            with self._lock:
                self._runs.pop(run_id, None)
                self._results.pop(run_id, None)
                self._last_result = None
        except CongineBaseException as exc:
            self._best_effort_log_validation_error(exc)
            raise
        except Exception as exc:
            self._best_effort_log_validation_error(exc)

    def result_for(self, run_id: Any) -> Optional["ValidationResult"]:
        """Return the validation result for a specific *run_id*."""
        with self._lock:
            return self._results.get(run_id)

    def _collect_token(
        self, key: Hashable, token: str, chunk: Any
    ) -> Optional[_RefusalReason]:
        """Record one stream observation; return the standing refusal, if any."""
        try:
            _inspect_stream_observation(token, chunk)
        except _Refusal as caught:
            return self._mark_refused(key, caught.reason)
        with self._lock:
            state = self._runs.setdefault(key, _RunState())
            if state.refusal_reason is not None:
                # Sticky: no later valid token restores a refused run.
                return state.refusal_reason
            if state.length + len(token) > self._max_buffer_chars:
                # Never clip: validating a prefix would certify unseen output.
                return self._refuse_locked(state, _RefusalReason.STREAM_BUFFER_EXCEEDED)
            state.parts.append(token)
            state.length += len(token)
        return None

    def _establish_completion(self, key: Hashable, response: Any) -> str:
        """Establish the complete governed text for *key* before any evaluation."""
        with self._lock:
            state = self._runs.pop(key, None)
        if state is not None and state.refusal_reason is not None:
            raise _Refusal(state.refusal_reason)
        final_text = _extract_complete_text(response)
        # Any stream, even of empty tokens, must agree with the final response.
        if state is not None and "".join(state.parts) != final_text:
            raise _Refusal(_RefusalReason.STREAM_FINAL_MISMATCH)
        return final_text

    def _evaluate(self, key: Hashable, completion: str) -> Optional["ValidationResult"]:
        """Run exactly one policy evaluation on an established representation."""
        try:
            result = self._container.validate_contract_usecase.execute(
                payload={self._payload_key: completion},
                contract_id=self._contract_id,
                contract_version=self._version,
            )
            self._record_result(key, result)
            return result
        except CongineBaseException as exc:
            self._best_effort_record_failure(key)
            self._best_effort_log_validation_error(exc)
            raise
        except Exception as exc:
            self._best_effort_record_failure(key)
            self._best_effort_log_validation_error(exc)
            return None

    def _mark_refused(self, key: Hashable, reason: _RefusalReason) -> _RefusalReason:
        """Sticky-refuse *key*'s run. Must be called without holding ``_lock``."""
        with self._lock:
            state = self._runs.setdefault(key, _RunState())
            return self._refuse_locked(state, reason)

    @staticmethod
    def _refuse_locked(state: _RunState, reason: _RefusalReason) -> _RefusalReason:
        """Refuse *state*, keeping the first reason. Caller must hold ``_lock``."""
        if state.refusal_reason is None:
            state.refusal_reason = reason
        state.status = _RunStatus.REFUSED
        state.parts.clear()
        state.length = 0
        return state.refusal_reason

    def _refusal_error(
        self, reason: _RefusalReason
    ) -> CongineUnsupportedRepresentationError:
        """Build the sanitized public refusal: a fixed reason code, no content."""
        self._best_effort_log_refusal(reason)
        return CongineUnsupportedRepresentationError(
            "LangChain output cannot be governed safely: "
            f"unsupported representation ({reason.value})"
        )

    def _best_effort_log_refusal(self, reason: _RefusalReason) -> None:
        """Log a refusal by reason code only; a logger failure never replaces it."""
        try:
            if self._logger is not None:
                self._logger.error(
                    "LangChain output representation refused",
                    contract_id=self._contract_id,
                    error_type=CongineUnsupportedRepresentationError.__name__,
                    reason=reason.value,
                )
        except Exception:
            return

    def _record_result(self, run_id: Any, result: Optional["ValidationResult"]) -> None:
        """Atomically update per-run and latest-result state."""
        with self._lock:
            if result is None:
                self._results.pop(run_id, None)
            else:
                self._results[run_id] = result
            self._last_result = result

    def _log_validation_error(self, exc: BaseException) -> None:
        """Log a callback failure without exposing its message or payload."""
        if self._logger is not None:
            self._logger.error(
                "LangChain validation failed",
                contract_id=self._contract_id,
                error_type=type(exc).__name__,
            )

    def _best_effort_record_failure(self, run_id: Any) -> None:
        """Clear result state without replacing the callback's original error."""
        try:
            self._record_result(run_id, None)
        except Exception:
            return

    def _best_effort_log_validation_error(self, exc: BaseException) -> None:
        """Keep host logger failures inside the callback containment boundary."""
        try:
            self._log_validation_error(exc)
        except Exception:
            return

    def _ensure_open(self) -> bool:
        """Guard callback state mutation against a closed host container."""
        try:
            self._container.ensure_open()
        except CongineBaseException as exc:
            self._best_effort_log_validation_error(exc)
            raise
        except Exception as exc:
            self._best_effort_log_validation_error(exc)
            return False
        return True
