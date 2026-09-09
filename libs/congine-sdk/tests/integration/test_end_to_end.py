"""End-to-end integration tests exercising the full wired container."""

from __future__ import annotations

import asyncio
from typing import Dict, List

import pytest

from congine_core.adapters.guard import congine_guard
from congine_core.config import CongineConfig, FailMode, Region
from congine_core.exceptions import CongineSyncError, CongineValidationError
from congine_core.adapters.dependency_injection import ServiceContainer
from tests.conftest import FakeContractRepository, FakeEventBus

_SCHEMA = {
    "required": ["score", "label"],
    "properties": {
        "score": {"type": "number", "min": 0, "max": 1},
        "label": {"type": "string", "enum": ["pos", "neg"]},
    },
}


def _config(fail_mode: FailMode = FailMode.DEGRADE) -> CongineConfig:
    return CongineConfig(
        base_url="http://control-plane.invalid",
        api_key="k",
        project_id="p",
        tenant_id="t",
        region=Region.US,
        allow_cleartext=True,  # cleartext test control plane (declared)
        validation_timeout_ms=200,
        fail_mode=fail_mode,
        cache_capacity=10,
        cache_ttl_seconds=300,
    )


def _container(fail_mode: FailMode = FailMode.DEGRADE) -> ServiceContainer:
    """Real container, but with telemetry captured by a fake bus (no network)."""
    container = ServiceContainer(_config(fail_mode))
    container.event_bus.stop(drain=False)  # kill the real shipping worker
    fake_bus = FakeEventBus()
    container.event_bus = fake_bus
    container.validate_contract_usecase.event_bus = fake_bus
    return container


def test_sync_guard_pass_end_to_end() -> None:
    container = _container()
    try:
        container.schema_storage.put("sentiment-v1", _SCHEMA, 300)

        @congine_guard("sentiment-v1", container=container)
        def analyze(text: str) -> Dict[str, object]:
            return {"score": 0.9, "label": "pos"}

        out = analyze("great!")
        assert out["output"] == {"score": 0.9, "label": "pos"}
        assert out["validation_result"].is_pass()
        assert len(container.event_bus.published) == 1
    finally:
        container.close()


def test_sync_guard_fail_end_to_end() -> None:
    container = _container()
    try:
        container.schema_storage.put("sentiment-v1", _SCHEMA, 300)

        @congine_guard("sentiment-v1", container=container)
        def analyze() -> Dict[str, object]:
            return {"score": 5, "label": "maybe"}  # range + enum breach

        out = analyze()
        result = out["validation_result"]
        assert not result.is_pass()
        rules = {b.rule for b in result.breaches}
        assert "RANGE_CHECK" in rules and "ENUM_VALUES" in rules
    finally:
        container.close()


def test_async_guard_end_to_end() -> None:
    container = _container()
    try:
        container.schema_storage.put("c", _SCHEMA, 300)

        @congine_guard("c", container=container)
        async def analyze() -> Dict[str, object]:
            return {"score": 0.5, "label": "neg"}

        out = asyncio.run(analyze())
        assert out["validation_result"].is_pass()
    finally:
        container.close()


def test_strict_mode_raises_end_to_end() -> None:
    container = _container(FailMode.STRICT)
    try:
        container.schema_storage.put("c", _SCHEMA, 300)

        @congine_guard("c", container=container)
        def analyze() -> Dict[str, object]:
            return {"score": 9, "label": "pos"}

        with pytest.raises(CongineValidationError):
            analyze()
        # Telemetry still captured before the raise.
        assert len(container.event_bus.published) == 1
    finally:
        container.close()


# --------------------------------------------------------------------------- #
# bootstrap() cache priming
# --------------------------------------------------------------------------- #


class _FakeRepoOnline:
    saved: List[Dict] = []

    async def fetch_active_contracts(self) -> List[Dict]:
        return [
            {"id": "c1", "version": "1", "schema": _SCHEMA},
            {"id": "c2", "version": "1", "schema": _SCHEMA},
        ]

    def load_snapshot(self):  # pragma: no cover - not used online
        return None

    def save_snapshot(self, contracts: List[Dict]) -> None:
        type(self).saved = contracts


