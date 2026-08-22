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

from tools.p1_5_evidence import benchmark, capability

#: Capabilities admission currently advertises as enforced. A silent pass here
#: means admission is lying, so the corpus fails.
_MUST_ENFORCE = ("pattern", "patternProperties", "ref-local-valid")

#: Known-untruthful advertisements confirmed in Slice A0. Listed so the corpus
#: reports them as *expected findings* rather than surprises, and so the entry
#: disappears the moment Slice B fixes admission.
_KNOWN_UNTRUTHFUL = ("contentEncoding", "contentMediaType")


def _capability(as_json: bool) -> int:
    witnesses = capability.run_local_witnesses() + capability.run_retrieval_witnesses()
    rows = capability.summarize(witnesses)

    failures: List[str] = []
    for name in _MUST_ENFORCE:
        row = rows.get(name)
        if row and row["outcomes"] != ["enforced"]:
            failures.append(
                f"{name}: expected enforced everywhere, got {row['outcomes']}"
            )

    retrieval = [n for n, r in rows.items() if r["retrieval_observed"]]

    if as_json:
        print(
            json.dumps(
                {
                    "kind": "p1_5_capability",
                    "platform": benchmark.platform_meta(),
                    "rows": rows,
                    "failures": failures,
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
            if name in _KNOWN_UNTRUTHFUL and row["outcomes"] == ["silent-pass"]:
                mark = "   <-- admitted but NOT enforced (A0 finding)"
            if row["retrieval_observed"]:
                mark = "   <-- NETWORK RETRIEVAL OBSERVED"
            print(
                f"{name:<30}{row['drafts']:>7}{'yes' if row['all_agree'] else 'NO':>7}  "
                f"{','.join(row['outcomes'])}{mark}"
            )
        print()
        if retrieval:
            print(f"external reference retrieval observed on: {', '.join(retrieval)}")
        if failures:
            print("FAILURES:")
            for line in failures:
                print(f"  {line}")
        else:
            print("All capabilities admission requires are genuinely enforced.")
    return 1 if failures else 0


def main(argv: List[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    as_json = "--json" in args
    mode = next((a for a in args if not a.startswith("-")), "all")

    if mode == "capability":
        return _capability(as_json)
    forwarded = [a for a in args if a in ("--json", "--quick")]
    if mode == "benchmark":
        return benchmark.main(forwarded)
    if mode == "all":
        rc = _capability(as_json)
        print()
        benchmark.main(forwarded)
        return rc
    print(f"unknown mode {mode!r}; expected capability | benchmark | all")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
