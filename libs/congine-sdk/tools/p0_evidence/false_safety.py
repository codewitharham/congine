"""P0 false-safety corpus: no unenforceable contract may be admitted.

Invariant I-02, at admission time. A contract that CONGINE cannot actually
enforce must be refused loudly, never accepted so that it later reports a clean
pass nobody checked. A false PASS here is the single worst outcome in the
system: the user believes a policy is protecting them when nothing is.

Three cases, each drawn from a real P0 finding:

``dotted``
    A property named ``user.email``. JSON Schema reads that as one literal key,
    not a path into a nested object, so the constraint the author intended is
    never applied to anything.

``unknown type``
    ``"type": "eemail"`` — not a JSON Schema type. Nothing can enforce it.

``unenforced keyword``
    A keyword CONGINE recognises but no *currently wired* evaluator executes.
    Recognition is not enforcement; without a capable evaluator the clause is
    decorative and must be refused rather than silently skipped.

Every case must be REFUSED. A case that returns admitted, or that merely warns,
is a false-safety regression.
"""

from __future__ import annotations

from typing import Any, Dict, List

from congine_core.domain.contract_admission import ContractAdmissionMode
from congine_core import admit_contract
from tools.p0_evidence.report import EvidenceResult
from tools.p0_evidence.admission_preflight import enforced_keywords

#: ``(label, schema, semantic_enabled, format_checking)``. The capability set is
#: per-case because "unenforceable" is relative to what is actually wired.
CASES: List[tuple[str, Dict[str, Any], bool, bool]] = [
    (
        "dotted property path",
        {
            "type": "object",
            "properties": {"user.email": {"type": "string"}},
            "required": ["user.email"],
        },
        False,
        False,
    ),
    (
        "unknown type",
        {
            "type": "object",
            "properties": {"email": {"type": "eemail"}},
        },
        False,
        False,
    ),
    (
        "semantic keyword, no semantic evaluator wired",
        {
            "type": "object",
            "properties": {"summary": {"type": "string", "minLength": 10}},
        },
        False,
        False,
    ),
    # The subtle one. Semantic validation is ON, so a reader might assume every
    # semantic keyword is covered — but the evaluator asserts `format` only when
    # format checking is *additionally* enabled. Admitting this would be exactly
    # the false-safety claim the vocabulary module warns about.
    (
        "format with semantic validation on but format checking off",
        {
            "type": "object",
            "properties": {"email": {"type": "string", "format": "email"}},
        },
        True,
        False,
    ),
]


def run() -> EvidenceResult:
    """Confirm every false-safety case is refused, with no false PASS."""
    outcomes: Dict[str, str] = {}
    false_passes: List[str] = []

    for label, schema, semantic_enabled, format_checking in CASES:
        result = admit_contract(
            schema,
            mode=ContractAdmissionMode.STRICT,
            enforced_keywords=enforced_keywords(
                semantic_validation_enabled=semantic_enabled,
                semantic_format_checking=format_checking,
            ),
        )
        if result.admitted:
            outcomes[label] = "ADMITTED (false safety!)"
            false_passes.append(label)
        else:
            codes = sorted({str(issue.code) for issue in result.errors})
            outcomes[label] = f"REFUSED ({', '.join(codes)})"

    return EvidenceResult(
        name="False-safety corpus",
        passed=not false_passes,
        headline=(
            f"{len(CASES) - len(false_passes)}/{len(CASES)} refused, "
            f"{len(false_passes)} false PASS"
        ),
        details=outcomes,
    )
