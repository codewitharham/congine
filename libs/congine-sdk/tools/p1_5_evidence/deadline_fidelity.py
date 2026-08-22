"""PRE-C deadline-fidelity witness: can the governed caller observe its deadline?

Slice C proposes native/semantic stage caps. Those are only meaningful if the
caller can actually *observe* deadline exhaustion without first waiting for the
expensive work to finish. The catastrophic stdlib-regex path could not: it held
the GIL, so a 100 ms budget was enforced 20x late or not at all. RE2 removed
that specific hazard, but it does **not** follow that ordinary jsonschema work
yields the GIL any better.

This module answers that empirically, for non-regex semantic work, through the
same bounded executor governed validation uses.

What is measured, per case:

* caller-observed elapsed time and outcome;
* executor ``in_flight`` immediately after the caller returns;
* whether the worker was still running at that moment;
* the worker's total runtime and its **tail** past the caller's return.

Two outcomes are acceptable and are recorded rather than hidden: already-running
thread work continues after the caller stops waiting, and the permit stays held
until it finishes, so later calls may load-shed. What is *not* acceptable is a
caller that cannot observe its own deadline.

A cooperative control task establishes what this machine's executor does when
the work releases the GIL normally, so a bad semantic result can be attributed
to the semantic work rather than to the scheduler.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict, dataclass
from typing import Any, Callable, Dict, List, Optional

from congine_core.domain.validator import CompositeValidator, LocalValidator
from congine_core.exceptions import LoadShedError
from congine_core.infrastructure.bounded_executor import BoundedValidationExecutor
from congine_core.infrastructure.jsonschema_validator import JsonSchemaSemanticValidator
from tools.p1_5_evidence import fixtures

#: The aggregate ceiling Slice C must honour.
BUDGET_MS = 100

#: Non-regex semantic shapes whose preparation cost already exceeds the budget.
CASES = (
    "semantic-large",
    "semantic-nested-d4",
    "semantic-nested-d6",
    "semantic-combinator-20",
    "semantic-refs-40",
)


@dataclass(frozen=True)
class DeadlineObservation:
    """One governed call measured against its configured deadline."""

    case: str
    budget_ms: int
    caller_elapsed_ms: float
    outcome: str
    in_flight_after_return: int
    worker_running_at_return: bool
    worker_total_ms: Optional[float]
    worker_tail_ms: Optional[float]
    overrun_ratio: float

    @property
    def deadline_observable(self) -> bool:
        """Whether the caller stopped waiting near its deadline.

        A generous 3x allowance absorbs scheduler jitter on a loaded developer
        machine. The failure this must catch is not a few milliseconds of slop —
        it is the regex case, where the caller waited ~20x the budget or was
        never released at all.
        """
        return self.caller_elapsed_ms <= self.budget_ms * 3


def _run_governed(
    work: Callable[[], Any], budget_ms: int = BUDGET_MS
) -> Dict[str, Any]:
    """Execute *work* through the real bounded executor and observe the deadline."""
    executor = BoundedValidationExecutor(
        max_workers=1, max_pending=0, register_atexit=False
    )
    finished = threading.Event()
    started_at: List[float] = []
    finished_at: List[float] = []

    def instrumented() -> Any:
        started_at.append(time.perf_counter())
        try:
            return work()
        finally:
            finished_at.append(time.perf_counter())
            finished.set()

    call_start = time.perf_counter()
    try:
        executor.run_with_timeout(instrumented, budget_ms)
        outcome = "normal-result"
    except LoadShedError:
        outcome = "LoadShedError"
    except TimeoutError:
        outcome = "TimeoutError"
    except Exception as exc:  # noqa: BLE001 - classification is the point
        outcome = type(exc).__name__
    caller_elapsed = (time.perf_counter() - call_start) * 1000.0

    in_flight = executor.in_flight
    still_running = not finished.is_set()

    # Let the worker finish so its full runtime and tail can be recorded.
    finished.wait(timeout=60)
    worker_total = None
    worker_tail = None
    if started_at and finished_at:
        worker_total = (finished_at[0] - started_at[0]) * 1000.0
        worker_tail = max(0.0, (finished_at[0] - call_start) * 1000.0 - caller_elapsed)
    executor.shutdown(wait=False)

    return {
        "caller_elapsed_ms": round(caller_elapsed, 2),
        "outcome": outcome,
        "in_flight_after_return": in_flight,
        "worker_running_at_return": still_running,
        "worker_total_ms": round(worker_total, 2) if worker_total else None,
        "worker_tail_ms": round(worker_tail, 2) if worker_tail else None,
        "overrun_ratio": round(caller_elapsed / budget_ms, 2),
    }


def cooperative_control(budget_ms: int = BUDGET_MS) -> Dict[str, Any]:
    """Reference measurement using work that releases the GIL normally.

    Establishes this machine's executor timeout behaviour independently of
    jsonschema, so a poor semantic result can be attributed correctly. This is a
    local control, never a release SLA.
    """
    record = _run_governed(lambda: time.sleep(1.0), budget_ms)
    record["case"] = "cooperative-control(sleep 1s)"
    record["budget_ms"] = budget_ms
    return record


def measure_case(name: str, budget_ms: int = BUDGET_MS) -> DeadlineObservation:
    """Measure one semantic fixture through the governed path."""
    schema = fixtures.CORPUS[name]
    payload = fixtures.payload_for(schema)
    validator = CompositeValidator(LocalValidator(), JsonSchemaSemanticValidator())
    record = _run_governed(lambda: validator.validate(payload, schema), budget_ms)
    return DeadlineObservation(case=name, budget_ms=budget_ms, **record)


def run(budget_ms: int = BUDGET_MS) -> Dict[str, Any]:
    """Run the control plus every case and return a machine-readable record."""
    from tools.p1_5_evidence.benchmark import platform_meta

    control = cooperative_control(budget_ms)
    observations = [measure_case(name, budget_ms) for name in CASES]
    blocking = [o.case for o in observations if not o.deadline_observable]
    return {
        "kind": "p1_5_deadline_fidelity",
        "budget_ms": budget_ms,
        "platform": platform_meta(),
        "cooperative_control": control,
        "observations": [asdict(o) for o in observations],
        "deadline_observable_everywhere": not blocking,
        "cases_blocking_slice_c": blocking,
    }


def render(record: Dict[str, Any]) -> str:
    """Render the deadline table and the PASS/STOP verdict."""
    control = record["cooperative_control"]
    lines = [
        f"PRE-C DEADLINE FIDELITY — budget {record['budget_ms']}ms",
        f"{record['platform']['python']} · {record['platform']['platform']}",
        "",
        "cooperative control (GIL-releasing work, 1s):",
        f"  caller returned after {control['caller_elapsed_ms']}ms "
        f"as {control['outcome']} "
        f"(overrun {control['overrun_ratio']}x)",
        "",
        f"{'case':<24}{'caller ms':>10}{'outcome':>16}{'over':>7}"
        f"{'in_flt':>7}{'running':>9}{'worker ms':>11}{'tail ms':>9}",
        "-" * 93,
    ]
    for obs in record["observations"]:
        lines.append(
            f"{obs['case']:<24}{obs['caller_elapsed_ms']:>10.1f}"
            f"{obs['outcome']:>16}{obs['overrun_ratio']:>6.1f}x"
            f"{obs['in_flight_after_return']:>7}"
            f"{str(obs['worker_running_at_return']):>9}"
            f"{(obs['worker_total_ms'] or 0):>11.1f}"
            f"{(obs['worker_tail_ms'] or 0):>9.1f}"
        )
    lines.append("")
    if record["deadline_observable_everywhere"]:
        lines.append(
            "VERDICT: the governed caller observes deadline exhaustion without "
            "waiting for the semantic work to finish."
        )
    else:
        lines.append(
            "VERDICT: BLOCKED — deadline not observable for: "
            + ", ".join(record["cases_blocking_slice_c"])
        )
    return "\n".join(lines)
