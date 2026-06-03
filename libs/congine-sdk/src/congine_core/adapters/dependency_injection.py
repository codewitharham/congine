"""Dependency-injection container (Layer 5).

:class:`ServiceContainer` is the composition root. It instantiates every layer
bottom-up — infrastructure, then domain, then use cases — wiring concrete
implementations into the abstractions each upper layer depends on. No globals
are used; all dependencies flow through constructors.
"""

from __future__ import annotations

from congine_core.config import CongineConfig
from congine_core.domain.validator import LocalValidator
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
        self.event_bus = QueueEventBus(self.logger)

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
        )

    @classmethod
    def from_env(cls) -> "ServiceContainer":
        """Build a container from environment-derived configuration.

        Returns:
            A fully wired :class:`ServiceContainer`.
        """
        return cls(CongineConfig.from_env())
