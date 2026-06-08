"""Tests for :class:`FileContractRepository` — the local-first contract source.

Covers the canonical happy path (a directory of JSON files round-trips through
``fetch_active_contracts``), envelope vs. flat shapes, malformed-file
robustness, and ServiceContainer routing via ``CONGINE_CONTRACT_SOURCE=file``.
"""

from __future__ import annotations

import asyncio
import json
import os

import pytest

from congine_core.adapters.dependency_injection import ServiceContainer
from congine_core.config import CongineConfig, Region
from congine_core.infrastructure.file_contract_repository import (
    FileContractRepository,
)
from tests.conftest import FakeLogger


def _config(**kw) -> CongineConfig:
    base = dict(
        base_url="http://localhost:8080",
        api_key=None,
        project_id=None,
        tenant_id=None,
        region=Region.US,
    )
    base.update(kw)
    return CongineConfig(**base)


def test_reads_flat_contract_files(tmp_path) -> None:
    (tmp_path / "a.json").write_text(
        json.dumps({"id": "a", "schema": {"type": "object"}})
    )
    (tmp_path / "b.json").write_text(json.dumps({"id": "b", "schema": {}}))
    repo = FileContractRepository(str(tmp_path), logger=FakeLogger())
    contracts = asyncio.run(repo.fetch_active_contracts())
    ids = sorted(c["id"] for c in contracts)
    assert ids == ["a", "b"]


def test_reads_contract_envelope(tmp_path) -> None:
    payload = {
        "contracts": [
            {"id": "x", "schema": {}},
            {"id": "y", "schema": {}},
        ]
    }
    (tmp_path / "bundle.json").write_text(json.dumps(payload))
    repo = FileContractRepository(str(tmp_path), logger=FakeLogger())
    contracts = asyncio.run(repo.fetch_active_contracts())
    assert sorted(c["id"] for c in contracts) == ["x", "y"]


def test_skips_malformed_files_and_logs(tmp_path) -> None:
    (tmp_path / "ok.json").write_text(json.dumps({"id": "ok", "schema": {}}))
    (tmp_path / "broken.json").write_text("not-json{")  # parse error
    logger = FakeLogger()
    repo = FileContractRepository(str(tmp_path), logger=logger)
    contracts = asyncio.run(repo.fetch_active_contracts())
    assert [c["id"] for c in contracts] == ["ok"]
    assert "WARNING" in logger.levels()


def test_missing_directory_returns_empty(tmp_path) -> None:
    missing = str(tmp_path / "does-not-exist")
    logger = FakeLogger()
    repo = FileContractRepository(missing, logger=logger)
    assert asyncio.run(repo.fetch_active_contracts()) == []
    assert "WARNING" in logger.levels()


def test_recursive_discovery(tmp_path) -> None:
    (tmp_path / "team").mkdir()
    (tmp_path / "team" / "nested.json").write_text(
        json.dumps({"id": "nested", "schema": {}})
    )
    repo = FileContractRepository(str(tmp_path), logger=FakeLogger())
    contracts = asyncio.run(repo.fetch_active_contracts())
    assert [c["id"] for c in contracts] == ["nested"]


def test_save_snapshot_is_noop(tmp_path) -> None:
    logger = FakeLogger()
    repo = FileContractRepository(str(tmp_path), logger=logger)
    repo.save_snapshot([{"id": "anything", "schema": {}}])
    # No file should be written; logger should record a debug breadcrumb.
    assert [p for p in os.listdir(str(tmp_path))] == []
    assert "DEBUG" in logger.levels()


def test_load_snapshot_returns_none(tmp_path) -> None:
    repo = FileContractRepository(str(tmp_path))
    assert repo.load_snapshot() is None


# --- Container routing via CONGINE_CONTRACT_SOURCE ----------------------- #


def test_container_wires_file_repo_when_source_is_file(tmp_path) -> None:
    cfg = _config(contract_source="file", contracts_dir=str(tmp_path))
    container = ServiceContainer(cfg)
    try:
        assert isinstance(container.contract_repository, FileContractRepository)
    finally:
        container.close()


def test_container_defaults_to_http_repo() -> None:
    from congine_core.infrastructure.http_contract_repository import (
        HttpContractRepository,
    )

    cfg = _config()  # contract_source defaults to "http"
    container = ServiceContainer(cfg)
    try:
        assert isinstance(container.contract_repository, HttpContractRepository)
    finally:
        container.close()


def test_file_repo_round_trips_via_bootstrap(tmp_path) -> None:
    (tmp_path / "c.json").write_text(
        json.dumps({"id": "c", "schema": {"type": "object"}})
    )
    cfg = _config(contract_source="file", contracts_dir=str(tmp_path))
    container = ServiceContainer(cfg)
    try:
        loaded = container.bootstrap()
        assert loaded == 1
        assert container.schema_storage.get("c") == {"type": "object"}
    finally:
        container.close()


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
