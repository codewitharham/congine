# CONGINE COMPONENT DEPENDENCY MAP

Generated: 2026-06-14
Based on import analysis of `libs/congine-sdk/src/congine_core/`.

---

## Dependency Graph (who imports whom)

Dependencies point **inward only** (L5 → L4 → L3 → L2 → L1 → L0). No inner layer imports an outer concrete.

```
L0  config.py ───────► exceptions.py, security_limits.py
    exceptions.py ────► (none)
    security_limits.py ► (none)
    pii_sanitize.py ──► (stdlib re only)

L1  ports/contract_repository.py   ► (typing only)
    ports/event_bus.py             ► domain.models.TelemetryEvent  [TYPE_CHECKING only]
    ports/logger.py                ► (typing only)
    ports/schema_storage.py        ► (typing only)
    ports/semantic_validator.py    ► domain.models.BreachDetail    [TYPE_CHECKING only]
    ports/validation_runner.py     ► (typing only)
    ports/circuit_breaker.py       ► (typing only)

L2  domain/models.py     ► (stdlib only)
    domain/validator.py  ► domain.models, security_limits, re2,
                           ports.semantic_validator [TYPE_CHECKING]
                           (defines in-domain IValidator strategy seam)

L3  usecases/validate_contract_usecase.py
        ► config.FailMode, domain.models, domain.validator.IValidator,
          exceptions, pii_sanitize,
          ports.{event_bus, logger, schema_storage, validation_runner}
    usecases/sync_contracts_usecase.py
        ► exceptions, ports.{contract_repository, logger, schema_storage},
          ports.circuit_breaker [TYPE_CHECKING], portalocker

L4  infrastructure/bounded_executor.py    ► (stdlib: threading, concurrent.futures, asyncio)
    infrastructure/lfu_cache.py           ► (stdlib)
    infrastructure/circuit_breaker.py     ► (stdlib)
    infrastructure/queue_event_bus.py     ► config, ports.logger, httpx,
                                            domain.models + ports.circuit_breaker [TYPE_CHECKING]
    infrastructure/http_contract_repository.py ► config, exceptions, ports.logger, httpx, portalocker
    infrastructure/file_contract_repository.py ► ports.logger (yaml optional/lazy)
    infrastructure/jsonschema_validator.py ► domain.models, exceptions, pii_sanitize,
                                            security_limits, jsonschema
    infrastructure/ks_drift.py            ► domain.models (numpy lazy)
    infrastructure/logger.py              ► (stdlib)
    infrastructure/background_sync.py     ► ports.logger, usecases.sync [TYPE_CHECKING]
    infrastructure/noop_event_bus.py      ► domain.models [TYPE_CHECKING]
    infrastructure/timer.py  (DEPRECATED) ► (stdlib)

L5  adapters/dependency_injection.py (ServiceContainer)
        ► config, exceptions, domain.{models,validator}, httpx,
          ALL of infrastructure/*, BOTH usecases, ports.{contract_repository,event_bus}
    adapters/guard.py        ► adapters.dependency_injection, exceptions
    adapters/langchain_handler.py ► (lazy) dependency_injection, config, exceptions,
                                    security_limits, domain.models; langchain_core optional
```

Key observations:
- **L1 stays import-light.** Cross-layer value-object references (`TelemetryEvent`, `BreachDetail`) are `TYPE_CHECKING`-only, so importing a port never drags in L2 at runtime.
- **`IValidator` is the one sanctioned in-domain protocol** (`domain/validator.py:293-301`), not in `ports/`. It is the rule-vs-composite strategy seam.
- **`ServiceContainer` is the only composition root** — the single module that imports concretes from every layer.

---

## Public API Surface (`congine_core/__init__.py` `__all__`)

| Symbol | Layer | What it is / intended caller |
| --- | --- | --- |
| `ServiceContainer` | L5 | Composition root. Build one per process (or per tenant), `bootstrap()`, share, `close()`. |
| `congine_guard` | L5 | Decorator for host functions. The primary integration surface. |
| `CongineConfig`, `Region`, `FailMode`, `DeploymentMode` | L0 | Config object + enums; usually via `from_env()`. |
| `BreachDetail`, `ValidationResult`, `DriftResult`, `TelemetryEvent` | L2 | Immutable result/event value objects returned to callers. |
| `RuleEngine`, `LocalValidator`, `CompositeValidator` | L2 | Validator building blocks; advanced callers composing custom rule sets. |
| `ValidateContractUseCase`, `SyncContractsUseCase` | L3 | Orchestrators; advanced callers wiring their own container. |
| `LFUCache`, `HttpContractRepository`, `FileContractRepository`, `QueueEventBus`, `NoOpEventBus`, `StructuredLogger`, `BackgroundSyncWorker`, `BoundedValidationExecutor`, `CircuitBreaker`, `JsonSchemaSemanticValidator`, `KSDriftEngine` | L4 | Concrete adapters; injectable for custom wiring/tests. |
| `ICircuitBreaker`, `IContractRepository`, `IEventBus`, `ILogger`, `ISchemaStorage`, `ISemanticValidator`, `IValidationRunner` | L1 | Extension-point protocols. |
| Exception tree + Tier-2 aliases | L0 | `except CongineBaseException` guards the whole SDK. |
| `__version__` | — | Resolved from installed dist metadata; `"0.0.0+unknown"` fallback. |

**Not exported** (intentionally): `CongineCallbackHandler` (lazy via `adapters.__getattr__`, gated on `[langchain]`), `ValidationTimer` (deprecated), `IValidator` (in-domain seam), all `security_limits` constants, `pii_sanitize`.

---

## Extension Points (Ports → implementations)

