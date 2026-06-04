"""Unit tests for :mod:`congine_core.infrastructure.logger`."""

from __future__ import annotations

import json

import pytest

from congine_core.infrastructure.logger import StructuredLogger


def _emit(capsys: pytest.CaptureFixture[str], level: str, **kw: object) -> dict:
    logger = StructuredLogger("congine-test", level="DEBUG")
    getattr(logger, level)("hello", **kw)
    line = capsys.readouterr().out.strip()
    return json.loads(line)


def test_info_emits_single_json_object(capsys: pytest.CaptureFixture[str]) -> None:
    record = _emit(capsys, "info", contract_id="c1")
    assert record["level"] == "INFO"
    assert record["logger"] == "congine-test"
    assert record["message"] == "hello"
    assert record["contract_id"] == "c1"
    assert "timestamp" in record


@pytest.mark.parametrize(
    "method,expected",
    [
        ("info", "INFO"),
        ("error", "ERROR"),
        ("warning", "WARNING"),
        ("debug", "DEBUG"),
    ],
)
def test_all_levels(
    capsys: pytest.CaptureFixture[str], method: str, expected: str
) -> None:
    assert _emit(capsys, method)["level"] == expected


def test_non_serializable_extra_is_coerced(
    capsys: pytest.CaptureFixture[str],
) -> None:
    record = _emit(capsys, "info", obj=object())
    # default=str keeps logging from raising; value becomes a string.
    assert isinstance(record["obj"], str)


def test_each_call_is_one_line(capsys: pytest.CaptureFixture[str]) -> None:
    logger = StructuredLogger()
    logger.info("a")
    logger.error("b")
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 2
    assert all(json.loads(line) for line in out)
