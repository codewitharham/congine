"""Structured JSON logger (Layer 4).

:class:`StructuredLogger` emits one JSON object per log line to stdout,
satisfying the :class:`congine_core.ports.logger.ILogger` protocol. A
configurable level threshold (audit L5) suppresses records below the chosen
severity so that, e.g., per-drain ``DEBUG`` telemetry is silent in production.

A per-logger ``log_safe_fields`` allowlist provides PII-safe behaviour for
multi-tenant log pipelines (audit §5.3): when set, any structured ``**kwargs``
key not in the allowlist has its value replaced with ``"<redacted>"`` before
the record is emitted. When unset (the default), no redaction is applied.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, FrozenSet, Optional

#: Severity ordering for threshold filtering.
_LEVELS = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}

#: Fields kept verbatim even when a redaction allowlist is active. Includes the
#: record envelope (always safe) plus the standard operational keys most
#: dashboards rely on for triage.
_DEFAULT_SAFE_FIELDS: FrozenSet[str] = frozenset(
    {"contract_id", "status", "duration_ms", "rule", "field", "error_type"}
)

# Unconditional blocklist — never logged verbatim (FIX-08).
_BLOCKED_LOG_KEYS: FrozenSet[str] = frozenset(
    {
        "api_key",
        "authorization",
        "x-api-key",
        "payload",
        "breach_details",
    }
)


class StructuredLogger:
    """JSON-formatted structured logger writing to stdout."""

    def __init__(
        self,
        name: str = "congine",
        level: str = "INFO",
        log_safe_fields: "Optional[FrozenSet[str]]" = None,
    ) -> None:
        """Args:
        name: Logger name embedded in every emitted record.
        level: Minimum severity to emit (``DEBUG``/``INFO``/``WARNING``/``ERROR``);
            unknown values fall back to ``INFO``.
        log_safe_fields: Optional allowlist of structured-extra keys that may be
            logged verbatim. When set, every other key has its value replaced
            with ``"<redacted>"``. Pass an empty frozenset to redact everything,
            or ``None`` (default) to disable redaction entirely (backward
            compatible).
        """
        self.name = name
        self._threshold = _LEVELS.get(str(level).upper(), _LEVELS["INFO"])
        self._log_safe_fields = log_safe_fields

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """Emit a single structured record if *level* meets the threshold.

        Non-JSON-serializable extras are coerced via ``default=str`` so logging
        never raises on the hot path. When ``log_safe_fields`` is configured,
        any kwarg key not in the allowlist has its value replaced.
        """
        if _LEVELS.get(level, _LEVELS["INFO"]) < self._threshold:
            return
        if kwargs:
            redacted: dict[str, Any] = {}
            for k, v in kwargs.items():
                key_lower = k.lower()
                if key_lower in _BLOCKED_LOG_KEYS:
                    redacted[k] = "<redacted>"
                elif (
                    self._log_safe_fields is not None and k not in self._log_safe_fields
                ):
                    redacted[k] = "<redacted>"
                else:
                    redacted[k] = v
            kwargs = redacted
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": level,
            "logger": self.name,
            "message": message,
            **kwargs,
        }
        print(json.dumps(entry, default=str), file=sys.stdout, flush=True)

    def info(self, message: str, **kwargs: Any) -> None:
        """Log at INFO level."""
        self._log("INFO", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        """Log at ERROR level."""
        self._log("ERROR", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log at WARNING level."""
        self._log("WARNING", message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log at DEBUG level."""
        self._log("DEBUG", message, **kwargs)
