"""Unit tests for
:class:`congine_core.domain.validator.CompositeValidator`.
"""

from __future__ import annotations

from typing import List

from congine_core.domain.models import BreachDetail
from congine_core.domain.validator import (
    CompositeValidator,
    IValidator,
    LocalValidator,
)
from congine_core.infrastructure.jsonschema_validator import (
    JsonSchemaSemanticValidator,
)


class _FakeSemantic:
    """ISemanticValidator double returning a fixed breach list."""

    def __init__(self, breaches: List[BreachDetail]) -> None:
        self._breaches = breaches

    def validate(self, payload: dict, schema: dict) -> List[BreachDetail]:
        return list(self._breaches)


def test_is_ivalidator() -> None:
    comp = CompositeValidator(LocalValidator(), _FakeSemantic([]))
    assert isinstance(comp, IValidator)


def test_merges_rule_and_semantic_breaches() -> None:
    rule = LocalValidator()
    semantic = _FakeSemantic(
        [BreachDetail(rule="SEMANTIC_SCHEMA", field="x", message="bad")]
    )
    comp = CompositeValidator(rule, semantic)
    # Rule layer flags missing required 'score'; semantic adds its own breach.
    schema = {"required": ["score"], "properties": {}}
    result = comp.validate({}, schema)
    assert not result.is_pass()
    rules = {b.rule for b in result.breaches}
    assert "FIELD_PRESENCE" in rules
    assert "SEMANTIC_SCHEMA" in rules


def test_passes_only_when_both_pass() -> None:
    comp = CompositeValidator(LocalValidator(), _FakeSemantic([]))
    result = comp.validate({"score": 1}, {"properties": {}})
    assert result.is_pass()
    assert result.duration_ms >= 0.0


def test_fails_when_only_semantic_fails() -> None:
    semantic = _FakeSemantic([BreachDetail(rule="SEMANTIC_SCHEMA", field="<root>")])
    comp = CompositeValidator(LocalValidator(), semantic)
    result = comp.validate({}, {"properties": {}})  # rule layer is clean
    assert not result.is_pass()
    assert len(result.breaches) == 1


def test_degraded_propagates_from_rule_validator() -> None:
    class _Degraded:
        def validate(self, payload, schema):
            from congine_core.domain.models import ValidationResult

            return ValidationResult(status="fail", degraded=True)

    comp = CompositeValidator(_Degraded(), _FakeSemantic([]))
    result = comp.validate({}, {})
    assert result.degraded is True


def test_with_real_jsonschema_validator() -> None:
    comp = CompositeValidator(LocalValidator(), JsonSchemaSemanticValidator())
    schema = {
        "type": "object",
        "required": ["score"],
        "properties": {"score": {"type": "number"}},
    }
    assert comp.validate({"score": 0.5}, schema).is_pass()
    assert not comp.validate({"score": "nan"}, schema).is_pass()
