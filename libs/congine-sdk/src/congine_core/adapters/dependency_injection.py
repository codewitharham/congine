"""Dependency-injection container (Layer 5).

:class:`ServiceContainer` is the composition root. It instantiates every layer
bottom-up — infrastructure, then domain, then use cases — wiring concrete
implementations into the abstractions each upper layer depends on. No globals
are used; all dependencies flow through constructors.
"""

from __future__ import annotations

import asyncio
from typing import Dict, List, Optional

from congine_core.config import CongineConfig
from congine_core.domain.validator import LocalValidator
from congine_core.exceptions import CongineSyncError
from congine_core.infrastructure.http_contract_repository import HttpContractRepository
from congine_core.infrastructure.lfu_cache import LFUCache
from congine_core.infrastructure.logger import StructuredLogger
from congine_core.infrastructure.queue_event_bus import QueueEventBus
from congine_core.infrastructure.timer import ValidationTimer
from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase


class ServiceContainer:
    """Assemble and own the full Congine object graph."""

    def __init__(self, config: CongineConfig) -> None:
        """Wire all layers top-to-bottom from *config*.

        Args:
            config: The validated runtime configuration.
        """
        self.config = config

        # --- Layer 4: Infrastructure (concrete implementations) --------- #
        self.logger = StructuredLogger("congine")
        self.timer = ValidationTimer()
        self.schema_storage = LFUCache(
            capacity=config.cache_capacity,
            ttl_seconds=config.cache_ttl_seconds,
        )
        self.contract_repository = HttpContractRepository(config, self.logger)
        self.event_bus = QueueEventBus(config=config, logger=self.logger)

        # --- Layer 2: Domain (pure business logic) ---------------------- #
        self.validator = LocalValidator()  # default six rules

        # --- Layer 3: Use cases (orchestration) ------------------------- #
        self.validate_contract_usecase = ValidateContractUseCase(
            schema_storage=self.schema_storage,
            validator=self.validator,
            event_bus=self.event_bus,
            logger=self.logger,
            timer=self.timer,
            timeout_ms=config.validation_timeout_ms,
            fail_mode=config.fail_mode,
        )

    @classmethod
    def from_env(cls) -> "ServiceContainer":
        """Build a container from environment-derived configuration.

        The container is assembled side-effect-free: it does NOT touch the
        network. Call :meth:`bootstrap` explicitly to prime the schema cache.

        Returns:
            A fully wired :class:`ServiceContainer`.
        """
        return cls(CongineConfig.from_env())

    def bootstrap(self) -> int:
        """Prime the schema cache from the control plane, offline-safe.

        Attempts an online fetch of the active contracts; on
        :class:`CongineSyncError` it degrades to the on-disk snapshot so a cold
        network never hard-fails boot. Each contract's schema is inserted into
        the cache, and a fresh snapshot is persisted after a successful fetch.

        Must be called from a synchronous context (it drives the async fetch via
        :func:`asyncio.run`).

        Returns:
            The number of contracts loaded into the cache.
        """
        contracts: Optional[List[Dict]] = None
        fetched = False
        try:
            contracts = asyncio.run(self.contract_repository.fetch_active_contracts())
            fetched = True
        except CongineSyncError:
            self.logger.warning("Contract fetch failed; falling back to disk snapshot")
            contracts = self.contract_repository.load_snapshot()

        if not contracts:
            self.logger.warning("No contracts available to prime cache")
            return 0

        loaded = 0
        for contract in contracts:
            contract_id = contract.get("id")
            schema = contract.get("schema")
            if contract_id and schema is not None:
                self.schema_storage.put(
                    contract_id, schema, self.config.cache_ttl_seconds
                )
                loaded += 1

        if fetched:
            try:
                self.contract_repository.save_snapshot(contracts)
            except OSError as exc:
                self.logger.error("Snapshot persist failed", error=str(exc))

        self.logger.info("Schema cache primed", count=loaded)
        return loaded

    def close(self) -> None:
        """Release background resources (cache sweeper, event bus, timer).

        Idempotent. Use for clean teardown of per-tenant containers; the event
        bus is flushed before its worker stops so buffered telemetry is shipped.
        """
        self.schema_storage.stop()
        self.event_bus.stop(drain=True)
        self.timer.shutdown(wait=False)

    def __enter__(self) -> "ServiceContainer":
        """Support ``with ServiceContainer(...) as c:`` usage."""
        return self

    def __exit__(self, *_exc: object) -> None:
        """Release resources on context-manager exit."""
        self.close()
