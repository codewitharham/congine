"""Bounded validation executor (Layer 4).

:class:`BoundedValidationExecutor` replaces a naked
:class:`concurrent.futures.ThreadPoolExecutor` for the validation hot path. It
fixes the timeout/exhaustion failure mode (audit H1): a vanilla pool has an
**unbounded** work queue, and because a timed-out callable cannot be killed, a
burst of slow validations fills every worker with zombies while new submissions
pile up unbounded — silently breaking the latency budget exactly under load.

This executor bounds total outstanding work with a :class:`threading.BoundedSemaphore`
(``capacity = max_workers + max_pending``) and **sheds load** (raises
``TimeoutError`` immediately, which the use case degrades) when saturated, rather
than queueing without limit. A permit is held until the underlying future
genuinely completes — so a zombie keeps occupying capacity and cannot be masked
by an over-optimistic "slot free" signal.

Re-entrancy: when ``run_with_timeout`` is invoked *from one of this pool's own
worker threads* (e.g. the async guard offloads ``execute`` onto the pool, and
``execute`` then calls back in), the work runs **inline** instead of submitting
again — preventing a nested-same-pool deadlock.
"""

from __future__ import annotations

import asyncio
import atexit
import concurrent.futures
import threading
from typing import Any, Callable


class BoundedValidationExecutor:
    """Bounded, load-shedding executor for time-boxed validation work."""

    def __init__(
        self,
        max_workers: int = 10,
        max_pending: int = 10,
        register_atexit: bool = True,
    ) -> None:
        """Args:
        max_workers: Worker threads running validations concurrently.
        max_pending: Extra slots allowed to queue before load is shed.
        register_atexit: Register a best-effort shutdown at interpreter exit.
        """
        if max_workers <= 0:
            raise ValueError("max_workers must be positive")
        if max_pending < 0:
            raise ValueError("max_pending must be non-negative")
        self._local = threading.local()
        self.thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="congine_validation",
            initializer=self._init_worker,
        )
        self.capacity = max_workers + max_pending
        self._sem = threading.BoundedSemaphore(self.capacity)
        self._lock = threading.Lock()
        self._in_flight = 0
        self._rejected_total = 0
        if register_atexit:
            atexit.register(self.shutdown)

    # ------------------------------------------------------------------ #
    # Worker-thread tagging (for re-entrancy detection)
    # ------------------------------------------------------------------ #
    def _init_worker(self) -> None:
        self._local.is_worker = True

    def _on_worker_thread(self) -> bool:
        return getattr(self._local, "is_worker", False)

    # ------------------------------------------------------------------ #
    # Public API (compatible with ValidationTimer.run_with_timeout)
    # ------------------------------------------------------------------ #
    def run_with_timeout(self, func: Callable[[], Any], timeout_ms: int) -> Any:
        """Run *func* with a millisecond timeout, shedding load when saturated.

        Args:
            func: Zero-argument callable to execute.
            timeout_ms: Timeout budget in milliseconds.

        Returns:
            Whatever *func* returns.

        Raises:
            TimeoutError: If *func* overruns the budget, OR if the pool is
                saturated (load shed) — the caller degrades either way.
        """
        # Re-entrant call from our own worker: run inline to avoid a nested
        # same-pool deadlock (best-effort timeout; CPU work is bounded upstream).
        if self._on_worker_thread():
            return func()

        future = self._acquire_and_submit(func)
        try:
            return future.result(timeout=timeout_ms / 1000.0)
        except concurrent.futures.TimeoutError as exc:
            # Permit stays held by the done-callback until the zombie finishes,
            # so sustained timeouts correctly drain capacity and shed new work.
            raise TimeoutError(f"Timeout after {timeout_ms}ms") from exc

    async def run_with_timeout_async(
        self, func: Callable[[], Any], timeout_ms: int
    ) -> Any:
        """Async-safe twin of :meth:`run_with_timeout` (audit H1/H2).

        Offloads *func* onto the same bounded pool the synchronous path uses, so
        ``async`` callers get the **identical** capacity bound and timeout —
        rather than bypassing the semaphore via a raw ``run_in_executor`` and
        unbounded-queueing. The permit is acquired non-blockingly (load shed on
        saturation) and the wait is awaited off the event loop, so a slow
        validation never stalls concurrent asyncio tasks.

        Args:
            func: Zero-argument callable to execute on the validation pool.
            timeout_ms: Timeout budget in milliseconds.

        Returns:
            Whatever *func* returns.

        Raises:
            TimeoutError: If *func* overruns the budget, OR if the pool is
                saturated (load shed), OR if the pool is already shut down.
        """
        # Re-entrancy: if we are already on a pool worker (e.g. the use case is
        # itself running inside an offloaded execute) run inline — no second
        # permit, no nested-pool deadlock. Mirrors the sync path.
        if self._on_worker_thread():
            return func()

        future = self._acquire_and_submit(func)
        try:
            return await asyncio.wait_for(
                asyncio.wrap_future(future), timeout=timeout_ms / 1000.0
            )
        except (asyncio.TimeoutError, concurrent.futures.TimeoutError) as exc:
            # As in the sync path, the permit stays held by the done-callback
            # until the zombie thread genuinely finishes, so sustained async
            # timeouts correctly drain capacity and shed new work.
            raise TimeoutError(f"Timeout after {timeout_ms}ms") from exc

    def _acquire_and_submit(
        self, func: Callable[[], Any]
    ) -> "concurrent.futures.Future[Any]":
        """Acquire a permit (shedding on saturation) and submit *func*.

        Shared by the sync and async entry points so both honour the exact same
        ``BoundedSemaphore`` capacity. The permit is released by a done-callback
        on the returned future, so a timed-out zombie keeps occupying capacity
        until it truly completes.
        """
        if not self._sem.acquire(blocking=False):
            with self._lock:
                self._rejected_total += 1
            raise TimeoutError("validation capacity exhausted (load shed)")

        with self._lock:
            self._in_flight += 1
        try:
            future = self.thread_pool.submit(func)
        except RuntimeError as exc:  # pool already shut down
            self._release()
            raise TimeoutError("validation executor unavailable") from exc

        future.add_done_callback(lambda _f: self._release())
        return future

    def _release(self) -> None:
        with self._lock:
            self._in_flight -= 1
        self._sem.release()

    # ------------------------------------------------------------------ #
    # Observability / lifecycle
    # ------------------------------------------------------------------ #
    @property
    def in_flight(self) -> int:
        """Number of validations currently submitted (running or queued)."""
        with self._lock:
            return self._in_flight

    @property
    def rejected_total(self) -> int:
        """Cumulative count of load-shed (rejected) validations."""
        with self._lock:
            return self._rejected_total

    def shutdown(self, wait: bool = False) -> None:
        """Shut the underlying pool down (idempotent)."""
        self.thread_pool.shutdown(wait=wait)
