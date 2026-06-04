"""Unit tests for :mod:`congine_core.infrastructure.background_sync`."""

from __future__ import annotations

import threading
import time

from congine_core.infrastructure.background_sync import BackgroundSyncWorker
from tests.conftest import FakeLogger


class _CountingUseCase:
    """Counts ``sync_once`` invocations; optionally raises each time."""

    def __init__(self, raises: bool = False) -> None:
        self.calls = 0
        self._lock = threading.Lock()
        self._raises = raises

    def sync_once(self) -> int:
        with self._lock:
            self.calls += 1
        if self._raises:
            raise RuntimeError("boom")
        return self.calls


def _wait_until(predicate, timeout: float = 2.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline and not predicate():
        time.sleep(0.02)


def test_worker_runs_sync_on_interval() -> None:
    uc = _CountingUseCase()
    worker = BackgroundSyncWorker(
        uc, interval_seconds=0.05, run_immediately=True, start_worker=True
    )
    try:
        _wait_until(lambda: uc.calls >= 2)
        assert uc.calls >= 2
    finally:
        worker.stop()
    assert worker._thread is not None
    assert not worker._thread.is_alive()


def test_start_worker_false_does_not_start() -> None:
    worker = BackgroundSyncWorker(_CountingUseCase(), start_worker=False)
    assert worker._thread is None


def test_stop_is_idempotent() -> None:
    worker = BackgroundSyncWorker(
        _CountingUseCase(), interval_seconds=0.05, start_worker=True
    )
    worker.stop()
    worker.stop()  # must not raise


def test_start_is_idempotent() -> None:
    worker = BackgroundSyncWorker(
        _CountingUseCase(), interval_seconds=0.05, start_worker=True
    )
    try:
        first = worker._thread
        worker.start()  # second start is a no-op while alive
        assert worker._thread is first
    finally:
        worker.stop()


def test_loop_survives_sync_errors() -> None:
    logger = FakeLogger()
    uc = _CountingUseCase(raises=True)
    worker = BackgroundSyncWorker(
        uc,
        interval_seconds=0.05,
        logger=logger,
        run_immediately=True,
        start_worker=True,
    )
    try:
        _wait_until(lambda: uc.calls >= 2)
        assert uc.calls >= 2  # kept looping despite raising every time
        assert "ERROR" in logger.levels()
    finally:
        worker.stop()
