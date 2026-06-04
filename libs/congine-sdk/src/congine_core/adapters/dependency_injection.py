"""Dependency-injection container (Layer 5).

:class:`ServiceContainer` is the composition root. It instantiates every layer
bottom-up — infrastructure, then domain, then use cases — wiring concrete
implementations into the abstractions each upper layer depends on. No globals
are used; all dependencies flow through constructors.
"""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Optional, Sequence

from congine_core.config import CongineConfig
from congine_core.domain.models import TelemetryEvent
from congine_core.domain.validator import CompositeValidator, LocalValidator
from congine_core.infrastructure.background_sync import BackgroundSyncWorker
from congine_core.infrastructure.bounded_executor import BoundedValidationExecutor
from congine_core.infrastructure.http_contract_repository import HttpContractRepository
from congine_core.infrastructure.jsonschema_validator import (
    JsonSchemaSemanticValidator,
)
from congine_core.infrastructure.ks_drift import KSDriftEngine
from congine_core.infrastructure.lfu_cache import LFUCache
from congine_core.infrastructure.logger import StructuredLogger
from congine_core.infrastructure.queue_event_bus import QueueEventBus
from congine_core.usecases.sync_contracts_usecase import SyncContractsUseCase
from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.domain.models import DriftResult


class ServiceContainer:
    """Assemble and own the full Congine object graph."""

    # Process-wide shared default (C1): one container — and therefore one cache,
    # one telemetry worker, one validation pool — backs every guard that is not
    # given an explicit container. Guarded against the per-decoration spawn that
    # would otherwise leak threads and never prime its cache.
    _default_instance: ClassVar[Optional["ServiceContainer"]] = None
    _default_lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_default(cls) -> "ServiceContainer":
        """Return the lazily-initialised, process-wide shared container.

        Thread-safe via double-checked locking. Built from
        :meth:`CongineConfig.from_env`, which raises
        :class:`CongineConfigurationError` on incomplete configuration — there is
        no silent boot.

        Returns:
            The singleton :class:`ServiceContainer` shared by all default guards.
        """
        if cls._default_instance is None:
            with cls._default_lock:
                if cls._default_instance is None:
                    cls._default_instance = cls.from_env()
        return cls._default_instance

    @classmethod
    def reset_default(cls) -> None:
        """Tear down and clear the shared default container (idempotent).

        Primarily for tests and graceful process shutdown; closes background
        resources before dropping the reference.
        """
        with cls._default_lock:
            if cls._default_instance is not None:
                cls._default_instance.close()
                cls._default_instance = None

    def __init__(self, config: CongineConfig) -> None:
        """Wire all layers top-to-bottom from *config*.

        Args:
            config: The validated runtime configuration.
        """
        self.config = config

        # --- Layer 4: Infrastructure (concrete implementations) --------- #
        self.logger = StructuredLogger("congine", level=config.log_level)
        # Security posture warning (H4): cleartext control plane leaks the API
        # key + telemetry. Hard enforcement is opt-in via require_https.
        if not config.is_local_base_url() and not config.base_url.lower().startswith(
            "https://"
        ):
            self.logger.warning(
                "base_url is not HTTPS; API key and telemetry are sent in cleartext",
                base_url=config.base_url,
            )
        # Bounded, load-shedding pool (H1) — also the off-loop executor for the
        # async guard (H2). Exposes run_with_timeout (ValidationTimer-compatible).
        self.validation_executor = BoundedValidationExecutor(
            max_workers=config.validation_max_workers,
            max_pending=config.validation_max_pending,
        )
        self.schema_storage = LFUCache(
            capacity=config.cache_capacity,
            ttl_seconds=config.cache_ttl_seconds,
        )
        self.contract_repository = HttpContractRepository(config, self.logger)
        self.event_bus = QueueEventBus(config=config, logger=self.logger)
        self.semantic_validator = JsonSchemaSemanticValidator()
        self.drift_engine = KSDriftEngine(
            threshold=config.drift_threshold,
            max_samples=config.drift_sample_limit,
        )

        # --- Layer 2: Domain (pure business logic) ---------------------- #
        # Rule-engine validation by default; when semantic validation is
        # enabled, compose it with the jsonschema validator via Constructor DI.
        rule_validator = LocalValidator()  # default six rules
        if config.semantic_validation_enabled:
            self.validator = CompositeValidator(
                rule_validator=rule_validator,
                semantic_validator=self.semantic_validator,
            )
        else:
            self.validator = rule_validator

        # --- Layer 3: Use cases (orchestration) ------------------------- #
        self.validate_contract_usecase = ValidateContractUseCase(
            schema_storage=self.schema_storage,
            validator=self.validator,
            event_bus=self.event_bus,
            logger=self.logger,
            timer=self.validation_executor,
            timeout_ms=config.validation_timeout_ms,
            fail_mode=config.fail_mode,
        )
        self.sync_contracts_usecase = SyncContractsUseCase(
            schema_storage=self.schema_storage,
            contract_repository=self.contract_repository,
            logger=self.logger,
            cache_ttl_seconds=config.cache_ttl_seconds,
        )

        # --- Background sync worker (started on demand) ----------------- #
        self.sync_worker = BackgroundSyncWorker(
            self.sync_contracts_usecase,
            interval_seconds=config.sync_interval_seconds,
            logger=self.logger,
            run_immediately=False,
            start_worker=False,
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

        Delegates to :meth:`SyncContractsUseCase.sync_once` (online fetch →
        snapshot fallback → cache prime → snapshot persist). When
        ``config.sync_enabled`` is set, also starts the periodic background sync
        worker so the cache is kept fresh.

        Must be called from a synchronous context; from inside a running event
        loop use :meth:`bootstrap_async` instead (this raises a clear error
        rather than the opaque ``asyncio.run`` failure).

        Returns:
            The number of contracts loaded into the cache by the initial sync.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass  # no running loop — safe to drive asyncio.run
        else:
            raise RuntimeError(
                "bootstrap() cannot run inside an event loop; await bootstrap_async()"
            )
        loaded = self.sync_contracts_usecase.sync_once()
        if self.config.sync_enabled:
            self.start_background_sync()
        return loaded

    async def bootstrap_async(self) -> int:
        """Async-safe cache priming for callers already inside an event loop.

        Returns:
            The number of contracts loaded into the cache by the initial sync.
        """
        loaded = await self.sync_contracts_usecase.sync_once_async()
        if self.config.sync_enabled:
            self.start_background_sync()
        return loaded

    def start_background_sync(self) -> None:
        """Start the periodic background contract-sync worker (idempotent)."""
        self.sync_worker.start()

    # ------------------------------------------------------------------ #
    # Drift detection (M1 — wires the KS engine to telemetry)
    # ------------------------------------------------------------------ #
    def record_drift_sample(self, value: float) -> None:
        """Add one observation to the drift engine's reference window."""
        self.drift_engine.add_reference(value)

    def evaluate_drift(self, current_samples: Sequence[float]) -> "DriftResult":
        """Run a drift check; on detected drift, log + publish telemetry.

        Args:
            current_samples: The current window to compare against the reference.

        Returns:
            The :class:`DriftResult`. Requires the optional ``numpy`` extension
            (``congine-sdk[stats]``); see :meth:`KSDriftEngine.detect`.
        """
        result = self.drift_engine.detect(current_samples)
        if result.drift_detected:
            self.logger.warning(
                "Distribution drift detected",
                statistic=result.statistic,
                p_value=result.p_value,
            )
            self.event_bus.publish(
                TelemetryEvent(
                    contract_id="__drift__",
                    contract_version="n/a",
                    status="drift",
                    duration_ms=0.0,
                    breach_details=[
                        {
                            "statistic": result.statistic,
                            "p_value": result.p_value,
                            "n_reference": result.n_reference,
                            "n_sample": result.n_sample,
                        }
                    ],
                )
            )
        return result

    def health(self) -> Dict[str, Any]:
        """Return a lightweight operational snapshot (L2 — observability)."""
        return {
            "cache_entries": self.schema_storage.size(),
            "validation_in_flight": self.validation_executor.in_flight,
            "validation_rejected_total": self.validation_executor.rejected_total,
            "telemetry_queue_depth": self.event_bus.queue_depth(),
            "sync_running": self.sync_worker.is_running(),
            "drift_reference_samples": self.drift_engine.sample_count,
        }

    def close(self) -> None:
        """Release background resources (sync worker, cache sweeper, bus, timer).

        Idempotent. Use for clean teardown of per-tenant containers; the event
        bus is flushed before its worker stops so buffered telemetry is shipped.
        """
        self.sync_worker.stop()
        self.schema_storage.stop()
        self.event_bus.stop(drain=True)
        self.validation_executor.shutdown(wait=False)

    def __enter__(self) -> "ServiceContainer":
        """Support ``with ServiceContainer(...) as c:`` usage."""
        return self

    def __exit__(self, *_exc: object) -> None:
        """Release resources on context-manager exit."""
        self.close()
