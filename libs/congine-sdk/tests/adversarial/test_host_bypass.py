"""Adversarial tests for localhost host parsing (FIX-01)."""

from __future__ import annotations

import pytest

from congine_core.config import CongineConfig, CongineConfigurationError, Region


def _cfg(url: str) -> CongineConfig:
    return CongineConfig(
        base_url=url,
        api_key=None,
        project_id=None,
        tenant_id=None,
        region=Region.US,
    )


def test_notlocalhost_is_not_local() -> None:
    assert not _cfg("http://notlocalhost:8080").is_local_base_url()


def test_localhost_subdomain_is_not_local() -> None:
    assert not _cfg("http://localhost.evil.com:8080").is_local_base_url()


def test_real_localhost_is_local() -> None:
    assert _cfg("http://localhost:8080").is_local_base_url()


def test_loopback_ip_is_local() -> None:
    assert _cfg("http://127.0.0.1:8080").is_local_base_url()


def test_notlocalhost_requires_credentials_on_validate() -> None:
    cfg = _cfg("http://notlocalhost:8080")
    with pytest.raises(CongineConfigurationError):
        cfg.validate()
