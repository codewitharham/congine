"""Slice-E measurement: does a static schema property predict semantic cost?

Three costs are measured and never conflated:

``preparation``
    ``check_schema`` plus validator construction. Payload-independent, and
    therefore measured **once per measurement context**, not once per payload.
``evaluation``
    ``iter_errors`` against an already-prepared validator, per payload class.
``semantic_evaluator_total``
    What one call to the wired semantic evaluator costs today: preparation plus
    evaluation plus that evaluator's own local orchestration.

**``semantic_evaluator_total`` is deliberately not called a "governed
semantic-stage total".** It does not run through the L3 scheduling and deadline
path, so it excludes contract resolution, the payload/schema size preflight,
native validation, executor queue residence, and aggregate-deadline
orchestration. It is not equatable with the ``validation_timeout_ms`` budget, and
no conclusion here may treat it as such.

Every number is machine-specific. These are P1.5 *safety* observations; P2 owns
release performance evidence, and nothing measured on one workstation can
establish cross-platform behaviour.
"""

from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from tools.p1_5_evidence import analysis, benchmark, complexity_corpus, features

#: Bumped whenever fixture tiers, iteration counts or the measured quantities
#: change. Independent of ``benchmark.METHODOLOGY_VERSION``, which stays frozen
#: as Slice-A/B methodology.
METHODOLOGY_VERSION = 1

#: Founder-selected. Five cold interpreters is enough to show whether an ordering
#: survives a fresh process; it is never raised after the fact to manufacture
#: agreement.
OFFICIAL_RUNS = 5

#: Sample floors for nearest-rank quantiles. Fixed **before** any measurement so
#: a quantile can never be quietly upgraded because it flattered a hypothesis.
P95_MIN_SAMPLES = 20
P99_MIN_SAMPLES = 100

#: Iteration schedule, keyed by canonical schema size alone. Chosen from
#: structure rather than from observed cost, so no case can have its precision
#: adjusted after its result is known. ``(tier, max_bytes, iterations, warmup)``.
ITERATION_SCHEDULE: Tuple[Tuple[str, Optional[int], int, int], ...] = (
    ("small", 2_000, 120, 5),
    ("medium", 20_000, 40, 5),
    ("large", None, 12, 3),
)


def tier_for(canonical_bytes: int) -> Tuple[str, int, int]:
    """Return ``(tier, iterations, warmup)`` for a schema of this size."""
    for name, ceiling, iterations, warmup in ITERATION_SCHEDULE:
        if ceiling is None or canonical_bytes < ceiling:
            return name, iterations, warmup
    raise AssertionError("iteration schedule must end with an open tier")


@dataclass(frozen=True)
class ComplexityTiming:
    """One measured operation, with quantiles only where the sample supports them.

    Slice A/B's :class:`benchmark.Timing` cannot express an omitted quantile — it
    always reports p95 and p99 — so it is left untouched as frozen prior evidence
    and this record is used instead. Emitting an interpolated p99 from twelve
    samples would be fabricated precision, and the whole point of Slice E is that
    the evidence has to survive being checked.
    """

    n: int
    warmup: int
    p50: float
    max: float
    p95: Optional[float] = None
    p99: Optional[float] = None
    not_reported_reason: Optional[str] = None

    @staticmethod
    def of(samples: Sequence[float], warmup: int) -> "ComplexityTiming":
        ordered = sorted(samples)
        n = len(ordered)
        if n == 0:
            raise ValueError("a timing needs at least one sample")

        def nearest_rank(fraction: float) -> float:
            # Nearest-rank: the smallest observation at or above the requested
            # fraction. No interpolation, so a reported value is always a value
            # that was actually measured.
            index = max(0, min(n - 1, math.ceil(fraction * n) - 1))
            return round(ordered[index], 5)

        missing: List[str] = []
        p95 = None
        p99 = None
        if n >= P95_MIN_SAMPLES:
            p95 = nearest_rank(0.95)
        else:
            missing.append(f"p95 requires n>={P95_MIN_SAMPLES}")
        if n >= P99_MIN_SAMPLES:
            p99 = nearest_rank(0.99)
        else:
            missing.append(f"p99 requires n>={P99_MIN_SAMPLES}")

        return ComplexityTiming(
            n=n,
            warmup=warmup,
            p50=nearest_rank(0.50),
            max=round(ordered[-1], 5),
            p95=p95,
            p99=p99,
            not_reported_reason=(f"{'; '.join(missing)} (n={n})" if missing else None),
        )

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _measure(fn: Callable[[], Any], iterations: int, warmup: int) -> ComplexityTiming:
    for _ in range(warmup):
        fn()
    samples: List[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000.0)
    return ComplexityTiming.of(samples, warmup)


# ---------------------------------------------------------------------------
# Measurement contexts
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MeasurementContext:
    """One schema under one evaluator configuration — the unit of preparation.

    Identity spans schema bytes *and* dialect, format policy and derived
    capability, because those change which validator class is built and what
    ``check_schema`` does. Two corpus entries that collapse to the same identity
    are aliases of one experiment and must contribute one observation, not two;
    two entries sharing bytes across dialects are genuinely different experiments
    and must contribute two.
    """

    context_id: str
    case: complexity_corpus.CorpusCase
    capability_identity: str
    aliases: Tuple[str, ...]
    tier: str
    iterations: int
    warmup: int


