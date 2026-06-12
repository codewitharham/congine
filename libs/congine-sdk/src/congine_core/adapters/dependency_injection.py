"""Dependency-injection container (Layer 5)."""

from __future__ import annotations

import asyncio
import threading
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Optional, Sequence
from dataclasses import fields, replace

import httpx

from congine_core.config import CongineConfig, DeploymentMode
from congine_core.domain.models import TelemetryEvent
from congine_core.exceptions import CongineConfigurationError
from congine_core.domain.validator import CompositeValidator, LocalValidator, IValidator
from congine_core.infrastructure.background_sync import BackgroundSyncWorker
from congine_core.infrastructure.bounded_executor import BoundedValidationExecutor
from congine_core.infrastructure.circuit_breaker import CircuitBreaker
from congine_core.infrastructure.file_contract_repository import FileContractRepository
from congine_core.infrastructure.http_contract_repository import HttpContractRepository
from congine_core.infrastructure.jsonschema_validator import (
    JsonSchemaSemanticValidator,
)
from congine_core.infrastructure.ks_drift import KSDriftEngine
from congine_core.infrastructure.lfu_cache import LFUCache
from congine_core.infrastructure.logger import StructuredLogger
from congine_core.infrastructure.noop_event_bus import NoOpEventBus
from congine_core.infrastructure.queue_event_bus import QueueEventBus
from congine_core.usecases.sync_contracts_usecase import SyncContractsUseCase
from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase
from congine_core.ports.contract_repository import IContractRepository
from congine_core.ports.event_bus import IEventBus

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.domain.models import DriftResult


