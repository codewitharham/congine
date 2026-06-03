"""Unit tests for :mod:`congine_core.domain.validator`."""

from __future__ import annotations

from congine_core.domain.validator import (
    IValidator,
    LocalValidator,
    RuleEngine,
)

# --------------------------------------------------------------------------- #
# RuleEngine — FIELD_PRESENCE
# --------------------------------------------------------------------------- #


def test_field_presence_pass() -> None:
    assert RuleEngine.FIELD_PRESENCE({"a": 1, "b": 2}, ["a", "b"]) == []


def test_field_presence_missing() -> None:
    breaches = RuleEngine.FIELD_PRESENCE({"a": 1}, ["a", "b"])
    assert len(breaches) == 1
    assert breaches[0].rule == "FIELD_PRESENCE"
    assert breaches[0].field == "b"


def test_field_presence_dot_notation() -> None:
    payload = {"user": {"profile": {"name": "x"}}}
    assert RuleEngine.FIELD_PRESENCE(payload, ["user.profile.name"]) == []
    missing = RuleEngine.FIELD_PRESENCE(payload, ["user.profile.age"])
    assert len(missing) == 1
    assert missing[0].field == "user.profile.age"


def test_field_presence_dot_notation_non_dict_intermediate() -> None:
    payload = {"user": "scalar"}
    breaches = RuleEngine.FIELD_PRESENCE(payload, ["user.profile.name"])
    assert len(breaches) == 1


def test_field_presence_none_value_counts_as_present() -> None:
    assert RuleEngine.FIELD_PRESENCE({"a": None}, ["a"]) == []


# --------------------------------------------------------------------------- #
# RuleEngine — TYPE_MATCH
# --------------------------------------------------------------------------- #


def test_type_match_pass() -> None:
    props = {"name": {"type": "string"}, "age": {"type": "integer"}}
    assert RuleEngine.TYPE_MATCH({"name": "x", "age": 3}, props) == []


def test_type_match_bool_is_not_integer() -> None:
    props = {"age": {"type": "integer"}}
    breaches = RuleEngine.TYPE_MATCH({"age": True}, props)
    assert len(breaches) == 1
    assert breaches[0].rule == "TYPE_MATCH"


def test_type_match_bool_is_not_number() -> None:
    props = {"v": {"type": "number"}}
    assert len(RuleEngine.TYPE_MATCH({"v": False}, props)) == 1


def test_type_match_int_satisfies_number() -> None:
    props = {"v": {"type": "number"}}
    assert RuleEngine.TYPE_MATCH({"v": 5}, props) == []


def test_type_match_float_not_integer() -> None:
    props = {"v": {"type": "integer"}}
    assert len(RuleEngine.TYPE_MATCH({"v": 1.5}, props)) == 1


def test_type_match_all_json_types() -> None:
    props = {
        "s": {"type": "string"},
        "n": {"type": "number"},
        "i": {"type": "integer"},
        "b": {"type": "boolean"},
        "o": {"type": "object"},
        "a": {"type": "array"},
    }
    payload = {"s": "x", "n": 1.0, "i": 2, "b": True, "o": {}, "a": []}
    assert RuleEngine.TYPE_MATCH(payload, props) == []


def test_type_match_skips_absent_and_none() -> None:
    props = {"x": {"type": "string"}}
    assert RuleEngine.TYPE_MATCH({}, props) == []
    assert RuleEngine.TYPE_MATCH({"x": None}, props) == []


def test_type_match_unknown_type_is_ignored() -> None:
    props = {"x": {"type": "weird"}}
    assert RuleEngine.TYPE_MATCH({"x": object()}, props) == []


# --------------------------------------------------------------------------- #
# RuleEngine — ENUM_VALUES
# --------------------------------------------------------------------------- #


def test_enum_values_pass_and_fail() -> None:
    enum_map = {"color": {"enum": ["red", "green"]}}
    assert RuleEngine.ENUM_VALUES({"color": "red"}, enum_map) == []
    bad = RuleEngine.ENUM_VALUES({"color": "blue"}, enum_map)
    assert len(bad) == 1
    assert bad[0].rule == "ENUM_VALUES"


def test_enum_values_absent_field_ok() -> None:
    assert RuleEngine.ENUM_VALUES({}, {"color": {"enum": ["red"]}}) == []


# --------------------------------------------------------------------------- #
# RuleEngine — RANGE_CHECK
# --------------------------------------------------------------------------- #


def test_range_check_within_bounds() -> None:
    rmap = {"score": {"min": 0, "max": 1}}
    assert RuleEngine.RANGE_CHECK({"score": 0.5}, rmap) == []


