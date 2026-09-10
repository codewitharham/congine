"""Unit tests for :mod:`congine_core.usecases.validate_contract_usecase`."""

from __future__ import annotations

from typing import Any

import pytest

from congine_core.config import FailMode
from congine_core.domain.validator import LocalValidator
from congine_core.exceptions import (
    CongineContractNotFoundError,
    CongineValidationError,
)
from congine_core.usecases.validate_contract_usecase import (
    ValidateContractUseCase,
)
from tests.conftest import (
    FakeEventBus,
    FakeLogger,
    FakeSchemaStorage,
    ImmediateTimer,
)

_SCHEMA = {
    "required": ["score"],
    "properties": {"score": {"type": "number", "min": 0, "max": 1}},
}


class _TimeoutTimer(ImmediateTimer):
    def run_with_timeout(self, func: Any, timeout_ms: int) -> Any:
        raise TimeoutError("too slow")


class _ErrorTimer(ImmediateTimer):
    def run_with_timeout(self, func: Any, timeout_ms: int) -> Any:
        raise RuntimeError("boom")


def _usecase(
    storage: FakeSchemaStorage,
    bus: FakeEventBus,
    logger: FakeLogger,
    *,
    timer: Any = None,
    fail_mode: FailMode = FailMode.DEGRADE,
) -> ValidateContractUseCase:
    return ValidateContractUseCase(
        schema_storage=storage,
        validator=LocalValidator(),
        event_bus=bus,
        logger=logger,
        timer=timer or ImmediateTimer(),
        timeout_ms=50,
        fail_mode=fail_mode,
    )


def test_schema_miss_raises_typed_error() -> None:
    storage, bus, logger = FakeSchemaStorage(), FakeEventBus(), FakeLogger()
    uc = _usecase(storage, bus, logger)
    with pytest.raises(CongineContractNotFoundError):
        uc.execute({"score": 0.5}, "absent", "1.0")


def test_happy_path_passes_and_publishes() -> None:
    storage = FakeSchemaStorage({"c": _SCHEMA})
    bus, logger = FakeEventBus(), FakeLogger()
    uc = _usecase(storage, bus, logger)
    result = uc.execute({"score": 0.5}, "c", "1.0")
    assert result.is_pass()
    assert len(bus.published) == 1
    assert bus.published[0].contract_id == "c"
    assert bus.published[0].status == "pass"


def test_degrade_returns_fail_and_publishes() -> None:
    storage = FakeSchemaStorage({"c": _SCHEMA})
    bus, logger = FakeEventBus(), FakeLogger()
    uc = _usecase(storage, bus, logger, fail_mode=FailMode.DEGRADE)
    result = uc.execute({"score": 9}, "c", "1.0")  # out of range
    assert not result.is_pass()
    assert len(bus.published) == 1
    assert "WARNING" in logger.levels()


def test_strict_raises_but_publishes_first() -> None:
    storage = FakeSchemaStorage({"c": _SCHEMA})
    bus, logger = FakeEventBus(), FakeLogger()
    uc = _usecase(storage, bus, logger, fail_mode=FailMode.STRICT)
    with pytest.raises(CongineValidationError):
        uc.execute({"score": 9}, "c", "1.0")
    # Telemetry must be published before the strict raise.
    assert len(bus.published) == 1
    assert bus.published[0].status == "fail"


def test_silent_suppresses_logging() -> None:
    storage = FakeSchemaStorage({"c": _SCHEMA})
    bus, logger = FakeEventBus(), FakeLogger()
    uc = _usecase(storage, bus, logger, fail_mode=FailMode.SILENT)
    result = uc.execute({"score": 9}, "c", "1.0")
    assert not result.is_pass()
    assert "WARNING" not in logger.levels()
    assert "ERROR" not in logger.levels()


def test_timeout_degrades() -> None:
    storage = FakeSchemaStorage({"c": _SCHEMA})
    bus, logger = FakeEventBus(), FakeLogger()
    uc = _usecase(storage, bus, logger, timer=_TimeoutTimer())
    result = uc.execute({"score": 0.5}, "c", "1.0")
    assert result.degraded is True
    assert not result.is_pass()
    assert "WARNING" in logger.levels()  # the timeout warning


def test_generic_error_degrades() -> None:
    storage = FakeSchemaStorage({"c": _SCHEMA})
    bus, logger = FakeEventBus(), FakeLogger()
    uc = _usecase(storage, bus, logger, timer=_ErrorTimer())
    result = uc.execute({"score": 0.5}, "c", "1.0")
    assert result.degraded is True
    assert "ERROR" in logger.levels()


def test_breach_details_serialized_into_event() -> None:
    storage = FakeSchemaStorage({"c": _SCHEMA})
    bus, logger = FakeEventBus(), FakeLogger()
    uc = _usecase(storage, bus, logger, fail_mode=FailMode.SILENT)
    uc.execute({"score": 9}, "c", "1.0")
    event = bus.published[0]
    assert event.breach_details
    assert {"rule", "field", "message"} <= set(event.breach_details[0])
