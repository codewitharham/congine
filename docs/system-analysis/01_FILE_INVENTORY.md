# 01 — File Inventory & Inter-File Import Map

> **Generated:** 2026-06-14 · Reverse-engineered by reading every source file (no inference from names).
> **Real package root:** `libs/congine-sdk/src/congine_core/` (confirmed via `pyproject.toml` `sourceRoot`).
> **Scope:** 36 Python source modules + config + tests + example. The path in the analysis prompt
> (`libs/congine-sdk/src/congine_core/`) is the real layout — no self-correction needed.

This file is the raw material for the linkage map in `00_SYSTEM_MAP.md`. For each module:
**Layer · one-line responsibility (after reading) · primary public constructs · internal imports (project files only).**

A module's "internal imports" lists only *other Congine source files* it depends on. `TYPE_CHECKING`-only
imports are marked `(TC)` — they exist for typing and create no runtime dependency, which is how L1 ports
reference L2 value objects without a runtime upward edge.

---

## Layer 0 — Shared / cross-cutting (imported by all, depend on ~none)

| File | Responsibility | Public constructs | Internal imports |
|------|----------------|-------------------|------------------|
| `config.py` | The single immutable runtime config object + env loader + security policy (`validate`, `is_local_base_url`, `effective_log_safe_fields`). | `CongineConfig` (frozen dataclass, ~45 fields), `Region`, `FailMode`, `DeploymentMode` | `exceptions` (`CongineConfigurationError`), `security_limits` (DEFAULT_MAX_* constants) |
| `exceptions.py` | The exception tree: one root + 6 canonical types + 4 compat aliases bound to canonical classes. | `CongineBaseException` (+`Validation`, `ContractNotFound`, `Configuration`, `Sync`, `Cache`, `Telemetry`); aliases `ContractBreachException`, `SchemaCacheMissException`, `ValidationTimeoutException`, `TenantIsolationViolationException` | *(none)* |
| `security_limits.py` | Centralised numeric bounds (ReDoS caps, payload/schema/file/stream/http byte limits, semantic breach cap). | `MAX_PATTERN_LENGTH`, `MAX_REGEX_VALUE_LENGTH`, `DEFAULT_MAX_PAYLOAD_BYTES`, `DEFAULT_MAX_SCHEMA_BYTES`, `DEFAULT_MAX_CONTRACT_FILES`, `DEFAULT_MAX_STREAM_BUFFER_CHARS`, `DEFAULT_MAX_HTTP_RESPONSE_BYTES`, `DEFAULT_SEMANTIC_MAX_BREACHES` | *(none)* |
| `pii_sanitize.py` | Redact instance values (quoted substrings, 4+ digit runs) out of breach messages before they hit logs/telemetry. | `sanitize_breach_message(message)` | *(none — uses stdlib `re`, not `re2`)* |
| `__init__.py` | The stable public API surface (`__all__`) re-exporting all 5 layers + config + exceptions; single-sources `__version__` from installed metadata. | `__all__`, `__version__` | `ports`, `domain`, `usecases`, `infrastructure`, `adapters`, `config`, `exceptions` |

---

## Layer 1 — Ports (`typing.Protocol` seams; pure interfaces, no logic)

| File | Responsibility | Public constructs | Internal imports |
|------|----------------|-------------------|------------------|
| `ports/__init__.py` | Aggregate re-export of all 7 ports. | the 7 `I*` protocols | the 7 port modules |
| `ports/contract_repository.py` | Seam for fetching contracts (network) + disk snapshot fallback. | `IContractRepository` (`fetch_active_contracts` async, `load_snapshot`, `save_snapshot`) | *(none)* |
| `ports/event_bus.py` | Seam for fire-and-forget telemetry publication. | `IEventBus` (`publish`) | `domain.models.TelemetryEvent` (TC) |
| `ports/logger.py` | Seam for structured level-based logging. | `ILogger` (`info/error/warning/debug`) | *(none)* |
| `ports/schema_storage.py` | Seam for the TTL schema cache. | `ISchemaStorage` (`get/put/clear/exists`) | *(none)* |
| `ports/semantic_validator.py` | Seam for full-schema (jsonschema) validation. | `ISemanticValidator` (`validate → List[BreachDetail]`) | `domain.models.BreachDetail` (TC) |
| `ports/validation_runner.py` | Seam for the bounded, time-boxed executor (sync + async + `capacity` + `health`). | `IValidationRunner` | *(none)* |
| `ports/circuit_breaker.py` | Seam for the control-plane circuit breaker. | `ICircuitBreaker` (`state/allow/record_success/record_failure`) | *(none)* |

