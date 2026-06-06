"""Tests for boot single-flight coordination (audit D-7).

The thundering-herd scenario (N Gunicorn/Uvicorn workers all calling
``bootstrap()`` at the same time) is reproduced by giving two
:class:`SyncContractsUseCase` instances the same lock path and asserting that
only one of them issues a network fetch — the other falls through to the
on-disk snapshot the first one just wrote.
"""

from __future__ import annotations

import asyncio

import pytest

from congine_core.usecases.sync_contracts_usecase import SyncContractsUseCase
from tests.conftest import FakeContractRepository, FakeLogger, FakeSchemaStorage


# Skip the whole module if portalocker is unavailable — single-flight degrades
# gracefully but cannot be exercised without it.
portalocker = pytest.importorskip("portalocker")


def _build(boot_lock: str, contracts: list, snapshot: list | None = None):
    repo = FakeContractRepository(contracts=contracts, snapshot=snapshot)
    return SyncContractsUseCase(
        schema_storage=FakeSchemaStorage(),
        contract_repository=repo,
        logger=FakeLogger(),
        cache_ttl_seconds=300,
        boot_lock_path=boot_lock,
    ), repo


def test_single_flight_only_one_worker_fetches(tmp_path) -> None:
    """Two workers sharing a lock — only one issues a fetch."""
    lock_path = str(tmp_path / "boot.lock")

    # Worker A primes the snapshot first by running sync_once_single_flight.
    a, repo_a = _build(
        lock_path,
        contracts=[{"id": "c1", "schema": {"type": "object"}}],
    )
    a.sync_once_single_flight()
    snapshot_after_a = repo_a.saved
    assert snapshot_after_a is not None

    # Worker B comes up holding *the same lock file* but pre-acquires it from
    # outside the use case, simulating "the other worker is still inside its
    # fetch window." The use-case's non-blocking acquire should fail and fall
    # through to load_snapshot.
    blocking_lock = portalocker.Lock(
        lock_path,
        mode="a",
        timeout=0,
        flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
    )
    blocking_lock.acquire()
    try:
        b, repo_b = _build(
            lock_path,
            contracts=[{"id": "c2", "schema": {"type": "different"}}],
            snapshot=snapshot_after_a,
        )
        # B's fetch_active_contracts SHOULD NOT be called — verify by replacing
        # it with a probe that flags if invoked.
        called = {"fetch": 0}

        async def tripwire_fetch() -> list:
            called["fetch"] += 1
            return []

        repo_b.fetch_active_contracts = tripwire_fetch  # type: ignore[assignment]
        loaded = b.sync_once_single_flight()
        # B loaded one contract — from the snapshot A wrote.
        assert loaded == 1
        assert called["fetch"] == 0
    finally:
        blocking_lock.release()


def test_single_flight_degrades_when_no_lock_path(tmp_path) -> None:
    """Without a boot_lock_path the method behaves like plain sync_once."""
    a, _repo = _build(
        boot_lock=None,  # type: ignore[arg-type]
        contracts=[{"id": "c1", "schema": {}}],
    )
    assert a.sync_once_single_flight() == 1


def test_single_flight_async_only_one_worker_fetches(tmp_path) -> None:
    """Async twin of the sync test."""
    lock_path = str(tmp_path / "boot.lock")

    async def run() -> None:
        a, repo_a = _build(
            lock_path,
            contracts=[{"id": "c1", "schema": {"type": "object"}}],
        )
        await a.sync_once_single_flight_async()
        snapshot_after_a = repo_a.saved
        assert snapshot_after_a is not None

        blocking_lock = portalocker.Lock(
            lock_path,
            mode="a",
            timeout=0,
            flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
        )
        blocking_lock.acquire()
        try:
            b, repo_b = _build(
                lock_path,
                contracts=[{"id": "c2", "schema": {}}],
                snapshot=snapshot_after_a,
            )
            called = {"fetch": 0}

            async def tripwire_fetch() -> list:
                called["fetch"] += 1
                return []

            repo_b.fetch_active_contracts = tripwire_fetch  # type: ignore[assignment]
            loaded = await b.sync_once_single_flight_async()
            assert loaded == 1
            assert called["fetch"] == 0
        finally:
            blocking_lock.release()

    asyncio.run(run())
