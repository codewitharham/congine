"""Dependency-injection container (Layer 5)."""

from __future__ import annotations

import asyncio
import contextlib
import threading
import weakref
from typing import TYPE_CHECKING, Any, ClassVar, Dict, Optional, Sequence
from dataclasses import fields, replace

import httpx

from congine_core.config import CongineConfig, ContractSource, DeploymentMode
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


def _teardown_components(
    sync_worker: Any,
    schema_storage: Any,
    event_bus: Any,
    validation_executor: Any,
) -> None:
    """Best-effort, non-blocking teardown for a deferred (evicted) container.

    Invoked by :func:`weakref.finalize` on an arbitrary thread once the container
    is unreferenced. Uses ``drain=False`` so a slow/unreachable control plane
    cannot stall the finalizer, and suppresses per-component errors so one failing
    component cannot block the others or escape the finalizer. Takes the components
    as arguments (never the container) so it holds no strong reference back to it.
    """
    if sync_worker is not None:
        with contextlib.suppress(Exception):
            sync_worker.stop()
    with contextlib.suppress(Exception):
        schema_storage.stop()
    with contextlib.suppress(Exception):
        event_bus.stop(drain=False)
    with contextlib.suppress(Exception):
        validation_executor.shutdown(wait=False)


class ServiceContainer:
    """Assemble and own the full Congine object graph."""

    _default_instance: ClassVar[Optional["ServiceContainer"]] = None
    _default_lock: ClassVar[threading.Lock] = threading.Lock()

    # Track instances via an insertion-ordered dict acting as a bounded LRU cache
    _tenant_registry: ClassVar[Dict[str, "ServiceContainer"]] = {}
    _tenant_lock: ClassVar[threading.Lock] = threading.Lock()

    # Safe multi-tenant boundary limit to guarantee resource constraints under load
    _MAX_TENANTS: ClassVar[int] = 128

    # Monotonic count of tenant-container evictions (observability, audit P0-1).
    _evicted_total: ClassVar[int] = 0

    @classmethod
    def get_default(cls) -> "ServiceContainer":
        """Return the lazily-initialised, process-wide shared container (audit C1).

        Raises :class:`CongineConfigurationError` in ``multi_tenant`` deployment
        mode — callers must pass an explicit ``container=`` or use
        :meth:`for_tenant` (FIX-05). The mode is re-read from the environment on
        every call so flipping ``CONGINE_DEPLOYMENT_MODE`` disables the shared
        singleton immediately, even once one has been built.

        Only that **one** variable is read on the cached path (audit Q10). This
        method is on the hot path: ``@congine_guard`` with no explicit
        ``container=`` resolves through it on *every guarded call*, and it used
        to run a full :meth:`CongineConfig.from_env` — parsing and validating
        ~47 variables per request, and able to raise mid-request even when a
        perfectly good singleton already existed.
        """
        if cls._deployment_mode_is_multi_tenant():
            raise CongineConfigurationError(
                "ServiceContainer.get_default() is disabled in multi_tenant mode. "
                "Pass container= explicitly per tenant, or use "
                "ServiceContainer.for_tenant(tenant_id, project_id)."
            )
        instance = cls._default_instance
        if instance is not None:
            return instance
        with cls._default_lock:
            if cls._default_instance is None:
                # Full environment parse happens ONCE, at construction.
                cls._default_instance = cls(CongineConfig.from_env())
            return cls._default_instance

    @staticmethod
    def _deployment_mode_is_multi_tenant() -> bool:
        """Cheap single-variable topology probe for :meth:`get_default`."""
        return CongineConfig.deployment_mode_from_env() is DeploymentMode.MULTI_TENANT

    @classmethod
    def for_tenant(
        cls,
        tenant_id: str,
        project_id: str,
        *,
        config: Optional[CongineConfig] = None,
        **config_overrides: Any,
    ) -> "ServiceContainer":
        """Return a registry-backed container scoped to *tenant_id* / *project_id*.

        The registry is a bounded (``_MAX_TENANTS``) insertion-ordered LRU. Recency
        is keyed on **``for_tenant()`` lookups, not validation activity**: a container
        fetched once and reused heavily still ages toward the LRU end unless it is
        looked up again. When the registry is full, the least-recently-*looked-up*
        entry is evicted.

        Eviction only *removes the registry entry* — it does **not** tear the
        container down. A caller still holding a reference to an evicted container
        keeps using it normally; its background daemons/pool are stopped lazily (via
        :func:`weakref.finalize`) once it becomes unreferenced. Teardown never runs
        while ``_tenant_lock`` is held, so one eviction cannot stall other tenants'
        lookups (audit P0-1 / H-1).

        Since audit Q5 every container arms that finalizer at construction, so the
        eviction-time call below is an idempotent no-op retained for clarity.
        """
        key = f"{tenant_id}|{project_id}"

        evicted_key: Optional[str] = None
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

            # Resource eviction pass. At capacity, remove the LRU registry entry and
            # arm *deferred* teardown. We MUST NOT call close() here: the evicted
            # container may still be referenced by a live caller, and close() both
            # tears down that live container and can block on a telemetry drain while
            # cls._tenant_lock is held (audit P0-1 / H-1).
            if len(cls._tenant_registry) >= cls._MAX_TENANTS:
                # Python 3.7+ dicts preserve insertion order; next(iter(...)) is the LRU key.
                evicted_key = next(iter(cls._tenant_registry))
                oldest_container = cls._tenant_registry.pop(evicted_key)
                cls._evicted_total += 1
                # No-op since audit Q5 (armed at construction); kept because the
                # eviction path is where the guarantee actually matters.
                oldest_container._arm_deferred_teardown()

            container = cls(config)
            cls._tenant_registry[key] = container

        # --- outside cls._tenant_lock: no teardown/blocking I/O under the lock --- #
        if evicted_key is not None:
            container.logger.warning(
                "Tenant container evicted (least-recently-looked-up); teardown "
                "deferred until it is no longer referenced",
                evicted_key=evicted_key,
                evicted_total=cls._evicted_total,
            )
        return container

    @classmethod
    def reset_default(cls) -> None:
        """Tear down and clear the shared default + all tenant containers (idempotent).

        ``close()`` runs **outside** both class locks so a slow telemetry drain
        cannot block concurrent ``get_default()`` / ``for_tenant()`` callers (P0-1).
        """
        with cls._default_lock:
            default = cls._default_instance
            cls._default_instance = None
        with cls._tenant_lock:
            tenants = list(cls._tenant_registry.values())
            cls._tenant_registry.clear()

        if default is not None:
            default.close()
        for container in tenants:
            container.close()

    @classmethod
    def evicted_total(cls) -> int:
        """Monotonic count of tenant-container evictions since process start (P0-1)."""
        return cls._evicted_total

    def __init__(self, config: CongineConfig) -> None:
        self.config = config
        # Lifecycle guards (audit P0-1): make close() idempotent and let an evicted
        # container defer teardown until it is genuinely unreferenced.
        self._closed = False
        self._close_lock = threading.Lock()
        self._finalizer: Optional[weakref.finalize] = None
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
                max_file_bytes=config.max_contract_file_bytes,
            )
        elif (
            config.contract_source is ContractSource.FILE
            and config.contracts_dir is not None
        ):
            self.contract_repository = FileContractRepository(
                contracts_dir=config.contracts_dir,
                logger=self.logger,
                max_contract_files=config.max_contract_files,
                max_file_bytes=config.max_contract_file_bytes,
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
            semantic_validation_enabled=config.semantic_validation_enabled,
            semantic_format_checking=config.semantic_format_checking,
            admission_mode=config.contract_admission,
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

        # Arm deferred teardown for EVERY container, not only evicted ones
        # (audit Q5). Construction may already have started the cache sweeper and
        # the telemetry drain thread; a container that is simply dropped — never
        # registered, never evicted, never closed — previously leaked both for
        # the life of the process, because the finalizer was armed only on the
        # eviction path. Arming here makes every container self-cleaning.
        #
        # Must be the LAST statement: the finalizer captures the sub-components,
        # so they all have to exist. A failure earlier in __init__ still leaks
        # (nothing is returned to close), which is tracked separately.
        self._arm_deferred_teardown()

    @classmethod
    def from_env(cls) -> "ServiceContainer":
        """Build a container from environment-derived configuration.

        Does not touch the network. Background daemons (telemetry drain, cache
        sweeper) start when ``start_background_services`` is True (FIX-14).
        """
        return cls(CongineConfig.from_env())

    def bootstrap(self) -> int:
        """Prime the schema cache, then optionally start the periodic sync worker.

        Refuses to run inside a running event loop (audit L6): the sync path
        drives the fetch with :func:`asyncio.run`, which would otherwise raise a
        far less actionable error deep in the call stack.
        """
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
        """Feed one observation into the drift reference window (audit M1).

        Drift is an opt-in *library capability*, not an automatic pipeline: no
        validation outcome reaches the engine unless a host calls this.
        """
        self.drift_engine.add_reference(value)

    def evaluate_drift(self, current_samples: Sequence[float]) -> "DriftResult":
        """Run the drift test and publish a ``__drift__`` event on detection (audit M1)."""
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
        """Aggregate one operational snapshot across every component (audit L2).

        Cheap and non-blocking — each component contributes a counter read, never
        I/O. ``dropped_total`` is probed rather than required: it is the one
        optional member of the event-bus surface (audit Q8).

        **Every value here is read through a port-declared member** (audit P0-01).
        The runner's counters used to be read as concrete attributes
        (``validation_executor.in_flight`` / ``.rejected_total``) that
        :class:`IValidationRunner` never declared, so an implementation that
        faithfully satisfied the port still raised ``AttributeError`` the first
        time an operator polled health. They now come from the port's own
        :meth:`IValidationRunner.health`, whose contract already specifies these
        keys. The published output keys are unchanged.
        """
        dropped_total = getattr(self.event_bus, "dropped_total", None)
        runner_health = self.validation_executor.health()
        return {
            "cache_entries": self.schema_storage.size(),
            "validation_in_flight": runner_health.get("in_flight"),
            "validation_rejected_total": runner_health.get("rejected_total"),
            "telemetry_queue_depth": self.event_bus.queue_depth(),
            "telemetry_dropped_total": dropped_total()
            if callable(dropped_total)
            else 0,
            "sync_running": (
                self.sync_worker.is_running() if self.sync_worker is not None else False
            ),
            "drift_reference_samples": self.drift_engine.sample_count,
            "breaker_state": self.circuit_breaker.state,
            # Refused policy updates (audit P0-03/P0-04), read through the use
            # case's declared admission_status() surface rather than its private
            # counters — the same principle as the runner fix above.
            **self.sync_contracts_usecase.admission_status(),
        }

    def _arm_deferred_teardown(self) -> None:
        """Schedule bounded teardown for when this container is no longer referenced.

        Called at the end of :meth:`__init__` for every container (audit Q5), and
        again — idempotently — when a container is evicted from the tenant
        registry. Cheap and non-blocking: registers a :func:`weakref.finalize`
        and performs NO teardown now, which is what makes it safe to call while
        ``_tenant_lock`` is held.

        The finalizer captures the sub-components (never ``self``) so it cannot
        keep the container alive, and :meth:`close` detaches it so an explicitly
        closed container never tears down twice.
        """
        with self._close_lock:
            if self._closed or self._finalizer is not None:
                return
            self._finalizer = weakref.finalize(
                self,
                _teardown_components,
                self.sync_worker,
                self.schema_storage,
                self.event_bus,
                self.validation_executor,
            )

    def close(self) -> None:
        """Idempotent teardown. Explicit callers keep the full ``drain=True`` flush.

        Teardown runs outside any class lock. If a deferred-teardown finalizer was
        armed (this container was evicted), it is detached so teardown happens once.
        """
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        if self.sync_worker is not None:
            self.sync_worker.stop()
        self.schema_storage.stop()
        self.event_bus.stop(drain=True)
        self.validation_executor.shutdown(wait=False)
        finalizer = self._finalizer
        self._finalizer = None
        if finalizer is not None:
            finalizer.detach()

    def __enter__(self) -> "ServiceContainer":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
