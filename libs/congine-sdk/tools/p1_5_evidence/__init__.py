"""Reproducible evidence for P1.5 Semantic Validation Safety.

Two independent corpora live here, and they answer different questions:

``capability``
    **Deterministic, functional.** Black-box witnesses that ask *"does the
    evaluator actually enforce what admission claims it enforces?"* These are
    pass/fail facts about the library, not timings, so they are stable enough to
    become a blocking gate.

``benchmark``
    **Observational.** Cost measurements used to justify — or refuse — the
    budget, complexity and caching decisions. Timings vary by machine, so this
    corpus is **local P1.5 safety evidence and never a release SLA**. P2 owns
    release performance gates.

Run them with::

    uv run --package congine-sdk python -m tools.p1_5_evidence capability
    uv run --package congine-sdk python -m tools.p1_5_evidence benchmark

Both emit a human summary and machine-readable JSON. Fixtures are fixed and
content-hashed so a later run can prove it measured the same inputs.
"""

from __future__ import annotations

__all__ = ["fixtures", "capability", "benchmark", "platform_meta"]
