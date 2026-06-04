"""Adversarial tests for the bounded validation executor (audit H1)."""

from __future__ import annotations

import asyncio
import threading
import time

import pytest

from congine_core.infrastructure.bounded_executor import BoundedValidationExecutor


def _executor(**kw) -> BoundedValidationExecutor:
    kw.setdefault("register_atexit", False)
    return BoundedValidationExecutor(**kw)


def test_runs_and_returns() -> None:
    ex = _executor(max_workers=2, max_pending=2)
    try:
        assert ex.run_with_timeout(lambda: 6 * 7, 1000) == 42
    finally:
        ex.shutdown()


def test_timeout_raises() -> None:
    ex = _executor(max_workers=2, max_pending=2)
    try:
        with pytest.raises(TimeoutError):
            ex.run_with_timeout(lambda: time.sleep(0.5), 10)
    finally:
        ex.shutdown()


def test_saturation_sheds_load() -> None:
    # capacity = max_workers + max_pending = 1 → one slot total.
    ex = _executor(max_workers=1, max_pending=0)
    started = threading.Event()
    release = threading.Event()

    def blocker() -> str:
        started.set()
        release.wait(5.0)
        return "done"

    holder = threading.Thread(target=lambda: ex.run_with_timeout(blocker, 10_000))
    holder.start()
    try:
        assert started.wait(2.0)
        # The only permit is held by the running blocker → next call is shed
        # IMMEDIATELY (not queued unbounded), raising TimeoutError.
        with pytest.raises(TimeoutError):
            ex.run_with_timeout(lambda: 1, 1000)
        assert ex.rejected_total >= 1
    finally:
        release.set()
        holder.join(5.0)
        ex.shutdown()


def test_reentrant_call_runs_inline_no_deadlock() -> None:
    # capacity = 1: a re-entrant submit would deadlock; it must run inline.
    ex = _executor(max_workers=1, max_pending=0)
    try:

        def outer() -> str:
            return ex.run_with_timeout(lambda: "inner", 1000)

        assert ex.run_with_timeout(outer, 2000) == "inner"
    finally:
        ex.shutdown()


def test_in_flight_returns_to_zero() -> None:
    ex = _executor(max_workers=2, max_pending=2)
    try:
        ex.run_with_timeout(lambda: 1, 1000)
        deadline = time.time() + 1.0
        while time.time() < deadline and ex.in_flight != 0:
            time.sleep(0.01)
        assert ex.in_flight == 0
    finally:
        ex.shutdown()


def test_invalid_construction() -> None:
    with pytest.raises(ValueError):
        BoundedValidationExecutor(max_workers=0, register_atexit=False)
    with pytest.raises(ValueError):
        BoundedValidationExecutor(max_pending=-1, register_atexit=False)


# --------------------------------------------------------------------------- #
# Async path (audit H1/H2): the async guard must get the SAME capacity bound
# and timeout as the sync path, not a raw unbounded run_in_executor.
# --------------------------------------------------------------------------- #
async def test_async_runs_and_returns() -> None:
    ex = _executor(max_workers=2, max_pending=2)
    try:
        assert await ex.run_with_timeout_async(lambda: 6 * 7, 1000) == 42
    finally:
        ex.shutdown()


async def test_async_timeout_raises() -> None:
    # A slow validation must hit the SAME millisecond budget as the sync path
    # and raise TimeoutError off the event loop (not run untimed to completion).
    ex = _executor(max_workers=2, max_pending=2)
    try:
        with pytest.raises(TimeoutError):
            await ex.run_with_timeout_async(lambda: time.sleep(0.5), 10)
    finally:
        ex.shutdown()


async def test_async_concurrent_saturation_sheds_load() -> None:
    # capacity = max_workers + max_pending = 1 → one slot total. Hold it with a
    # blocker on a worker thread, then fire several CONCURRENT async submissions:
    # every one must be shed IMMEDIATELY (load shed) rather than queue unbounded.
    ex = _executor(max_workers=1, max_pending=0)
    started = threading.Event()
    release = threading.Event()

    def blocker() -> str:
        started.set()
        release.wait(5.0)
        return "done"

    holder = threading.Thread(target=lambda: ex.run_with_timeout(blocker, 10_000))
    holder.start()
    try:
        assert started.wait(2.0)
        results = await asyncio.gather(
            *[ex.run_with_timeout_async(lambda: 1, 1000) for _ in range(5)],
            return_exceptions=True,
        )
        assert all(isinstance(r, TimeoutError) for r in results)
        assert ex.rejected_total >= 5
    finally:
        release.set()
        holder.join(5.0)
        ex.shutdown()


async def test_async_reentrant_call_runs_inline() -> None:
    # When invoked from one of the pool's own workers (the use case offloads
    # execute, which re-enters), the async path must run inline — no second
    # permit, no nested-pool deadlock — exactly like the sync path.
    ex = _executor(max_workers=1, max_pending=0)
    try:

        def on_worker() -> str:
            # Synchronous re-entry from a worker thread runs inline.
            return ex.run_with_timeout(lambda: "inner", 1000)

        assert await ex.run_with_timeout_async(on_worker, 2000) == "inner"
    finally:
        ex.shutdown()
