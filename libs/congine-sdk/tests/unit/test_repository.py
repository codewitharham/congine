"""Unit tests for
:mod:`congine_core.infrastructure.http_contract_repository`.
"""

from __future__ import annotations
from types import SimpleNamespace

import json
import os
from typing import Callable

import httpx
import pytest

from congine_core.config import CongineConfig, Region
from congine_core.exceptions import CongineSyncError
from congine_core.infrastructure import http_contract_repository as repo_mod
from congine_core.infrastructure.http_contract_repository import (
    HttpContractRepository,
)
from tests.conftest import FakeLogger


def _config() -> CongineConfig:
    return CongineConfig(
        base_url="http://cp.test",
        api_key="key-123",
        project_id="proj",
        tenant_id="tenant",
        region=Region.US,
        allow_cleartext=True,  # cleartext test control plane (declared)
    )


@pytest.fixture
def patch_async_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[Callable[[httpx.Request], httpx.Response]], None]:
    """Return an installer that routes the repo's AsyncClient via MockTransport."""

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        transport = httpx.MockTransport(handler)
        original = httpx.AsyncClient

        def factory(*args: object, **kwargs: object) -> httpx.AsyncClient:
            kwargs.pop("transport", None)
            return original(*args, transport=transport, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(repo_mod.httpx, "AsyncClient", factory)

    return install


async def test_fetch_active_contracts_success(patch_async_client) -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = request.headers
        captured["url"] = str(request.url)
        return httpx.Response(
            200, json={"contracts": [{"id": "c1", "version": "1", "schema": {}}]}
        )

    patch_async_client(handler)
    repo = HttpContractRepository(_config())
    contracts = await repo.fetch_active_contracts()

    assert contracts == [{"id": "c1", "version": "1", "schema": {}}]
    assert captured["url"] == "http://cp.test/api/v1/contracts/active"
    assert captured["headers"]["X-API-Key"] == "key-123"
    assert captured["headers"]["X-Project-ID"] == "proj"
    assert captured["headers"]["X-Tenant-ID"] == "tenant"


async def test_fetch_non_2xx_raises_sync_error(patch_async_client) -> None:
    patch_async_client(lambda req: httpx.Response(500, text="nope"))
    repo = HttpContractRepository(_config())
    with pytest.raises(CongineSyncError):
        await repo.fetch_active_contracts()


async def test_fetch_transport_error_raises_sync_error(patch_async_client) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    patch_async_client(handler)
    repo = HttpContractRepository(_config())
    with pytest.raises(CongineSyncError):
        await repo.fetch_active_contracts()


async def test_fetch_missing_key_raises_sync_error(patch_async_client) -> None:
    patch_async_client(lambda req: httpx.Response(200, json={"wrong": []}))
    repo = HttpContractRepository(_config())
    with pytest.raises(CongineSyncError):
        await repo.fetch_active_contracts()


def _config_with_dir(tmp_path) -> CongineConfig:
    return CongineConfig(
        base_url="http://cp.test",
        api_key="key-123",
        project_id="proj",
        tenant_id="tenant",
        region=Region.US,
        allow_cleartext=True,  # cleartext test control plane (declared)
        snapshot_dir=str(tmp_path),
    )


def test_snapshot_round_trip(tmp_path) -> None:
    repo = HttpContractRepository(_config_with_dir(tmp_path))
    contracts = [{"id": "c1", "version": "1", "schema": {"x": 1}}]
    repo.save_snapshot(contracts)

    assert os.path.exists(repo._snapshot_path)
    assert repo.load_snapshot() == contracts
    body = json.loads(open(repo._snapshot_path, encoding="utf-8").read())
    assert body["contracts"] == contracts
    assert "fetched_at" in body


def test_snapshot_path_is_tenant_scoped(tmp_path) -> None:
    # Different tenant/project → different snapshot file (C2: no cross-tenant).
    cfg_a = CongineConfig(
        base_url="http://cp.test",
        api_key="k",
        project_id="proj",
        tenant_id="tenant-A",
        region=Region.US,
        allow_cleartext=True,  # cleartext test control plane (declared)
        snapshot_dir=str(tmp_path),
    )
    cfg_b = CongineConfig(
        base_url="http://cp.test",
        api_key="k",
        project_id="proj",
        tenant_id="tenant-B",
        region=Region.US,
        allow_cleartext=True,  # cleartext test control plane (declared)
        snapshot_dir=str(tmp_path),
    )
    repo_a = HttpContractRepository(cfg_a)
    repo_b = HttpContractRepository(cfg_b)
    assert repo_a._snapshot_path != repo_b._snapshot_path
    repo_a.save_snapshot([{"id": "a", "schema": {}}])
    # Tenant B sees no snapshot — it is isolated.
    assert repo_b.load_snapshot() is None


def test_load_snapshot_missing_returns_none(tmp_path) -> None:
    assert HttpContractRepository(_config_with_dir(tmp_path)).load_snapshot() is None


def test_load_snapshot_corrupt_returns_none(tmp_path) -> None:
    repo = HttpContractRepository(_config_with_dir(tmp_path))
    os.makedirs(repo._snapshot_dir, exist_ok=True)
    with open(repo._snapshot_path, "w", encoding="utf-8") as fh:
        fh.write("{ not json")
    assert repo.load_snapshot() is None


def test_load_snapshot_bad_envelope_returns_none(tmp_path) -> None:
    repo = HttpContractRepository(_config_with_dir(tmp_path))
    os.makedirs(repo._snapshot_dir, exist_ok=True)
    # Valid JSON, wrong shape (contracts not a list).
    with open(repo._snapshot_path, "w", encoding="utf-8") as fh:
        json.dump({"version": "1.0", "contracts": {"oops": True}}, fh)
    assert repo.load_snapshot() is None


def test_validate_envelope_variants() -> None:
    v = HttpContractRepository._validate_envelope
    assert v("not a dict") is None
    assert v({"contracts": "nope"}) is None
    assert v({"contracts": []}) is None  # empty → None
    assert v({"contracts": [{"id": "a"}, "junk", 5]}) == [{"id": "a"}]


def test_default_snapshot_dir_is_per_user() -> None:
    path = repo_mod._default_snapshot_dir()
    assert isinstance(path, str)
    assert "congine" in path
    assert path != repo_mod.tempfile.gettempdir()  # not the world-shared root


def test_load_refuses_foreign_owned_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    logger = FakeLogger()
    repo = HttpContractRepository(_config_with_dir(tmp_path), logger=logger)
    os.makedirs(repo._snapshot_dir, exist_ok=True)
    with open(repo._snapshot_path, "w", encoding="utf-8") as fh:
        json.dump({"contracts": [{"id": "x", "schema": {}}]}, fh)
    monkeypatch.setattr(
        HttpContractRepository, "_owned_by_current_user", staticmethod(lambda p: False)
    )
    assert repo.load_snapshot() is None
    assert "WARNING" in logger.levels()


def test_owned_by_current_user_non_posix(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_os = SimpleNamespace(name="nt")
    monkeypatch.setattr(repo_mod, "os", fake_os)

    assert HttpContractRepository._owned_by_current_user("anything")


def test_save_snapshot_cleans_temp_on_error(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    repo = HttpContractRepository(_config_with_dir(tmp_path))

    def boom(*_a, **_k):
        raise RuntimeError("write failed")

    monkeypatch.setattr(repo_mod.json, "dump", boom)
    with pytest.raises(RuntimeError):
        repo.save_snapshot([{"id": "a", "schema": {}}])
    # No stray temp files left behind in the snapshot dir.
    leftovers = [p for p in os.listdir(repo._snapshot_dir) if p.endswith(".json")]
    assert leftovers == []
