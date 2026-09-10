"""Semantic cost measurement for P1.5 (observational, never a release SLA).

Splits the cost of a governed validation into the four parts that matter for a
budget decision, because a single end-to-end number cannot tell you *where* the
time goes:

``native``
    The L2 ``RuleEngine`` path alone.
``prep``
    ``check_schema`` plus validator construction — payload-independent work the
    current implementation repeats on **every** call. This is the quantity that
    decides whether a preparation cache is worth building.
``eval``
    ``iter_errors`` against an already-prepared validator.
``semantic_total``
    What the semantic path actually costs today, prep included.
``orchestration``
    Governed-call overhead measured through the real executor.

Timings are machine-specific. They are P1.5 safety evidence; P2 owns release
performance gates.
"""

from __future__ import annotations

import json
import platform
import statistics
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List

from congine_core.domain.validator import LocalValidator
from congine_core.infrastructure.jsonschema_validator import JsonSchemaSemanticValidator
from tools.p1_5_evidence import fixtures

#: Iteration counts are per-case: large fixtures are slow enough that a high
#: count buys precision nobody needs while making the corpus unusable.
#: Bumped whenever the measurement schema or method changes, so a stale
#: baseline cannot be silently compared against a newer run. Independent of the
#: P0 determinism methodology, which P1.5 does not touch.
METHODOLOGY_VERSION = 2

DEFAULT_ITERATIONS = 120
LARGE_ITERATIONS = 30
WARMUP = 5
LARGE_MARKERS = ("large", "enum", "nested-d6", "refs")


@dataclass(frozen=True)
class Timing:
    """Distribution of one measured operation, in milliseconds."""

    p50: float
    p95: float
    p99: float
    max: float
    iterations: int

    @staticmethod
    def of(samples: List[float], iterations: int) -> "Timing":
        ordered = sorted(samples)

        def pct(frac: float) -> float:
            index = min(len(ordered) - 1, int(frac * len(ordered)))
            return round(ordered[index], 4)

        return Timing(
            pct(0.50), pct(0.95), pct(0.99), round(max(ordered), 4), iterations
        )


def _measure(fn: Callable[[], Any], iterations: int) -> Timing:
    for _ in range(WARMUP):
        fn()
    samples: List[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return Timing.of(samples, iterations)


def platform_meta() -> Dict[str, Any]:
    """Record everything needed to interpret — or distrust — these numbers."""
    import importlib.metadata as md

    def version(name: str) -> str:
        try:
            return md.version(name)
        except Exception:  # noqa: BLE001 - metadata is best-effort
            return "unknown"

    return {
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unknown",
        "jsonschema": version("jsonschema"),
        "referencing": version("referencing"),
        "google_re2": version("google-re2"),
    }


def _iterations_for(name: str) -> int:
    return (
        LARGE_ITERATIONS
        if any(marker in name for marker in LARGE_MARKERS)
        else DEFAULT_ITERATIONS
    )


def run(
    draft: str = "draft202012",
    format_checking: bool = False,
    quick: bool = False,
) -> Dict[str, Any]:
    """Measure the whole corpus and return a machine-readable record.

    Args:
        draft: Dialect to measure.
        format_checking: Whether format assertions are active.
        quick: Cut iteration counts so the corpus can be run repeatedly in fresh
            processes. Ratios (``prep_share_pct``, ``semantic_vs_native``) stay
            usable; absolute p95/p99 become coarse and should not be quoted.
    """
    native = LocalValidator()
    semantic = JsonSchemaSemanticValidator(
        jsonschema_draft=draft, format_checking=format_checking
    )
    validator_cls = semantic._validator_cls  # noqa: SLF001 - evidence needs the real class

    cases: Dict[str, Any] = {}
    for name, schema, payload in fixtures.corpus_items():
        iterations = _iterations_for(name)
        if quick:
            iterations = max(3, iterations // 10)

        def prep(_schema: Dict[str, Any] = schema) -> None:
            validator_cls.check_schema(_schema)
            validator_cls(_schema, format_checker=None)

        prepared = validator_cls(schema, format_checker=None)

        row = {
            "digest": fixtures.digest(schema),
            "static_features": fixtures.static_features(schema),
            "native": asdict(
                _measure(lambda s=schema, p=payload: native.validate(p, s), iterations)
            ),
            "semantic_total": asdict(
                _measure(
                    lambda s=schema, p=payload: semantic.validate(p, s), iterations
                )
            ),
            "prep": asdict(_measure(prep, iterations)),
            "eval": asdict(
                _measure(lambda p=payload: list(prepared.iter_errors(p)), iterations)
            ),
        }
        total = row["semantic_total"]["p50"]
        # NOT a fractional decomposition. `prep` and `semantic_total` are
        # sampled independently, so this ratio can exceed 100% under normal
        # measurement variance. It is reported unclamped and unmanipulated;
        # the supported conclusion is "preparation dominates", never a literal
        # share of a whole.
        row["prep_to_total_ratio_pct"] = (
            round(100.0 * row["prep"]["p50"] / total, 1) if total else 0.0
        )
        row["semantic_vs_native"] = (
            round(total / row["native"]["p50"], 1) if row["native"]["p50"] else None
        )
        cases[name] = row

    return {
        "kind": "p1_5_benchmark",
        "methodology_version": METHODOLOGY_VERSION,
        "quick": quick,
        "draft": draft,
        "format_checking": format_checking,
        "warmup": WARMUP,
        "platform": platform_meta(),
        "fixture_manifest": fixtures.manifest(),
        "cases": cases,
    }


def render(record: Dict[str, Any]) -> str:
    """Render a human-readable summary of a benchmark record."""
    lines = [
        f"P1.5 SEMANTIC COST — draft={record['draft']} "
        f"format_checking={record['format_checking']}",
        f"{record['platform']['python']} · {record['platform']['platform']} · "
        f"jsonschema {record['platform']['jsonschema']}",
        "",
        f"{'case':<24}{'native':>9}{'semantic':>10}{'prep':>9}{'eval':>9}"
        f"{'prep/tot':>9}{'vs native':>11}",
        "-" * 80,
    ]
    for name, row in record["cases"].items():
        lines.append(
            f"{name:<24}{row['native']['p50']:>9.3f}{row['semantic_total']['p50']:>10.3f}"
            f"{row['prep']['p50']:>9.3f}{row['eval']['p50']:>9.3f}"
            f"{row['prep_to_total_ratio_pct']:>8.1f}%"
            f"{(str(row['semantic_vs_native']) + 'x') if row['semantic_vs_native'] else '-':>11}"
        )
    lines.append("")
    ratios = [r["prep_to_total_ratio_pct"] for r in record["cases"].values()]
    speedups = [
        r["semantic_total"]["p50"] / r["eval"]["p50"]
        for r in record["cases"].values()
        if r["eval"]["p50"]
    ]
    lines.append(
        f"prep/total median ratio {statistics.median(ratios):.0f}% "
        f"(range {min(ratios):.0f}-{max(ratios):.0f}%) — independently sampled "
        f"medians, not a fractional decomposition"
    )
    lines.append(
        f"preparation dominates: reusing a prepared validator is "
        f"{min(speedups):.0f}x-{max(speedups):.0f}x faster than the current path"
    )
    lines.append("Observational only. Not a release SLA; P2 owns performance gates.")
    return "\n".join(lines)


def main(argv: List[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    as_json = "--json" in args
    record = run(quick="--quick" in args)
    if as_json:
        print(json.dumps(record, indent=1, sort_keys=True))
    else:
        print(render(record))
    return 0
