"""Unit tests for :mod:`congine_core.config`."""

from __future__ import annotations

import dataclasses

import pytest

from congine_core.config import CongineConfig, FailMode, Region
from congine_core.exceptions import CongineConfigurationError


def test_defaults_applied() -> None:
    cfg = CongineConfig(
        base_url="http://x",
        api_key=None,
        project_id=None,
        tenant_id=None,
        region=Region.US,
    )
    assert cfg.validation_timeout_ms == 15
    assert cfg.fail_mode is FailMode.DEGRADE
    assert cfg.cache_capacity == 500
    assert cfg.cache_ttl_seconds == 300


def test_is_frozen() -> None:
    cfg = CongineConfig(
        base_url="http://x",
        api_key="k",
        project_id="p",
        tenant_id="t",
        region=Region.EU,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        cfg.base_url = "mutated"  # type: ignore[misc]


def test_enums_are_str() -> None:
    assert Region.EU == "eu"
    assert FailMode.STRICT == "strict"
    assert Region("apac") is Region.APAC


def test_from_env_reads_all(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONGINE_BASE_URL", "http://cp:9000")
    monkeypatch.setenv("CONGINE_API_KEY", "secret")
    monkeypatch.setenv("CONGINE_PROJECT_ID", "proj")
    monkeypatch.setenv("CONGINE_TENANT_ID", "tenant")
    monkeypatch.setenv("CONGINE_REGION", "eu")
    monkeypatch.setenv("CONGINE_TIMEOUT_MS", "42")
    monkeypatch.setenv("CONGINE_FAIL_MODE", "strict")
    monkeypatch.setenv("CONGINE_CACHE_CAPACITY", "99")
    monkeypatch.setenv("CONGINE_CACHE_TTL", "120")

    cfg = CongineConfig.from_env()

    assert cfg.base_url == "http://cp:9000"
    assert cfg.api_key == "secret"
    assert cfg.project_id == "proj"
    assert cfg.tenant_id == "tenant"
    assert cfg.region is Region.EU
    assert cfg.validation_timeout_ms == 42
    assert cfg.fail_mode is FailMode.STRICT
    assert cfg.cache_capacity == 99
    assert cfg.cache_ttl_seconds == 120


def test_from_env_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "CONGINE_BASE_URL",
        "CONGINE_API_KEY",
        "CONGINE_REGION",
        "CONGINE_TIMEOUT_MS",
        "CONGINE_FAIL_MODE",
        "CONGINE_CACHE_CAPACITY",
        "CONGINE_CACHE_TTL",
    ):
        monkeypatch.delenv(key, raising=False)

    cfg = CongineConfig.from_env()
    assert cfg.base_url == "http://localhost:8080"
    assert cfg.region is Region.US
    assert cfg.api_key is None


def test_from_env_bad_region(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CONGINE_REGION", "mars")
    with pytest.raises(CongineConfigurationError):
        CongineConfig.from_env()


def test_from_env_bad_fail_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONGINE_REGION", raising=False)
    monkeypatch.setenv("CONGINE_FAIL_MODE", "explode")
    with pytest.raises(CongineConfigurationError):
        CongineConfig.from_env()


def test_from_env_bad_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CONGINE_REGION", raising=False)
    monkeypatch.delenv("CONGINE_FAIL_MODE", raising=False)
    monkeypatch.setenv("CONGINE_TIMEOUT_MS", "not-a-number")
    with pytest.raises(CongineConfigurationError):
        CongineConfig.from_env()
