"""Abstraction for structured logging (Layer 1).

Defines :class:`ILogger`, a structural interface for level-based structured
logging where arbitrary key-value context is supplied via ``**kwargs``.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ILogger(Protocol):
    """Structural interface for structured logging.

    Each method accepts a human-readable *message* plus arbitrary structured
    key-value extras as ``**kwargs``.
    """

    def info(self, message: str, **kwargs: Any) -> None:
        """Log an informational message with structured extras."""
        ...

    def error(self, message: str, **kwargs: Any) -> None:
        """Log an error message with structured extras."""
        ...

    def warning(self, message: str, **kwargs: Any) -> None:
        """Log a warning message with structured extras."""
        ...

    def debug(self, message: str, **kwargs: Any) -> None:
        """Log a debug message with structured extras."""
        ...
