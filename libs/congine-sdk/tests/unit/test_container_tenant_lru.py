"""Direct tests for ``ServiceContainer.for_tenant()`` LRU eviction safety (audit P0-1).

The bug being guarded against: eviction used to call ``close()`` on the LRU
container — tearing down a container a caller may still hold (silently breaking
it) and doing so while ``_tenant_lock`` was held (stalling every other tenant).

The fix: eviction only *removes the registry entry* and arms a
``weakref.finalize`` so teardown happens lazily once the container is
unreferenced; no teardown work runs under the lock.

Test hygiene: the registry / default singleton / ``_MAX_TENANTS`` are class-level
state that leaks between tests, so an autouse fixture resets them and shrinks the
cap to 3 (rather than constructing 128 containers). ``for_tenant()`` calls
``CongineConfig.from_env()`` internally, so the environment is pinned to a local,
offline, background-service-free config.
"""

from __future__ import annotations

import contextlib
import gc
import os
import time

import pytest

from congine_core.adapters.dependency_injection import (
    ServiceContainer,
    _teardown_components,
)
from congine_core.config import CongineConfig


@pytest.fixture(autouse=True)
def _isolate_container_state(monkeypatch: pytest.MonkeyPatch):
    """Reset class-level state and pin a deterministic, offline config per test."""
    for key in [k for k in os.environ if k.startswith("CONGINE_")]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("CONGINE_BASE_URL", "http://localhost:8080")  # local: no api key
    monkeypatch.setenv("CONGINE_START_BACKGROUND_SERVICES", "false")  # no daemons
    monkeypatch.setenv("CONGINE_TELEMETRY_ENABLED", "false")  # NoOpEventBus
    monkeypatch.setattr(ServiceContainer, "_MAX_TENANTS", 3)  # auto-restored

    ServiceContainer.reset_default()
    ServiceContainer._tenant_registry.clear()
    yield
    for container in list(ServiceContainer._tenant_registry.values()):
        with contextlib.suppress(Exception):
            container.close()
    ServiceContainer._tenant_registry.clear()
    with contextlib.suppress(Exception):
        ServiceContainer.reset_default()


def test_eviction_does_not_disable_live_container() -> None:
    """A still-referenced container that gets evicted must keep working.

    With the old bug, eviction called ``c0.close()``; the next validation on the
    still-held container ran on a shut-down pool and *degraded*. The decisive
    assertion is therefore ``result.degraded is False`` — a genuinely live
    container returns a real ``pass``, not a timeout/degrade fallback.
    """
    c0 = ServiceContainer.for_tenant("t0", "p")  # keep a live reference
    ServiceContainer.for_tenant("t1", "p")
    ServiceContainer.for_tenant("t2", "p")  # registry full: [t0, t1, t2]
    ServiceContainer.for_tenant("t3", "p")  # forces eviction of the LRU entry (t0)

    assert "t0|p" not in ServiceContainer._tenant_registry  # entry evicted...
    assert c0.validation_executor.health()["capacity"] > 0  # ...but pool is alive

    c0.schema_storage.put("cid", {"type": "object"}, 300)
    result = c0.validate_contract_usecase.execute({"x": 1}, "cid", "v")

    assert result.degraded is False  # decisive: not a shut-down-pool fallback
    assert result.is_pass() is True

    c0.close()


def test_eviction_targets_least_recently_looked_up() -> None:
    """Regression guard for LRU-by-lookup ordering.

    This already passed before P0-1 (the bump-on-cache-hit path was correct); it
    is kept to ensure the eviction rewrite preserved that ordering.
    """
    ServiceContainer.for_tenant("t0", "p")
    ServiceContainer.for_tenant("t1", "p")
    ServiceContainer.for_tenant("t2", "p")  # [t0, t1, t2]
    ServiceContainer.for_tenant("t0", "p")  # bump t0 -> [t1, t2, t0]
    ServiceContainer.for_tenant("t3", "p")  # evict genuine LRU = t1

    registry = ServiceContainer._tenant_registry
    assert "t1|p" not in registry  # the least-recently-looked-up was evicted
    assert "t0|p" in registry  # the bumped one survived
    assert "t3|p" in registry


def test_for_tenant_eviction_returns_promptly() -> None:
    """Teardown must be off the lock's critical path.

    Deterministic (no real network): the victim's event bus is replaced with one
    whose ``stop()`` blocks ~3s. With the old code the eviction ``close()`` ran
    synchronously under ``_tenant_lock`` and the triggering ``for_tenant()`` would
    block for ~3s. With the fix it only arms a finalizer, so it returns instantly.
    """

    class _SlowStopBus:
        def publish(self, event: object) -> None: ...
        def stop(self, drain: bool = True) -> None:
            time.sleep(3.0)

        def queue_depth(self) -> int:
            return 0

        def dropped_total(self) -> int:
            return 0

    victim = ServiceContainer.for_tenant("t0", "p")
    ServiceContainer.for_tenant("t1", "p")
    ServiceContainer.for_tenant("t2", "p")  # full: [t0, t1, t2]; t0 is LRU
    victim.event_bus = _SlowStopBus()  # captured by the finalizer at eviction time

    start = time.perf_counter()
    ServiceContainer.for_tenant("t3", "p")  # triggers eviction of the victim
    elapsed = time.perf_counter() - start

    assert elapsed < 1.0, f"for_tenant blocked on eviction teardown: {elapsed:.2f}s"

    # Cleanup: detach the armed finalizer so the 3s stop never runs during GC.
    if victim._finalizer is not None:
        victim._finalizer.detach()


