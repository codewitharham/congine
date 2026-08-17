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


def test_unenforced_keyword_contract_is_refused() -> None:
    """A contract whose clause no active evaluator runs is REFUSED (audit P0-04).

    Behaviour change. This test previously asserted the opposite — that such a
    contract was still primed and merely warned about, "enforcement/caching
    unchanged". That was the false-safety failure the hardening pass removes: a
    contract declaring ``minLength: 10`` was cached, validated, and reported
    ``status="pass"`` for a two-character string, with the only signal a log line
    at boot that nobody had to read.

    Refusing is strictly safer. Because a missing contract already fails closed,
    the operator gets a loud error instead of silent non-enforcement.
    """
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(contracts=[_MINLENGTH_CONTRACT])
    loaded = _sync_usecase(storage, repo, logger).sync_once()

    assert loaded == 0
    assert not storage.exists("c")  # never becomes active policy

    rejections = [
        kwargs
        for level, message, kwargs in logger.records
        if level == "ERROR" and "rejected at admission" in message
    ]
    assert len(rejections) == 1
    assert rejections[0]["contract_id"] == "c"
    assert "unsupported_keyword" in rejections[0]["codes"]
    assert "summary.minLength" in rejections[0]["paths"]


def test_semantic_validation_enabled_suppresses_warning() -> None:
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(contracts=[_MINLENGTH_CONTRACT])
    loaded = _sync_usecase(storage, repo, logger, semantic=True).sync_once()

    assert loaded == 1  # still primed; full JSON Schema now enforces minLength
    assert _unenforced_warnings(logger) == []


def test_repeated_rejection_is_counted_every_sync() -> None:
    """Rejection is reported on every pass, and is observable (audit P0-04).

    Behaviour change. This previously asserted the unenforced-keyword *warning*
    was de-duplicated across background re-syncs, so an operator saw it once at
    boot and never again. Now the contract is refused instead of warned about,
    and refusal is deliberately **not** de-duplicated: a policy update that keeps
    being rejected is an ongoing unhealthy state, not a one-off notice.

    ``admission_status()`` is the durable signal — logs rotate, counters do not.
    """
    storage, logger = FakeSchemaStorage(), FakeLogger()
    repo = FakeContractRepository(contracts=[_MINLENGTH_CONTRACT])
    uc = _sync_usecase(storage, repo, logger)

    uc.sync_once()
    uc.sync_once()

    status = uc.admission_status()
    assert status["contracts_rejected_total"] == 2
    assert status["last_admission_failure"]["contract_id"] == "c"
    assert "unsupported_keyword" in status["last_admission_failure"]["codes"]
    assert status["admission_mode"] == "strict"


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


def test_malformed_schema_is_refused_without_breaking_the_sync() -> None:
    """Malformed contracts are refused; a valid sibling still loads (audit P0-03).

    Behaviour change, but only half of it. The original intent — *a bad contract
    must never break the sync pass or raise* — is still asserted and still holds.
    What changed is the other half: it used to assert all four were **cached**,
    including a schema that is not even a mapping. Such a contract cannot be
    evaluated at all; caching it produced a permanent ``internal_error``
    degradation on every validation, reported as ``status="fail"`` with zero
    breaches. Refusing it at admission converts a silent, permanent runtime
    defect into one loud load-time error.
    """
    storage, logger = FakeSchemaStorage(), FakeLogger()
    contracts = [
        {"id": "props-list", "schema": {"properties": ["not", "a", "dict"]}},
        {"id": "string-spec", "schema": {"properties": {"f": "bare-string-spec"}}},
        {"id": "not-a-dict", "schema": "i-am-not-a-mapping"},
        {"id": "ok", "schema": {"required": ["x"]}},
    ]
    repo = FakeContractRepository(contracts=contracts)
    uc = _sync_usecase(storage, repo, logger)
    loaded = uc.sync_once()  # must not raise

    assert loaded == 1
    assert storage.exists("ok")  # the well-formed contract is unaffected
    assert not any(
        storage.exists(cid) for cid in ("props-list", "string-spec", "not-a-dict")
    )
    assert uc.admission_status()["contracts_rejected_total"] == 3


def test_unrecognised_type_contract_is_refused() -> None:
    """A type the rule engine cannot honour is REFUSED at load (audit P0-04).

    Behaviour change. Previously "priming is unaffected; the scan is a diagnostic
    only" — the contract became active and the unknown type simply disabled type
    checking for that field. The union case is worse still: a union containing an
    unrecognised member matches *every* value, so the field was entirely
    unchecked while the contract looked well-formed.

    An unknown type name is a defect in the policy, not in the output being
    judged, so it belongs at admission rather than as a runtime verdict.
    """
    storage, logger = FakeSchemaStorage(), FakeLogger()
    contracts = [
        {"id": "bad-type", "schema": {"properties": {"a": {"type": "frobnicate"}}}},
        {
            "id": "bad-union",
            "schema": {"properties": {"b": {"type": ["string", "frobnicate"]}}},
        },
    ]
    repo = FakeContractRepository(contracts=contracts)
    uc = _sync_usecase(storage, repo, logger)
    loaded = uc.sync_once()

    assert loaded == 0
    assert not storage.exists("bad-type") and not storage.exists("bad-union")

    rejections = [
        kwargs
        for level, message, kwargs in logger.records
        if level == "ERROR" and "rejected at admission" in message
    ]
    assert len(rejections) == 2
    assert all("unknown_type" in r["codes"] for r in rejections)
    assert {"a.type", "b.type"} == {p for r in rejections for p in r["paths"]}


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
