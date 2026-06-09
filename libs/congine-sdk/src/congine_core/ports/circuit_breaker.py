"""Abstraction for the control-plane circuit breaker (Layer 1).

Defines :class:`ICircuitBreaker`, the structural interface for fast-failing
control-plane calls when the remote plane is hung or flapping. The production
implementation is :class:`congine_core.infrastructure.circuit_breaker.CircuitBreaker`.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ICircuitBreaker(Protocol):
    """Structural interface for a process-local circuit breaker."""

    @property
    def state(self) -> str:
        """Current state: ``CLOSED``, ``OPEN``, or ``HALF_OPEN``."""
        ...

    def allow(self) -> bool:
        """Return ``True`` when a protected call may be attempted."""
        ...

    def record_success(self) -> None:
        """Record a successful protected call."""
        ...

    def record_failure(self) -> None:
        """Record a failed protected call."""
        ...