def test_range_check_below_min() -> None:
    bad = RuleEngine.RANGE_CHECK({"score": -1}, {"score": {"min": 0}})
    assert len(bad) == 1
    assert "below" in (bad[0].message or "")


def test_range_check_above_max() -> None:
    bad = RuleEngine.RANGE_CHECK({"score": 5}, {"score": {"max": 1}})
    assert len(bad) == 1
    assert "above" in (bad[0].message or "")


def test_range_check_minimum_maximum_aliases() -> None:
    rmap = {"v": {"minimum": 10, "maximum": 20}}
    assert RuleEngine.RANGE_CHECK({"v": 15}, rmap) == []
    assert len(RuleEngine.RANGE_CHECK({"v": 5}, rmap)) == 1


def test_range_check_ignores_non_numeric_and_bool() -> None:
    rmap = {"v": {"min": 0, "max": 1}}
    assert RuleEngine.RANGE_CHECK({"v": "str"}, rmap) == []
    assert RuleEngine.RANGE_CHECK({"v": True}, rmap) == []


# --------------------------------------------------------------------------- #
# RuleEngine — NULL_GUARD
# --------------------------------------------------------------------------- #


def test_null_guard_flags_none() -> None:
    bad = RuleEngine.NULL_GUARD({"x": None}, ["x"])
    assert len(bad) == 1
    assert bad[0].rule == "NULL_GUARD"


def test_null_guard_passes_non_none_and_absent() -> None:
    assert RuleEngine.NULL_GUARD({"x": 1}, ["x"]) == []
    assert RuleEngine.NULL_GUARD({}, ["x"]) == []


# --------------------------------------------------------------------------- #
# RuleEngine — REGEX_PATTERN
# --------------------------------------------------------------------------- #


def test_regex_pattern_fullmatch_required() -> None:
    pmap = {"id": {"pattern": r"[a-z]+"}}
    assert RuleEngine.REGEX_PATTERN({"id": "abc"}, pmap) == []
    # Partial match must fail under fullmatch semantics.
    bad = RuleEngine.REGEX_PATTERN({"id": "abc123"}, pmap)
    assert len(bad) == 1
    assert bad[0].rule == "REGEX_PATTERN"


def test_regex_pattern_skips_non_string() -> None:
    assert RuleEngine.REGEX_PATTERN({"id": 5}, {"id": {"pattern": r"\d+"}}) == []


# --------------------------------------------------------------------------- #
# LocalValidator
# --------------------------------------------------------------------------- #


def _schema() -> dict:
    return {
        "required": ["score", "label"],
        "null_forbidden": ["score"],
        "properties": {
            "score": {"type": "number", "min": 0, "max": 1},
            "label": {"type": "string", "enum": ["pos", "neg"]},
            "code": {"type": "string", "pattern": r"[A-Z]{3}"},
        },
    }


def test_local_validator_is_ivalidator() -> None:
    assert isinstance(LocalValidator(), IValidator)


def test_local_validator_pass() -> None:
    payload = {"score": 0.8, "label": "pos", "code": "ABC"}
    result = LocalValidator().validate(payload, _schema())
    assert result.is_pass()
    assert result.breaches == ()
    assert result.duration_ms >= 0.0


def test_local_validator_collects_multiple_breaches() -> None:
    payload = {"score": 5, "label": "maybe", "code": "abc"}
    result = LocalValidator().validate(payload, _schema())
    assert not result.is_pass()
    rules = {b.rule for b in result.breaches}
    assert "RANGE_CHECK" in rules
    assert "ENUM_VALUES" in rules
    assert "REGEX_PATTERN" in rules


def test_local_validator_non_dict_root_breach() -> None:
    result = LocalValidator().validate(["not", "a", "dict"], _schema())
    assert not result.is_pass()
    assert len(result.breaches) == 1
    assert result.breaches[0].field == "<root>"
    assert result.breaches[0].rule == "TYPE_MATCH"


def test_local_validator_custom_rule_subset() -> None:
    # Only run NULL_GUARD — a range violation must NOT be reported.
    validator = LocalValidator(rules=[("NULL_GUARD", RuleEngine.NULL_GUARD)])
    schema = {"null_forbidden": ["score"], "properties": {}}
    result = validator.validate({"score": 999}, schema)
    assert result.is_pass()


def test_local_validator_missing_required_fails() -> None:
    result = LocalValidator().validate({"score": 0.5}, _schema())
    assert not result.is_pass()
    assert any(b.rule == "FIELD_PRESENCE" for b in result.breaches)


def test_local_validator_null_forbidden() -> None:
    payload = {"score": None, "label": "pos"}
    result = LocalValidator().validate(payload, _schema())
    assert any(b.rule == "NULL_GUARD" for b in result.breaches)
