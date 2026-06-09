"""Adversarial/regression tests for the remediation pass.

Covers: C1 (container singleton), C2 (snapshot symlink defence), M1 (drift
wiring), L2 (health), L6 (bootstrap loop-safety), and H4 (config validation).
"""

from __future__ import annotations

import asyncio
import os

import pytest

from congine_core.adapters.dependency_injection import ServiceContainer
from congine_core.config import CongineConfig, CongineConfigurationError, Region
from congine_core.infrastructure.http_contract_repository import (
    HttpContractRepository,
)
from tests.conftest import FakeContractRepository, FakeEventBus

pytest.importorskip("numpy")  # drift tests need the stats extra


def _config(**kw) -> CongineConfig:
    base = dict(
        base_url="http://control-plane.invalid",
        api_key="k",
        project_id="p",
        tenant_id="t",
        region=Region.US,
        start_background_services=False,
        allow_cleartext=True,
    )
    base.update(kw)
    return CongineConfig(**base)


def _container(**kw) -> ServiceContainer:
    container = ServiceContainer(_config(**kw))
    container.event_bus.stop(drain=False)
    fake = FakeEventBus()
    container.event_bus = fake
    container.validate_contract_usecase.event_bus = fake
    return container


# --- C1: process-wide singleton -------------------------------------------- #