---

## Layer 2 — Domain (pure logic + immutable models; no I/O)

| File | Responsibility | Public constructs | Internal imports |
|------|----------------|-------------------|------------------|
| `domain/__init__.py` | Aggregate re-export of models + validators. | — | `domain.models`, `domain.validator` |
| `domain/models.py` | The immutable value objects that flow through the system. | `BreachDetail` (frozen), `ValidationResult` (frozen, `is_pass()`), `DriftResult` (frozen), `TelemetryEvent` (frozen, post-init default of `breach_details`/`created_at`) | *(none)* |
| `domain/validator.py` | The deterministic validation core: 6 stateless rules + 2 composing validators + the in-domain strategy seam. | `RuleEngine` (6 static rules), `IValidator` (in-domain Protocol), `LocalValidator`, `CompositeValidator`; helpers `_compiled_pattern`, `_path_present`, `_type_matches` | `domain.models` (`BreachDetail`, `ValidationResult`), `security_limits`, `ports.semantic_validator.ISemanticValidator` (TC); 3rd-party `re2` |

---

## Layer 3 — Use cases (stateless orchestration; depend only on L1 + L2)

| File | Responsibility | Public constructs | Internal imports |
|------|----------------|-------------------|------------------|
| `usecases/__init__.py` | Aggregate re-export of the two use cases. | — | the two usecase modules |
| `usecases/validate_contract_usecase.py` | The hot-path orchestrator: size-guard → resolve schema → run-in-executor (timeout) → degrade-on-error → publish telemetry → enforce fail-mode. Sync + async twins. | `ValidateContractUseCase` (`execute`, `execute_async`) | `config.FailMode`, `domain.models`, `domain.validator.IValidator`, `exceptions` (3), `pii_sanitize`, `ports.event_bus`, `ports.logger`, `ports.schema_storage`, `ports.validation_runner` |
| `usecases/sync_contracts_usecase.py` | The boot/sync orchestrator: fetch → prime cache → snapshot; breaker-gated; single-flight (portalocker); snapshot-only fast-fail. Sync + async twins. | `SyncContractsUseCase` (`sync_once`, `sync_once_async`, `sync_once_single_flight[_async]`, `load_snapshot_only`) | `exceptions.CongineSyncError`, `ports.contract_repository`, `ports.logger`, `ports.schema_storage`, `ports.circuit_breaker` (TC); 3rd-party `portalocker` |

---

## Layer 4 — Infrastructure (concrete, side-effecting implementations of L1 ports)

