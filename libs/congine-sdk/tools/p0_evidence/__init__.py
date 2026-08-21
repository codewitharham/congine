"""Reproducible harnesses for the P0 trust-critical evidence.

P0 recorded five constitutional properties — determinism, contract admission,
absence of false safety, load shedding distinct from timeout, and configuration
parity — but the programs that produced those numbers were never committed. The
figures in ``docs/_suite/hardening/P0_COMPLETION_REPORT.md`` therefore could not
be reproduced, only re-derived, and the recorded determinism hash survives in
the report only in truncated form (``3ab5ce02…``).

These modules reconstruct that evidence as committed, runnable code so P1
closure and every later phase re-run **identical** methodology instead of
inventing new methodology each time. Run them with::

    uv run --package congine-sdk python -m tools.p0_evidence

Each harness returns a :class:`~tools.p0_evidence.report.EvidenceResult` and
exits non-zero if its invariant fails. They import only the shipped public
surface, so they measure the SDK a consumer actually gets.

**These harnesses observe; they never tune.** A failure here is a finding about
CONGINE, not a number to adjust until it looks acceptable.
"""

from __future__ import annotations

from tools.p0_evidence.report import EvidenceResult

__all__ = ["EvidenceResult"]