def test_get_default_is_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    ServiceContainer.reset_default()
    built = {"n": 0}
    real_init = ServiceContainer.__init__

    def counting_init(self, config, *_a, **_kw):
        built["n"] += 1
        return real_init(self, config)

    monkeypatch.setenv("CONGINE_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv("CONGINE_DEPLOYMENT_MODE", "single_tenant")
    monkeypatch.setattr(ServiceContainer, "__init__", counting_init)
    try:
        a = ServiceContainer.get_default()
        b = ServiceContainer.get_default()
        assert a is b
        assert built["n"] == 1
    finally:
        ServiceContainer.reset_default()


def test_reset_default_clears() -> None:
    a = ServiceContainer.get_default()
    ServiceContainer.reset_default()
    b = ServiceContainer.get_default()
    assert a is not b
    ServiceContainer.reset_default()


# --- M1 + L2: drift wiring & health ---------------------------------------- #


def test_evaluate_drift_publishes_telemetry_on_drift() -> None:
    container = _container()
    try:
        container.record_drift_sample(0.0)
        for v in range(100):
            container.record_drift_sample(float(v))
        result = container.evaluate_drift([float(v) for v in range(1000, 1100)])
        assert result.drift_detected
        assert any(e.status == "drift" for e in container.event_bus.published)
    finally:
        container.close()


def test_no_drift_does_not_publish() -> None:
    container = _container()
    try:
        for v in range(100):
            container.record_drift_sample(float(v))
        result = container.evaluate_drift([float(v) for v in range(100)])
        assert not result.drift_detected
        assert container.event_bus.published == []
    finally:
        container.close()


def test_health_snapshot_shape() -> None:
    container = _container()
    try:
        container.schema_storage.put("c", {"properties": {}}, 300)
        health = container.health()
        assert health["cache_entries"] == 1
        assert health["validation_in_flight"] == 0
        assert "telemetry_queue_depth" in health
        assert health["sync_running"] is False
    finally:
        container.close()


# --- L6: bootstrap loop-safety --------------------------------------------- #


def test_bootstrap_inside_running_loop_raises() -> None:
    async def main() -> None:
        container = _container()
        container.sync_contracts_usecase.contract_repository = FakeContractRepository(
            contracts=[{"id": "c1", "schema": {}}]
        )
        try:
            with pytest.raises(RuntimeError):
                container.bootstrap()
            # The async variant is safe inside the loop.
            loaded = await container.bootstrap_async()
            assert loaded == 1
        finally:
            container.close()

    asyncio.run(main())


# --- H4: config validation ------------------------------------------------- #


def test_validate_missing_creds_nonlocal_raises() -> None:
    cfg = CongineConfig(
        base_url="https://cp.prod",
        api_key=None,
        project_id=None,
        tenant_id=None,
        region=Region.US,
    )
    with pytest.raises(CongineConfigurationError):
        cfg.validate()


def test_validate_local_is_exempt() -> None:
    cfg = CongineConfig(
        base_url="http://localhost:8080",
        api_key=None,
        project_id=None,
        tenant_id=None,
        region=Region.US,
    )
    cfg.validate()  # no raise


def test_validate_https_enforced_when_required() -> None:
    cfg = CongineConfig(
        base_url="http://cp.prod",
        api_key="k",
        project_id="p",
        tenant_id="t",
        region=Region.US,
        require_https=True,
    )
    with pytest.raises(CongineConfigurationError):
        cfg.validate()


# --- C2: snapshot symlink defence ------------------------------------------ #


def test_symlinked_snapshot_is_refused(tmp_path) -> None:
    cfg = _config(snapshot_dir=str(tmp_path))
    repo = HttpContractRepository(cfg)
    os.makedirs(repo._snapshot_dir, exist_ok=True)

    real = tmp_path / "real.json"
    real.write_text('{"version":"1.0","contracts":[{"id":"x","schema":{}}]}')
    try:
        os.symlink(str(real), repo._snapshot_path)
    except (OSError, NotImplementedError, AttributeError):
        pytest.skip("symlinks not permitted on this platform/user")
    # Even though the link target is valid, a symlinked snapshot is refused.
    assert repo.load_snapshot() is None


# --- H4: circuit breaker on the control-plane boundary -------------------- #


def test_bootstrap_does_not_stall_when_breaker_is_open() -> None:
    """An OPEN breaker must short-circuit bootstrap directly to the snapshot
    fallback — bootstrap() must not eat the 10s HTTP timeout per attempt."""
    import time

    container = _container()
    try:
        # Wire a slow fetch (would stall bootstrap if it ran) + a snapshot
        # ready to load. The breaker should short-circuit *before* the fetch.
        async def slow_fetch() -> list:
            await asyncio.sleep(10)
            return [{"id": "stalled", "schema": {}}]

        fake_repo = FakeContractRepository(
            contracts=None,
            snapshot=[{"id": "from-snapshot", "schema": {"type": "object"}}],
        )
        fake_repo.fetch_active_contracts = slow_fetch  # type: ignore[assignment]
        container.sync_contracts_usecase.contract_repository = fake_repo

        # Trip the breaker to OPEN — every record_failure beyond threshold is OK.
        for _ in range(container.config.breaker_failure_threshold):
            container.circuit_breaker.record_failure()
        assert container.circuit_breaker.state == "OPEN"

        started = time.perf_counter()
        loaded = container.bootstrap()
        elapsed_ms = (time.perf_counter() - started) * 1000.0

        assert loaded == 1
        # Snapshot-only path must complete in <500ms even with a 10s slow fetch.
        assert elapsed_ms < 500, f"bootstrap stalled: {elapsed_ms:.0f}ms"
        assert container.health()["breaker_state"] == "OPEN"
    finally:
        container.close()


def test_breaker_trips_open_after_consecutive_fetch_failures() -> None:
    """Repeated CongineSyncError from fetch_active_contracts must trip the
    breaker via SyncContractsUseCase.record_failure()."""
    from congine_core.exceptions import CongineSyncError

    container = _container()
    try:
        threshold = container.config.breaker_failure_threshold
        fake_repo = FakeContractRepository(
            fetch_error=CongineSyncError("boom"),
            snapshot=None,
        )
        container.sync_contracts_usecase.contract_repository = fake_repo

        for _ in range(threshold):
            container.sync_contracts_usecase.sync_once()

        assert container.circuit_breaker.state == "OPEN"
        assert container.health()["breaker_state"] == "OPEN"
    finally:
        container.close()


def test_breaker_success_resets_on_successful_fetch() -> None:
    container = _container()
    try:
        # Simulate one failure shy of the threshold, then a success.
        threshold = container.config.breaker_failure_threshold
        for _ in range(threshold - 1):
            container.circuit_breaker.record_failure()
        # Now a successful fetch should reset.
        fake_repo = FakeContractRepository(
            contracts=[{"id": "ok", "schema": {}}],
        )
        container.sync_contracts_usecase.contract_repository = fake_repo
        container.sync_contracts_usecase.sync_once()
        assert container.circuit_breaker.state == "CLOSED"
    finally:
        container.close()
