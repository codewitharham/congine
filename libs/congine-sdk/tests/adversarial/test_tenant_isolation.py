"""Adversarial tests for multi-tenant container isolation (FIX-05)."""

from __future__ import annotations

import pytest

from congine_core.adapters.dependency_injection import ServiceContainer
from congine_core.config import CongineConfig, CongineConfigurationError, DeploymentMode, Region


def _base_config(**overrides) -> CongineConfig:
    data = dict(
        base_url="http://localhost:8080",
        api_key="k",
        project_id="p",
        tenant_id="t",
        region=Region.US,
        start_background_services=False,
    )
    data.update(overrides)
    return CongineConfig(**data)


def test_multi_tenant_disables_get_default(monkeypatch: pytest.MonkeyPatch) -> None:
    ServiceContainer.reset_default()
    monkeypatch.setenv("CONGINE_DEPLOYMENT_MODE", "multi_tenant")
    monkeypatch.setenv("CONGINE_BASE_URL", "http://localhost:8080")
    try:
        with pytest.raises(CongineConfigurationError):
            ServiceContainer.get_default()
    finally:
        ServiceContainer.reset_default()
        monkeypatch.delenv("CONGINE_DEPLOYMENT_MODE", raising=False)


def test_for_tenant_isolates_cache() -> None:
    ServiceContainer.reset_default()
    try:
        c1 = ServiceContainer.for_tenant(
            "tenant-a",
            "proj-1",
            config=_base_config(tenant_id="tenant-a", project_id="proj-1"),
        )
        c2 = ServiceContainer.for_tenant(
            "tenant-b",
            "proj-1",
            config=_base_config(tenant_id="tenant-b", project_id="proj-1"),
        )
        c1.schema_storage.put("shared-id", {"properties": {"a": {"type": "string"}}}, 300)
        assert c2.schema_storage.get("shared-id") is None
        assert c1 is not c2
    finally:
        ServiceContainer.reset_default()
