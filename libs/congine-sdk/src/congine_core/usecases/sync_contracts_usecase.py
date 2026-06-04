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
from typing import Dict, List, Optional

from congine_core.exceptions import CongineSyncError
from congine_core.repositories.contract_repository import IContractRepository
from congine_core.repositories.logger import ILogger
from congine_core.repositories.schema_storage import ISchemaStorage


class SyncContractsUseCase:
    """Prime the schema cache from active contracts (online, snapshot-safe)."""

    def __init__(
        self,
        schema_storage: ISchemaStorage,
        contract_repository: IContractRepository,
        logger: ILogger,
        cache_ttl_seconds: int = 300,
    ) -> None:
        """Constructor injection of all collaborators.

        Args:
            schema_storage: Schema cache abstraction to prime.
            contract_repository: Source of active contracts (network + snapshot).
            logger: Structured logger abstraction.
            cache_ttl_seconds: TTL applied to each cached schema.
        """
        self.schema_storage = schema_storage
        self.contract_repository = contract_repository
        self.logger = logger
        self.cache_ttl_seconds = cache_ttl_seconds

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

    def _fetch_sync(self) -> "tuple[Optional[List[Dict]], bool]":
        try:
            contracts = asyncio.run(self.contract_repository.fetch_active_contracts())
            return contracts, True
        except CongineSyncError:
            self.logger.warning("Contract fetch failed; falling back to disk snapshot")
            return self.contract_repository.load_snapshot(), False

    async def _fetch_async(self) -> "tuple[Optional[List[Dict]], bool]":
        try:
            contracts = await self.contract_repository.fetch_active_contracts()
            return contracts, True
        except CongineSyncError:
            self.logger.warning("Contract fetch failed; falling back to disk snapshot")
            return self.contract_repository.load_snapshot(), False

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
