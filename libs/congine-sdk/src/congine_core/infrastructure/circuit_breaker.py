"""Circuit breaker (Layer 4).

A small, process-local :class:`CircuitBreaker` that wraps the control-plane
boundary (contract fetch + telemetry ship) and converts a hung/flapping plane
into a fast-fail. Without this, a cold control plane can stall application
boot up to 10s per attempt (the ``httpx`` client timeout) — long enough to
trip Kubernetes liveness/readiness gates — and a persistently dead plane burns
the full backoff window on every background sync pass.

The breaker is **not a dependency-inverted seam**: it wraps existing adapters
rather than abstracting them, so it lives at L4 without a matching L1 port.

State machine::

    CLOSED ──(k consecutive failures)──► OPEN
    OPEN   ──(cooldown_seconds elapsed)──► HALF_OPEN
    HALF_OPEN ──(probe success)──────────► CLOSED
    HALF_OPEN ──(probe fails)────────────► OPEN

The breaker is strictly in-memory and per-process; a distributed/Redis-backed
breaker is Phase 2+. For Phase 0, the per-process variant already provides the
two protections that matter most: boot-stall protection and background-sync
fast-fail.
"""

from __future__ import annotations

import threading
import time
from typing import Callable


_CLOSED = "CLOSED"
_OPEN = "OPEN"
_HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """Thread-safe, in-memory circuit breaker for the control-plane boundary."""

    def __init__(
        self,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Args:
        failure_threshold: Consecutive failures before tripping to OPEN.
        cooldown_seconds: Seconds the breaker stays OPEN before allowing a
            single probe (HALF_OPEN).
        clock: Monotonic clock function; injectable for deterministic tests.
        """
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be non-negative")
        self._failure_threshold = failure_threshold
        self._cooldown_seconds = float(cooldown_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._state = _CLOSED
        self._consecutive_failures = 0
        self._opened_at: float = 0.0

    @property
    def state(self) -> str:
        """Current state: ``"CLOSED" | "OPEN" | "HALF_OPEN"``.

        Reading the state may transition OPEN → HALF_OPEN if the cooldown has
        elapsed — so a caller that consults ``state`` and then ``allow()`` is
        guaranteed coherent behaviour.
        """
        with self._lock:
            self._maybe_half_open_locked()
            return self._state

    def allow(self) -> bool:
        """Return ``True`` when the caller may attempt the protected call.

        - ``CLOSED``      → always ``True``.
        - ``OPEN``        → ``True`` once the cooldown has elapsed (transitions
          to HALF_OPEN); otherwise ``False``.
        - ``HALF_OPEN``   → ``True`` (the single probe). Subsequent callers see
          OPEN/HALF_OPEN until the probe records success or failure.
        """
        with self._lock:
            self._maybe_half_open_locked()
            return self._state != _OPEN

    def record_success(self) -> None:
        """Record a successful call: reset to CLOSED and clear the counter."""
        with self._lock:
            self._state = _CLOSED
            self._consecutive_failures = 0
            self._opened_at = 0.0

    def record_failure(self) -> None:
        """Record a failed call. Trips to OPEN at the threshold; in HALF_OPEN,
        a failure flips straight back to OPEN."""
        with self._lock:
            if self._state == _HALF_OPEN:
                self._state = _OPEN
                self._opened_at = self._clock()
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._state = _OPEN
                self._opened_at = self._clock()

    def _maybe_half_open_locked(self) -> None:
        """If OPEN and the cooldown has elapsed, transition to HALF_OPEN."""
        if self._state != _OPEN:
            return
        if self._clock() - self._opened_at >= self._cooldown_seconds:
            self._state = _HALF_OPEN
