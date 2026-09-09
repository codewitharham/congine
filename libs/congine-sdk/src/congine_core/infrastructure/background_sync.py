"""Background contract-sync worker (Layer 4).

:class:`BackgroundSyncWorker` is the mechanism that periodically drives a
contract-sync policy. It runs a daemon thread that wakes every
``interval_seconds`` and calls ``sync_once``.

The collaborator is typed as the :class:`~congine_core.ports.sync_runner.ISyncRunner`
port rather than the concrete ``SyncContractsUseCase`` it is wired to in
production: infrastructure (L4) may depend on ports (L1), never on use cases
(L3). See that port's docstring for the full rationale.

The sleep is interruptible (``threading.Event.wait``) so :meth:`stop` wakes the
worker promptly, and the worker swallows any error from a sync pass so a single
failure never kills the loop.
"""

from __future__ import annotations

import atexit
import contextlib
import threading
from typing import Callable, Optional

from congine_core.exceptions import CongineLifecycleError
from congine_core.ports.logger import ILogger
from congine_core.ports.sync_runner import ISyncRunner

_WORKER_JOIN_TIMEOUT_SECONDS = 2.0


class BackgroundSyncWorker:
    """Daemon thread that periodically runs a contract-sync pass."""

    def __init__(
        self,
        sync_usecase: ISyncRunner,
        interval_seconds: float = 300,
        logger: Optional[ILogger] = None,
        run_immediately: bool = True,
        start_worker: bool = False,
    ) -> None:
        """Args:
        sync_usecase: The sync runner whose ``sync_once`` is invoked each cycle.
        interval_seconds: Seconds between sync passes.
        logger: Optional structured logger for observability.
        run_immediately: When ``True`` run one sync before the first wait.
        start_worker: When ``True`` start the daemon immediately; defaults to
            ``False`` so the container can decide (and tests stay deterministic).
        """
        self._sync_usecase = sync_usecase
        self._interval = interval_seconds
        self._logger = logger
        self._run_immediately = run_immediately
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()
        self._closed = False
        self._atexit_callback: Optional[Callable[[], None]] = None
        if start_worker:
            self.start()

    def start(self) -> None:
        """Start the daemon once; terminally stopped workers cannot restart."""
        with self._lifecycle_lock:
            if self._closed:
                raise CongineLifecycleError(
                    "BackgroundSyncWorker is closed and cannot accept new work"
                )
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_event.clear()
            thread = threading.Thread(
                target=self._run_loop,
                name="congine_background_sync",
                daemon=True,
            )
            callback = self.stop
            atexit.register(callback)
            self._atexit_callback = callback
            self._thread = thread
            try:
                thread.start()
            except BaseException:
                self._thread = None
                self._atexit_callback = None
                with contextlib.suppress(Exception):
                    atexit.unregister(callback)
                raise

    def is_running(self) -> bool:
        """Return ``True`` if the worker thread is alive."""
        with self._lifecycle_lock:
            return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        """Terminally stop the worker with a fixed, bounded join."""
        with self._lifecycle_lock:
            if self._closed:
                return
            self._closed = True
            self._stop_event.set()
            thread = self._thread
            callback = self._atexit_callback
            self._atexit_callback = None
        if callback is not None:
            with contextlib.suppress(Exception):
                atexit.unregister(callback)
        if (
            thread is not None
            and thread.is_alive()
            and thread is not threading.current_thread()
        ):
            thread.join(timeout=_WORKER_JOIN_TIMEOUT_SECONDS)

    def _run_loop(self) -> None:
        """Daemon loop: sync now (optional), then every ``interval`` seconds."""
        if self._run_immediately:
            self._safe_sync()
        while not self._stop_event.wait(self._interval):
            self._safe_sync()

    def _safe_sync(self) -> None:
        """Run one sync pass, swallowing errors so the loop never dies."""
        try:
            self._sync_usecase.sync_once()
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:  # noqa: BLE001 - loop must survive transport defects
            if self._logger is not None:
                self._logger.error(
                    "Background sync pass failed",
                    error_type=type(exc).__name__,
                )
