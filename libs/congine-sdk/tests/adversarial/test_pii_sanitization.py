"""Adversarial tests for PII sanitization in telemetry (FIX-04)."""

from __future__ import annotations

from congine_core.config import FailMode
from congine_core.domain.validator import LocalValidator
from congine_core.infrastructure.jsonschema_validator import JsonSchemaSemanticValidator
from congine_core.pii_sanitize import sanitize_breach_message
from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase
from tests.conftest import FakeEventBus, FakeLogger, FakeSchemaStorage, ImmediateTimer


def test_sanitize_strips_quoted_values() -> None:
    raw = "'secret@evil.com' is not of type 'string'"
    assert "secret@evil.com" not in sanitize_breach_message(raw)
    assert "<redacted>" in sanitize_breach_message(raw)


def test_telemetry_breach_details_sanitized() -> None:
    secret = "ssn-999-88-7777"
    schema = {
        "type": "object",
        "properties": {"email": {"type": "string", "format": "email"}},
    }
    storage = FakeSchemaStorage({"c1": schema})
    bus = FakeEventBus()
    usecase = ValidateContractUseCase(
        schema_storage=storage,
        validator=LocalValidator(),
        event_bus=bus,
        logger=FakeLogger(),
        timer=ImmediateTimer(),
        fail_mode=FailMode.DEGRADE,
    )
    usecase.execute(
        payload={"email": secret},
        contract_id="c1",
        contract_version="v1",
    )
    assert bus.published
    details = bus.published[0].breach_details
    serialized = str(details)
    assert secret not in serialized


def test_jsonschema_messages_sanitized() -> None:
    validator = JsonSchemaSemanticValidator(format_checking=True)
    schema = {
        "type": "object",
        "properties": {"name": {"type": "string", "minLength": 10}},
    }
    breaches = validator.validate({"name": "short"}, schema)
    assert breaches
    msg = breaches[0].message or ""
    assert "'short'" not in msg
    assert "<redacted>" in msg
