"""Unit tests for the pure L2 schema-vocabulary scanner (audit P0-2).

Covers ``find_unenforced_keywords`` in isolation (no use case, no I/O) plus the
anti-drift guards that keep the mirrored vocabulary honest against the real rule
engine.
"""

from __future__ import annotations

from congine_core.domain.schema_vocabulary import (
    ENFORCED_PROPERTY_KEYWORDS,
    RECOGNISED_TYPE_NAMES,
    find_unenforced_keywords,
)


def test_flags_property_minlength() -> None:
    schema = {"properties": {"summary": {"type": "string", "minLength": 10}}}
    assert find_unenforced_keywords(schema) == ["summary.minLength"]


def test_clean_schema_has_no_findings() -> None:
    schema = {
        "type": "object",
        "required": ["label"],
        "null_forbidden": ["label"],
        "description": "documented, no enforcement intent",
        "properties": {
            "label": {"type": "string", "enum": ["a", "b"], "pattern": "^.+$"},
            "score": {"type": "number", "minimum": 0, "maximum": 1, "min": 0, "max": 1},
        },
    }
    assert find_unenforced_keywords(schema) == []


def test_top_level_unenforced_keyword_flagged() -> None:
    schema = {"type": "object", "required": ["a"], "additionalProperties": False}
    assert find_unenforced_keywords(schema) == ["<root>.additionalProperties"]


def test_top_level_non_object_type_flagged() -> None:
    assert find_unenforced_keywords({"type": "string"}) == ["<root>.type"]


def test_metadata_keywords_never_flagged() -> None:
    schema = {
        "title": "t",
        "description": "d",
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "properties": {"a": {"type": "string", "description": "x", "default": "y"}},
    }
    assert find_unenforced_keywords(schema) == []


def test_does_not_recurse_into_nested_schemas() -> None:
    # A nested object/array is reported once at the field; its interior
    # (zip.minLength / item patterns) must NOT be enumerated.
    schema = {
        "properties": {
            "addr": {"type": "object", "properties": {"zip": {"minLength": 5}}},
            "tags": {"type": "array", "items": {"type": "string", "maxLength": 3}},
        }
    }
    assert find_unenforced_keywords(schema) == ["addr.properties", "tags.items"]


def test_well_formed_union_and_null_types_are_enforced() -> None:
    """Since audit Q2 both are first-class, so neither is reported.

    ``"null"`` is now in ``_JSON_TYPE_MAP`` and TYPE_MATCH evaluates a union
    member-wise, so ``["string", "null"]`` — the idiomatic JSON Schema spelling
    of a nullable field — is genuinely enforced. It previously raised
    ``TypeError`` inside the rule engine and was reported here as unenforceable.
    """
    assert find_unenforced_keywords({"properties": {"a": {"type": "null"}}}) == []
    assert (
        find_unenforced_keywords({"properties": {"b": {"type": ["string", "null"]}}})
        == []
    )


def test_unenforceable_types_still_flagged() -> None:
    """A type the rule engine cannot honour is still surfaced at load."""
    # Unrecognised single name.
    assert find_unenforced_keywords({"properties": {"a": {"type": "frobnicate"}}}) == [
        "a.type"
    ]
    # Union containing an unrecognised name: matches everything, enforces nothing.
    assert find_unenforced_keywords(
        {"properties": {"b": {"type": ["string", "frobnicate"]}}}
    ) == ["b.type"]
    # Empty union declares nothing.
    assert find_unenforced_keywords({"properties": {"c": {"type": []}}}) == ["c.type"]


def test_malformed_inputs_never_raise() -> None:
    assert find_unenforced_keywords("not-a-dict") == []  # type: ignore[arg-type]
    assert find_unenforced_keywords({"properties": ["not", "a", "dict"]}) == []
    assert find_unenforced_keywords({"properties": {"f": "bare-string-spec"}}) == []
    assert find_unenforced_keywords({"properties": {"f": None}}) == []


def test_output_is_sorted_and_deduplicated() -> None:
    schema = {
        "properties": {
            "b": {"maxLength": 1, "format": "email"},
            "a": {"minLength": 1},
        }
    }
    result = find_unenforced_keywords(schema)
    assert result == sorted(result)
    assert result == ["a.minLength", "b.format", "b.maxLength"]


