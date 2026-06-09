"""Unit tests for the L4 :class:`CircuitBreaker`.

Validates the CLOSED → OPEN → HALF_OPEN → CLOSED state machine using an
injected fake clock so tests are deterministic and millisecond-fast.
"""

from __future__ import annotations

import pytest

from congine_core.infrastructure.circuit_breaker import CircuitBreaker


class FakeClock:
    """Monotonic clock with explicit ticks. Replaces :func:`time.monotonic`."""

    def __init__(self, t: float = 0.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


def _breaker(
    threshold: int = 3, cooldown: float = 5.0
) -> tuple[CircuitBreaker, FakeClock]:
    clock = FakeClock()
    return CircuitBreaker(
        failure_threshold=threshold,
        cooldown_seconds=cooldown,
        clock=clock,
    ), clock


# --- Construction --------------------------------------------------------- #


def test_rejects_non_positive_threshold() -> None:
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=0, cooldown_seconds=1.0)
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=-1, cooldown_seconds=1.0)


def test_rejects_negative_cooldown() -> None:
    with pytest.raises(ValueError):
        CircuitBreaker(failure_threshold=1, cooldown_seconds=-1.0)


# --- CLOSED → OPEN -------------------------------------------------------- #


def test_starts_closed_and_allows() -> None:
    breaker, _ = _breaker()
    assert breaker.state == "CLOSED"
    assert breaker.allow() is True


def test_trips_open_after_threshold_consecutive_failures() -> None:
    breaker, _ = _breaker(threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "CLOSED"
    assert breaker.allow() is True
    breaker.record_failure()
    assert breaker.state == "OPEN"
    assert breaker.allow() is False


def test_success_resets_consecutive_failure_counter() -> None:
    breaker, _ = _breaker(threshold=3)
    breaker.record_failure()
    breaker.record_failure()
    breaker.record_success()
    # Counter cleared; needs 3 more failures to trip
    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "CLOSED"


# --- OPEN → HALF_OPEN ----------------------------------------------------- #


def test_open_does_not_transition_before_cooldown() -> None:
    breaker, clock = _breaker(threshold=1, cooldown=5.0)
    breaker.record_failure()
    assert breaker.state == "OPEN"
    clock.advance(4.999)
    assert breaker.allow() is False
    assert breaker.state == "OPEN"


def test_open_transitions_to_half_open_after_cooldown() -> None:
    breaker, clock = _breaker(threshold=1, cooldown=5.0)
    breaker.record_failure()
    clock.advance(5.0)
    assert breaker.allow() is True
    assert breaker.state == "HALF_OPEN"


# --- HALF_OPEN behaviour -------------------------------------------------- #


def test_half_open_probe_success_closes_circuit() -> None:
    breaker, clock = _breaker(threshold=1, cooldown=5.0)
    breaker.record_failure()
    clock.advance(5.0)
    breaker.allow()  # transitions to HALF_OPEN
    breaker.record_success()
    assert breaker.state == "CLOSED"
    assert breaker.allow() is True


def test_half_open_probe_failure_reopens_circuit() -> None:
    breaker, clock = _breaker(threshold=1, cooldown=5.0)
    breaker.record_failure()
    clock.advance(5.0)
    breaker.allow()  # transitions to HALF_OPEN
    breaker.record_failure()
    assert breaker.state == "OPEN"
    # And the cooldown restarts from this new opened_at:
    clock.advance(4.999)
    assert breaker.allow() is False


def test_half_open_allows_only_single_probe() -> None:
    breaker, clock = _breaker(threshold=1, cooldown=5.0)
    breaker.record_failure()
    clock.advance(5.0)
    assert breaker.allow() is True
    assert breaker.allow() is False
    breaker.record_success()
    assert breaker.allow() is True


def test_state_property_triggers_half_open_transition() -> None:
    """Reading `state` is coherent with `allow` — it also advances the FSM."""
    breaker, clock = _breaker(threshold=1, cooldown=5.0)
    breaker.record_failure()
    clock.advance(5.0)
    # Just reading state (without calling allow) should still transition.
    assert breaker.state == "HALF_OPEN"
