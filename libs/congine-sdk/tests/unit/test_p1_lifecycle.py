"""P1 transactional-composition and terminal-lifecycle regression tests."""

from __future__ import annotations

import atexit
import asyncio
import threading
import time
from dataclasses import replace
from typing import Any

import pytest

import congine_core.adapters.dependency_injection as di_module
from congine_core.adapters.dependency_injection import ServiceContainer
from congine_core.config import CongineConfig, Region
from congine_core.exceptions import CongineLifecycleError
from congine_core.infrastructure.background_sync import BackgroundSyncWorker
from congine_core.infrastructure.bounded_executor import BoundedValidationExecutor
from congine_core.infrastructure.lfu_cache import LFUCache
from congine_core.infrastructure.queue_event_bus import QueueEventBus


def _config(
    *, telemetry_enabled: bool = False, start_background_services: bool = False
) -> CongineConfig:
    return CongineConfig(
        base_url="http://localhost:8080",
        api_key=None,
        project_id=None,
        tenant_id=None,
        region=Region.US,
        telemetry_enabled=telemetry_enabled,
        start_background_services=start_background_services,
    )


@pytest.mark.parametrize(
    "failure_stage", ["cache", "event_bus", "semantic_validator", "finalizer"]
)
def test_container_construction_rolls_back_every_acquired_owner(
    monkeypatch: pytest.MonkeyPatch, failure_stage: str
) -> None:
    created: dict[str, Any] = {}
    real_executor = di_module.BoundedValidationExecutor
    real_cache = di_module.LFUCache
    real_bus = di_module.QueueEventBus
    real_worker = di_module.BackgroundSyncWorker

    def build_executor(*args: Any, **kwargs: Any) -> BoundedValidationExecutor:
        instance = real_executor(*args, **kwargs)
        created["executor"] = instance
        return instance

    def build_cache(*args: Any, **kwargs: Any) -> LFUCache:
        instance = real_cache(*args, **kwargs)
        created["cache"] = instance
        return instance

    def build_bus(*args: Any, **kwargs: Any) -> QueueEventBus:
        instance = real_bus(*args, **kwargs)
        created["event_bus"] = instance
        return instance

    def build_worker(*args: Any, **kwargs: Any) -> BackgroundSyncWorker:
        instance = real_worker(*args, **kwargs)
        created["sync_worker"] = instance
        return instance

    def fail(stage: str):
        def raise_failure(*_args: Any, **_kwargs: Any) -> Any:
            raise RuntimeError(stage)

        return raise_failure

    with monkeypatch.context() as patch:
        patch.setattr(di_module, "BoundedValidationExecutor", build_executor)
        patch.setattr(di_module, "LFUCache", build_cache)
        patch.setattr(di_module, "QueueEventBus", build_bus)
        patch.setattr(di_module, "BackgroundSyncWorker", build_worker)

        if failure_stage == "cache":
            patch.setattr(di_module, "LFUCache", fail(failure_stage))
        elif failure_stage == "event_bus":
            patch.setattr(di_module, "QueueEventBus", fail(failure_stage))
        elif failure_stage == "semantic_validator":
            patch.setattr(di_module, "JsonSchemaSemanticValidator", fail(failure_stage))
        else:
            patch.setattr(
                ServiceContainer, "_arm_deferred_teardown", fail(failure_stage)
            )

        with pytest.raises(RuntimeError, match=failure_stage):
            ServiceContainer(_config(telemetry_enabled=True))

    executor = created.get("executor")
    if executor is not None:
        assert executor._shutdown is True
    cache = created.get("cache")
    if cache is not None:
        assert cache._closed is True
    event_bus = created.get("event_bus")
    if event_bus is not None:
        assert event_bus.closed is True
        assert event_bus._shutdown_complete.wait(1.0)
    sync_worker = created.get("sync_worker")
    if sync_worker is not None:
        assert sync_worker._closed is True

    # A failed composition attempt must not poison later clean construction.
    with ServiceContainer(_config()) as clean:
        assert clean.closed is False


def test_lifecycle_owners_unregister_atexit_callbacks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[Any] = []
    unregistered: list[Any] = []

    monkeypatch.setattr(
        atexit, "register", lambda callback: registered.append(callback) or callback
    )
    monkeypatch.setattr(
        atexit, "unregister", lambda callback: unregistered.append(callback)
    )

    class _SyncUseCase:
        def sync_once(self) -> int:
            return 0

    executor = BoundedValidationExecutor(register_atexit=True)
    cache = LFUCache(sweep_interval=0.01, start_sweeper=True)
    bus = QueueEventBus(start_worker=True)
    worker = BackgroundSyncWorker(
        _SyncUseCase(), interval_seconds=0.01, start_worker=True
    )
    try:
        worker.stop()
        bus.stop(drain=False)
        cache.stop()
        executor.shutdown(wait=False)
    finally:
        worker.stop()
        bus.stop(drain=False)
        cache.stop()
        executor.shutdown(wait=False)

    assert len(registered) == 4
    assert {id(callback) for callback in unregistered} == {
        id(callback) for callback in registered
    }


