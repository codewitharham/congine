"""Tests for the contract-admission boundary (audit P0-03 / P0-04).

Admission decides whether a contract may become **active policy**. Everything
here protects one property:

    A contract whose meaning CONGINE cannot determine never reaches the cache.

The fixtures below are the shapes that used to load happily and then enforce
nothing — an unknown type name, a union containing one, a dotted property key, a
keyword no evaluator runs, a schema that is not even a mapping.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from congine_core.config import ContractAdmissionMode
from congine_core.domain.contract_admission import (
    ContractAdmissionCode,
    ContractAdmissionLevel,
    admit_contract,
)
from congine_core.domain.schema_vocabulary import (
    NATIVE_ENFORCED_KEYWORDS,
    SEMANTIC_ENFORCED_KEYWORDS,
)

NATIVE = NATIVE_ENFORCED_KEYWORDS
SEMANTIC = NATIVE_ENFORCED_KEYWORDS | SEMANTIC_ENFORCED_KEYWORDS

STRICT = ContractAdmissionMode.STRICT
WARN = ContractAdmissionMode.WARN


def _admit(schema, *, mode=STRICT, keywords=NATIVE):
    return admit_contract(schema, mode=mode, enforced_keywords=keywords)


# --------------------------------------------------------------------------- #
# Valid contracts
# --------------------------------------------------------------------------- #
def test_simple_valid_contract_is_admitted() -> None:
    result = _admit(
        {
            "type": "object",
            "required": ["label"],
            "properties": {"label": {"type": "string", "enum": ["a", "b"]}},
        }
    )
    assert result.admitted
    assert result.issues == ()


def test_string_null_union_is_admitted() -> None:
    """The idiomatic nullable spelling is first-class, not merely tolerated."""
    result = _admit(
        {"type": "object", "properties": {"a": {"type": ["string", "null"]}}}
    )
    assert result.admitted


def test_legacy_null_forbidden_is_admitted() -> None:
    """A CONGINE extension that the rule engine genuinely enforces stays valid."""
    schema = {
        "type": "object",
        "null_forbidden": ["a"],
        "properties": {"a": {"type": "string"}},
    }
    assert _admit(schema).admitted
    assert _admit(schema, mode=WARN).admitted


def test_warn_mode_adds_a_migration_advisory_for_legacy_syntax() -> None:
    schema = {"type": "object", "null_forbidden": ["a"], "properties": {}}

    strict = _admit(schema, mode=STRICT)
    warn = _admit(schema, mode=WARN)

    assert strict.admitted and strict.issues == ()
    assert warn.admitted  # advisory only, never blocking
    assert [i.code for i in warn.warnings] == [ContractAdmissionCode.LEGACY_CONSTRUCT]
    assert warn.warnings[0].level is ContractAdmissionLevel.WARNING


def test_dotted_path_in_required_is_still_admitted() -> None:
    """``required`` genuinely walks dotted paths, so it stays valid.

    Only *property* keys are ambiguous. Rejecting dotted entries in ``required``
    would break working, intentional nested-presence checks.
    """
    assert _admit(
        {"type": "object", "required": ["user.email"], "properties": {}}
    ).admitted


# --------------------------------------------------------------------------- #
# Invalid contracts — refused in BOTH modes
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "name,schema,code",
    [
        (
            "unknown scalar type",
            {"type": "object", "properties": {"a": {"type": "str"}}},
            ContractAdmissionCode.UNKNOWN_TYPE,
        ),
        (
            "union with unknown member",
            {"type": "object", "properties": {"a": {"type": ["string", "mystery"]}}},
            ContractAdmissionCode.UNKNOWN_TYPE,
        ),
        (
            "empty type union",
            {"type": "object", "properties": {"a": {"type": []}}},
            ContractAdmissionCode.EMPTY_TYPE_UNION,
        ),
        (
            "uncompilable regex",
            {"type": "object", "properties": {"a": {"pattern": "(unclosed"}}},
            ContractAdmissionCode.INVALID_PATTERN,
        ),
        (
            "backreference regex (RE2 cannot compile)",
            {"type": "object", "properties": {"a": {"pattern": r"(a)\1"}}},
            ContractAdmissionCode.INVALID_PATTERN,
        ),
        (
            "over-long regex",
            {"type": "object", "properties": {"a": {"pattern": "a" * 1001}}},
            ContractAdmissionCode.INVALID_PATTERN,
        ),
        (
            "dotted property key",
            {"type": "object", "properties": {"user.email": {"type": "string"}}},
            ContractAdmissionCode.AMBIGUOUS_PROPERTY_PATH,
        ),
        (
            "unenforced keyword",
            {"type": "object", "properties": {"a": {"minLength": 10}}},
            ContractAdmissionCode.UNSUPPORTED_KEYWORD,
        ),
        (
            "non-mapping root",
            "i-am-not-a-mapping",
            ContractAdmissionCode.INVALID_STRUCTURE,
        ),
        (
            "properties is a list",
            {"type": "object", "properties": ["nope"]},
            ContractAdmissionCode.INVALID_STRUCTURE,
        ),
        (
            "required is a bare string",
            {"type": "object", "required": "email", "properties": {}},
            ContractAdmissionCode.INVALID_STRUCTURE,
        ),
        (
            "bare-string property spec",
            {"type": "object", "properties": {"a": "string"}},
            ContractAdmissionCode.INVALID_STRUCTURE,
        ),
        (
            "enum is a bare string",
            {"type": "object", "properties": {"a": {"enum": "abc"}}},
            ContractAdmissionCode.INVALID_STRUCTURE,
        ),
        (
            "non-numeric range operand",
            {"type": "object", "properties": {"a": {"min": "0"}}},
            ContractAdmissionCode.INVALID_STRUCTURE,
        ),
        (
            "pattern is not a string",
            {"type": "object", "properties": {"a": {"pattern": 42}}},
            ContractAdmissionCode.INVALID_STRUCTURE,
        ),
    ],
)
def test_invalid_contracts_are_refused_in_both_modes(name, schema, code) -> None:
    """**The migration-safety invariant.**

    ``WARN`` relaxes compatibility, never correctness. If it could rescue any of
    these, a contract whose meaning CONGINE cannot determine would be cached and
    every validation against it would report ``is_enforced() is True`` — exactly
    the false safety admission exists to remove.
    """
    for mode in (STRICT, WARN):
        result = _admit(schema, mode=mode)
        assert not result.admitted, f"{name} was admitted in {mode}"
        assert code in {i.code for i in result.errors}, f"{name} missing {code}"


def test_required_bare_string_names_the_character_iteration_trap() -> None:
    """The message must explain *why*, since the failure mode is non-obvious."""
    result = _admit({"type": "object", "required": "email", "properties": {}})
    assert "character-by-character" in result.errors[0].message


# --------------------------------------------------------------------------- #
# Enforcement depends on the ACTIVE evaluator set, not a boolean
# --------------------------------------------------------------------------- #
def test_semantic_only_keyword_flips_on_evaluator_capability() -> None:
    """``minLength`` is refused natively and admitted when something enforces it.

    This is why admission takes a capability set rather than an
    "is semantic validation on?" flag: the real question is per-keyword.
    """
    schema = {
        "type": "object",
        "properties": {"a": {"type": "string", "minLength": 10}},
    }

    assert not _admit(schema, keywords=NATIVE).admitted
    assert _admit(schema, keywords=SEMANTIC).admitted
    # ...and it stays refused under WARN when nothing will enforce it.
    assert not _admit(schema, mode=WARN, keywords=NATIVE).admitted


def test_format_is_not_assumed_enforced() -> None:
    """``format`` needs a second flag, so the base semantic set must exclude it."""
    assert "format" not in SEMANTIC_ENFORCED_KEYWORDS
    schema = {"type": "object", "properties": {"a": {"format": "email"}}}
    assert not _admit(schema, keywords=SEMANTIC).admitted
    assert _admit(schema, keywords=SEMANTIC | {"format"}).admitted


# --------------------------------------------------------------------------- #
# Robustness and machine-facing contract
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "schema", [None, 42, [], "", {"properties": None}, {"required": [1, 2]}]
)
def test_admission_never_raises(schema) -> None:
    """A contract too broken to inspect is reported, never thrown."""
    result = _admit(schema)
    assert isinstance(result.admitted, bool)


def test_issue_codes_serialize_as_wire_values() -> None:
    """Codes cross into logs, and later MCP/evidence. They must not leak class names."""
    import json

    code = ContractAdmissionCode.UNKNOWN_TYPE
    assert json.dumps({"code": code}) == '{"code": "unknown_type"}'
    assert json.dumps({"code": code}, default=str) == '{"code": "unknown_type"}'
    assert f"{code}" == "unknown_type"
    assert str(code) == "unknown_type"
    assert code == "unknown_type"


def test_admission_mode_serializes_as_wire_value() -> None:
    assert f"{ContractAdmissionMode.STRICT}" == "strict"
    assert str(ContractAdmissionMode.WARN) == "warn"


def test_result_exposes_sorted_distinct_codes() -> None:
    result = _admit(
        {
            "type": "object",
            "properties": {
                "a": {"type": "nope"},
                "b.c": {"type": "string"},
            },
        }
    )
    assert result.codes() == ("ambiguous_property_path", "unknown_type")


# --------------------------------------------------------------------------- #
# Architectural guard: no production writer may bypass admission
# --------------------------------------------------------------------------- #
def test_every_schema_writer_runs_admission() -> None:
    """Any module writing into ``ISchemaStorage`` must admit the contract first.

    Admission is only as strong as its narrowest bypass. Every entry point on the
    roadmap — MCP server, CLI, direct injection — adds another writer, and one
    that forgets silently reopens the false-safety hole this boundary closes.

    If this fails on code you just wrote: call ``admit_contract`` and refuse to
    ``put`` a contract it did not admit.
    """
    src_root = Path(__file__).resolve().parents[2] / "src" / "congine_core"
    assert src_root.is_dir(), src_root

    offenders: list[str] = []
    for path in sorted(src_root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        # A schema write is a 3-positional-arg `.put(id, schema, ttl)` call —
        # the ISchemaStorage.put signature. dict/set .put() and queue
        # .put_nowait() do not match.
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
        if "admit_contract" in source or "_admit" in source:
            continue
        offenders.append(
            f"{path.relative_to(src_root)}:{sorted({n.lineno for n in writes})}"
        )

    assert not offenders, (
        "These modules write schemas into ISchemaStorage without running contract "
        "admission (audit P0-03/P0-04): " + "; ".join(offenders)
    )


def test_the_admission_guard_would_catch_a_new_bypassing_loader() -> None:
    """Guard the guard: a broken detector would be enforcement theatre."""
    bypassing_loader = (
        "def load(storage, contracts, ttl):\n"
        "    for c in contracts:\n"
        "        storage.put(c['id'], c['schema'], ttl)\n"
    )
    writes = [
        node
        for node in ast.walk(ast.parse(bypassing_loader))
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "put"
        and len(node.args) == 3
    ]
    assert len(writes) == 1
    assert "admit_contract" not in bypassing_loader
