"""Unit tests for :mod:`congine_core.usecases.sync_contracts_usecase`."""

from __future__ import annotations

from congine_core.exceptions import CongineSyncError
from congine_core.usecases.sync_contracts_usecase import SyncContractsUseCase
from tests.conftest import (
    FakeContractRepository,
    FakeLogger,
    FakeSchemaStorage,
)

_C1 = {"id": "c1", "version": "1", "schema": {"required": ["a"]}}
_C2 = {"id": "c2", "version": "1", "schema": {"required": ["b"]}}


def _usecase(storage, repo, logger) -> SyncContractsUseCase:
    return SyncContractsUseCase(
        schema_storage=storage,
        contract_repository=repo,
        logger=logger,
        cache_ttl_seconds=300,
    )


def test_sync_once_online_success() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(contracts=[_C1, _C2])
    loaded = _usecase(storage, repo, logger).sync_once()
    assert loaded == 2
    assert storage.exists("c1") and storage.exists("c2")
    assert repo.saved == [_C1, _C2]  # snapshot persisted after a live fetch


def test_sync_once_falls_back_to_snapshot() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(
        fetch_error=CongineSyncError("offline"), snapshot=[_C1]
    )
    loaded = _usecase(storage, repo, logger).sync_once()
    assert loaded == 1
    assert storage.exists("c1")
    assert repo.saved is None  # never persist a snapshot we just read back


def test_sync_once_corrupt_snapshot_returns_zero() -> None:
    # Simulates fetch failure AND a corrupt/missing snapshot (load returns None).
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(
        fetch_error=CongineSyncError("offline"), snapshot=None
    )
    loaded = _usecase(storage, repo, logger).sync_once()
    assert loaded == 0
    assert "WARNING" in logger.levels()


def test_failure_does_not_clear_existing_cache() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    storage.put("existing", {"required": ["x"]}, 300)
    repo = FakeContractRepository(
        fetch_error=CongineSyncError("offline"), snapshot=None
    )
    _usecase(storage, repo, logger).sync_once()
    # A poisoned snapshot / dead control plane must not wipe healthy entries.
    assert storage.exists("existing")


def test_partial_contracts_are_skipped() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(contracts=[_C1, {"id": "no-schema"}, {"schema": {}}])
    loaded = _usecase(storage, repo, logger).sync_once()
    assert loaded == 1
    assert storage.exists("c1")


def test_snapshot_persist_oserror_is_handled() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(contracts=[_C1], save_error=OSError("disk full"))
    loaded = _usecase(storage, repo, logger).sync_once()
    assert loaded == 1  # cache primed despite snapshot write failure
    assert "ERROR" in logger.levels()


def test_repeatable_sync_updates_in_place() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(contracts=[_C1])
    uc = _usecase(storage, repo, logger)
    uc.sync_once()
    # Second pass with an updated schema must refresh, not duplicate.
    repo._contracts = [{"id": "c1", "version": "2", "schema": {"required": ["z"]}}]
    uc.sync_once()
    assert storage.get("c1") == {"required": ["z"]}
