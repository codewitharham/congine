"""Statistics for the Slice-E complexity experiment. Standard library only.

No scipy, no pandas, no sklearn — and not even the optional ``stats`` extra.
Evidence tooling that needs a new dependency to reach its conclusion makes that
conclusion harder to reproduce, and everything here is a few dozen lines.

Two principles run through this module:

**Rank relationships come first.** Absolute milliseconds are platform-sensitive,
so Pearson on raw times mostly measures the machine. Spearman asks the question a
deterministic admission rule would actually need answered — *does this feature
order contracts the same way cost does?* — and that survives a machine that is 30%
faster. Pearson is computed too, but reported as secondary and insufficient.

**A statistic that cannot be computed is reported as absent, never as zero.** A
constant feature column has no correlation with anything; emitting ``0.0`` would
read as "measured, and unrelated", which is a different and false claim. Every
result is therefore either a number or ``None`` with a machine-readable reason.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: Minimum paired observations before a correlation is meaningful at all.
MIN_OBSERVATIONS = 3

CONSTANT_FEATURE = "constant_feature"
CONSTANT_COST = "constant_cost"
INSUFFICIENT = "insufficient_observations"


@dataclass(frozen=True)
class Stat:
    """One statistic, or an explicit statement that it could not be computed."""

    value: Optional[float]
    reason: Optional[str] = None
    n: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def absent(reason: str, n: int = 0) -> "Stat":
        return Stat(value=None, reason=reason, n=n)


def _average_ranks(values: Sequence[float]) -> List[float]:
    """Ranks with ties averaged, which is what Spearman requires.

    Assigning ties arbitrary distinct ranks would invent an ordering the data does
    not contain — and this corpus has real ties, because families deliberately
    hold features constant while varying structure.
    """
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(order):
        stop = index
        while stop + 1 < len(order) and values[order[stop + 1]] == values[order[index]]:
            stop += 1
        shared = (index + stop) / 2.0 + 1.0
        for position in range(index, stop + 1):
            ranks[order[position]] = shared
        index = stop + 1
    return ranks


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Stat:
    n = len(xs)
    if n < MIN_OBSERVATIONS:
        return Stat.absent(INSUFFICIENT, n)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    dx = [x - mean_x for x in xs]
    dy = [y - mean_y for y in ys]
    denom_x = math.sqrt(sum(v * v for v in dx))
    denom_y = math.sqrt(sum(v * v for v in dy))
    if denom_x == 0.0:
        return Stat.absent(CONSTANT_FEATURE, n)
    if denom_y == 0.0:
        return Stat.absent(CONSTANT_COST, n)
    return Stat(
        round(sum(a * b for a, b in zip(dx, dy)) / (denom_x * denom_y), 4), None, n
    )


def pearson(xs: Sequence[float], ys: Sequence[float]) -> Stat:
    """Linear correlation on raw values. **Secondary evidence only.**

    Reported because its absence would be conspicuous, not because it settles
    anything: it is dominated by absolute magnitudes, and absolute magnitudes here
    are a property of this workstation.
    """
    return _pearson(xs, ys)


def spearman(xs: Sequence[float], ys: Sequence[float]) -> Stat:
    """Rank correlation — the primary statistic for this experiment."""
    n = len(xs)
    if n < MIN_OBSERVATIONS:
        return Stat.absent(INSUFFICIENT, n)
    if len(set(xs)) <= 1:
        return Stat.absent(CONSTANT_FEATURE, n)
    if len(set(ys)) <= 1:
        return Stat.absent(CONSTANT_COST, n)
    return _pearson(_average_ranks(xs), _average_ranks(ys))


@dataclass(frozen=True)
class Monotonicity:
    """How closely cost follows a family's single varied parameter."""

    pairs: int
    non_decreasing: int
    strict: bool
    fraction: Optional[float]
    reason: Optional[str] = None

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def monotonicity(parameter: Sequence[float], cost: Sequence[float]) -> Monotonicity:
    """Check whether cost rises with the parameter, over adjacent pairs.

    Within a family this is stronger evidence than a correlation coefficient: the
    family varies exactly one structural axis, so a broken step is a concrete
    counterexample rather than noise in an aggregate.
    """
    if len(parameter) < 2:
        return Monotonicity(0, 0, False, None, INSUFFICIENT)
    ordered = sorted(zip(parameter, cost), key=lambda pair: pair[0])
    steps = list(zip(ordered, ordered[1:]))
    non_decreasing = sum(1 for (_, a), (_, b) in steps if b >= a)
    strict = all(b > a for (_, a), (_, b) in steps)
    return Monotonicity(
        pairs=len(steps),
        non_decreasing=non_decreasing,
        strict=strict,
        fraction=round(non_decreasing / len(steps), 4),
    )


