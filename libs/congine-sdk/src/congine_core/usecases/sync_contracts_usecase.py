"""Sync-contracts workflow (Layer 3).

:class:`SyncContractsUseCase` orchestrates priming the schema cache from the
control plane, off the validation hot path. It is offline-safe: a transport
failure or a corrupted snapshot never wipes a healthy in-memory cache and never
raises into the host application.

It depends only on Layer-1 abstractions (injected via the constructor):
:class:`ISchemaStorage`, :class:`IContractRepository`, and :class:`ILogger`.
"""

from __future__ import annotations

import asyncio
import contextlib
import random
from typing import TYPE_CHECKING, Dict, Iterator, List, Optional

from congine_core.exceptions import CongineSyncError
from congine_core.ports.contract_repository import IContractRepository
from congine_core.ports.logger import ILogger
from congine_core.ports.schema_storage import ISchemaStorage

try:  # Advisory inter-process lock for single-flight boot (audit D-7).
    import portalocker

    _PORTALOCKER_AVAILABLE = True
except ImportError:  # pragma: no cover - portalocker is a declared core dependency
    portalocker = None  # type: ignore[assignment]
    _PORTALOCKER_AVAILABLE = False

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.ports.circuit_breaker import ICircuitBreaker


class SyncContractsUseCase:
    """Prime the schema cache from active contracts (online, snapshot-safe)."""

    def __init__(
        self,
        schema_storage: ISchemaStorage,
        contract_repository: IContractRepository,
        logger: ILogger,
        cache_ttl_seconds: int = 300,
        circuit_breaker: "Optional[ICircuitBreaker]" = None,
        boot_lock_path: Optional[str] = None,
    ) -> None:
        """Constructor injection of all collaborators.

        Args:
            schema_storage: Schema cache abstraction to prime.
            contract_repository: Source of active contracts (network + snapshot).
            logger: Structured logger abstraction.
            cache_ttl_seconds: TTL applied to each cached schema.
            circuit_breaker: Optional :class:`CircuitBreaker` consulted before
                each control-plane fetch. ``None`` disables breaker integration
                (legacy / tests).
            boot_lock_path: Path to the per-scope boot-coordination lock file
                used by :meth:`sync_once_single_flight`. ``None`` disables
                single-flight coordination (the method degrades to a regular
                fetch).
        """
        self.schema_storage = schema_storage
        self.contract_repository = contract_repository
        self.logger = logger
        self.cache_ttl_seconds = cache_ttl_seconds
        self.circuit_breaker = circuit_breaker
        self.boot_lock_path = boot_lock_path

    def sync_once(self) -> int:
        """Run one full sync pass and return the number of contracts loaded.

        Online path: ``fetch_active_contracts`` → prime cache → persist snapshot.
        Degraded path: on :class:`CongineSyncError`, fall back to the on-disk
        snapshot (which itself tolerates a missing/corrupt file by returning
        ``None``). If no contracts can be obtained, the existing cache is left
        untouched and ``0`` is returned — a dead control plane or a poisoned
        snapshot never clears healthy cached schemas.

        Must be called from a synchronous context (it drives the async fetch via
        :func:`asyncio.run`).
        """
        contracts, fetched = self._fetch_sync()
        return self._apply(contracts, fetched)

    async def sync_once_async(self) -> int:
        """Async variant of :meth:`sync_once` for callers inside an event loop.

        Awaits the control-plane fetch directly instead of :func:`asyncio.run`,
        so it is safe to call from within a running asyncio loop.
        """
        contracts, fetched = await self._fetch_async()
        return self._apply(contracts, fetched)

    def load_snapshot_only(self) -> int:
        """Skip the network fetch and prime the cache from the on-disk snapshot.

        Used by :class:`ServiceContainer.bootstrap` when the circuit breaker is
        OPEN — a fast-fail path that bypasses the 10s HTTP timeout entirely.
        Returns the number of schemas loaded (``0`` if no snapshot exists).
        """
        contracts = self.contract_repository.load_snapshot()
        return self._apply(contracts, fetched=False)

    def sync_once_single_flight(self) -> int:
        """Run sync_once with N-worker boot coordination (audit D-7).

        The first worker to acquire the per-scope boot lock fetches and writes
        the snapshot; sibling workers immediately fall through to the on-disk
        snapshot the lock-holder just wrote. A small random jitter (0–0.5s)
        before the lock attempt desynchronises a deployment burst so all
        workers do not simultaneously slam the registry.

        If no ``boot_lock_path`` was injected (or :mod:`portalocker` is absent),
        this degrades to a regular :meth:`sync_once` call.

        Returns:
            The number of schemas loaded into the cache.
        """
        if self.boot_lock_path is None or not _PORTALOCKER_AVAILABLE:
            return self.sync_once()

        # Desynchronise the herd. Cheap: bounded by 500ms.
        sleep_seconds = random.uniform(0.0, 0.5)
        if sleep_seconds > 0:
            import time as _time  # local import keeps the hot path lean

            _time.sleep(sleep_seconds)

        with self._try_boot_lock() as acquired:
            if acquired:
                return self.sync_once()
            # Another worker is fetching — skip the network entirely.
            self.logger.info("Boot lock held by sibling worker; loading snapshot only")
            return self.load_snapshot_only()

    async def sync_once_single_flight_async(self) -> int:
        """Async twin of :meth:`sync_once_single_flight`.

        Uses :func:`asyncio.sleep` for the jitter so the event loop is not
        blocked, and awaits the fetch inside the held lock.
        """
        if self.boot_lock_path is None or not _PORTALOCKER_AVAILABLE:
            return await self.sync_once_async()

        sleep_seconds = random.uniform(0.0, 0.5)
        if sleep_seconds > 0:
            await asyncio.sleep(sleep_seconds)

        with self._try_boot_lock() as acquired:
            if acquired:
                return await self.sync_once_async()
            self.logger.info("Boot lock held by sibling worker; loading snapshot only")
            return self.load_snapshot_only()

    @contextlib.contextmanager
    def _try_boot_lock(self) -> "Iterator[bool]":
        """Acquire the per-scope boot lock non-blockingly; yield acquired bool."""
        assert self.boot_lock_path is not None  # caller guarded
        assert _PORTALOCKER_AVAILABLE
        # Touch the lockfile dir so portalocker can create the file.
        import os

        os.makedirs(os.path.dirname(self.boot_lock_path), exist_ok=True)
        lock = portalocker.Lock(
            self.boot_lock_path,
            mode="a",
            timeout=0,
            flags=portalocker.LOCK_EX | portalocker.LOCK_NB,
        )
        try:
            lock.acquire()
        except portalocker.exceptions.LockException:
            yield False
            return
        try:
            yield True
        finally:
            with contextlib.suppress(Exception):
                lock.release()

    def _fetch_sync(self) -> "tuple[Optional[List[Dict]], bool]":
        if not self._breaker_allows():
            self.logger.warning(
                "Circuit breaker OPEN; skipping contract fetch (snapshot fallback)"
            )
            return self.contract_repository.load_snapshot(), False
        try:
            contracts = asyncio.run(self.contract_repository.fetch_active_contracts())
        except CongineSyncError:
            self._breaker_record_failure()
            self.logger.warning("Contract fetch failed; falling back to disk snapshot")
            return self.contract_repository.load_snapshot(), False
        self._breaker_record_success()
        return contracts, True

    async def _fetch_async(self) -> "tuple[Optional[List[Dict]], bool]":
        if not self._breaker_allows():
            self.logger.warning(
                "Circuit breaker OPEN; skipping contract fetch (snapshot fallback)"
            )
            return self.contract_repository.load_snapshot(), False
        try:
            contracts = await self.contract_repository.fetch_active_contracts()
        except CongineSyncError:
            self._breaker_record_failure()
            self.logger.warning("Contract fetch failed; falling back to disk snapshot")
            return self.contract_repository.load_snapshot(), False
        self._breaker_record_success()
        return contracts, True

    def _breaker_allows(self) -> bool:
        return self.circuit_breaker is None or self.circuit_breaker.allow()

    def _breaker_record_failure(self) -> None:
        if self.circuit_breaker is not None:
            self.circuit_breaker.record_failure()

    def _breaker_record_success(self) -> None:
        if self.circuit_breaker is not None:
            self.circuit_breaker.record_success()

    def _apply(self, contracts: Optional[List[Dict]], fetched: bool) -> int:
        if not contracts:
            self.logger.warning("No contracts available; retaining current cache")
            return 0

        loaded = self._prime_cache(contracts)

        if fetched:
            try:
                self.contract_repository.save_snapshot(contracts)
            except OSError as exc:
                self.logger.error("Snapshot persist failed", error=str(exc))

        self.logger.info("Schema cache synced", count=loaded)
        return loaded

    def _prime_cache(self, contracts: List[Dict]) -> int:
        """Insert each contract's schema into the cache (each ``put`` atomic).

        Updates keys in place rather than clear-then-refill, so a concurrent
        ``get`` on the validation hot path always observes a coherent cache.
        """
        loaded = 0
        for contract in contracts:
            contract_id = contract.get("id")
            schema = contract.get("schema")
            if contract_id and schema is not None:
                self.schema_storage.put(contract_id, schema, self.cache_ttl_seconds)
                loaded += 1
        return loaded
