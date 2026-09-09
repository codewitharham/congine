"""P0 admission preflight: every shipped contract must be admissible.

Invariant I-03. The three contracts shipped under ``examples/LangChain/contracts``
are what a new user meets first. If any of them were refused by the admission
boundary under its own documented configuration, CONGINE would be shipping
policy it will not itself accept.

Each contract is judged against the capability set its documented configuration
actually wires — composed exactly as
:class:`~congine_core.usecases.sync_contracts_usecase.SyncContractsUseCase`
composes it, so this measures the real production rule and not a restatement of
it.

**The configuration is read from the shipped example, not assumed.** The example
runs provider-free (no LLM credentials) *and* with
``CONGINE_SEMANTIC_VALIDATION=true``, which are independent switches: the
semantic evaluator is a local JSON Schema evaluator, not a remote provider. Two
of the three contracts constrain ``minLength``/``maxLength``, which only that
evaluator enforces, so judging them with native rules alone would report a
refusal that the shipped topology does not actually produce. To keep the harness
from silently drifting from what ships, :func:`documented_semantic_validation`
parses the example rather than hardcoding the answer, and fails loudly if the
setting disappears.

Acceptance is 3/3. It is met by the contracts being correct under the
configuration they ship with — never by relaxing admission.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from congine_core.domain.contract_admission import ContractAdmissionMode
from congine_core.domain.schema_vocabulary import (
    NATIVE_ENFORCED_KEYWORDS,
    SEMANTIC_ENFORCED_KEYWORDS,
)
from congine_core import admit_contract
from tools.p0_evidence.report import EvidenceResult

EXAMPLE_DIR = Path(__file__).resolve().parents[2] / "examples" / "LangChain"
CONTRACTS_DIR = EXAMPLE_DIR / "contracts"
SMOKE_SCRIPT = EXAMPLE_DIR / "smoke.py"


def documented_semantic_validation() -> tuple[bool, bool]:
    """Read the example's own semantic settings, so the harness cannot drift.

    Returns ``(semantic_validation_enabled, semantic_format_checking)``.

    Raises:
        RuntimeError: If the example no longer states the setting. Guessing
            here would silently measure a topology CONGINE does not ship.
    """
    source = SMOKE_SCRIPT.read_text(encoding="utf-8")
    if "CONGINE_SEMANTIC_VALIDATION" not in source:
        raise RuntimeError(
            f"{SMOKE_SCRIPT.name} no longer sets CONGINE_SEMANTIC_VALIDATION; "
            "the documented admission configuration is unknown. Update this "
            "harness deliberately rather than assuming a default."
        )
    enabled = '"CONGINE_SEMANTIC_VALIDATION"] = "true"' in source
    formats = '"CONGINE_SEMANTIC_FORMAT_CHECKING"] = "true"' in source
    return enabled, formats


def enforced_keywords(
    *, semantic_validation_enabled: bool = False, semantic_format_checking: bool = False
) -> frozenset[str]:
    """Compose the capability set exactly as the sync use case does."""
    enforced = set(NATIVE_ENFORCED_KEYWORDS)
    if semantic_validation_enabled:
        enforced |= SEMANTIC_ENFORCED_KEYWORDS
        if semantic_format_checking:
            enforced.add("format")
    return frozenset(enforced)


def run() -> EvidenceResult:
    """Admit every shipped contract under its documented configuration."""
    semantic_enabled, format_checking = documented_semantic_validation()
    capability_set = enforced_keywords(
        semantic_validation_enabled=semantic_enabled,
        semantic_format_checking=format_checking,
    )
    paths = sorted(CONTRACTS_DIR.glob("*.json"))
    admitted: List[str] = []
    refused: Dict[str, Any] = {}

    for path in paths:
        document = json.loads(path.read_text(encoding="utf-8"))
        result = admit_contract(
            document["schema"],
            mode=ContractAdmissionMode.STRICT,
            enforced_keywords=capability_set,
        )
        if result.admitted:
            admitted.append(document["id"])
        else:
            refused[document["id"]] = [
                f"{issue.path}: {issue.code}" for issue in result.errors
            ]

    total = len(paths)
    percentage = (len(admitted) / total * 100) if total else 0.0

    return EvidenceResult(
        name="Admission preflight",
        passed=total > 0 and len(admitted) == total,
        headline=f"{len(admitted)}/{total} = {percentage:.0f}% admitted",
        details={
            "mode": "STRICT",
            "semantic validation": (
                f"{'enabled' if semantic_enabled else 'disabled'} "
                f"(read from {SMOKE_SCRIPT.name})"
            ),
            "format checking": "enabled" if format_checking else "disabled",
            "admitted": ", ".join(admitted) or "none",
            "refused": refused or "none",
        },
    )
