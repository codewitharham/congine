"""Adversarial tests for global input bounds (FIX-06)."""

from __future__ import annotations

from congine_core.config import FailMode
from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase
from tests.conftest import FakeEventBus, FakeLogger, FakeSchemaStorage, ImmediateTimer
from congine_core.domain.validator import LocalValidator


def test_oversized_payload_rejected() -> None:
    storage = FakeSchemaStorage({"c1": {"type": "object", "properties": {}}})
    usecase = ValidateContractUseCase(
        schema_storage=storage,
        validator=LocalValidator(),
        event_bus=FakeEventBus(),
        logger=FakeLogger(),
        timer=ImmediateTimer(),
        fail_mode=FailMode.DEGRADE,
        max_payload_bytes=50,
    )
    result = usecase.execute(
        payload={"data": "x" * 100},
        contract_id="c1",
        contract_version="v1",
    )
    assert not result.is_pass()
    assert any(b.rule == "INPUT_BOUNDS" for b in result.breaches)