def test_close_is_idempotent() -> None:
    """Calling close() more than once must be safe and not double-stop into a raise."""
    c = ServiceContainer.for_tenant("solo", "p")
    c.close()
    c.close()  # second call is a no-op
    assert c._closed is True


def test_evicted_container_explicit_close_detaches_finalizer() -> None:
    """An explicitly-closed, evicted container must not tear down twice.

    close() detaches the armed finalizer, so when the last reference drops the
    finalizer does not fire a second teardown.
    """
    victim = ServiceContainer.for_tenant("v0", "p")
    ServiceContainer.for_tenant("v1", "p")
    ServiceContainer.for_tenant("v2", "p")  # full: [v0, v1, v2]
    ServiceContainer.for_tenant("v3", "p")  # evict v0 -> arms its finalizer

    assert victim._finalizer is not None and victim._finalizer.alive
    victim.close()
    assert victim._finalizer is None  # detached by close()

    del victim
    gc.collect()  # finalizer detached -> no second teardown, no error


def test_evicted_unreferenced_container_is_torn_down() -> None:
    """No leak: once the last reference to an evicted container drops, its deferred
    teardown fires and genuinely stops its components.

    Observes the container's *real* components rather than substituting a spy.
    Since audit Q5 the finalizer is armed in ``__init__``, so it captures the
    components the container constructed — reassigning ``container.event_bus``
    afterwards would not be seen by it.
    """
    c0 = ServiceContainer.for_tenant("t0", "p")
    # Hold the components (not the container) so teardown is observable after
    # the container itself has been collected.
    storage = c0.schema_storage
    executor = c0.validation_executor
    finalizer = c0._finalizer
    assert finalizer is not None and finalizer.alive

    ServiceContainer.for_tenant("t1", "p")
    ServiceContainer.for_tenant("t2", "p")  # full
    ServiceContainer.for_tenant("t3", "p")  # evicts t0

    assert "t0|p" not in ServiceContainer._tenant_registry
    assert finalizer.alive  # eviction alone must NOT tear anything down

    del c0
    gc.collect()

    assert not finalizer.alive  # the finalizer fired
    assert storage._stop_event.is_set()  # cache sweeper signalled to stop
    with pytest.raises(RuntimeError):  # pool genuinely shut down
        executor.thread_pool.submit(lambda: None)


def test_teardown_is_bounded_and_error_suppressing() -> None:
    """The deferred teardown must never drain and never raise.

    It runs on an arbitrary thread during garbage collection, so a slow control
    plane must not stall it (``drain=False``) and one failing component must not
    prevent the others from stopping or let an exception escape a finalizer.
    """
    seen: dict[str, object] = {}

    class _RaisingStorage:
        def stop(self) -> None:
            raise RuntimeError("storage teardown exploded")

    class _Bus:
        def stop(self, drain: bool = True) -> None:
            seen["drain"] = drain

    class _Executor:
        def shutdown(self, wait: bool = False) -> None:
            seen["wait"] = wait

    _teardown_components(None, _RaisingStorage(), _Bus(), _Executor())

    assert seen["drain"] is False  # bounded: never waits on the control plane
    assert seen["wait"] is False  # never blocks on in-flight validations
    # ...and the raising component did not stop the others or escape.


def test_plain_container_arms_teardown_at_construction() -> None:
    """Audit Q5: every container self-cleans, not only evicted ones.

    A container that is never registered, never evicted and never closed used to
    arm no finalizer at all, leaking its sweeper and drain threads for the life
    of the process.
    """
    container = ServiceContainer(CongineConfig.from_env())
    storage = container.schema_storage
    finalizer = container._finalizer
    assert finalizer is not None and finalizer.alive

    del container
    gc.collect()

    assert not finalizer.alive
    assert storage._stop_event.is_set()


def test_eviction_counter_increments() -> None:
    """The monotonic eviction counter is observable for operators."""
    before = ServiceContainer.evicted_total()
    ServiceContainer.for_tenant("t0", "p")
    ServiceContainer.for_tenant("t1", "p")
    ServiceContainer.for_tenant("t2", "p")  # full
    ServiceContainer.for_tenant("t3", "p")  # one eviction
    assert ServiceContainer.evicted_total() == before + 1
