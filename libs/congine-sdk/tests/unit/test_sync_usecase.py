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


# --------------------------------------------------------------------------- #
# Unenforced-keyword diagnostic (audit P0-2). Load-time WARNING only; enforcement
# and cached contents are unchanged.
# --------------------------------------------------------------------------- #
_MINLENGTH_CONTRACT = {
    "id": "c",
    "schema": {"properties": {"summary": {"type": "string", "minLength": 10}}},
}


def _unenforced_warnings(logger: FakeLogger) -> list[dict]:
    return [
        kwargs
        for level, message, kwargs in logger.records
        if level == "WARNING" and "does not enforce" in message
    ]


def _sync_usecase(storage, repo, logger, *, semantic: bool = False):
    return SyncContractsUseCase(
        schema_storage=storage,
        contract_repository=repo,
        logger=logger,
        cache_ttl_seconds=300,
        semantic_validation_enabled=semantic,
    )


def test_unenforced_keyword_warns() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(contracts=[_MINLENGTH_CONTRACT])
    loaded = _sync_usecase(storage, repo, logger).sync_once()

    assert loaded == 1  # enforcement/caching unchanged: the schema is still primed
    assert storage.exists("c")
    warnings = _unenforced_warnings(logger)
    assert len(warnings) == 1
    kwargs = warnings[0]
    assert kwargs["contract_id"] == "c"
    assert "summary.minLength" in kwargs["unenforced"]  # names both field & keyword


def test_semantic_validation_enabled_suppresses_warning() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(contracts=[_MINLENGTH_CONTRACT])
    loaded = _sync_usecase(storage, repo, logger, semantic=True).sync_once()

    assert loaded == 1  # still primed; full JSON Schema now enforces minLength
    assert _unenforced_warnings(logger) == []


def test_unenforced_keyword_warning_is_deduplicated() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(contracts=[_MINLENGTH_CONTRACT])
    uc = _sync_usecase(storage, repo, logger)

    uc.sync_once()
    uc.sync_once()  # a background re-sync must NOT repeat the warning
    assert len(_unenforced_warnings(logger)) == 1

    # A changed schema for the same contract id warns again (fingerprint differs).
    repo._contracts = [
        {
            "id": "c",
            "schema": {"properties": {"summary": {"type": "string", "maxLength": 5}}},
        }
    ]
    uc.sync_once()
    warnings = _unenforced_warnings(logger)
    assert len(warnings) == 2
    assert "summary.maxLength" in warnings[1]["unenforced"]


def test_clean_contract_produces_no_warning() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    clean = {
        "id": "clean",
        "schema": {
            "type": "object",
            "required": ["label"],
            "null_forbidden": ["label"],
            "description": "ordinary contract, fully enforced vocabulary",
            "properties": {
                "label": {"type": "string", "enum": ["a", "b"], "pattern": "^.+$"},
                "score": {"type": "number", "minimum": 0, "maximum": 1},
            },
        },
    }
    repo = FakeContractRepository(contracts=[clean])
    _sync_usecase(storage, repo, logger).sync_once()

    # Anti-noise guard: if ordinary contracts warn, operators mute the channel.
    assert _unenforced_warnings(logger) == []


def test_malformed_schema_does_not_break_priming() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    contracts = [
        {"id": "props-list", "schema": {"properties": ["not", "a", "dict"]}},
        {"id": "string-spec", "schema": {"properties": {"f": "bare-string-spec"}}},
        {"id": "not-a-dict", "schema": "i-am-not-a-mapping"},
        {"id": "ok", "schema": {"required": ["x"]}},
    ]
    repo = FakeContractRepository(contracts=contracts)
    loaded = _sync_usecase(storage, repo, logger).sync_once()

    # The diagnostic never blocks priming: all four still cached, nothing raised.
    assert loaded == 4
    assert all(
        storage.exists(cid) for cid in ("props-list", "string-spec", "not-a-dict", "ok")
    )


def test_unrecognised_type_warns() -> None:
    """A type the rule engine cannot honour is warned about at load."""
    storage, logger = FakeSchemaStorage(), FakeLogger()
    contracts = [
        {"id": "bad-type", "schema": {"properties": {"a": {"type": "frobnicate"}}}},
        {
            "id": "bad-union",
            "schema": {"properties": {"b": {"type": ["string", "frobnicate"]}}},
        },
    ]
    repo = FakeContractRepository(contracts=contracts)
    loaded = _sync_usecase(storage, repo, logger).sync_once()

    assert loaded == 2  # priming is unaffected; the scan is a diagnostic only
    paths = [p for w in _unenforced_warnings(logger) for p in w["unenforced"]]
    assert "a.type" in paths
    assert "b.type" in paths


def test_union_and_null_types_do_not_warn() -> None:
    """Audit Q2: ``["string", "null"]`` is enforced, so loading it is silent."""
    storage, logger = FakeSchemaStorage(), FakeLogger()
    contracts = [
        {"id": "null-type", "schema": {"properties": {"a": {"type": "null"}}}},
        {
            "id": "union-type",
            "schema": {"properties": {"b": {"type": ["string", "null"]}}},
        },
    ]
    repo = FakeContractRepository(contracts=contracts)
    loaded = _sync_usecase(storage, repo, logger).sync_once()

    assert loaded == 2
    assert _unenforced_warnings(logger) == []
