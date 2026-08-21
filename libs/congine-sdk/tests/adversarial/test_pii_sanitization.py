"""Adversarial tests for PII sanitization in telemetry (FIX-04)."""

from __future__ import annotations

import random
import re
import string

import pytest

from congine_core.config import FailMode
from congine_core.domain.validator import CompositeValidator, LocalValidator
from congine_core.infrastructure.jsonschema_validator import JsonSchemaSemanticValidator
from congine_core.pii_sanitize import sanitize_breach_message
from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase
from tests.conftest import FakeEventBus, FakeLogger, FakeSchemaStorage, ImmediateTimer


_LEGACY_SANITIZATION_RE = re.compile(r"(['\"])(.*?)\1|(\b\d{4,}\b)")


@pytest.mark.parametrize(
    "message",
    [
        "'secret@evil.com' is not of type 'string'",
        '"value" failed at record 12345',
        "minimum 1234 and code 999",
        "empty '' and another 'quoted value'",
        "short number 123 remains unchanged",
    ],
)
def test_re2_sanitizer_preserves_legacy_output_for_normal_inputs(
    message: str,
) -> None:
    expected = _LEGACY_SANITIZATION_RE.sub("'<redacted>'", message)
    assert sanitize_breach_message(message) == expected


def test_re2_sanitizer_matches_legacy_over_deterministic_10k_corpus() -> None:
    rng = random.Random(0xC0A61E)
    alphabet = string.ascii_letters + string.punctuation.replace("'", "").replace(
        '"', ""
    )

    for _ in range(10_000):
        parts: list[str] = []
        for _ in range(rng.randint(1, 8)):
            kind = rng.randrange(4)
            if kind == 0:
                value = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 32)))
                parts.append(f"'{value}'")
            elif kind == 1:
                value = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 32)))
                parts.append(f'"{value}"')
            elif kind == 2:
                parts.append(
                    "".join(
                        rng.choice(string.digits) for _ in range(rng.randint(4, 12))
                    )
                )
            else:
                parts.append(
                    "".join(rng.choice(string.ascii_letters) for _ in range(16))
                )
        message = " ".join(parts)
        expected = _LEGACY_SANITIZATION_RE.sub("'<redacted>'", message)
        assert sanitize_breach_message(message) == expected


def test_sanitize_strips_quoted_values() -> None:
    raw = "'secret@evil.com' is not of type 'string'"
    assert "secret@evil.com" not in sanitize_breach_message(raw)
    assert "<redacted>" in sanitize_breach_message(raw)


def test_sanitize_redacts_long_numeric_tokens() -> None:
    assert sanitize_breach_message("record 123456 failed") == (
        "record '<redacted>' failed"
    )


def test_sanitize_handles_adversarial_quote_runs() -> None:
    raw = ('"' * 100_000) + " account 123456 " + ("'" * 100_000)
    sanitized = sanitize_breach_message(raw)
    assert "123456" not in sanitized
    assert "<redacted>" in sanitized


def test_sanitize_handles_a_large_quoted_value() -> None:
    raw = '"' + ("s" * 1_000_000) + '" is invalid'
    assert sanitize_breach_message(raw) == "'<redacted>' is invalid"


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
        validator=CompositeValidator(
            LocalValidator(),
            JsonSchemaSemanticValidator(format_checking=True),
        ),
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
    assert details
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