class ServiceContainer:
    """Assemble and own the full Congine object graph."""

    _default_instance: ClassVar[Optional["ServiceContainer"]] = None
    _default_lock: ClassVar[threading.Lock] = threading.Lock()

    # Track instances via an insertion-ordered dict acting as a bounded LRU cache
    _tenant_registry: ClassVar[Dict[str, "ServiceContainer"]] = {}
    _tenant_lock: ClassVar[threading.Lock] = threading.Lock()

    # Safe multi-tenant boundary limit to guarantee resource constraints under load
    _MAX_TENANTS: ClassVar[int] = 128

    @classmethod
    def get_default(cls) -> "ServiceContainer":
        """Return the lazily-initialised, process-wide shared container.

        Raises :class:`CongineConfigurationError` in ``multi_tenant`` deployment
        mode — callers must pass an explicit ``container=`` or use
        :meth:`for_tenant` (FIX-05).
        """
        config = CongineConfig.from_env()
        if config.deployment_mode is DeploymentMode.MULTI_TENANT:
            raise CongineConfigurationError(
                "ServiceContainer.get_default() is disabled in multi_tenant mode. "
                "Pass container= explicitly per tenant, or use "
                "ServiceContainer.for_tenant(tenant_id, project_id)."
            )
        if cls._default_instance is None:
            with cls._default_lock:
                if cls._default_instance is None:
                    cls._default_instance = cls(config)
        return cls._default_instance

    @classmethod
    def for_tenant(
        cls,
        tenant_id: str,
        project_id: str,
        *,
        config: Optional[CongineConfig] = None,
        **config_overrides: Any,
    ) -> "ServiceContainer":
        """Return a registry-backed container scoped to *tenant_id* / *project_id*."""
        key = f"{tenant_id}|{project_id}"

        with cls._tenant_lock:
            existing = cls._tenant_registry.get(key)
            if existing is not None:
                cls._tenant_registry.pop(key)
                cls._tenant_registry[key] = existing
                return existing

            if config is None:
                base = CongineConfig.from_env()
                overrides = dict(config_overrides)
                overrides.setdefault("tenant_id", tenant_id)
                overrides.setdefault("project_id", project_id)
                overrides["deployment_mode"] = DeploymentMode.MULTI_TENANT

                valid = {f.name for f in fields(CongineConfig)}
                filtered = {k: v for k, v in overrides.items() if k in valid}
                config = replace(base, **filtered)
            else:
                if config.tenant_id != tenant_id or config.project_id != project_id:
                    raise CongineConfigurationError(
                        "for_tenant config tenant_id/project_id must match arguments"
                    )

            # Resource Eviction Pass: If registry is at capacity, pop and clear the oldest entry
            if len(cls._tenant_registry) >= cls._MAX_TENANTS:
                # Python 3.7+ dictionaries preserve insertion order; next(iter(...)) fetches the LRU key
                oldest_key = next(iter(cls._tenant_registry))
                oldest_container = cls._tenant_registry.pop(oldest_key)

                # CRITICAL: Stop background loops so GC can cleanly reclaim C-level memory
                oldest_container.close()

            container = cls(config)
            cls._tenant_registry[key] = container
            return container

    @classmethod
    def reset_default(cls) -> None:
        """Tear down and clear the shared default container (idempotent)."""
        with cls._default_lock:
            if cls._default_instance is not None:
                cls._default_instance.close()
                cls._default_instance = None
        with cls._tenant_lock:
            for container in cls._tenant_registry.values():
                container.close()
            cls._tenant_registry.clear()

    def __init__(self, config: CongineConfig) -> None:
        self.config = config
        start_bg = config.start_background_services

        self.logger = StructuredLogger(
            "congine",
            level=config.log_level,
            log_safe_fields=config.effective_log_safe_fields(),
        )
        if not config.is_local_base_url() and not config.base_url.lower().startswith(
            "https://"
        ):
            self.logger.warning(
                "Cleartext control plane in use (allow_cleartext=True); "
                "API key and telemetry are sent in cleartext",
                base_url=config.base_url,
            )
        self.validation_executor = BoundedValidationExecutor(
            max_workers=config.validation_max_workers,
            max_pending=config.validation_max_pending,
            register_atexit=start_bg,
        )
        self.schema_storage = LFUCache(
            capacity=config.cache_capacity,
            ttl_seconds=config.cache_ttl_seconds,
            sweep_interval=config.cache_sweep_interval_seconds,
            start_sweeper=start_bg,
        )
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=config.breaker_failure_threshold,
            cooldown_seconds=config.breaker_cooldown_seconds,
        )
        # Standalone, offline-first topology: an explicit local_contracts_dir binds
        # a FileContractRepository straight to disk and suppresses the background
        # sync daemon (the boot prime reads the directory once). Falls back to the
        # legacy file-source switch, then to the HTTP control plane.
        self._standalone = config.local_contracts_dir is not None
        self.contract_repository: IContractRepository
        if self._standalone:
            self.contract_repository = FileContractRepository(
                contracts_dir=config.local_contracts_dir,
                logger=self.logger,
                max_contract_files=config.max_contract_files,
                max_file_bytes=config.max_schema_bytes,
            )
        elif config.contract_source == "file" and config.contracts_dir is not None:
            self.contract_repository = FileContractRepository(
                contracts_dir=config.contracts_dir,
                logger=self.logger,
                max_contract_files=config.max_contract_files,
                max_file_bytes=config.max_schema_bytes,
            )
        else:
            self.contract_repository = HttpContractRepository(config, self.logger)
        self.event_bus: IEventBus
        if not config.telemetry_enabled:
            # Offline / test mode: discard telemetry with no drain thread and no
            # network client, so nothing trails behind at shutdown (FIX).
            self.event_bus = NoOpEventBus()
        else:
            self.event_bus = QueueEventBus(
                config=config,
                logger=self.logger,
                max_queue_size=config.telemetry_queue_size,
                batch_size=config.telemetry_batch_size,
                max_retries=config.telemetry_max_retries,
                backoff_base=config.telemetry_backoff_base,
                backoff_max=config.telemetry_backoff_max,
                client_factory=lambda: httpx.Client(
                    timeout=config.control_plane_http_timeout_seconds
                ),
                circuit_breaker=self.circuit_breaker,
                start_worker=start_bg,
            )
        self.semantic_validator = JsonSchemaSemanticValidator(
            max_breaches=config.semantic_max_breaches,
            format_checking=config.semantic_format_checking,
            jsonschema_draft=config.jsonschema_draft,
        )
        self.drift_engine = KSDriftEngine(
            threshold=config.drift_threshold,
            max_samples=config.drift_sample_limit,
        )

        rule_validator = LocalValidator()
        self.validator: IValidator
        if config.semantic_validation_enabled:
            self.validator = CompositeValidator(
                rule_validator=rule_validator,
                semantic_validator=self.semantic_validator,
            )
        else:
            self.validator = rule_validator

        self.validate_contract_usecase = ValidateContractUseCase(
            schema_storage=self.schema_storage,
            validator=self.validator,
            event_bus=self.event_bus,
            logger=self.logger,
            timer=self.validation_executor,
            timeout_ms=config.validation_timeout_ms,
            fail_mode=config.fail_mode,
            max_payload_bytes=config.max_payload_bytes,
            max_schema_bytes=config.max_schema_bytes,
        )
        boot_lock_path = getattr(self.contract_repository, "snapshot_lock_path", None)
        self.sync_contracts_usecase = SyncContractsUseCase(
            schema_storage=self.schema_storage,
            contract_repository=self.contract_repository,
            logger=self.logger,
            cache_ttl_seconds=config.cache_ttl_seconds,
            circuit_breaker=self.circuit_breaker,
            boot_lock_path=boot_lock_path,
        )

        # Standalone file mode needs no periodic re-sync daemon; leave the worker
        # unallocated so no background network loop is ever created (FIX).
        self.sync_worker: Optional[BackgroundSyncWorker]
        if self._standalone:
            self.sync_worker = None
        else:
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

        Does not touch the network. Background daemons (telemetry drain, cache
        sweeper) start when ``start_background_services`` is True (FIX-14).
        """
        return cls(CongineConfig.from_env())

    def bootstrap(self) -> int:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError(
                "bootstrap() cannot run inside an event loop; await bootstrap_async()"
            )
        loaded = self.sync_contracts_usecase.sync_once_single_flight()
        if self.config.sync_enabled:
            self.start_background_sync()
        return loaded

    async def bootstrap_async(self) -> int:
        loaded = await self.sync_contracts_usecase.sync_once_single_flight_async()
        if self.config.sync_enabled:
            self.start_background_sync()
        return loaded

    def start_background_sync(self) -> None:
        if self.sync_worker is not None:
            self.sync_worker.start()

    def record_drift_sample(self, value: float) -> None:
        self.drift_engine.add_reference(value)

    def evaluate_drift(self, current_samples: Sequence[float]) -> "DriftResult":
        try:
            result = self.drift_engine.detect(current_samples)
        except ImportError as exc:
            raise CongineConfigurationError(
                "Drift detection requires the [stats] extra. "
                "Install with: pip install 'congine-sdk[stats]'"
            ) from exc
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
        dropped_total = getattr(self.event_bus, "dropped_total", None)
        return {
            "cache_entries": self.schema_storage.size(),
            "validation_in_flight": self.validation_executor.in_flight,
            "validation_rejected_total": self.validation_executor.rejected_total,
            "telemetry_queue_depth": self.event_bus.queue_depth(),
            "telemetry_dropped_total": dropped_total()
            if callable(dropped_total)
            else 0,
            "sync_running": (
                self.sync_worker.is_running() if self.sync_worker is not None else False
            ),
            "drift_reference_samples": self.drift_engine.sample_count,
            "breaker_state": self.circuit_breaker.state,
        }

    def close(self) -> None:
        if self.sync_worker is not None:
            self.sync_worker.stop()
        self.schema_storage.stop()
        self.event_bus.stop(drain=True)
        self.validation_executor.shutdown(wait=False)

    def __enter__(self) -> "ServiceContainer":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