def test_finalizer_failure_rolls_back_started_workers_and_hooks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[Any] = []
    unregistered: list[Any] = []
    created: dict[str, Any] = {}
    real_executor = di_module.BoundedValidationExecutor
    real_cache = di_module.LFUCache
    real_bus = di_module.QueueEventBus

    monkeypatch.setattr(
        atexit, "register", lambda callback: registered.append(callback) or callback
    )
    monkeypatch.setattr(
        atexit, "unregister", lambda callback: unregistered.append(callback)
    )

    def capture_executor(*args: Any, **kwargs: Any) -> BoundedValidationExecutor:
        created["executor"] = real_executor(*args, **kwargs)
        return created["executor"]

    def capture_cache(*args: Any, **kwargs: Any) -> LFUCache:
        created["cache"] = real_cache(*args, **kwargs)
        return created["cache"]

    class CapturingBus(real_bus):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            created["event_bus"] = self

    def fail_finalizer(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("finalizer")

    monkeypatch.setattr(di_module, "BoundedValidationExecutor", capture_executor)
    monkeypatch.setattr(di_module, "LFUCache", capture_cache)
    monkeypatch.setattr(di_module, "QueueEventBus", CapturingBus)
    monkeypatch.setattr(ServiceContainer, "_arm_deferred_teardown", fail_finalizer)

    with pytest.raises(RuntimeError, match="finalizer"):
        ServiceContainer(
            _config(telemetry_enabled=True, start_background_services=True)
        )

    executor = created["executor"]
    cache = created["cache"]
    event_bus = created["event_bus"]
    assert executor._shutdown is True
    assert cache._closed is True
    assert cache._sweeper is not None and not cache._sweeper.is_alive()
    assert event_bus.closed is True
    assert event_bus._shutdown_complete.wait(2.0)
    assert event_bus._daemon is not None and not event_bus._daemon.is_alive()
    assert len(registered) == 3
    assert {id(callback) for callback in unregistered} == {
        id(callback) for callback in registered
    }


def test_container_entry_points_fail_fast_after_close() -> None:
    container = ServiceContainer(_config())
    container.close()

    assert container.closed is True
    actions = [
        container.ensure_open,
        container.bootstrap,
        container.start_background_sync,
        lambda: container.record_drift_sample(1.0),
        lambda: container.evaluate_drift([1.0, 2.0]),
        container.health,
        container.__enter__,
    ]
    for action in actions:
        with pytest.raises(CongineLifecycleError, match="closed"):
            action()

    with pytest.raises(CongineLifecycleError, match="closed"):
        asyncio.run(container.bootstrap_async())


def test_context_manager_closes_container_with_open_breaker() -> None:
    config = replace(_config(), breaker_failure_threshold=1)
    with ServiceContainer(config) as container:
        container.circuit_breaker.record_failure()
        assert str(container.circuit_breaker.state) == "OPEN"
    assert container.closed is True


def test_concurrent_close_waits_for_single_teardown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    container = ServiceContainer(_config())
    original_teardown = di_module._teardown_components
    entered = threading.Event()
    release = threading.Event()
    calls = 0

    def slow_teardown(*args: Any, **kwargs: Any) -> None:
        nonlocal calls
        calls += 1
        entered.set()
        release.wait(1.0)
        original_teardown(*args, **kwargs)

    monkeypatch.setattr(di_module, "_teardown_components", slow_teardown)
    first = threading.Thread(target=container.close)
    second = threading.Thread(target=container.close)
    first.start()
    assert entered.wait(1.0)
    second.start()
    time.sleep(0.05)

    assert second.is_alive()
    release.set()
    first.join(1.0)
    second.join(1.0)

    assert not first.is_alive()
    assert not second.is_alive()
    assert calls == 1
    assert container._close_complete.is_set()


def test_stopped_resource_owners_reject_restart_or_submission() -> None:
    executor = BoundedValidationExecutor(register_atexit=False)
    executor.shutdown(wait=False)
    with pytest.raises(CongineLifecycleError):
        executor.run_with_timeout(lambda: None, 100)

    cache = LFUCache(start_sweeper=False)
    cache.stop()
    with pytest.raises(CongineLifecycleError):
        cache.start()

    class _SyncUseCase:
        def sync_once(self) -> int:
            return 0

    worker = BackgroundSyncWorker(_SyncUseCase(), start_worker=False)
    worker.stop()
    with pytest.raises(CongineLifecycleError):
        worker.start()

    bus = QueueEventBus(start_worker=False)
    bus.stop(drain=False)
    with pytest.raises(CongineLifecycleError):
        bus.start()
