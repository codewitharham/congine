"""End-to-end policy-truth gate for semantic validation (P1.5 Slice B).

This module asks the only question that actually matters for G12:

    **Does contract admission refuse everything the wired evaluator cannot
    enforce, and admit everything it can?**

It deliberately does *not* maintain an allowlist of "known untruthful" cases.
An allowlist would let a G12 violation sit in the corpus indefinitely while the
suite still reported success — which is the precise failure mode P1.5 exists to
remove. Every entry below is instead a defect that was measured in Slice A0 and
closed in Slice B; if one regresses, the gate fails.

Both directions are checked. Refusals alone could be satisfied by refusing
everything, so the admit set proves the safety fixes cost no legitimate
capability.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

#: ``(name, schema, why it is unenforceable)`` — admission must refuse each.
MUST_REFUSE: Tuple[Tuple[str, Dict[str, Any], str], ...] = (
    (
        "contentEncoding",
        {"type": "object", "properties": {"f": {"contentEncoding": "base64"}}},
        "annotation-only on every supported draft",
    ),
    (
        "contentMediaType",
        {
            "type": "object",
            "properties": {"f": {"contentMediaType": "application/json"}},
        },
        "annotation-only on every supported draft",
    ),
    (
        "external-http-ref",
        {"type": "object", "properties": {"f": {"$ref": "http://example.invalid/s"}}},
        "would fetch a remote document",
    ),
    (
        "external-file-ref",
        {"type": "object", "properties": {"f": {"$ref": "file:///etc/passwd"}}},
        "would read the filesystem",
    ),
    (
        "relative-external-ref",
        {"type": "object", "properties": {"f": {"$ref": "other.json#/x"}}},
        "resolves outside the contract",
    ),
    (
        "missing-local-ref",
        {"type": "object", "properties": {"f": {"$ref": "#/$defs/ABSENT"}}},
        "unresolvable at evaluation time",
    ),
    (
        "cyclic-local-ref",
        {
            "type": "object",
            "$defs": {"A": {"$ref": "#/$defs/A"}},
            "properties": {"f": {"$ref": "#/$defs/A"}},
        },
        "unsupported CONGINE subset; exhausts the stack",
    ),
    (
        "non-re2-pattern",
        {"type": "object", "properties": {"f": {"pattern": "(?<=a)b"}}},
        "RE2 cannot compile it, so it is unenforceable",
    ),
    (
        "non-re2-patternProperties-key",
        {"type": "object", "patternProperties": {"(?<=a)b": {"type": "number"}}},
        "pattern keys are regexes too",
    ),
    (
        "nested-non-re2-pattern",
        {
            "type": "object",
            "properties": {
                "o": {"type": "object", "properties": {"x": {"pattern": "(?<=a)b"}}}
            },
        },
        "regex checks must be recursive",
    ),
    (
        "format-without-assertion",
        {"type": "object", "properties": {"f": {"format": "email"}}},
        "format assertions are disabled",
    ),
)

#: ``(name, schema)`` — admission must admit each, proving the refusals above
#: are targeted rather than blanket.
MUST_ADMIT: Tuple[Tuple[str, Dict[str, Any]], ...] = (
    ("flat-semantic", {"type": "object", "properties": {"f": {"minLength": 2}}}),
    (
        "re2-safe-pattern",
        {"type": "object", "properties": {"f": {"pattern": "^[a-z]+$"}}},
    ),
    (
        "re2-patternProperties",
        {"type": "object", "patternProperties": {"^n_": {"type": "number"}}},
    ),
    (
        "valid-local-ref",
        {
            "type": "object",
            "$defs": {"S": {"type": "number"}},
            "properties": {"f": {"$ref": "#/$defs/S"}},
        },
    ),
)

#: ``(name, schema, draft that must refuse, draft that must admit)`` — the
#: dialect-blindness defect. A keyword the configured draft silently ignores
#: must be refused *on that draft* and admitted where it is genuinely enforced.
DIALECT_CASES: Tuple[Tuple[str, Dict[str, Any], str, str], ...] = (
    (
        "minContains",
        {
            "type": "object",
            "properties": {
                "f": {"type": "array", "contains": {"type": "number"}, "minContains": 2}
            },
        },
        "draft7",
        "draft202012",
    ),
    (
        "prefixItems",
        {
            "type": "object",
            "properties": {"f": {"type": "array", "prefixItems": [{"type": "number"}]}},
        },
        "draft201909",
        "draft202012",
    ),
    (
        "dependentRequired",
        {"type": "object", "dependentRequired": {"a": ["b"]}},
        "draft7",
        "draft202012",
    ),
)


def _admits(schema: Dict[str, Any], draft: str) -> bool:
    from congine_core import admit_contract
    from congine_core.domain.contract_admission import ContractAdmissionMode
    from congine_core.infrastructure.jsonschema_validator import (
        JsonSchemaSemanticValidator,
    )

    capability = JsonSchemaSemanticValidator(jsonschema_draft=draft).capability
    result = admit_contract(
        schema,
        mode=ContractAdmissionMode.STRICT,
        enforced_keywords=capability.enforced_keywords,
        capability=capability,
    )
    return bool(result.admitted)


def evaluate(draft: str = "draft202012") -> Tuple[List[str], List[str]]:
    """Return ``(failures, report_lines)`` for the policy-truth gate."""
    failures: List[str] = []
    lines: List[str] = []

    for name, schema, why in MUST_REFUSE:
        ok = not _admits(schema, draft)
        lines.append(f"  {'OK  ' if ok else 'FAIL'} refuse  {name:<31} {why}")
        if not ok:
            failures.append(f"admission ADMITTED {name!r}, but {why}")

    for name, schema in MUST_ADMIT:
        ok = _admits(schema, draft)
        lines.append(f"  {'OK  ' if ok else 'FAIL'} admit   {name:<31}")
        if not ok:
            failures.append(
                f"admission refused {name!r}, which the evaluator does enforce"
            )

    for name, schema, refusing, admitting in DIALECT_CASES:
        refused = not _admits(schema, refusing)
        admitted = _admits(schema, admitting)
        ok = refused and admitted
        lines.append(
            f"  {'OK  ' if ok else 'FAIL'} dialect {name:<31} "
            f"refused on {refusing}, admitted on {admitting}"
        )
        if not refused:
            failures.append(f"{name!r} admitted on {refusing}, which ignores it")
        if not admitted:
            failures.append(f"{name!r} refused on {admitting}, which enforces it")

    return failures, lines
