"""LangChain callback handler (Layer 5).

:class:`CongineCallbackHandler` is an **optional** adapter that validates LLM
output produced through LangChain against a Congine contract, reusing the exact
:class:`ValidateContractUseCase` path that ``@congine_guard`` uses.

Optional dependency: ``langchain-core`` is imported lazily inside a
``try/except`` so importing the core SDK never requires LangChain. The module is
NOT eagerly imported by :mod:`congine_core` or :mod:`congine_core.adapters`; it
is reachable via ``congine_core.adapters.langchain_handler`` or the lazy
``congine_core.adapters.CongineCallbackHandler`` attribute. Instantiating the
handler without LangChain installed raises a clear :class:`ImportError`.

Thread-safety: ``on_llm_new_token`` may be invoked at high throughput from many
concurrent runs. Tokens are accumulated per ``run_id`` under a single
:class:`threading.Lock`; validation runs in ``on_llm_end`` *outside* the lock so
token ingestion is never serialized behind validation latency.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Any, Dict, List, Optional

try:  # Optional dependency.
    from langchain_core.callbacks.base import (
        BaseCallbackHandler as _BaseCallbackHandler,
    )

    _LANGCHAIN_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without langchain-core
    _BaseCallbackHandler = object  # type: ignore[assignment,misc]
    _LANGCHAIN_AVAILABLE = False

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.adapters.dependency_injection import ServiceContainer
    from congine_core.domain.models import ValidationResult


class CongineCallbackHandler(_BaseCallbackHandler):  # type: ignore[misc,valid-type]
    """Validate streamed/!streamed LLM completions against a Congine contract.

    Args:
        contract_id: Contract identifier the completion must satisfy.
        version: Contract version recorded in telemetry (default ``"latest"``).
        container: A :class:`ServiceContainer`; built from the environment when
            ``None``.
        payload_key: Key under which the joined completion text is wrapped into
            the validation payload dict (the RuleEngine validates mappings).
    """

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
        # Imported lazily so the module stays import-safe without a container.
        from congine_core.adapters.dependency_injection import ServiceContainer

        self._container = container or ServiceContainer.from_env()
        self._logger = getattr(self._container, "logger", None)
        self._contract_id = contract_id
        self._version = version
        self._payload_key = payload_key

        self._lock = threading.Lock()
        self._buffers: Dict[Any, List[str]] = {}
        #: Result of the most recent ``on_llm_end`` validation (or ``None``).
        self.last_result: Optional["ValidationResult"] = None

    # ------------------------------------------------------------------ #
    # LangChain callback surface
    # ------------------------------------------------------------------ #
    def on_llm_new_token(
        self, token: str, *, run_id: Any = None, **kwargs: Any
    ) -> None:
        """Accumulate a streamed *token* for its run (O(1), lock-guarded)."""
        with self._lock:
            self._buffers.setdefault(run_id, []).append(token)

    def on_llm_end(
        self, response: Any = None, *, run_id: Any = None, **kwargs: Any
    ) -> Optional["ValidationResult"]:
        """Join the run's tokens and validate the completion against the contract.

        Validation runs outside the accumulation lock. Any error is logged and
        swallowed so the handler can never break the host LLM run; the result
        (or ``None`` on error/strict-raise) is also stored on
        :attr:`last_result`.
        """
        with self._lock:
            tokens = self._buffers.pop(run_id, [])

        completion = "".join(tokens)
        if not completion and response is not None:
            completion = self._extract_text(response)

        payload = {self._payload_key: completion}
        try:
            self.last_result = self._container.validate_contract_usecase.execute(
                payload=payload,
                contract_id=self._contract_id,
                contract_version=self._version,
            )
        except Exception as exc:  # noqa: BLE001 - never break the host stream
            self.last_result = None
            if self._logger is not None:
                self._logger.error(
                    "LangChain validation failed",
                    contract_id=self._contract_id,
                    error=str(exc),
                )
        return self.last_result

    def on_llm_error(
        self, error: BaseException, *, run_id: Any = None, **kwargs: Any
    ) -> None:
        """Discard a failed run's partial buffer to avoid leaking memory."""
        with self._lock:
            self._buffers.pop(run_id, None)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _extract_text(response: Any) -> str:
        """Best-effort extraction of completion text from an ``LLMResult``.

        Used for non-streaming runs where no tokens were emitted. Tolerant of
        shape differences across LangChain versions.
        """
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