def contexts(cases: Sequence[complexity_corpus.CorpusCase]) -> List[MeasurementContext]:
    """Collapse predictor cases into deduplicated measurement contexts."""
    by_id: Dict[str, MeasurementContext] = {}
    order: List[str] = []
    capability_cache: Dict[Tuple[str, bool], str] = {}

    for case in complexity_corpus.predictors(cases):
        key = (case.draft, case.format_checking)
        if key not in capability_cache:
            evaluator = complexity_corpus.evaluator(case.draft, case.format_checking)
            capability_cache[key] = complexity_corpus.capability_identity(
                evaluator.capability
            )
        identity = capability_cache[key]
        context_id = case.context_key(identity)

        if context_id in by_id:
            existing = by_id[context_id]
            by_id[context_id] = MeasurementContext(
                context_id=existing.context_id,
                case=existing.case,
                capability_identity=existing.capability_identity,
                aliases=existing.aliases + (case.name,),
                tier=existing.tier,
                iterations=existing.iterations,
                warmup=existing.warmup,
            )
            continue

        tier, iterations, warmup = tier_for(case.canonical_bytes)
        by_id[context_id] = MeasurementContext(
            context_id=context_id,
            case=case,
            capability_identity=identity,
            aliases=(),
            tier=tier,
            iterations=iterations,
            warmup=warmup,
        )
        order.append(context_id)

    return [by_id[cid] for cid in order]


def rotate(items: Sequence[Any], run_index: int, total: int) -> List[Any]:
    """Deterministic per-worker execution order.

    Five workers running one identical sequence would let a cross-case warming
    effect look like a property of the schemas. Rotation is deterministic rather
    than random so a run stays reproducible, and the offset is recorded so an
    ordering effect shows up as evidence instead of being averaged away.
    """
    if not items:
        return []
    offset = (run_index * len(items)) // max(1, total)
    return list(items[offset:]) + list(items[:offset])


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------