| File | Responsibility | Public constructs | Internal imports |
|------|----------------|-------------------|------------------|
| `infrastructure/__init__.py` | Aggregate re-export of concretes. **Deliberately excludes** `ValidationTimer`. | — | all infra concretes below |
| `infrastructure/lfu_cache.py` | `ISchemaStorage`: O(1) LFU cache + per-entry TTL + background daemon sweeper. RLock-guarded. | `LFUCache` (`get/put/clear/size/exists/sweep_expired/stop`) | *(none — stdlib threading/atexit)* |
| `infrastructure/bounded_executor.py` | `IValidationRunner`: bounded, load-shedding thread pool; permit held until future completes; re-entrancy-safe; sync+async parity. | `BoundedValidationExecutor` (`run_with_timeout[_async]`, `capacity`, `health`, `in_flight`, `rejected_total`, `shutdown`) | *(none)* |
| `infrastructure/timer.py` | **DEPRECATED, not wired.** Naked timeout runner kept for legacy reference; warns on construct. | `ValidationTimer` | *(none)* |
| `infrastructure/circuit_breaker.py` | `ICircuitBreaker`: in-process state machine CLOSED→OPEN→HALF_OPEN with single-flight probe. | `CircuitBreaker` | *(none)* |
| `infrastructure/http_contract_repository.py` | `IContractRepository`: HTTP fetch + secure per-tenant atomic disk snapshot (symlink/owner-checked, portalocker-serialized). | `HttpContractRepository`, `snapshot_lock_path`; helpers `_default_snapshot_dir`, `_scope_key` | `config.CongineConfig`, `exceptions.CongineSyncError`, `ports.logger`; 3rd-party `httpx`, `portalocker` |
| `infrastructure/file_contract_repository.py` | `IContractRepository`: read contracts from a local dir (JSON, + YAML if PyYAML present); offline-safe; snapshot is a no-op. | `FileContractRepository` | `ports.logger`; optional `yaml` |
| `infrastructure/queue_event_bus.py` | `IEventBus`: non-blocking enqueue + daemon drain worker batching POSTs to `/api/v1/telemetry`; breaker-gated; backoff; drop-counting. | `QueueEventBus` (`publish/queue_depth/dropped_total/stop`) | `config.CongineConfig`, `ports.logger`, `domain.models.TelemetryEvent` (TC), `ports.circuit_breaker` (TC); 3rd-party `httpx` |
| `infrastructure/noop_event_bus.py` | `IEventBus`: discards events; no thread, no socket. Selected when telemetry disabled. | `NoOpEventBus` | `domain.models.TelemetryEvent` (TC) |
| `infrastructure/logger.py` | `ILogger`: JSON-per-line stdout logger; level threshold; unconditional sensitive-key blocklist + optional allowlist redaction. | `StructuredLogger` | *(none)* |
| `infrastructure/jsonschema_validator.py` | `ISemanticValidator`: full JSON-Schema validation via `jsonschema`; draft-string→class resolution (fail-closed); breach cap; PII-sanitized messages; pre-rejects over-long schema patterns. | `JsonSchemaSemanticValidator`; helper `_resolve_draft` | `domain.models.BreachDetail`, `exceptions.CongineConfigurationError`, `pii_sanitize`, `security_limits`; 3rd-party `jsonschema` |
| `infrastructure/ks_drift.py` | Two-sample KS drift detector over a bounded reference deque; numpy imported lazily inside `detect`. | `KSDriftEngine` (`add_reference[_samples]`, `detect`, …); helper `_ks_p_value` | `domain.models.DriftResult`; optional `numpy` |
| `infrastructure/background_sync.py` | Daemon thread that periodically drives `SyncContractsUseCase.sync_once`; interruptible sleep; swallows errors so the loop survives. | `BackgroundSyncWorker` (`start/stop/is_running`) | `ports.logger`, `usecases.sync_contracts_usecase.SyncContractsUseCase` (TC) |

---

## Layer 5 — Adapters (composition root + framework entry points; top of the graph)

| File | Responsibility | Public constructs | Internal imports |
|------|----------------|-------------------|------------------|
| `adapters/__init__.py` | Re-export `ServiceContainer` + `congine_guard`; lazily expose `CongineCallbackHandler` via `__getattr__` (no eager langchain import). | `ServiceContainer`, `congine_guard`, `CongineCallbackHandler` (lazy) | `adapters.dependency_injection`, `adapters.guard`, `adapters.langchain_handler` (lazy) |
| `adapters/dependency_injection.py` | **The sole composition root.** Builds the entire object graph bottom-up, wires every config knob, owns lifecycle (`bootstrap[_async]`, `close`), the default singleton, and the multi-tenant registry. | `ServiceContainer` (`get_default`, `for_tenant`, `reset_default`, `from_env`, `bootstrap[_async]`, `health`, `evaluate_drift`, `close`, ctx-mgr) | `config`, `domain.models.TelemetryEvent`, `exceptions`, `domain.validator`, **all** infra concretes, both usecases, `ports.contract_repository`, `ports.event_bus`, `domain.models.DriftResult` (TC); 3rd-party `httpx` |
| `adapters/guard.py` | The `@congine_guard` decorator: wraps sync/async fns, resolves container lazily, runs the validate use case, returns envelope/output/raise per `mode`. | `congine_guard(contract_id, version, container, mode, extractor)` | `adapters.dependency_injection.ServiceContainer`, `exceptions.CongineValidationError` |
| `adapters/langchain_handler.py` | LangChain `BaseCallbackHandler`: buffers streamed tokens (bounded), validates the completed text at `on_llm_end`; per-run results. Optional (`[langchain]`). | `CongineCallbackHandler` | (lazy, inside methods) `adapters.dependency_injection`, `config`, `exceptions`, `security_limits`; optional `langchain_core` |

---

## Non-package files

