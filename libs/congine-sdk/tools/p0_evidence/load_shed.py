"""P0 load shedding: saturation is refused, and stays distinct from timeout.

Invariant I-05, and the I-02 distinction that makes it meaningful.

Two failures look alike from the outside and must never be conflated:

``LoadShedError``
    The executor was saturated, so the work **never ran**. CONGINE did not
    evaluate the policy at all.

``TimeoutError``
    The work was admitted and ran, but exceeded its deadline. CONGINE tried and
    could not finish in budget.

``LoadShedError`` subclasses ``TimeoutError`` so existing ``except TimeoutError``
callers keep working, which makes the distinction easy to lose by accident. This
harness pins both directions: saturated work raises the subclass, and a genuine
deadline overrun raises a plain ``TimeoutError`` that is *not* a
``LoadShedError``.

Latency is recorded as evidence only. It is never tuned toward a previous
figure — the numbers move with the host, and chasing them would be measurement
theatre.
"""

from __future__ import annotations

import threading
import time
from typing import Any, Dict, List

from congine_core.exceptions import LoadShedError
from congine_core.infrastructure.bounded_executor import BoundedValidationExecutor
from tools.p0_evidence.report import EvidenceResult

N_SATURATED = 2000


def _percentile(values: List[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(fraction * len(ordered)))
    return ordered[index]


def run(n: int = N_SATURATED) -> EvidenceResult:
    """Saturate a bounded executor and classify every rejection."""
    details: Dict[str, Any] = {}

    # Fill every slot with work that blocks until we release it, so the pool is
    # genuinely saturated rather than merely busy.
    executor = BoundedValidationExecutor(
        max_workers=1, max_pending=0, register_atexit=False
    )
    release = threading.Event()
    occupied = threading.Event()

    def block() -> str:
        occupied.set()
        release.wait(timeout=30)
        return "done"

    holder = threading.Thread(
        target=lambda: executor.run_with_timeout(block, 30_000), daemon=True
    )
    holder.start()
    occupied.wait(timeout=5)

    shed = 0
    other: Dict[str, int] = {}
    latencies: List[float] = []
    try:
        for _ in range(n):
            started = time.perf_counter()
            try:
                executor.run_with_timeout(lambda: "unreachable", 1000)
            except LoadShedError:
                shed += 1
            except Exception as exc:  # noqa: BLE001 - classification is the point
                name = type(exc).__name__
                other[name] = other.get(name, 0) + 1
            latencies.append((time.perf_counter() - started) * 1_000_000)
    finally:
        release.set()
        holder.join(timeout=5)
        executor.shutdown(wait=True)

    details["saturated calls"] = f"{shed}/{n} -> LoadShedError"
    if other:
        details["unexpected"] = other
    details["rejection p50"] = f"{_percentile(latencies, 0.50):.2f} us"
    details["rejection p90"] = f"{_percentile(latencies, 0.90):.2f} us"
    details["rejection p99"] = f"{_percentile(latencies, 0.99):.2f} us"

    # The other half of the invariant: an admitted call that overruns its
    # deadline must raise a plain TimeoutError, never the load-shed subclass.
    deadline_executor = BoundedValidationExecutor(
        max_workers=2, max_pending=2, register_atexit=False
    )
    timeout_is_distinct = False
    timeout_type = "none raised"
    try:
        deadline_executor.run_with_timeout(lambda: time.sleep(1.5), 50)
    except LoadShedError:
        timeout_type = "LoadShedError (WRONG - conflated)"
    except TimeoutError as exc:
        timeout_type = type(exc).__name__
        timeout_is_distinct = True
    finally:
        deadline_executor.shutdown(wait=False)

    details["deadline overrun"] = f"{timeout_type} (not a LoadShedError)"

    passed = shed == n and not other and timeout_is_distinct
    return EvidenceResult(
        name="Load shedding",
        passed=passed,
        headline=(
            f"{shed}/{n} saturated calls shed; "
            f"deadline overrun {'stays distinct' if timeout_is_distinct else 'CONFLATED'}"
        ),
        details=details,
    )
