"""Adversarial tests for semantic validation bounds (FIX-03)."""

from __future__ import annotations

from congine_core.infrastructure.jsonschema_validator import JsonSchemaSemanticValidator


def test_format_checker_off_by_default() -> None:
    validator = JsonSchemaSemanticValidator()
    assert validator._format_checking is False


def test_iter_errors_capped() -> None:
    validator = JsonSchemaSemanticValidator(max_breaches=5)
    schema = {
        "type": "object",
        "properties": {f"f{i}": {"type": "string"} for i in range(20)},
        "required": [f"f{i}" for i in range(20)],
    }
    payload: dict = {}
    breaches = validator.validate(payload, schema)
    assert len(breaches) == 6  # 5 violations + SEMANTIC_TRUNCATED
    assert any(b.rule == "SEMANTIC_TRUNCATED" for b in breaches)


def test_oversized_schema_pattern_rejected() -> None:
    from congine_core.security_limits import MAX_PATTERN_LENGTH

    validator = JsonSchemaSemanticValidator()
    schema = {
        "type": "object",
        "properties": {
            "x": {"type": "string", "pattern": "a" * (MAX_PATTERN_LENGTH + 1)}
        },
    }
    breaches = validator.validate({"x": "a"}, schema)
    assert len(breaches) == 1
    assert "length budget" in (breaches[0].message or "")
