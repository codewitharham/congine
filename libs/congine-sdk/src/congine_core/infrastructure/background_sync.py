"""Background contract-sync worker (Layer 4).

:class:`BackgroundSyncWorker` is the *mechanism* that periodically drives the
:class:`SyncContractsUseCase` *policy* — mirroring how :class:`ValidationTimer`
(mechanism) drives :class:`ValidateContractUseCase` (policy). It runs a daemon
thread that wakes every ``interval_seconds`` and calls ``sync_once``.

The sleep is interruptible (``threading.Event.wait``) so :meth:`stop` wakes the
worker promptly, and the worker swallows any error from a sync pass so a single
failure never kills the loop.
"""

from __future__ import annotations

import atexit
import threading
from typing import TYPE_CHECKING, Optional

from congine_core.ports.logger import ILogger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.usecases.sync_contracts_usecase import (
        SyncContractsUseCase,
    )


class BackgroundSyncWorker:
    """Daemon thread that periodically runs a contract-sync pass."""

    def __init__(
        self,
        sync_usecase: "SyncContractsUseCase",
        interval_seconds: int = 300,
        logger: Optional[ILogger] = None,
        run_immediately: bool = True,
        start_worker: bool = False,
    ) -> None:
        """Args:
        sync_usecase: The use case whose ``sync_once`` is invoked each cycle.
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
        if start_worker:
            self.start()

    def start(self) -> None:
        """Start the daemon worker thread (idempotent)."""
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="congine_background_sync",
            daemon=True,
        )
        self._thread.start()
        atexit.register(self.stop)

    def is_running(self) -> bool:
        """Return ``True`` if the worker thread is alive."""
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        """Signal the worker to stop and join it (idempotent)."""
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=self._interval + 1.0)

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
        except Exception as exc:  # noqa: BLE001 - loop must survive any failure
            if self._logger is not None:
                self._logger.error("Background sync pass failed", error=str(exc))
