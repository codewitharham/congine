"""Entry point for the P1.5 evidence corpora.

    uv run --package congine-sdk python -m tools.p1_5_evidence capability [--json]
    uv run --package congine-sdk python -m tools.p1_5_evidence benchmark  [--json]
    uv run --package congine-sdk python -m tools.p1_5_evidence all

``capability`` exits non-zero when the evaluator fails to enforce something
contract admission currently claims it enforces — that is a G12 violation, not a
style preference. ``benchmark`` is observational and always exits zero.
"""

from __future__ import annotations

import json
import sys
from typing import List

from tools.p1_5_evidence import (
    benchmark,
    capability,
    deadline_fidelity,
    policy_truth,
)

#: Capabilities admission currently advertises as enforced. A silent pass here
#: means admission is lying, so the corpus fails.
_MUST_ENFORCE = ("pattern", "patternProperties", "ref-local-valid")

# End-to-end policy truth lives in `policy_truth`; this corpus no longer keeps
# an allowlist of tolerated untruthful advertisements.


def _capability(as_json: bool, live_server: bool = False) -> int:
    """Report semantic capability truth.

    Args:
        as_json: Emit the machine-readable record instead of the summary.
        live_server: Also run the loopback-server retrieval witness. It is the
            most decisive evidence but binds a socket, so it stays opt-in and
            the hermetic retriever-spy witness carries the routine check.
    """
    witnesses = capability.run_local_witnesses() + capability.run_dialect_witnesses()
    if live_server:
        witnesses += capability.run_retrieval_witnesses()
    rows = capability.summarize(witnesses)

    drift = capability.capability_drift()
    hermetic_external = capability.hermetic_retrieval_witness(
        "http://example.invalid/s.json"
    )
    hermetic_local = capability.hermetic_local_ref_witness()
    surface = {
        draft: sorted(
            k for k, v in capability.observed_capability(draft).items() if not v
        )
        for draft in capability.DRAFTS
    }

    failures: List[str] = []
    for name in _MUST_ENFORCE:
        row = rows.get(name)
        if row and row["outcomes"] != ["enforced"]:
            failures.append(
                f"{name}: expected enforced everywhere, got {row['outcomes']}"
            )

    retrieval = [n for n, r in rows.items() if r["retrieval_observed"]]

    # The derived capability model is only trustworthy while it agrees with
    # black-box observation, so disagreement is a hard failure.
    if drift:
        failures.append(f"derived capability drifted from observation: {drift}")
    if any(r["fetched"] for r in hermetic_external.values()):
        failures.append("no-retrieval registry did not prevent a fetch")
    if not all(r["enforced"] for r in hermetic_local.values()):
        failures.append("no-retrieval registry broke valid local references")

    policy_failures, policy_lines = policy_truth.evaluate()
    failures.extend(policy_failures)

    if as_json:
        print(
            json.dumps(
                {
                    "kind": "p1_5_capability",
                    "methodology_version": benchmark.METHODOLOGY_VERSION,
                    "platform": benchmark.platform_meta(),
                    "rows": rows,
                    "silent_advertised_keywords_by_draft": surface,
                    "capability_drift": drift,
                    "hermetic_external_ref": hermetic_external,
                    "hermetic_local_ref": hermetic_local,
                    "failures": failures,
                    "policy_truth": policy_lines,
                    "retrieval_observed": retrieval,
                },
                indent=1,
                sort_keys=True,
            )
        )
    else:
        print("P1.5 SEMANTIC CAPABILITY WITNESSES")
        print(f"{'capability':<30}{'drafts':>7}{'agree':>7}  outcomes")
        print("-" * 78)
        for name, row in sorted(rows.items()):
            mark = ""
            if row["retrieval_observed"]:
                mark = "   <-- NETWORK RETRIEVAL OBSERVED"
            print(
                f"{name:<30}{row['drafts']:>7}{'yes' if row['all_agree'] else 'NO':>7}  "
                f"{','.join(row['outcomes'])}{mark}"
            )
        print()
        print()
        print("per-draft keywords that are SILENT despite being advertised:")
        for draft, silent in surface.items():
            print(
                f"  {draft:12} {len(silent):2}  {', '.join(silent) if silent else '-'}"
            )
        print()
        print(
            f"derived-vs-observed capability drift: "
            f"{drift if drift else 'NONE (model matches all 5 drafts)'}"
        )
        fetched = sum(r["retrieval_requested"] for r in hermetic_external.values())
        print(
            f"hermetic no-retrieval registry: {fetched} retrieval request(s) refused, "
            f"0 fetched; local refs still enforced on "
            f"{sum(1 for r in hermetic_local.values() if r['enforced'])}/"
            f"{len(hermetic_local)} drafts"
        )
        if retrieval:
            print(f"live-server retrieval observed on: {', '.join(retrieval)}")
        print()
        print("END-TO-END POLICY TRUTH (admission vs. evaluator reality):")
        for line in policy_lines:
            print(line)
        print()
        if failures:
            print("FAILURES:")
            for line in failures:
                print(f"  {line}")
        else:
            print(
                "Admission refuses everything the wired evaluator cannot enforce, "
                "and admits everything it can."
            )
    return 1 if failures else 0


def main(argv: List[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    as_json = "--json" in args
    mode = next((a for a in args if not a.startswith("-")), "all")

    if mode == "capability":
        return _capability(as_json, live_server="--live-server" in args)
    forwarded = [a for a in args if a in ("--json", "--quick")]
    if mode == "benchmark":
        return benchmark.main(forwarded)
    if mode == "deadline":
        record = deadline_fidelity.run()
        if as_json:
            print(json.dumps(record, indent=1, sort_keys=True))
        else:
            print(deadline_fidelity.render(record))
        # Observational: a blocking result is reported, not raised, so the
        # founder decision stays explicit rather than implied by an exit code.
        return 0
    if mode == "all":
        rc = _capability(as_json, live_server="--live-server" in args)
        print()
        benchmark.main(forwarded)
        return rc
    print(f"unknown mode {mode!r}; expected capability | benchmark | deadline | all")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
