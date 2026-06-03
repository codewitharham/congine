"""Unit tests for
:mod:`congine_core.infrastructure.http_contract_repository`.
"""

from __future__ import annotations

import json
from typing import Callable

import httpx
import pytest

from congine_core.config import CongineConfig, Region
from congine_core.exceptions import CongineSyncError
from congine_core.infrastructure import http_contract_repository as repo_mod
from congine_core.infrastructure.http_contract_repository import (
    HttpContractRepository,
)


def _config() -> CongineConfig:
    return CongineConfig(
        base_url="http://cp.test",
        api_key="key-123",
        project_id="proj",
        tenant_id="tenant",
        region=Region.US,
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


def test_snapshot_round_trip(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    snap = tmp_path / "snap.json"
    monkeypatch.setattr(repo_mod, "_SNAPSHOT_DIR", str(tmp_path))
    monkeypatch.setattr(repo_mod, "_SNAPSHOT_PATH", str(snap))

    repo = HttpContractRepository(_config())
    contracts = [{"id": "c1", "version": "1", "schema": {"x": 1}}]
    repo.save_snapshot(contracts)

    assert snap.exists()
    assert repo.load_snapshot() == contracts
    # The persisted file carries metadata around the contracts.
    body = json.loads(snap.read_text())
    assert body["contracts"] == contracts
    assert "fetched_at" in body


def test_load_snapshot_missing_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr(repo_mod, "_SNAPSHOT_PATH", str(tmp_path / "nope.json"))
    assert HttpContractRepository(_config()).load_snapshot() is None


def test_load_snapshot_corrupt_returns_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json")
    monkeypatch.setattr(repo_mod, "_SNAPSHOT_PATH", str(bad))
    assert HttpContractRepository(_config()).load_snapshot() is None