def rank_stability(rankings: Sequence[Sequence[float]]) -> Dict[str, Any]:
    """Pairwise Spearman between per-run orderings of the same cases.

    A predictor that ranks contracts differently on two cold interpreters of the
    *same* machine cannot be the basis of a portable admission rule, so this is a
    falsification check rather than a summary statistic.
    """
    stats: List[Stat] = []
    pairs: List[str] = []
    for i in range(len(rankings)):
        for j in range(i + 1, len(rankings)):
            stats.append(spearman(rankings[i], rankings[j]))
            pairs.append(f"run{i}-run{j}")
    usable = [s.value for s in stats if s.value is not None]
    return {
        "pairs": {name: stat.as_dict() for name, stat in zip(pairs, stats)},
        "min": round(min(usable), 4) if usable else None,
        "median": round(median(usable), 4) if usable else None,
        "reason": None if usable else INSUFFICIENT,
    }


def median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


@dataclass(frozen=True)
class Confusion:
    """FP/FN for one candidate threshold against a cost reference."""

    feature: str
    threshold: float
    reference_ms: float
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    false_positive_examples: Tuple[str, ...]
    false_negative_examples: Tuple[str, ...]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def confusion(
    feature: str,
    threshold: float,
    reference_ms: float,
    rows: Sequence[Tuple[str, float, float]],
    examples: int = 4,
) -> Confusion:
    """Score ``feature > threshold`` as a refusal rule against a cost reference.

    ``rows`` is ``(name, feature_value, observed_cost_ms)``.

    The reference is a **local sensitivity reference**, never a normative
    boundary — see the Slice-E report. Its only job here is to sort cases into
    "cheap" and "expensive" so a structural rule can be shown to disagree with
    reality, in both directions.
    """
    tp = fp = tn = fn = 0
    fps: List[str] = []
    fns: List[str] = []
    for name, value, cost in rows:
        rejected = value > threshold
        expensive = cost > reference_ms
        if rejected and expensive:
            tp += 1
        elif rejected and not expensive:
            fp += 1
            if len(fps) < examples:
                fps.append(f"{name} ({feature}={value:g}, {cost:.2f}ms)")
        elif not rejected and not expensive:
            tn += 1
        else:
            fn += 1
            if len(fns) < examples:
                fns.append(f"{name} ({feature}={value:g}, {cost:.2f}ms)")
    return Confusion(
        feature=feature,
        threshold=threshold,
        reference_ms=reference_ms,
        true_positive=tp,
        false_positive=fp,
        true_negative=tn,
        false_negative=fn,
        false_positive_examples=tuple(fps),
        false_negative_examples=tuple(fns),
    )


def candidate_thresholds(values: Sequence[float]) -> Tuple[float, ...]:
    """Midpoints between adjacent distinct feature values.

    Every threshold a rule of the form ``feature > T`` could distinguish, and no
    more. Sweeping the whole set is what makes "the best achievable rule still
    misclassifies" a defensible statement rather than an argument about tuning.
    """
    distinct = sorted(set(values))
    if len(distinct) < 2:
        return ()
    return tuple(
        (distinct[i] + distinct[i + 1]) / 2.0 for i in range(len(distinct) - 1)
    )


def best_threshold(
    feature: str,
    reference_ms: float,
    rows: Sequence[Tuple[str, float, float]],
) -> Optional[Confusion]:
    """The threshold with the fewest total misclassifications, or ``None``.

    Chosen **in-sample on purpose**, and only ever used as a ceiling: if the best
    rule the discovery data can produce is already wrong often, no out-of-sample
    rule will do better, and the candidate dies without needing a holdout.
    """
    thresholds = candidate_thresholds([value for _, value, _ in rows])
    if not thresholds:
        return None
    scored = [confusion(feature, t, reference_ms, rows) for t in thresholds]
    return min(scored, key=lambda c: (c.false_positive + c.false_negative, c.threshold))