| Port (L1) | Method surface | Concrete impl(s) (L4) | A new impl must provide |
| --- | --- | --- | --- |
| `ISchemaStorage` | `get`, `put(ttl)`, `clear`, `exists` | `LFUCache` (`FakeSchemaStorage` in tests) | Thread-safe TTL store; expired ⇒ absent. |
| `IContractRepository` | `async fetch_active_contracts`, `load_snapshot`, `save_snapshot` | `HttpContractRepository`, `FileContractRepository` | Offline-safe fetch (never hard-fail the use case); snapshot load/save (may be no-ops). Optional `snapshot_lock_path` property enables boot single-flight. |
| `IEventBus` | `publish` (+ `queue_depth`, `dropped_total`, `stop` used by container) | `QueueEventBus`, `NoOpEventBus` | Non-blocking publish; may drop under back-pressure. |
| `ILogger` | `info/error/warning/debug(**kwargs)` | `StructuredLogger` | Structured key-value logging. |
| `ISemanticValidator` | `validate(payload, schema) -> List[BreachDetail]` | `JsonSchemaSemanticValidator` | Full-schema validation returning flat breach list. |
| `IValidationRunner` | `capacity`, `run_with_timeout`, `run_with_timeout_async`, `health` | `BoundedValidationExecutor` (`ImmediateTimer` in tests) | Capacity bound + deadline + re-entrancy + async twin. |
| `ICircuitBreaker` | `state`, `allow`, `record_success`, `record_failure` | `CircuitBreaker` | CLOSED/OPEN/HALF_OPEN state machine. |
| `IValidator` (in-domain) | `validate(payload, schema) -> ValidationResult` | `LocalValidator`, `CompositeValidator` | A validation strategy. |

All ports are `@runtime_checkable` `Protocol`s, so any structural match satisfies them — tests use plain fakes (`tests/conftest.py`) that neither import nor subclass the protocols.

---

## Wiring Map (`ServiceContainer.__init__`, `dependency_injection.py:132-259`)

Read as: **"When X is configured, port Y is implemented by Z."**

```
logger              := StructuredLogger(level=log_level,
                                        log_safe_fields=effective_log_safe_fields())   # auto-redacts on non-local
validation_executor := BoundedValidationExecutor(max_workers, max_pending,
                                                  register_atexit=start_background_services)
schema_storage      := LFUCache(capacity, ttl, sweep_interval,
                                start_sweeper=start_background_services)
circuit_breaker     := CircuitBreaker(failure_threshold, cooldown_seconds)

contract_repository :=
    if local_contracts_dir set            -> FileContractRepository(local_contracts_dir)   # STANDALONE: no sync worker
    elif contract_source=="file" & dir    -> FileContractRepository(contracts_dir)
    else                                  -> HttpContractRepository(config, logger)

event_bus :=
    if not telemetry_enabled              -> NoOpEventBus()                                 # no thread, no socket
    else                                  -> QueueEventBus(config, queue/batch/retry/backoff,
                                                client_factory= httpx.Client(timeout=control_plane_http_timeout_seconds),
                                                circuit_breaker, start_worker=start_background_services)

semantic_validator  := JsonSchemaSemanticValidator(max_breaches, format_checking, jsonschema_draft)
drift_engine        := KSDriftEngine(threshold=drift_threshold, max_samples=drift_sample_limit)

validator :=
    if semantic_validation_enabled        -> CompositeValidator(LocalValidator(), semantic_validator)
    else                                  -> LocalValidator()

validate_contract_usecase := ValidateContractUseCase(schema_storage, validator, event_bus, logger,
                                timer=validation_executor, timeout_ms=validation_timeout_ms,
                                fail_mode, max_payload_bytes, max_schema_bytes)

sync_contracts_usecase    := SyncContractsUseCase(schema_storage, contract_repository, logger,
                                cache_ttl_seconds, circuit_breaker,
                                boot_lock_path = contract_repository.snapshot_lock_path (if present))

sync_worker :=
    if standalone (local_contracts_dir)   -> None                                          # the 4 call sites guard for None
    else                                  -> BackgroundSyncWorker(sync_contracts_usecase, interval,
                                                run_immediately=False, start_worker=False)  # started by bootstrap() iff sync_enabled
```

### Config knob → concrete (the "no dead-configurable" contract)

Every `CongineConfig` field is threaded to its concrete (guarded by `tests/unit/test_config_wiring.py`). Notable ones often missed:
- `cache_sweep_interval_seconds` → `LFUCache(sweep_interval=…)`
- `control_plane_http_timeout_seconds` → both `HttpContractRepository` (per-request `AsyncClient`) and `QueueEventBus` `client_factory`
- `jsonschema_draft` → `JsonSchemaSemanticValidator` (fail-closed on unknown dialect)
- `snapshot_lock_timeout_seconds` → `HttpContractRepository._snapshot_lock`
- `start_background_services` → gates the executor atexit hook, cache sweeper, and telemetry drain thread (FIX-14)

### Lifecycle ownership

`ServiceContainer.close()` (`dependency_injection.py:346-351`) tears down, in order: `sync_worker.stop()` (if any) → `schema_storage.stop()` → `event_bus.stop(drain=True)` → `validation_executor.shutdown(wait=False)`. The container also supports `with ServiceContainer(cfg) as c:`.

### Singletons / registries

- `get_default()` — lazy double-checked process-wide singleton (`dependency_injection.py:51-70`); **raises** in `multi_tenant` mode.
- `for_tenant()` — bounded (128) insertion-ordered registry acting as LRU-by-lookup (`dependency_injection.py:72-118`); see `01_SYSTEM_STATE.md` debt #2.
- `reset_default()` — tears down default + all tenant containers.
