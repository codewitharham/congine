"""Configuration pass-through wiring tests (L0 → L5).

Confirms that the infrastructure knobs unified under ``CongineConfig`` actually
reach the concretes the :class:`ServiceContainer` builds — closing the
"dead-configurable" anti-pattern where an ``__init__`` exposed a hook that the
composition root silently dropped. Each test drives the real
``env -> CongineConfig.from_env() -> ServiceContainer`` path and asserts on the
component's runtime state.

Background services are disabled (``CONGINE_START_BACKGROUND_SERVICES=false``) so
no sweeper/drain/sync threads spawn; deployment mode is pinned single-tenant so a
sibling test that mutates the process env at import time cannot leak in.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from jsonschema import Draft7Validator, Draft202012Validator

from congine_core.adapters.dependency_injection import ServiceContainer
from congine_core.config import CongineConfig, Region
from congine_core.exceptions import CongineConfigurationError, CongineSyncError
from congine_core.infrastructure.file_contract_repository import FileContractRepository
from congine_core.infrastructure.http_contract_repository import HttpContractRepository
from congine_core.infrastructure.jsonschema_validator import JsonSchemaSemanticValidator
from congine_core.infrastructure.noop_event_bus import NoOpEventBus
from congine_core.infrastructure.queue_event_bus import QueueEventBus


def _baseline_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    """Set a deterministic, thread-free, single-tenant local env baseline."""
    env = {
        "CONGINE_BASE_URL": "http://localhost:8080",  # local -> skips creds/https policy
        "CONGINE_DEPLOYMENT_MODE": "single_tenant",
        "CONGINE_START_BACKGROUND_SERVICES": "false",
        "CONGINE_TELEMETRY_ENABLED": "true",
    }
    env.update(overrides)
    for key, value in env.items():
        monkeypatch.setenv(key, value)


# --------------------------------------------------------------------------- #
# 1. Cache tuning pass-through
# --------------------------------------------------------------------------- #
def test_cache_sweep_interval_env_propagates_to_lfu_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CONGINE_CACHE_SWEEP_INTERVAL_SECONDS must reach LFUCache.sweep_interval."""
    _baseline_env(monkeypatch, CONGINE_CACHE_SWEEP_INTERVAL_SECONDS="12.5")

    container = ServiceContainer.from_env()
    try:
        assert container.config.cache_sweep_interval_seconds == 12.5
        # The non-default cadence must be the one the cache actually runs on,
        # not the hardcoded 30.0s module default it used to be clamped to.
        assert container.schema_storage.sweep_interval == 12.5
    finally:
        container.close()


# --------------------------------------------------------------------------- #
# 2. Telemetry pipeline bounds
# --------------------------------------------------------------------------- #
def test_telemetry_env_propagates_to_queue_event_bus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All five telemetry knobs + the HTTP timeout must reach QueueEventBus."""
    _baseline_env(
        monkeypatch,
        CONGINE_TELEMETRY_QUEUE_SIZE="222",
        CONGINE_TELEMETRY_BATCH_SIZE="7",
        CONGINE_TELEMETRY_MAX_RETRIES="9",
        CONGINE_TELEMETRY_BACKOFF_BASE="1.5",
        CONGINE_TELEMETRY_BACKOFF_MAX="12.0",
        CONGINE_CONTROL_PLANE_HTTP_TIMEOUT="3.5",
    )

    container = ServiceContainer.from_env()
    try:
        bus = container.event_bus
        assert isinstance(bus, QueueEventBus)
        # Storage / retry parameters propagated down (previously locked to the
        # __init__ literals because the container never passed them).
        assert bus._queue.maxsize == 222
        assert bus._batch_size == 7
        assert bus._max_retries == 9
        assert bus._backoff_base == 1.5
        assert bus._backoff_max == 12.0

        # The control-plane timeout is baked into the injected client factory.
        client = bus._client_factory()
        try:
            assert client.timeout.read == 3.5
        finally:
            client.close()
    finally:
        container.close()


def test_telemetry_disabled_selects_noop_event_bus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """telemetry_enabled=False must swap in the thread-free NoOpEventBus."""
    _baseline_env(monkeypatch, CONGINE_TELEMETRY_ENABLED="false")

    container = ServiceContainer.from_env()
    try:
        assert isinstance(container.event_bus, NoOpEventBus)
        # The container's health()/close() surface must still work over the NoOp.
        assert container.health()["telemetry_queue_depth"] == 0
    finally:
        container.close()


# --------------------------------------------------------------------------- #
# 3. Standalone topology execution
# --------------------------------------------------------------------------- #
def test_standalone_local_contracts_dir_binds_file_repo_and_no_sync_worker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """local_contracts_dir attaches the file repo and allocates no sync worker."""
    _baseline_env(
        monkeypatch,
        CONGINE_LOCAL_CONTRACTS_DIR=str(tmp_path),
        CONGINE_TELEMETRY_ENABLED="false",
    )

    container = ServiceContainer.from_env()
    try:
        # File repository bound straight to the supplied directory.
        assert isinstance(container.contract_repository, FileContractRepository)
        assert container.contract_repository.contracts_dir == str(tmp_path)

        # Background network sync worker left entirely unallocated.
        assert container._standalone is True
        assert container.sync_worker is None

        # The lifecycle/observability surface tolerates the missing worker.
        assert container.health()["sync_running"] is False
        container.start_background_sync()  # must be a no-op, not an AttributeError
    finally:
        container.close()  # must not raise on the unallocated worker


# --------------------------------------------------------------------------- #
# 4. JSON Schema dialect switch (bonus — same config-unification change)
# --------------------------------------------------------------------------- #
def test_jsonschema_draft_env_selects_validator_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CONGINE_JSONSCHEMA_DRAFT must pick the matching jsonschema validator class."""
    _baseline_env(monkeypatch, CONGINE_JSONSCHEMA_DRAFT="draft7")

    container = ServiceContainer.from_env()
    try:
        assert container.semantic_validator._validator_cls is Draft7Validator
    finally:
        container.close()


