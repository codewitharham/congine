"""Run every P0 evidence harness and report a single verdict.

Usage::

    uv run --package congine-sdk python -m tools.p0_evidence

Exits zero only when all five constitutional properties hold. Any non-zero exit
is a stop-and-investigate signal, never something to work around.
"""

from __future__ import annotations

from tools.p0_evidence import (
    admission_preflight,
    config_parity,
    determinism,
    false_safety,
    load_shed,
)
from tools.p0_evidence.report import EvidenceResult


def main() -> int:
    results: list[EvidenceResult] = [
        determinism.run(),
        admission_preflight.run(),
        false_safety.run(),
        load_shed.run(),
        config_parity.run(),
    ]

    print("P0 TRUST BASELINE — EVIDENCE RERUN")
    print("=" * 72)
    for result in results:
        print(result.render())
        print()

    failed = [result.name for result in results if not result.passed]
    print("=" * 72)
    if failed:
        print(f"P0 EVIDENCE FAILED: {', '.join(failed)}")
        return 1
    print(f"P0 EVIDENCE INTACT: {len(results)}/{len(results)} properties hold")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
