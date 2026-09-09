"""LangChain callback handler (Layer 5)."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from congine_core.exceptions import CongineBaseException

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


class CongineCallbackHandler(_BaseCallbackHandler):
    """Validate streamed LLM completions against a Congine contract."""

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
        self._buffers: Dict[Any, List[str]] = {}
        self._buffer_lengths: Dict[Any, int] = {}
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
            with self._lock:
                current = self._buffer_lengths.get(run_id, 0)
                if current >= self._max_buffer_chars:
                    return
                remaining = self._max_buffer_chars - current
                clipped = token[:remaining]
                self._buffers.setdefault(run_id, []).append(clipped)
                self._buffer_lengths[run_id] = current + len(clipped)
        except CongineBaseException as exc:
            self._best_effort_log_validation_error(exc)
            raise
        except Exception as exc:
            self._best_effort_log_validation_error(exc)

    def on_llm_end(
        self, response: Any = None, *, run_id: Any = None, **kwargs: Any
    ) -> Optional["ValidationResult"]:
        # A callback can outlive its host container. Refuse a new callback
        # completion before mutating state or touching torn-down resources.
        if not self._ensure_open():
            return None

        try:
            with self._lock:
                tokens = self._buffers.pop(run_id, [])
                self._buffer_lengths.pop(run_id, None)

            completion = "".join(tokens)
            if not completion and response is not None:
                completion = self._extract_text(response)

            payload = {self._payload_key: completion}
            result = self._container.validate_contract_usecase.execute(
                payload=payload,
                contract_id=self._contract_id,
                contract_version=self._version,
            )
            self._record_result(run_id, result)
            return result
        except CongineBaseException as exc:
            self._best_effort_record_failure(run_id)
            self._best_effort_log_validation_error(exc)
            raise
        except Exception as exc:
            self._best_effort_record_failure(run_id)
            self._best_effort_log_validation_error(exc)
            return None

    def on_llm_error(
        self, error: BaseException, *, run_id: Any = None, **kwargs: Any
    ) -> None:
        if not self._ensure_open():
            return
        try:
            with self._lock:
                self._buffers.pop(run_id, None)
                self._buffer_lengths.pop(run_id, None)
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

    @staticmethod
    def _extract_text(response: Any) -> str:
        generations = getattr(response, "generations", None)
        if not generations:
            return ""
        try:
            first = generations[0][0]
        except (IndexError, TypeError):
            return ""
        text = getattr(first, "text", None)
        if isinstance(text, str):
            return text
        message = getattr(first, "message", None)
        content = getattr(message, "content", None)
        return content if isinstance(content, str) else ""