def test_jsonschema_draft_defaults_to_2020_12(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Absent the env var, the validator defaults to Draft 2020-12."""
    _baseline_env(monkeypatch)

    container = ServiceContainer.from_env()
    try:
        assert container.semantic_validator._validator_cls is Draft202012Validator
    finally:
        container.close()


def test_unsupported_jsonschema_draft_fails_closed() -> None:
    """An unrecognised dialect raises rather than silently defaulting."""
    with pytest.raises(CongineConfigurationError):
        JsonSchemaSemanticValidator(jsonschema_draft="draft-bogus")


# --------------------------------------------------------------------------- #
# 5. HTTP repository honours the shared control-plane timeout
# --------------------------------------------------------------------------- #
async def test_http_repository_uses_configured_http_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """HttpContractRepository must build its client with the configured timeout."""
    captured: dict[str, Any] = {}

    class _SpyAsyncClient:
        """Socket-free stand-in that records the timeout and fails the request."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self) -> "_SpyAsyncClient":
            return self

        async def __aexit__(self, *exc: object) -> bool:
            return False

        async def get(self, *args: Any, **kwargs: Any) -> Any:
            raise httpx.ConnectError("no control plane in tests")

    monkeypatch.setattr(httpx, "AsyncClient", _SpyAsyncClient)

    config = CongineConfig(
        base_url="http://localhost:8080",
        api_key=None,
        project_id=None,
        tenant_id=None,
        region=Region.US,
        control_plane_http_timeout_seconds=2.5,
        start_background_services=False,
    )
    repo = HttpContractRepository(config)

    # The fetch fails closed (no server), but the client is constructed first —
    # which is all we assert: the configured timeout reached httpx.AsyncClient,
    # not the former hardcoded 10.0s literal.
    with pytest.raises(CongineSyncError):
        await repo.fetch_active_contracts()
    assert captured["timeout"] == 2.5


# --------------------------------------------------------------------------- #
# 6. Snapshot-write lock timeout is developer-configurable
# --------------------------------------------------------------------------- #
def test_snapshot_lock_timeout_env_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    """CONGINE_SNAPSHOT_LOCK_TIMEOUT must reach the config and the HTTP repo."""
    _baseline_env(monkeypatch, CONGINE_SNAPSHOT_LOCK_TIMEOUT="30.0")

    container = ServiceContainer.from_env()
    try:
        assert container.config.snapshot_lock_timeout_seconds == 30.0
        # Default (non-standalone) source is the HTTP repo, which reads it through.
        assert (
            container.contract_repository.config.snapshot_lock_timeout_seconds == 30.0
        )
    finally:
        container.close()


def test_snapshot_lock_timeout_propagates_to_portalocker(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Any
) -> None:
    """snapshot_lock_timeout_seconds must reach the portalocker advisory lock."""
    import portalocker

    captured: dict[str, Any] = {}

    class _SpyLock:
        """Records the timeout; acquire/release are inert (no real file lock)."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            captured["timeout"] = kwargs.get("timeout")

        def acquire(self) -> None:
            return None

        def release(self) -> None:
            return None

    monkeypatch.setattr(portalocker, "Lock", _SpyLock)

    config = CongineConfig(
        base_url="http://localhost:8080",
        api_key=None,
        project_id=None,
        tenant_id=None,
        region=Region.US,
        snapshot_dir=str(tmp_path),
        snapshot_lock_timeout_seconds=1.0,  # aggressive fail-fast (local NVMe)
        start_background_services=False,
    )
    repo = HttpContractRepository(config)
    repo.save_snapshot([{"id": "c1", "schema": {"type": "object"}}])

    assert captured["timeout"] == 1.0
