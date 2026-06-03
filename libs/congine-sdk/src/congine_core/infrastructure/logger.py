"""Structured JSON logger (Layer 4).

:class:`StructuredLogger` emits one JSON object per log line to stdout,
satisfying the :class:`congine_core.repositories.logger.ILogger` protocol.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any


class StructuredLogger:
    """JSON-formatted structured logger writing to stdout."""

    def __init__(self, name: str = "congine") -> None:
        """Args:
        name: Logger name embedded in every emitted record.
        """
        self.name = name

    def _log(self, level: str, message: str, **kwargs: Any) -> None:
        """Emit a single structured record.

        Non-JSON-serializable extras are coerced via ``default=str`` so logging
        never raises on the hot path.
        """
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