def test_output_is_capped() -> None:
    schema = {f"customKeyword{i:03d}": True for i in range(30)}
    result = find_unenforced_keywords(schema)
    assert len(result) == 21  # 20 paths + a truncation marker
    assert result[-1].startswith("... (+")


# --------------------------------------------------------------------------- #
# Anti-drift guards: the mirrored vocabulary must not silently lie after a rule
# is added to (or a type removed from) the real engine.
# --------------------------------------------------------------------------- #
_PROPERTY_KEYWORD_TO_RULE = {
    "type": "TYPE_MATCH",
    "enum": "ENUM_VALUES",
    "min": "RANGE_CHECK",
    "max": "RANGE_CHECK",
    "minimum": "RANGE_CHECK",
    "maximum": "RANGE_CHECK",
    "pattern": "REGEX_PATTERN",
}


def test_vocabulary_matches_rule_engine() -> None:
    """Every ENFORCED_PROPERTY_KEYWORD must actually be selected by the rule it
    claims — otherwise the vocabulary is lying and would suppress a real warning."""
    from congine_core.domain.validator import LocalValidator

    sample_value = {"type": "string", "enum": [1], "pattern": "x"}
    for keyword in ENFORCED_PROPERTY_KEYWORDS:
        rule = _PROPERTY_KEYWORD_TO_RULE[keyword]  # KeyError here = drift to fix
        value = sample_value.get(keyword, 5)
        schema = {"properties": {"f": {keyword: value}}}
        selected = LocalValidator._extract_params(rule, schema)
        assert "f" in selected, f"{keyword!r} not selected by {rule}"


def test_recognised_types_mirror_json_type_map() -> None:
    from congine_core.domain.validator import _JSON_TYPE_MAP

    assert RECOGNISED_TYPE_NAMES == frozenset(_JSON_TYPE_MAP)


# --------------------------------------------------------------------------- #
# Q4: the scan is a required step for EVERY schema writer, not just one path
# --------------------------------------------------------------------------- #


def test_every_schema_writer_scans_for_unenforced_keywords() -> None:
    """Any module that writes a schema into ``ISchemaStorage`` must run the scan.

    The P0-2 warning is the only signal a user gets that part of their contract
    is decorative, and it originally fired on exactly one path (the cache-prime
    path in ``SyncContractsUseCase``). Every entry point on the roadmap — MCP
    server, CLI, direct injection — adds another writer, and each one that
    forgets silently reopens the false-safety foot-gun (audit Q4).

    This walks the real source tree with ``ast`` and fails when a new
    ``*.put(contract_id, schema, ...)`` call site appears in a module that does
    not reference the scan. If this fails on code you just wrote: call
    ``find_unenforced_keywords`` on the schema and log what it returns.
    """
    import ast
    from pathlib import Path

    src_root = Path(__file__).resolve().parents[2] / "src" / "congine_core"
    assert src_root.is_dir(), src_root

    offenders: list[str] = []
    for path in sorted(src_root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # A schema write is a 3-positional-argument `.put(id, schema, ttl)` call
        # — the ISchemaStorage.put signature. Plain dict/set .put() calls and
        # queue .put_nowait() do not match.
        writes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "put"
            and len(node.args) == 3
        ]
        if not writes:
            continue
        if (
            "find_unenforced_keywords" in source
            or "_warn_unenforced_keywords" in source
        ):
            continue
        lines = sorted({node.lineno for node in writes})
        offenders.append(f"{path.relative_to(src_root)}:{lines}")

    assert not offenders, (
        "These modules write schemas into ISchemaStorage without running the "
        "unenforced-keyword scan (audit Q4): " + "; ".join(offenders)
    )


def test_the_writer_guard_would_catch_a_new_unscanned_loader() -> None:
    """Guard the guard: the detector must actually fire on an unscanned writer.

    Without this, a broken detector would pass silently forever and the
    convention above would be enforcement theatre.
    """
    import ast

    unscanned_loader = (
        "def load(storage, contracts, ttl):\n"
        "    for c in contracts:\n"
        "        storage.put(c['id'], c['schema'], ttl)\n"
    )
    tree = ast.parse(unscanned_loader)
    writes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "put"
        and len(node.args) == 3
    ]
    assert len(writes) == 1
    assert "find_unenforced_keywords" not in unscanned_loader
