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
    real_from_env = ServiceContainer.from_env.__func__

    @classmethod
    def counting(cls):
        built["n"] += 1
        return real_from_env(cls)

    monkeypatch.setattr(ServiceContainer, "from_env", counting)
    try:
        a = ServiceContainer.get_default()
        b = ServiceContainer.get_default()
        assert a is b
        assert built["n"] == 1  # built exactly once, despite two calls
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
    except OSError, NotImplementedError, AttributeError:
        pytest.skip("symlinks not permitted on this platform/user")
    # Even though the link target is valid, a symlinked snapshot is refused.
    assert repo.load_snapshot() is None