class _FakeRepoOffline:
    async def fetch_active_contracts(self) -> List[Dict]:
        raise CongineSyncError("offline")

    def load_snapshot(self) -> List[Dict]:
        return [{"id": "snap-1", "version": "1", "schema": _SCHEMA}]

    def save_snapshot(self, contracts: List[Dict]) -> None:  # pragma: no cover
        raise AssertionError("save_snapshot must not run on offline boot")


def test_bootstrap_primes_cache_online() -> None:
    container = _container()
    try:
        container.sync_contracts_usecase.contract_repository = _FakeRepoOnline()
        loaded = container.bootstrap()
        assert loaded == 2
        assert container.schema_storage.exists("c1")
        assert container.schema_storage.exists("c2")
        assert len(_FakeRepoOnline.saved) == 2
    finally:
        container.close()


def test_bootstrap_falls_back_to_snapshot() -> None:
    container = _container()
    try:
        container.sync_contracts_usecase.contract_repository = _FakeRepoOffline()
        loaded = container.bootstrap()
        assert loaded == 1
        assert container.schema_storage.exists("snap-1")
    finally:
        container.close()


def test_container_context_manager_closes() -> None:
    with ServiceContainer(_config()) as container:
        container.event_bus.stop(drain=False)
        container.schema_storage.put("c", _SCHEMA, 300)
        assert container.schema_storage.exists("c")
    # After exit, the cache sweeper is stopped.
    assert container.schema_storage._stop_event.is_set()


def test_bootstrap_starts_background_worker_when_enabled() -> None:
    cfg = CongineConfig(
        base_url="http://control-plane.invalid",
        api_key="k",
        project_id="p",
        tenant_id="t",
        region=Region.US,
        allow_cleartext=True,  # cleartext test control plane (declared)
        sync_enabled=True,
        sync_interval_seconds=300,
    )
    container = ServiceContainer(cfg)
    container.event_bus.stop(drain=False)
    fake_bus = FakeEventBus()
    container.event_bus = fake_bus
    container.validate_contract_usecase.event_bus = fake_bus
    container.sync_contracts_usecase.contract_repository = FakeContractRepository(
        contracts=[{"id": "c1", "version": "1", "schema": _SCHEMA}]
    )
    try:
        container.bootstrap()
        assert container.sync_worker._thread is not None
        assert container.sync_worker._thread.is_alive()
        assert container.schema_storage.exists("c1")
    finally:
        container.close()
    assert not container.sync_worker._thread.is_alive()


def test_semantic_validation_enabled_uses_composite() -> None:
    from congine_core.domain.validator import CompositeValidator

    cfg = CongineConfig(
        base_url="http://control-plane.invalid",
        api_key="k",
        project_id="p",
        tenant_id="t",
        region=Region.US,
        allow_cleartext=True,  # cleartext test control plane (declared)
        semantic_validation_enabled=True,
    )
    container = ServiceContainer(cfg)
    container.event_bus.stop(drain=False)
    fake_bus = FakeEventBus()
    container.event_bus = fake_bus
    container.validate_contract_usecase.event_bus = fake_bus
    try:
        assert isinstance(container.validator, CompositeValidator)
        json_schema = {
            "type": "object",
            "required": ["score"],
            "properties": {"score": {"type": "number"}},
        }
        container.schema_storage.put("c", json_schema, 300)

        @congine_guard("c", container=container)
        def good() -> dict:
            return {"score": 0.5}

        @congine_guard("c", container=container)
        def bad() -> dict:
            return {"score": "high"}  # violates JSON Schema type

        assert good()["validation_result"].is_pass()
        assert not bad()["validation_result"].is_pass()
    finally:
        container.close()


def test_semantic_validation_disabled_by_default() -> None:
    from congine_core.domain.validator import LocalValidator

    container = _container()  # default config → semantic disabled
    try:
        assert isinstance(container.validator, LocalValidator)
    finally:
        container.close()


def test_langchain_handler_through_real_container() -> None:
    pytest.importorskip("langchain_core")
    from congine_core.adapters.langchain_handler import CongineCallbackHandler

    container = _container()
    try:
        container.schema_storage.put("lc-contract", {}, 300)  # permissive schema
        handler = CongineCallbackHandler("lc-contract", container=container)
        for tok in ["hel", "lo ", "there"]:
            handler.on_llm_new_token(tok, run_id="run-1")
        result = handler.on_llm_end(run_id="run-1")
        assert result is not None and result.is_pass()
        assert len(container.event_bus.published) == 1
    finally:
        container.close()