| File | Role |
|------|------|
| `main.py` | Stub (`print("Hello from congine-sdk!")`). No CLI. Not part of the SDK. |
| `pyproject.toml` | Package metadata + deps (`google-re2`, `httpx`, `jsonschema`, `portalocker`) + extras (`langchain`, `stats`, `redos`, `dev`). **Note divergence:** `requires-python = ">=3.11"` while classifiers/ruff/CLAUDE.md claim 3.10 floor (see `03_SPEC_RECONCILIATION.md`). |
| `project.json` | Nx targets: `lint` (ruff), `test` (uv + pytest with `--extra langchain --extra stats --extra dev`). |
| `examples/LangChain/agent.py` | Reference integration (Gemini + LangChain) in **standalone file-contract mode**. Contains a contract/enum defect (offline fallback `action="manual_review"` ∉ enum). |
| `examples/LangChain/contracts/*.json` | `return_processing.json`, `support_reply.json`, `weather_policy.json` — contract fixtures for the example. |

---

## Test inventory (read, classified separately per prompt)

**Unit (`tests/unit/`):** `test_config.py`, `test_config_wiring.py`, `test_exceptions.py`, `test_cache.py`,
`test_validator.py`, `test_composite_validator.py`, `test_models.py`, `test_usecase.py`, `test_sync_usecase.py`,
`test_event_bus.py`, `test_repository.py`, `test_semantic_validator.py`, `test_ks_drift.py`, `test_logger.py`,
`test_background_sync.py`, `test_guard.py`, `test_langchain_handler.py`, `test_timer.py`.

**Integration (`tests/integration/`):** `test_end_to_end.py` — full wired container, real components, fake bus.

**Adversarial (`tests/adversarial/`):** `test_bounded_executor.py` (H1 load-shed/timeout/re-entrancy, sync+async),
`test_redos.py` (H3), `test_input_bounds.py` (FIX-06), `test_pii_sanitization.py` (FIX-04),
`test_semantic_bounds.py` (FIX-03), `test_tenant_isolation.py` (FIX-05), `test_host_bypass.py` (snapshot poisoning),
`test_remediations.py` (cross-cutting fixes).

**Root-level (`tests/`):** `test_circuit_breaker.py`, `test_single_flight_boot.py` (D-7),
`test_validation_runner_port.py` (D-4), `test_file_contract_repository.py`, `test_agent_workflow.py` (multi-tenant agent flow), `conftest.py` (structural-typing fakes: `FakeLogger`, `FakeEventBus`, `FakeSchemaStorage`, `ImmediateTimer`, `FakeContractRepository`).

> The conftest fakes satisfy L1 protocols **structurally** (no import/subclass of the Protocols) — confirming
> the ports are genuine duck-typed seams, not ABCs.

---

## Inter-file dependency summary (who imports whom, runtime edges only)

```
config            ← exceptions, security_limits
domain/validator  ← domain/models, security_limits          (ports.semantic_validator = TC only)
usecases/validate ← config, domain/*, exceptions, pii_sanitize, ports/{event_bus,logger,schema_storage,validation_runner}
usecases/sync     ← exceptions, ports/{contract_repository,logger,schema_storage}   (ports.circuit_breaker = TC)
infra/http_repo   ← config, exceptions, ports/logger
infra/file_repo   ← ports/logger
infra/queue_bus   ← config, ports/logger                     (domain.models, ports.circuit_breaker = TC)
infra/noop_bus    ← (domain.models = TC)
infra/jsonschema  ← domain/models, exceptions, pii_sanitize, security_limits
infra/ks_drift    ← domain/models
infra/bg_sync     ← ports/logger                             (usecases.sync = TC)
infra/lfu, infra/bounded, infra/timer, infra/circuit_breaker, infra/logger ← (no internal runtime imports)
adapters/DI       ← config, domain/*, exceptions, ALL infra concretes, BOTH usecases, ports/{contract_repository,event_bus}
adapters/guard    ← adapters/DI, exceptions
adapters/langchain← (lazy) adapters/DI, config, exceptions, security_limits
```

**Boundary verdict:** every runtime edge points inward (L5→L4→L3→L2→L0; L1 is referenced by L3/L4 but L1 itself
imports nothing inward except L2 value objects under `TYPE_CHECKING`). **No inner layer imports an outer concrete.**
The lone in-domain `IValidator` Protocol living in `domain/validator.py` (not in `ports/`) is the one sanctioned
exception, documented in `ARCHITECTURE.md`. Full narrative in `00_SYSTEM_MAP.md`.
