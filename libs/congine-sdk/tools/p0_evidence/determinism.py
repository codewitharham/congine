"""P0 determinism: N=5000 identical evaluations must yield one canonical verdict.

Invariant I-01. Holding the payload, contract and every evaluation-relevant
configuration value fixed, the canonical judgment must not vary — not across
repetitions, not across worker threads. Any variation means something
non-deterministic reached the judgment path, which is the failure mode CONGINE
exists to preclude.

``duration_ms`` is deliberately excluded from the canonical form: it is wall
clock, not judgment. Everything that constitutes the verdict is included.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict

from congine_core.domain.validator import LocalValidator
from congine_core.models import ValidationResult
from tools.p0_evidence.report import EvidenceResult

N = 5000

#: Fixed contract. Exercises all six native rules: presence, type, enum, range,
#: null guard and regex.
CONTRACT: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "ticket_id": {"type": "string", "pattern": "^TKT-\\d{4}$"},
        "action": {
            "type": "string",
            "enum": ["approve_return", "reject_return", "escalate"],
        },
        "confidence_score": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "summary": {"type": "string", "minLength": 10},
    },
    "required": ["ticket_id", "action", "confidence_score", "summary"],
}

#: Fixed payload, deliberately breaching several rules at once so the canonical
#: form covers breach ordering as well as the pass/fail bit. A verdict that
#: reorders breaches is not the same verdict.
PAYLOAD: Dict[str, Any] = {
    "ticket_id": "BAD-01",
    "action": "refund_everything",
    "confidence_score": 4.2,
    "summary": "short",
}


def canonical_verdict(result: ValidationResult) -> str:
    """Serialise the judgment-bearing content of *result*, stably.

    Excludes ``duration_ms``. Breaches keep their emitted order, because that
    order is itself part of the deterministic output.
    """
    return json.dumps(
        {
            "status": result.status,
            "degraded": result.degraded,
            "degraded_reason": (
                None if result.degraded_reason is None else str(result.degraded_reason)
            ),
            "is_enforced": result.is_enforced(),
            "is_pass": result.is_pass(),
            "breaches": [
                {
                    "rule": breach.rule,
                    "field": breach.field,
                    "message": breach.message,
                }
                for breach in result.breaches
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def run(n: int = N) -> EvidenceResult:
    """Evaluate the fixed case *n* times and count distinct canonical verdicts."""
    validator = LocalValidator()
    verdicts: Dict[str, int] = {}
    for _ in range(n):
        verdict = canonical_verdict(validator.validate(PAYLOAD, CONTRACT))
        verdicts[verdict] = verdicts.get(verdict, 0) + 1

    distinct = len(verdicts)
    canonical = next(iter(verdicts)) if distinct == 1 else ""
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest() if canonical else "-"

    return EvidenceResult(
        name="Determinism",
        passed=distinct == 1,
        headline=f"{distinct} distinct canonical verdict across N={n}",
        details={
            "N": n,
            "distinct verdicts": distinct,
            "canonical sha256": digest,
            "breach count": (
                len(json.loads(canonical)["breaches"]) if canonical else "n/a"
            ),
            "is_enforced": json.loads(canonical)["is_enforced"] if canonical else "n/a",
        },
    )