def measure_run(run_index: int, *, pilot: bool = False) -> Dict[str, Any]:
    """Measure the whole corpus once, in this process."""
    supported = complexity_corpus.supported_formats()
    cases = complexity_corpus.build(supported)
    report = complexity_corpus.validate_corpus(cases)
    if not report.ok:
        raise RuntimeError(
            "corpus validation failed; refusing to measure: "
            + "; ".join(report.failures + report.oversize)
        )

    ordered = rotate(contexts(cases), run_index, OFFICIAL_RUNS)
    kept, skipped = complexity_corpus.format_candidates(supported)

    rows: List[Dict[str, Any]] = []
    for context in ordered:
        case = context.case
        schema = dict(case.schema)
        evaluator = complexity_corpus.evaluator(case.draft, case.format_checking)
        validator_cls = evaluator._validator_cls  # noqa: SLF001 - evidence needs the real class
        registry = evaluator._registry  # noqa: SLF001
        format_checker = (
            getattr(validator_cls, "FORMAT_CHECKER", None)
            if case.format_checking
            else None
        )

        iterations = max(3, context.iterations // 10) if pilot else context.iterations
        warmup = 1 if pilot else context.warmup

        def prepare() -> None:
            validator_cls.check_schema(schema)
            validator_cls(schema, format_checker=format_checker, registry=registry)

        preparation = _measure(prepare, iterations, warmup)
        prepared = validator_cls(
            schema, format_checker=format_checker, registry=registry
        )

        payload_cases: Dict[str, Any] = {}
        for label in sorted(case.payloads):
            payload = case.payloads[label]
            payload_cases[label] = {
                "evaluation": _measure(
                    lambda p=payload: list(prepared.iter_errors(p)), iterations, warmup
                ).as_dict(),
                "semantic_evaluator_total": _measure(
                    lambda p=payload: evaluator.validate(p, schema), iterations, warmup
                ).as_dict(),
            }

        rows.append(
            {
                "measurement_context_id": context.context_id,
                "schema_digest": case.digest,
                "draft": case.draft,
                "format_checking": case.format_checking,
                "capability_identity": context.capability_identity,
                "family": case.family,
                "name": case.name,
                "aliases": list(context.aliases),
                "parameters": dict(case.parameters),
                "note": case.note,
                "canonical_bytes": case.canonical_bytes,
                "tier": context.tier,
                "features": features.extract(schema),
                "admission_witness": report.witnesses[case.name],
                "preparation": preparation.as_dict(),
                "payload_cases": payload_cases,
            }
        )

    return {
        "kind": "p1_5_complexity_run",
        "evidence": not pilot,
        "pilot": pilot,
        "run_index": run_index,
        "rotation_offset": (run_index * len(ordered)) // max(1, OFFICIAL_RUNS),
        "case_order": [row["measurement_context_id"] for row in rows],
        "methodology_version": METHODOLOGY_VERSION,
        "corpus_version": complexity_corpus.CORPUS_VERSION,
        "corpus_hash": complexity_corpus.corpus_hash(cases),
        "feature_schema_version": features.FEATURE_SCHEMA_VERSION,
        "iteration_schedule": [
            {"tier": t, "max_bytes": c, "iterations": i, "warmup": w}
            for t, c, i, w in ITERATION_SCHEDULE
        ],
        "quantile_floors": {
            "p50": 1,
            "max": 1,
            "p95": P95_MIN_SAMPLES,
            "p99": P99_MIN_SAMPLES,
        },
        "format_family_included": list(kept),
        "format_family_skipped": skipped,
        "platform": benchmark.platform_meta(),
        "contexts": rows,
    }


def spawn(run_index: int, *, pilot: bool = False) -> Dict[str, Any]:
    """Run one measurement in a **fresh interpreter** and return its record.

    A cold process matters here: import cost, first-touch allocation and any
    process-wide caching inside ``jsonschema`` would otherwise be paid once by the
    first case measured and by nobody else, which is exactly the kind of artefact
    that makes an in-process ranking untrustworthy.
    """
    env = dict(os.environ)
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = os.pathsep.join(
        [os.path.dirname(root), env.get("PYTHONPATH", "")]
    ).strip(os.pathsep)
    argv = [
        sys.executable,
        "-m",
        "tools.p1_5_evidence",
        "complexity",
        "--worker",
        f"--run-index={run_index}",
    ]
    if pilot:
        argv.append("--pilot")
    completed = subprocess.run(
        argv,
        cwd=os.path.dirname(root),
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


#: The default aggregate governed budget, used **only** to sort measured cases
#: into "cheap" and "expensive" so a structural rule can be shown to disagree with
#: reality. It is a *local default aggregate-budget sensitivity reference*, never
#: a normative semantic-stage boundary: `validation_timeout_ms` covers the whole
#: governed validation, and semantic evaluation receives only what remains after
#: the native stage and orchestration.
LOCAL_AGGREGATE_REFERENCE_MS = 100.0

#: A second, deliberately tighter reference. Labelled a HYPOTHETICAL SENSITIVITY
#: SCENARIO because no run configured it: it exists to show whether conclusions
#: depend on where the line is drawn, not to propose a new default.
HYPOTHETICAL_REFERENCE_MS = 25.0

#: Synthetic multipliers for the machine-speed falsification probe. These may
#: DISQUALIFY a candidate as fragile. They can never QUALIFY one: surviving them
#: is not machine independence, not cross-platform evidence, and not release
#: portability. P2 owns real cross-version/cross-platform performance evidence.
SPEED_SCALES = (0.5, 1.5)


def run_experiment() -> Dict[str, Any]:
    """Run five fresh workers and derive the Slice-E analysis from them."""
    runs = [spawn(index) for index in range(OFFICIAL_RUNS)]
    return assemble(runs)


def assemble(runs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the evidence record: static corpus once, timings per run, analysis.

    Static per-context data is stored once rather than repeated in all five runs.
    That is purely a size decision — every raw observation is still present, so
    the analysis can be recomputed from the record without trusting the rendered
    summary.
    """
    for run in runs:
        if not run.get("evidence", False):
            raise RuntimeError(
                "refusing to analyse a pilot run: pilot output is not evidence"
            )
    hashes = {run["corpus_hash"] for run in runs}
    versions = {run["methodology_version"] for run in runs}
    if len(hashes) != 1 or len(versions) != 1:
        raise RuntimeError(f"runs disagree on corpus/methodology: {hashes} {versions}")

    first = runs[0]
    corpus: Dict[str, Any] = {}
    for row in first["contexts"]:
        corpus[row["measurement_context_id"]] = {
            "name": row["name"],
            "family": row["family"],
            "draft": row["draft"],
            "format_checking": row["format_checking"],
            "capability_identity": row["capability_identity"],
            "aliases": row["aliases"],
            "parameters": row["parameters"],
            "note": row["note"],
            "canonical_bytes": row["canonical_bytes"],
            "tier": row["tier"],
            "features": row["features"],
            "admission_witness": row["admission_witness"],
        }

    stored_runs = [
        {
            "run_index": run["run_index"],
            "rotation_offset": run["rotation_offset"],
            "case_order": run["case_order"],
            "platform": run["platform"],
            "measurements": {
                row["measurement_context_id"]: {
                    "preparation": row["preparation"],
                    "payload_cases": row["payload_cases"],
                }
                for row in run["contexts"]
            },
        }
        for run in runs
    ]

    return {
        "kind": "p1_5_complexity",
        "methodology_version": first["methodology_version"],
        "corpus_version": first["corpus_version"],
        "corpus_hash": first["corpus_hash"],
        "feature_schema_version": first["feature_schema_version"],
        "feature_definitions": features.FEATURE_DEFINITIONS,
        "iteration_schedule": first["iteration_schedule"],
        "quantile_floors": first["quantile_floors"],
        "format_family_included": first["format_family_included"],
        "format_family_skipped": first["format_family_skipped"],
        "platform": first["platform"],
        "scale": corpus_scale(),
        "references": {
            "local_default_aggregate_budget_ms": LOCAL_AGGREGATE_REFERENCE_MS,
            "hypothetical_sensitivity_scenario_ms": HYPOTHETICAL_REFERENCE_MS,
            "label": (
                "local default aggregate-budget sensitivity reference; NOT a "
                "normative semantic-stage boundary"
            ),
        },
        "measured_quantity_note": (
            "semantic_evaluator_total = semantic preparation + payload evaluation + "
            "semantic-validator-local orchestration. It EXCLUDES contract "
            "resolution, size preflight, native validation, executor queue "
            "residence and L3 aggregate-deadline orchestration, and is therefore "
            "not equatable with the validation_timeout_ms budget."
        ),
        "corpus": corpus,
        "runs": stored_runs,
        "analysis": analyse(corpus, stored_runs),
    }


def reanalyse(record: Dict[str, Any]) -> Dict[str, Any]:
    """Recompute the analysis from a stored record's raw observations.

    The point of retaining every per-run observation is that a conclusion can be
    re-derived without re-measuring — including by a future engineer who does not
    trust the rendered summary, and including when the analysis itself is
    corrected. Nothing here touches the raw section.
    """
    updated = dict(record)
    updated["analysis"] = analyse(record["corpus"], record["runs"])
    return updated


def _median_across_runs(values: Sequence[float]) -> float:
    return round(analysis.median(values), 5)


def analyse(corpus: Dict[str, Any], runs: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Derive every Slice-E conclusion from the stored raw observations."""
    ids = list(corpus)

    # --- per-context cost summaries, median across the five fresh processes ---
    prep: Dict[str, float] = {}
    total_median: Dict[str, float] = {}
    total_max: Dict[str, float] = {}
    total_min: Dict[str, float] = {}
    eval_max: Dict[str, float] = {}
    payload_spread: Dict[str, Any] = {}

    for context_id in ids:
        prep[context_id] = _median_across_runs(
            [run["measurements"][context_id]["preparation"]["p50"] for run in runs]
        )
        per_label_total: Dict[str, float] = {}
        per_label_eval: Dict[str, float] = {}
        labels = sorted(runs[0]["measurements"][context_id]["payload_cases"])
        for label in labels:
            per_label_total[label] = _median_across_runs(
                [
                    run["measurements"][context_id]["payload_cases"][label][
                        "semantic_evaluator_total"
                    ]["p50"]
                    for run in runs
                ]
            )
            per_label_eval[label] = _median_across_runs(
                [
                    run["measurements"][context_id]["payload_cases"][label][
                        "evaluation"
                    ]["p50"]
                    for run in runs
                ]
            )
        totals = list(per_label_total.values())
        total_median[context_id] = round(analysis.median(totals), 5)
        total_max[context_id] = max(totals)
        total_min[context_id] = min(totals)
        eval_max[context_id] = max(per_label_eval.values())
        worst = max(per_label_total, key=lambda label: per_label_total[label])
        payload_spread[context_id] = {
            "labels": labels,
            "per_label_total_ms": per_label_total,
            "per_label_evaluation_ms": per_label_eval,
            "min_ms": min(totals),
            "median_ms": round(analysis.median(totals), 5),
            "max_ms": max(totals),
            "max_over_min": (
                round(max(totals) / min(totals), 3) if min(totals) > 0 else None
            ),
            "worst_payload_class": worst,
        }

    feature_names = sorted(features.FEATURE_DEFINITIONS)

    def column(name: str) -> List[float]:
        return [float(corpus[cid]["features"][name]) for cid in ids]

    # --- B: schema-level (measurement-context-weighted) predictor analysis ---
    schema_level: Dict[str, Any] = {}
    for name in feature_names:
        xs = column(name)
        schema_level[name] = {
            "preparation": {
                "spearman": analysis.spearman(xs, [prep[c] for c in ids]).as_dict(),
                "pearson_secondary": analysis.pearson(
                    xs, [prep[c] for c in ids]
                ).as_dict(),
            },
            "total_worst_payload": {
                "spearman": analysis.spearman(
                    xs, [total_max[c] for c in ids]
                ).as_dict(),
                "pearson_secondary": analysis.pearson(
                    xs, [total_max[c] for c in ids]
                ).as_dict(),
            },
            "total_median_payload": {
                "spearman": analysis.spearman(
                    xs, [total_median[c] for c in ids]
                ).as_dict()
            },
            "evaluation_worst_payload": {
                "spearman": analysis.spearman(xs, [eval_max[c] for c in ids]).as_dict()
            },
        }

    # --- A: case-level payload sensitivity (falsification, not admission) ---
    case_rows: List[Tuple[str, str, float]] = []
    for context_id in ids:
        for label, value in payload_spread[context_id]["per_label_total_ms"].items():
            case_rows.append(
                (f"{corpus[context_id]['name']}::{label}", context_id, value)
            )
    case_level: Dict[str, Any] = {}
    for name in feature_names:
        xs = [float(corpus[cid]["features"][name]) for _, cid, _ in case_rows]
        ys = [value for _, _, value in case_rows]
        case_level[name] = analysis.spearman(xs, ys).as_dict()

    spreads = [
        payload_spread[c]["max_over_min"]
        for c in ids
        if payload_spread[c]["max_over_min"] is not None
    ]
    identical_features = _identical_feature_groups(corpus, ids, total_max)

    # --- family monotonicity ---
    family_monotonicity = _family_monotonicity(corpus, ids, prep, total_max)

    # --- cross-run rank stability (also the order-rotation check) ---
    stability = _rank_stability(ids, runs)

    # --- candidate rules, in-sample ceiling then out-of-sample holdout ---
    candidates = _candidate_rules(corpus, ids, total_max, feature_names)
    holdout = _holdout(corpus, ids, total_max, candidates)
    scaling = _speed_sensitivity(corpus, ids, total_max, candidates)

    # --- Slice-F observations (recorded, never acted on here) ---
    slice_f = _slice_f_observations(corpus, ids, prep, total_median, runs)

    return {
        "context_summary": {
            corpus[c]["name"]: {
                "measurement_context_id": c,
                "family": corpus[c]["family"],
                "preparation_p50_ms": prep[c],
                "total_min_ms": total_min[c],
                "total_median_ms": total_median[c],
                "total_max_ms": total_max[c],
                "payload_spread": payload_spread[c],
            }
            for c in ids
        },
        "schema_level_predictors": schema_level,
        "case_level_payload_sensitivity": {
            "spearman_by_feature": case_level,
            "cases": len(case_rows),
            "payload_spread_max_over_min": {
                "min": round(min(spreads), 3) if spreads else None,
                "median": round(analysis.median(spreads), 3) if spreads else None,
                "max": round(max(spreads), 3) if spreads else None,
                "reason": None if spreads else analysis.INSUFFICIENT,
            },
            "identical_features_different_cost": identical_features,
        },
        "family_monotonicity": family_monotonicity,
        "rank_stability": stability,
        "candidate_rules": candidates,
        "family_holdout": holdout,
        "synthetic_speed_sensitivity": scaling,
        "slice_f_observations": slice_f,
    }


def _identical_feature_groups(
    corpus: Dict[str, Any], ids: Sequence[str], cost: Dict[str, float]
) -> List[Dict[str, Any]]:
    """Contexts with identical static features but different measured cost.

    This is the single most direct falsification available: if the entire feature
    vector cannot tell two contracts apart while measurement can, no rule over
    those features can separate them either.
    """
    groups: Dict[str, List[str]] = {}
    for context_id in ids:
        key = json.dumps(corpus[context_id]["features"], sort_keys=True)
        groups.setdefault(key, []).append(context_id)
    out: List[Dict[str, Any]] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        costs = [cost[m] for m in members]
        out.append(
            {
                "names": [corpus[m]["name"] for m in members],
                "drafts": sorted({corpus[m]["draft"] for m in members}),
                "total_max_ms": {corpus[m]["name"]: cost[m] for m in members},
                "max_over_min": (
                    round(max(costs) / min(costs), 3) if min(costs) > 0 else None
                ),
            }
        )
    return sorted(out, key=lambda row: -(row["max_over_min"] or 0))


#: Families whose single varied parameter is the value monotonicity is checked
#: against. A family absent here has no single ordered axis to test.
_FAMILY_PARAMETER: Dict[str, str] = {
    "width": "properties",
    "depth": "depth",
    "anyof": "breadth",
    "oneof": "breadth",
    "allof": "breadth",
    "combo-depth": "combinator_depth",
    "enum": "cardinality",
    "ref-depth": "ref_chain",
}


def _family_monotonicity(
    corpus: Dict[str, Any],
    ids: Sequence[str],
    prep: Dict[str, float],
    total: Dict[str, float],
) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for family, parameter in _FAMILY_PARAMETER.items():
        members = [
            c
            for c in ids
            if corpus[c]["family"] == family and parameter in corpus[c]["parameters"]
        ]
        if family == "enum":
            # The mixed properties x cardinality members would make the single
            # varied axis ambiguous, so only the single-property series is used.
            members = [
                c for c in members if corpus[c]["parameters"].get("properties") == 1
            ]
        values = [float(corpus[c]["parameters"][parameter]) for c in members]
        out[family] = {
            "parameter": parameter,
            "members": [corpus[c]["name"] for c in members],
            "preparation": analysis.monotonicity(
                values, [prep[c] for c in members]
            ).as_dict(),
            "total_worst_payload": analysis.monotonicity(
                values, [total[c] for c in members]
            ).as_dict(),
        }
    return out


def _rank_stability(
    ids: Sequence[str], runs: Sequence[Dict[str, Any]]
) -> Dict[str, Any]:
    """Do five cold processes, each with a different rotation, agree on the order?

    Run identity and rotation offset are deliberately confounded: each worker uses
    its own deterministic rotation, so agreement means neither a cold start nor a
    case ordering changed the ranking, and disagreement is recorded as evidence
    instability rather than averaged away.
    """
    per_run: List[List[float]] = []
    for run in runs:
        per_run.append(
            [
                max(
                    case["semantic_evaluator_total"]["p50"]
                    for case in run["measurements"][c]["payload_cases"].values()
                )
                for c in ids
            ]
        )
    prep_runs = [
        [run["measurements"][c]["preparation"]["p50"] for c in ids] for run in runs
    ]
    return {
        "total_worst_payload": analysis.rank_stability(per_run),
        "preparation": analysis.rank_stability(prep_runs),
        "rotation_offsets": [run["rotation_offset"] for run in runs],
        "note": (
            "each run used a different deterministic case rotation, so these "
            "coefficients test cold-start and ordering effects together"
        ),
    }


def _rows_for(
    corpus: Dict[str, Any], ids: Sequence[str], cost: Dict[str, float], feature: str
) -> List[Tuple[str, float, float]]:
    return [
        (corpus[c]["name"], float(corpus[c]["features"][feature]), cost[c]) for c in ids
    ]


def _candidate_rules(
    corpus: Dict[str, Any],
    ids: Sequence[str],
    cost: Dict[str, float],
    feature_names: Sequence[str],
) -> Dict[str, Any]:
    """Best achievable ``feature > T`` rule per feature, against both references.

    Deliberately in-sample, and used only as a ceiling: a rule that already
    misclassifies on the data it was tuned on cannot be rescued out-of-sample.
    """
    out: Dict[str, Any] = {}
    for reference, label in (
        (LOCAL_AGGREGATE_REFERENCE_MS, "local_default_aggregate_budget"),
        (HYPOTHETICAL_REFERENCE_MS, "hypothetical_sensitivity_scenario"),
    ):
        expensive = [corpus[c]["name"] for c in ids if cost[c] > reference]
        # Degenerate references have to say so. With no contract above the
        # reference there is nothing for a cost boundary to separate, so every
        # non-trivial rule is pure false positive and a "best rule" would be an
        # artefact of the threshold sweep rather than a finding.
        separable = 0 < len(expensive) < len(ids)
        per_feature: Dict[str, Any] = {}
        if separable:
            for feature in feature_names:
                best = analysis.best_threshold(
                    feature, reference, _rows_for(corpus, ids, cost, feature)
                )
                if best is not None:
                    per_feature[feature] = best.as_dict()
        out[label] = {
            "reference_ms": reference,
            "contexts_above_reference": expensive,
            "contexts_above_reference_count": len(expensive),
            "contexts_total": len(ids),
            "separable": separable,
            "reason": (
                None
                if separable
                else (
                    "no_contexts_above_reference"
                    if not expensive
                    else "all_contexts_above_reference"
                )
            ),
            "best_in_sample_rule_per_feature": per_feature,
        }
    return out


def _holdout(
    corpus: Dict[str, Any],
    ids: Sequence[str],
    cost: Dict[str, float],
    candidates: Dict[str, Any],
) -> Dict[str, Any]:
    """Leave-one-family-out falsification, with **no retuning** on the held-out set.

    A threshold chosen on the whole corpus and scored on the whole corpus proves
    nothing; the question is whether a rule derived without ever seeing a
    structural family still classifies that family correctly. If it needs
    retuning when a new family appears, it is not a stable production boundary.
    """
    out: Dict[str, Any] = {}
    for reference, label in (
        (LOCAL_AGGREGATE_REFERENCE_MS, "local_default_aggregate_budget"),
        (HYPOTHETICAL_REFERENCE_MS, "hypothetical_sensitivity_scenario"),
    ):
        per_feature = candidates[label]["best_in_sample_rule_per_feature"]
        if not per_feature:
            out[label] = {
                "reference_ms": reference,
                "reason": candidates[label]["reason"] or analysis.INSUFFICIENT,
            }
            continue
        ranked = sorted(
            per_feature.items(),
            key=lambda item: item[1]["false_positive"] + item[1]["false_negative"],
        )[:3]
        families = sorted({corpus[c]["family"] for c in ids})
        feature_results: Dict[str, Any] = {}
        for feature, _ in ranked:
            folds: List[Dict[str, Any]] = []
            for held in families:
                discovery = [c for c in ids if corpus[c]["family"] != held]
                test = [c for c in ids if corpus[c]["family"] == held]
                if not test or len(discovery) < analysis.MIN_OBSERVATIONS:
                    continue
                derived = analysis.best_threshold(
                    feature, reference, _rows_for(corpus, discovery, cost, feature)
                )
                if derived is None:
                    continue
                scored = analysis.confusion(
                    feature,
                    derived.threshold,
                    reference,
                    _rows_for(corpus, test, cost, feature),
                )
                folds.append(
                    {
                        "held_out_family": held,
                        "discovery_contexts": len(discovery),
                        "derived_threshold": derived.threshold,
                        "discovery_false_positive": derived.false_positive,
                        "discovery_false_negative": derived.false_negative,
                        "holdout": scored.as_dict(),
                    }
                )
            thresholds = sorted({fold["derived_threshold"] for fold in folds})
            feature_results[feature] = {
                "folds": folds,
                "distinct_derived_thresholds": thresholds,
                "threshold_is_stable_across_folds": len(thresholds) <= 1,
                "holdout_false_positive_total": sum(
                    fold["holdout"]["false_positive"] for fold in folds
                ),
                "holdout_false_negative_total": sum(
                    fold["holdout"]["false_negative"] for fold in folds
                ),
            }
        out[label] = {"reference_ms": reference, "features": feature_results}
    return out


def _speed_sensitivity(
    corpus: Dict[str, Any],
    ids: Sequence[str],
    cost: Dict[str, float],
    candidates: Dict[str, Any],
) -> Dict[str, Any]:
    """Would the best local rule still classify the same way on a faster machine?

    **Falsification only.** A rule whose verdicts move when every measurement is
    scaled by a plausible machine-speed factor is disqualified as a local artefact.
    A rule that survives is *not* thereby shown to be machine-independent: this
    probe cannot establish cross-machine invariance, cross-platform performance or
    release portability, and P2 owns that evidence.
    """
    # How many contracts land on the "expensive" side is itself machine-speed
    # dependent. Reported for both references before any rule is scored, because
    # a classification that moves with the clock cannot anchor a static boundary.
    reference_fragility = {
        label: {
            "reference_ms": reference,
            "unscaled": sum(1 for c in ids if cost[c] > reference),
            **{
                f"x{scale}": sum(1 for c in ids if cost[c] * scale > reference)
                for scale in SPEED_SCALES
            },
        }
        for reference, label in (
            (LOCAL_AGGREGATE_REFERENCE_MS, "local_default_aggregate_budget"),
            (HYPOTHETICAL_REFERENCE_MS, "hypothetical_sensitivity_scenario"),
        )
    }

    # Score whichever reference actually separates the corpus. When the default
    # reference has nothing above it, a rule derived against it would be scoring
    # noise, so the tighter hypothetical scenario carries the probe instead.
    label = next(
        (
            name
            for name in (
                "local_default_aggregate_budget",
                "hypothetical_sensitivity_scenario",
            )
            if candidates[name]["separable"]
        ),
        "",
    )
    if not label:
        return {
            "reason": "no_separable_reference",
            "reference_fragility": reference_fragility,
        }
    reference = candidates[label]["reference_ms"]
    per_feature = candidates[label]["best_in_sample_rule_per_feature"]
    if not per_feature:
        return {
            "reason": analysis.INSUFFICIENT,
            "reference_fragility": reference_fragility,
        }
    ranked = sorted(
        per_feature.items(),
        key=lambda item: item[1]["false_positive"] + item[1]["false_negative"],
    )[:3]

    out: Dict[str, Any] = {
        "interpretation": (
            "MAY DISQUALIFY a candidate as fragile; MUST NOT QUALIFY one. "
            "Surviving synthetic scaling is not machine independence."
        ),
        "scored_against": label,
        "reference_ms": reference,
        "reference_fragility": reference_fragility,
        "features": {},
    }
    for feature, best in ranked:
        scales: Dict[str, Any] = {}
        for scale in SPEED_SCALES:
            scaled = {c: cost[c] * scale for c in ids}
            rescored = analysis.confusion(
                feature,
                best["threshold"],
                reference,
                _rows_for(corpus, ids, scaled, feature),
            )
            retuned = analysis.best_threshold(
                feature, reference, _rows_for(corpus, ids, scaled, feature)
            )
            scales[f"x{scale}"] = {
                "same_threshold_errors": rescored.false_positive
                + rescored.false_negative,
                "retuned_threshold": None if retuned is None else retuned.threshold,
                "threshold_moved": (
                    retuned is not None and retuned.threshold != best["threshold"]
                ),
                "contexts_above_reference": sum(
                    1 for c in ids if scaled[c] > reference
                ),
            }
        out["features"][feature] = {
            "unscaled_threshold": best["threshold"],
            "unscaled_errors": best["false_positive"] + best["false_negative"],
            "scaled": scales,
        }
    return out


def _slice_f_observations(
    corpus: Dict[str, Any],
    ids: Sequence[str],
    prep: Dict[str, float],
    total_median: Dict[str, float],
    runs: Sequence[Dict[str, Any]],
) -> Dict[str, Any]:
    """Observations for Slice F. Recorded only — nothing here is implemented.

    No cache is built, no validator instance is shared, and semantic evaluator
    construction is unchanged.
    """
    ratios = [
        round(100.0 * prep[c] / total_median[c], 1) for c in ids if total_median[c] > 0
    ]
    # Spread of one context's preparation cost across five cold processes: how
    # deterministic preparation is as a function of the schema alone.
    determinism: List[float] = []
    for context_id in ids:
        values = [run["measurements"][context_id]["preparation"]["p50"] for run in runs]
        if min(values) > 0:
            determinism.append(round(max(values) / min(values), 3))
    return {
        "question": [
            "Is semantic preparation mainly a deterministic function of the schema?",
            "Does repeated validation of the same schema repay preparation every call?",
            "Is preparation dominant enough for caching to remain worth investigating?",
        ],
        "prep_to_total_ratio_pct": {
            "min": min(ratios) if ratios else None,
            "median": round(analysis.median(ratios), 1) if ratios else None,
            "max": max(ratios) if ratios else None,
            "note": (
                "preparation and total are sampled independently, so this ratio can "
                "exceed 100% under normal variance; it supports 'preparation "
                "dominates', never a literal share of a whole"
            ),
        },
        "preparation_cross_process_max_over_min": {
            "min": min(determinism) if determinism else None,
            "median": round(analysis.median(determinism), 3) if determinism else None,
            "max": max(determinism) if determinism else None,
        },
        "repeated_per_call": (
            "JsonSchemaSemanticValidator.validate() calls check_schema and "
            "constructs a validator on every call, so preparation is paid per "
            "validation for an unchanged schema."
        ),
        "implemented_in_slice_e": "nothing",
    }


def _fmt(stat: Dict[str, Any]) -> str:
    if stat.get("value") is None:
        return f"n/a ({stat.get('reason')})"
    return f"{stat['value']:+.3f}"


def render(record: Dict[str, Any]) -> str:
    """Human-readable summary. The JSON record remains the authority."""
    a = record["analysis"]
    lines = [
        f"P1.5 SLICE E — SEMANTIC COMPLEXITY PREDICTORS (methodology v{record['methodology_version']})",
        f"corpus v{record['corpus_version']} {record['corpus_hash'][:16]} · "
        f"{record['scale']['measurement_contexts']} measurement contexts · "
        f"{record['scale']['payload_cases']} payload cases · "
        f"{record['scale']['official_runs']} fresh processes",
        f"{record['platform']['python']} · {record['platform']['platform']} · "
        f"jsonschema {record['platform']['jsonschema']}",
        "",
        "SCHEMA-LEVEL PREDICTORS (authoritative for admission; Spearman primary)",
        f"{'feature':<26}{'prep':>18}{'total(worst)':>20}{'eval(worst)':>18}",
        "-" * 82,
    ]
    ranked = sorted(
        record["analysis"]["schema_level_predictors"].items(),
        key=lambda item: -abs(item[1]["preparation"]["spearman"]["value"] or 0.0),
    )
    for name, row in ranked:
        lines.append(
            f"{name:<26}{_fmt(row['preparation']['spearman']):>18}"
            f"{_fmt(row['total_worst_payload']['spearman']):>20}"
            f"{_fmt(row['evaluation_worst_payload']['spearman']):>18}"
        )

    spread = a["case_level_payload_sensitivity"]["payload_spread_max_over_min"]
    lines += [
        "",
        "PAYLOAD SENSITIVITY (falsification axis)",
        f"  same schema, different payload: total cost varies by "
        f"{spread['min']}x-{spread['max']}x (median {spread['median']}x)",
        f"  contexts whose entire feature vector is identical yet cost differs: "
        f"{len(a['case_level_payload_sensitivity']['identical_features_different_cost'])}",
        "",
        "CROSS-PROCESS RANK STABILITY (each run used a different case rotation)",
        f"  preparation      min {a['rank_stability']['preparation']['min']} "
        f"median {a['rank_stability']['preparation']['median']}",
        f"  total(worst)     min {a['rank_stability']['total_worst_payload']['min']} "
        f"median {a['rank_stability']['total_worst_payload']['median']}",
        "",
        "FAMILY MONOTONICITY (cost vs the single varied parameter)",
    ]
    for family, row in a["family_monotonicity"].items():
        prep_mono = row["preparation"]
        total_mono = row["total_worst_payload"]
        lines.append(
            f"  {family:<14} prep {prep_mono['non_decreasing']}/{prep_mono['pairs']} "
            f"{'strict' if prep_mono['strict'] else 'non-strict':<11} "
            f"total {total_mono['non_decreasing']}/{total_mono['pairs']} "
            f"{'strict' if total_mono['strict'] else 'non-strict'}"
        )

    for label in (
        "local_default_aggregate_budget",
        "hypothetical_sensitivity_scenario",
    ):
        block = a["candidate_rules"][label]
        lines += [
            "",
            f"CANDIDATE HARD RULES vs {label} ({block['reference_ms']}ms) — "
            f"{block['contexts_above_reference_count']}/{block['contexts_total']} "
            "context(s) above it",
        ]
        if not block["separable"]:
            lines.append(
                f"  NOT SEPARABLE ({block['reason']}): nothing for a cost boundary to "
                "divide, so every non-trivial rule here is pure false positive"
            )
            continue
        best = sorted(
            block["best_in_sample_rule_per_feature"].items(),
            key=lambda item: item[1]["false_positive"] + item[1]["false_negative"],
        )[:3]
        for feature, rule in best:
            lines.append(
                f"  best in-sample {feature} > {rule['threshold']:g}: "
                f"FP={rule['false_positive']} FN={rule['false_negative']}"
            )
            if rule["false_positive_examples"]:
                lines.append(
                    f"    FP e.g. {', '.join(rule['false_positive_examples'][:2])}"
                )
            if rule["false_negative_examples"]:
                lines.append(
                    f"    FN e.g. {', '.join(rule['false_negative_examples'][:2])}"
                )

    lines += ["", "OUT-OF-SAMPLE FAMILY HOLDOUT (no retuning on the held-out family)"]
    for label, block in a["family_holdout"].items():
        if "features" not in block:
            lines.append(f"  {label}: not run ({block.get('reason')})")
            continue
        for feature, row in block["features"].items():
            lines.append(
                f"  {label[:24]:<24} {feature:<20} holdout FP={row['holdout_false_positive_total']} "
                f"FN={row['holdout_false_negative_total']} "
                f"threshold stable across folds: "
                f"{'yes' if row['threshold_is_stable_across_folds'] else 'NO'} "
                f"({len(row['distinct_derived_thresholds'])} distinct)"
            )

    lines += [
        "",
        "SYNTHETIC MACHINE-SPEED PROBE — falsification only, never qualifying",
    ]
    scaling = a["synthetic_speed_sensitivity"]
    for label, row in scaling.get("reference_fragility", {}).items():
        scaled = ", ".join(f"{k}={row[k]}" for k in row if k.startswith("x"))
        lines.append(
            f"  contexts above {label} ({row['reference_ms']}ms): "
            f"unscaled={row['unscaled']}, {scaled}"
        )
    if "features" in scaling:
        lines.append(f"  rules scored against {scaling['scored_against']}:")
        for feature, row in scaling["features"].items():
            moved = [k for k, v in row["scaled"].items() if v["threshold_moved"]]
            lines.append(
                f"    {feature:<22} threshold {row['unscaled_threshold']:g} moves under: "
                f"{', '.join(moved) if moved else 'neither scale'}"
            )
    elif scaling.get("reason"):
        lines.append(f"  no rule scored ({scaling['reason']})")

    f_obs = a["slice_f_observations"]
    lines += [
        "",
        "SLICE F OBSERVATIONS (recorded only; nothing implemented)",
        f"  prep/total ratio median {f_obs['prep_to_total_ratio_pct']['median']}% "
        f"(range {f_obs['prep_to_total_ratio_pct']['min']}-{f_obs['prep_to_total_ratio_pct']['max']}%)",
        f"  preparation cross-process max/min median "
        f"{f_obs['preparation_cross_process_max_over_min']['median']}x",
        "",
        record["measured_quantity_note"],
        f"References are a {record['references']['label']}.",
        "Observational only. Not a release SLA; P2 owns performance gates.",
    ]
    return "\n".join(lines)


def corpus_scale() -> Dict[str, Any]:
    """Deterministic size of the experiment, computed before it is run."""
    supported = complexity_corpus.supported_formats()
    cases = complexity_corpus.build(supported)
    resolved = contexts(cases)
    payload_cases = 0
    iterations = 0
    for context in resolved:
        labels = len(context.case.payloads)
        payload_cases += labels
        # preparation once, then evaluation + total per payload class.
        iterations += context.iterations * (1 + 2 * labels)
    return {
        "corpus_cases": len(cases),
        "predictors": len(complexity_corpus.predictors(cases)),
        "refusal_controls": len(complexity_corpus.controls(cases)),
        "measurement_contexts": len(resolved),
        "aliased_cases": sum(len(c.aliases) for c in resolved),
        "payload_cases": payload_cases,
        "timed_operations_per_run": iterations,
        "official_runs": OFFICIAL_RUNS,
        "tiers": {
            tier: sum(1 for c in resolved if c.tier == tier)
            for tier, _, _, _ in ITERATION_SCHEDULE
        },
    }
