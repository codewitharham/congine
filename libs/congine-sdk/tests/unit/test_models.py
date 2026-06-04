"""Unit tests for :mod:`congine_core.domain.models`."""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone

import pytest

from congine_core.domain.models import (
    BreachDetail,
    TelemetryEvent,
    ValidationResult,
)


def test_breach_detail_frozen() -> None:
    b = BreachDetail(rule="TYPE_MATCH", field="score")
    assert b.message is None
    with pytest.raises(dataclasses.FrozenInstanceError):
        b.field = "other"  # type: ignore[misc]


def test_validation_result_defaults_and_is_pass() -> None:
    ok = ValidationResult(status="pass")
    assert ok.is_pass() is True
    assert ok.breaches == ()
    assert ok.duration_ms == 0.0
    assert ok.degraded is False

    bad = ValidationResult(status="fail", breaches=(BreachDetail("X", "y"),))
    assert bad.is_pass() is False


def test_validation_result_frozen_and_tuple() -> None:
    r = ValidationResult(status="pass")
    assert isinstance(r.breaches, tuple)
    with pytest.raises(dataclasses.FrozenInstanceError):
        r.status = "fail"  # type: ignore[misc]


def test_telemetry_event_post_init_defaults() -> None:
    ev = TelemetryEvent(
        contract_id="c",
        contract_version="1.0",
        status="pass",
        duration_ms=1.2,
    )
    assert ev.breach_details == []
    assert isinstance(ev.created_at, datetime)
    assert ev.created_at.tzinfo is timezone.utc


def test_telemetry_event_preserves_supplied_values() -> None:
    when = datetime(2026, 1, 1, tzinfo=timezone.utc)
    details = [{"rule": "NULL_GUARD", "field": "x", "message": None}]
    ev = TelemetryEvent(
        contract_id="c",
        contract_version="2",
        status="fail",
        duration_ms=3.0,
        breach_details=details,
        created_at=when,
    )
    assert ev.breach_details is details
    assert ev.created_at == when


def test_telemetry_event_is_frozen() -> None:
    ev = TelemetryEvent("c", "1", "pass", 0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        ev.status = "fail"  # frozen (L7): cannot race the drain worker
