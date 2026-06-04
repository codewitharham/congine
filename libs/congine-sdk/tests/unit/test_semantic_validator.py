"""Unit tests for
:mod:`congine_core.infrastructure.jsonschema_validator`.
"""

from __future__ import annotations

from congine_core.infrastructure.jsonschema_validator import (
    JsonSchemaSemanticValidator,
)

_SCHEMA = {
    "type": "object",
    "required": ["name", "age"],
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer", "minimum": 0},
        "address": {
            "type": "object",
            "required": ["zip"],
            "properties": {"zip": {"type": "string"}},
        },
    },
}


def test_valid_payload_has_no_breaches() -> None:
    sv = JsonSchemaSemanticValidator()
    assert sv.validate({"name": "x", "age": 3}, _SCHEMA) == []


def test_iter_errors_surfaces_multiple_violations() -> None:
    sv = JsonSchemaSemanticValidator()
    # Missing 'name', wrong type for 'age', and 'age' below minimum.
    breaches = sv.validate({"age": -5}, _SCHEMA)
    assert len(breaches) >= 2
    assert all(b.rule == "SEMANTIC_SCHEMA" for b in breaches)
    messages = " ".join(b.message or "" for b in breaches)
    assert "name" in messages  # missing required property reported


def test_missing_required_is_root_field() -> None:
    sv = JsonSchemaSemanticValidator()
    breaches = sv.validate({"name": "x"}, _SCHEMA)  # missing 'age'
    assert any(b.field == "<root>" for b in breaches)


def test_nested_violation_has_dotted_path() -> None:
    sv = JsonSchemaSemanticValidator()
    payload = {"name": "x", "age": 1, "address": {"zip": 123}}  # zip not a string
    breaches = sv.validate(payload, _SCHEMA)
    assert any(b.field == "address.zip" for b in breaches)


def test_invalid_schema_is_reported_not_raised() -> None:
    sv = JsonSchemaSemanticValidator()
    bad_schema = {"type": "not-a-real-type"}
    breaches = sv.validate({"a": 1}, bad_schema)
    assert len(breaches) == 1
    assert breaches[0].rule == "SEMANTIC_SCHEMA"
    assert breaches[0].field == "<schema>"


def test_type_violation_field_path() -> None:
    sv = JsonSchemaSemanticValidator()
    breaches = sv.validate({"name": 5, "age": 3}, _SCHEMA)
    assert any(b.field == "name" for b in breaches)


def test_format_assertions_enabled() -> None:
    # L1: `format` is enforced (off by default in jsonschema).
    sv = JsonSchemaSemanticValidator()
    schema = {
        "type": "object",
        "properties": {"email": {"type": "string", "format": "email"}},
    }
    assert sv.validate({"email": "a@b.com"}, schema) == []
    bad = sv.validate({"email": "not-an-email"}, schema)
    assert len(bad) == 1
    assert bad[0].field == "email"
