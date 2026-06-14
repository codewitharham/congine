# Congine SDK — Enterprise Code-Level Audit

> **Purpose:** Canonical audit snapshot for architecture decisions, onboarding, and enterprise roadmap planning.  
> **Generated:** 2026-06-14  
> **Package:** `congine-sdk` v0.1.0 (`congine_core`)  
> **Scope:** All non-markdown source under `libs/congine-sdk/` — 38 Python modules, config, tests, examples.  
> **Method:** Code-only analysis (implementation files); no reliance on existing documentation prose.

---

## Table of Contents

1. [Executive Summary](#executive-summary)
2. [Part 1 — Codebase Audit & Functional Status](#part-1--codebase-audit--functional-status)
3. [Part 2 — Zero-to-Hero Onboarding Guide](#part-2--zero-to-hero-onboarding-guide)
4. [Part 3 — Enterprise Readiness & Roadmap](#part-3--enterprise-readiness--roadmap)
5. [Quick Reference](#quick-reference)
6. [File Inventory](#file-inventory)

---

## Executive Summary

**What it is:** A Phase 0 **contract-validation SDK** for LLM/agent outputs — a hexagonal Python library that wraps function returns (or LangChain streams), validates them against JSON-schema-like contracts, emits telemetry, and optionally blocks or degrades on failure.

**What it is not:** A general-purpose autonomous-agent state machine, distributed policy engine, RBAC/ABAC system, or durable audit platform.

**Verdict:**

| Dimension | Assessment |
|-----------|------------|
| Code quality & hexagonal architecture | **Strong** |
| Hot-path safety (bounded pool, ReDoS, load shedding) | **Strong** |
| Single-node operational resilience | **Strong** |
| Strict deterministic enforcement (default policy) | **Moderate** — validation is deterministic; default `FailMode` is `DEGRADE` |
| Enterprise readiness (authZ, audit, versioning, distributed state) | **Early / Phase 0** |

**Correct mental model:** A **synchronous output firewall** between stochastic model output and downstream systems — not a deterministic agent orchestrator.

---

## Part 1 — Codebase Audit & Functional Status

### 1.1 Layer Architecture

Dependencies point **inward only**. `ServiceContainer.__init__` in `adapters/dependency_injection.py` is the sole composition root.

| Layer | Package | Contents |
|-------|---------|----------|
| **L0** | `config.py`, `exceptions.py`, `security_limits.py`, `pii_sanitize.py` | Frozen config, exception tree, shared bounds, PII redaction |
| **L1** | `ports/` | 7 `typing.Protocol` seams |
| **L2** | `domain/` | Pure validation logic + immutable models |
| **L3** | `usecases/` | Orchestration only (`ValidateContractUseCase`, `SyncContractsUseCase`) |
| **L4** | `infrastructure/` | I/O, threads, HTTP, cache, breaker |
| **L5** | `adapters/` | `ServiceContainer`, `@congine_guard`, LangChain handler |

**Core dependencies:** `google-re2`, `httpx`, `jsonschema`, `portalocker`  
**Optional extras:** `[langchain]` → `CongineCallbackHandler`; `[stats]` → `KSDriftEngine`; `[dev]` → pytest/ruff

### 1.2 Architecture Map

```
┌─────────────────────────────────────────────────────────────────┐
│ L5: @congine_guard │ CongineCallbackHandler │ ServiceContainer  │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│ L3: ValidateContractUseCase          SyncContractsUseCase        │
└──────┬───────────────────────────────┬──────────────────────────┘
       │                               │
┌──────▼──────────┐            ┌───────▼──────────────────────────┐
│ L2: LocalValidator            │ L4: HttpContractRepository       │
│     CompositeValidator        │     FileContractRepository       │
│     RuleEngine                │     BackgroundSyncWorker         │
│     ValidationResult          │     CircuitBreaker               │
└──────┬──────────┘            └──────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│ L4: BoundedValidationExecutor │ LFUCache │ QueueEventBus        │
│     JsonSchemaSemanticValidator │ KSDriftEngine │ StructuredLogger│
└─────────────────────────────────────────────────────────────────┘
```

**Contract source topology (mutually exclusive switches):**

| Config | Repository | Background sync |
|--------|------------|-----------------|
| `CONGINE_LOCAL_CONTRACTS_DIR` set | `FileContractRepository` | **None** (`sync_worker is None`) |
| `CONGINE_CONTRACT_SOURCE=file` + `CONGINE_CONTRACTS_DIR` | `FileContractRepository` | Optional |
| Default | `HttpContractRepository` → `GET /api/v1/contracts/active` | Optional via `CONGINE_SYNC_ENABLED` |

**Offline / air-gapped:** Set both `CONGINE_LOCAL_CONTRACTS_DIR` and `CONGINE_TELEMETRY_ENABLED=false`.

### 1.3 Mechanisms of Determinism

The SDK does **not** make LLM outputs deterministic. It makes **validation outcomes deterministic** for `(payload, schema, config)`.

#### A. Rule-engine validation (always on)

**`RuleEngine`** (`domain/validator.py`) — six static rules:

| Rule | Constraint |
|------|------------|
| `FIELD_PRESENCE` | Required fields (dot-path traversal) |
| `TYPE_MATCH` | JSON types vs Python types (bool/int ambiguity handled) |
| `ENUM_VALUES` | Allowed enumerations |
| `RANGE_CHECK` | min/max on numerics |
| `NULL_GUARD` | `null_forbidden` list |
| `REGEX_PATTERN` | RE2 fullmatch; pattern ≤1000 chars, value ≤50,000 chars |

**`LocalValidator.validate()`** runs all rules sequentially → frozen **`ValidationResult`**.

#### B. Optional semantic validation

When `semantic_validation_enabled=True`, **`CompositeValidator`** merges `LocalValidator` + **`JsonSchemaSemanticValidator`**. Breaches capped at `semantic_max_breaches` (default 100) with `SEMANTIC_TRUNCATED` marker.

#### C. Enforcement modes

**`ValidateContractUseCase._handle_failure()`** + **`FailMode`**:

| Mode | Behavior |
|------|----------|
| `STRICT` | Raises `CongineValidationError` after telemetry publish |
| `DEGRADE` (**default**) | Logs warning; returns failed `ValidationResult` |
| `SILENT` | Returns result; no log on failure |

**`@congine_guard` modes:** `envelope` (default) | `output` | `raise`

#### D. Hot-path safety bounds

| Mechanism | Class | Guarantee |
|-----------|-------|-----------|
| Bounded pool | `BoundedValidationExecutor` | `capacity = max_workers + max_pending`; load shed via `TimeoutError` |
| Hard deadline | Same | Default 100ms (`CONGINE_TIMEOUT_MS`) |
| Re-entrancy | Same | Inline on pool worker threads (no nested deadlock) |
| Async parity | `execute_async` | Same pool + semaphore as sync |
| Input bounds | `ValidateContractUseCase` | `max_payload_bytes`, `max_schema_bytes` |
| ReDoS guard | `RuleEngine.REGEX_PATTERN`, `JsonSchemaSemanticValidator` | RE2 only; length caps |
| PII safety | `sanitize_breach_message`, `StructuredLogger` | Redact quoted values / long digits |

#### E. Resilience patterns

- **`CircuitBreaker`:** CLOSED → OPEN (5 failures) → HALF_OPEN probe → CLOSED
- **`SyncContractsUseCase`:** Never clears cache on fetch failure; falls back to disk snapshot
- **`sync_once_single_flight`:** `portalocker` boot lock + 0–0.5s jitter
- **`QueueEventBus`:** Non-blocking publish; drops on full queue (`dropped_total()`)

### 1.4 State & Data Flow

#### Boot / contract priming

```
ServiceContainer.bootstrap()
  → SyncContractsUseCase.sync_once_single_flight()
    → [lock acquired] HttpContractRepository.fetch_active_contracts()
      → GET {base_url}/api/v1/contracts/active
      → LFUCache.put(id, schema, ttl)
      → HttpContractRepository.save_snapshot() [atomic temp+replace, portalocker]
    → [lock held by sibling] load_snapshot_only()
  → [if sync_enabled] BackgroundSyncWorker.start()
```

Snapshot paths scoped by SHA-256 of `base_url|project_id|tenant_id` under user-owned cache dir.

#### Validation hot path (sync)

```
@congine_guard → fn(*args) → output
  → ValidateContractUseCase.execute(payload, contract_id, version)
    → _check_payload_size (json.dumps length)
    → _resolve_schema → LFUCache.get(contract_id) [miss → CongineContractNotFoundError]
    → _check_schema_size
    → BoundedValidationExecutor.run_with_timeout(validator.validate, timeout_ms)
      → LocalValidator / CompositeValidator
    → _finalize:
        → TelemetryEvent → event_bus.publish (non-blocking)
        → _handle_failure per FailMode
  → envelope | raw output | raise per guard mode
```

#### Telemetry side channel

```
TelemetryEvent → QueueEventBus._queue (max 10_000)
  → daemon _drain_loop → batch POST /api/v1/telemetry
  → exponential backoff, circuit breaker gated
  → drops counted on failure / OPEN breaker
```

#### Drift detection (optional, `[stats]` extra)

```
ServiceContainer.record_drift_sample(value) → KSDriftEngine.add_reference
ServiceContainer.evaluate_drift(samples) → KS test → TelemetryEvent(status="drift")
```

Not wired into validation hot path automatically — caller must invoke explicitly.

### 1.5 Technical Debt & Risks

#### Critical / production-relevant

1. **Timeout ≠ cancellation.** `BoundedValidationExecutor` cannot kill runaway threads. Zombies hold semaphore permits until completion.
2. **Default fail mode is permissive.** `FailMode.DEGRADE` default — failures pass through unless host uses `mode="raise"` or `STRICT`.
3. **Telemetry loss is silent by design.** Queue-full and ship-failure drops counted but never surfaced to caller.
4. **Process-local isolation only.** `ServiceContainer.for_tenant()` — in-process LRU registry (max 128 tenants). No cross-process/node boundary enforcement in SDK.
5. **`TenantIsolationViolationException` is a placeholder alias** — never raised in source.
6. **No contract version resolution.** `@congine_guard(version="latest")` records version in telemetry only; cache keyed by `contract_id` alone.
7. **Semantic validation off by default.** `minLength`, nested objects, `$ref`, etc. ignored unless `CONGINE_SEMANTIC_VALIDATION=true`.
8. **`asyncio.run` in sync sync path.** `SyncContractsUseCase._fetch_sync` — problematic if called from running event loop.

#### Performance notes

- Default target: **low tens of ms**, not sub-millisecond (`validation_timeout_ms=100`).
- `json.dumps` size checks on every validation add allocation overhead.
- `LFUCache.get` takes `RLock` on every schema read.
- `CompositeValidator` runs rule engine then jsonschema sequentially — no short-circuit.

#### Consistency gaps

- `pyproject.toml`: `requires-python >= 3.11` vs `ruff target-version = py310`.
- `CongineCallbackHandler.on_llm_end` swallows non-`CongineBaseException` errors → returns `None`.
- `main.py` is a stub — no CLI.

#### Positive signals (test coverage)

Adversarial suite covers: bounded executor, ReDoS, PII, tenant container isolation, host bypass, single-flight boot, config wiring. ~40 test modules.

---

## Part 2 — Zero-to-Hero Onboarding Guide

### 2.1 Reading Order

**Phase A — Foundations (Day 1)**

1. `security_limits.py`
2. `exceptions.py`
3. `config.py`
4. `domain/models.py`

**Phase B — Validation core (Day 1–2)**

5. `domain/validator.py`
6. `pii_sanitize.py`
7. `ports/` (all 7 files)

**Phase C — Orchestration (Day 2)**

8. `usecases/validate_contract_usecase.py`
9. `usecases/sync_contracts_usecase.py`

**Phase D — Infrastructure (Day 3)**

10. `infrastructure/bounded_executor.py`
11. `infrastructure/lfu_cache.py`
12. `infrastructure/http_contract_repository.py`
13. `infrastructure/file_contract_repository.py`
14. `infrastructure/jsonschema_validator.py`
15. `infrastructure/circuit_breaker.py`
16. `infrastructure/queue_event_bus.py` + `noop_event_bus.py`
17. `infrastructure/background_sync.py`
18. `infrastructure/logger.py`
19. `infrastructure/ks_drift.py` (optional)

**Phase E — Entry points (Day 3–4)**

20. `adapters/dependency_injection.py` — read fully
21. `adapters/guard.py`
22. `adapters/langchain_handler.py`
23. `__init__.py`

**Phase F — Tests (Day 4)**

24. `tests/conftest.py`
25. `tests/integration/test_end_to_end.py`
26. `tests/adversarial/`

**Phase G — Reference**

27. `examples/LangChain/agent.py` + `examples/LangChain/contracts/*.json`

### 2.2 Lifecycle Trace — Breakpoint Map

**Validation path:**

| Step | File | Method | What you see |
|------|------|--------|--------------|
| 1 | `adapters/guard.py` | `sync_wrapper` ~L76–84 | Decorated fn returns; container resolved |
| 2 | `usecases/validate_contract_usecase.py` | `execute` ~L49–84 | Size check, schema resolve, timer |
| 3 | `infrastructure/lfu_cache.py` | `get` ~L79–94 | Cache hit/miss + LFU bump |
| 4 | `infrastructure/bounded_executor.py` | `run_with_timeout` ~L84–109 | Semaphore, pool submit, deadline |
| 5 | `domain/validator.py` | `LocalValidator.validate` ~L369–408 | Rule composition |
| 6 | `domain/validator.py` | `RuleEngine.*` | Individual rule failures |
| 7 | `usecases/validate_contract_usecase.py` | `_finalize` ~L205–230 | Telemetry + fail_mode |
| 8 | `usecases/validate_contract_usecase.py` | `_handle_failure` ~L232–260 | STRICT raise vs DEGRADE |
| 9 | `infrastructure/queue_event_bus.py` | `publish` ~L99–116 | Non-blocking enqueue |
| 10 | `adapters/guard.py` | `_finish` ~L63–72 | Envelope or re-raise |

**Boot path:**

| Step | File | Method |
|------|------|--------|
| B1 | `adapters/dependency_injection.py` | `bootstrap` ~L270–282 |
| B2 | `usecases/sync_contracts_usecase.py` | `sync_once_single_flight` ~L105–135 |
| B3 | `infrastructure/http_contract_repository.py` | `fetch_active_contracts` ~L93–140 |
| B4 | `usecases/sync_contracts_usecase.py` | `_prime_cache` ~L239–252 |

### 2.3 Design Patterns in Code

| Pattern | Present? | Location |
|---------|----------|----------|
| Hexagonal / Ports & Adapters | **Yes** | Full codebase |
| Composition Root DI | **Yes** | `ServiceContainer` |
| Strategy | **Yes** | `IValidator`, `ISemanticValidator` |
| Circuit Breaker | **Yes** | `CircuitBreaker` |
| Outbox-ish telemetry | **Partial** | `QueueEventBus` — no transactional outbox |
| CQRS | **No** | — |
| Event Sourcing | **No** | — |
| State Machine | **Minimal** | Breaker states only |
| Single-flight locking | **Yes** | Boot lock, snapshot lock |

### 2.4 Key Commands

From workspace root (`congine_workspace/`):

```bash
# Test
pnpm nx test congine-sdk

# Lint
pnpm nx lint congine-sdk

# Single test file
uv run --package congine-sdk --extra langchain --extra stats pytest libs/congine-sdk/tests/unit/test_guard.py
```

---

## Part 3 — Enterprise Readiness & Roadmap

### 3.1 Enterprise Gap Analysis

| Requirement | Current state | Gap |
|-------------|---------------|-----|
| Multi-tenant isolation | In-process registry (128 cap); HTTP headers to control plane | **High** — no runtime tenant enforcement in validation path |
| Compliance audit trail | JSON logs + best-effort telemetry; PII sanitization | **High** — no immutable audit log, correlation IDs, signed events |
| RBAC / ABAC | None | **Critical** |
| Zero-trust verification | API key headers; HTTPS for non-local | **Medium** — no mTLS, token rotation, request signing |
| Contract versioning | Version in telemetry only; cache by `contract_id` | **High** |
| Policy beyond JSON Schema | 6 rules + optional jsonschema | **Medium** |
| Healing / remediation | Fail/degrade/raise only | **High** |
| Observability | `health()`, structured logs | **Medium** — no OpenTelemetry/Prometheus |
| Horizontal scaling | Process-local everything | **Critical** |
| Edge deployment | File contracts + NoOpEventBus | **Low–Medium** — viable; no WASM/sidecar |

### 3.2 Recommended Next-Phase Features (Priority)

1. **Contract version pinning & provenance** — cache key `(tenant, project, contract_id, version)`; schema hash in `ValidationResult`
2. **Durable audit pipeline (transactional outbox)** — spool-to-disk before ACK; correlation/trace IDs; at-least-once delivery
3. **Tenant context & policy enforcement** — mandatory `TenantContext`; real `TenantIsolationViolationException`; JWT/RBAC integration
4. **Strict enforcement profile + remediation hook** — `IRemediationStrategy`; enterprise default STRICT
5. **Distributed control-plane coordination** — Redis/etcd breaker + single-flight; optional shared schema cache

### 3.3 Scalability Strategy

**Scales today (single pod):**

- Vertical: `CONGINE_VALIDATION_WORKERS` / `CONGINE_VALIDATION_PENDING`
- Stateless validation across replicas if each bootstraps own cache (accept stale schemas)

**Does not scale as-is:**

| Component | Refactor |
|-----------|----------|
| `LFUCache` | L1 local + L2 Redis; pub/sub invalidation |
| `CircuitBreaker` | Shared state or health proxy |
| `sync_once_single_flight` | K8s Job or lease-based leader election |
| `for_tenant` registry | Per-tenant sidecar or subprocess |
| Telemetry | Kafka/Pulsar `IEventBus` adapter |

**Recommended enterprise topology:**

```
App Pod(s) → Congine Sidecar (strict mode) → Control Plane API
                      ↓
              Outbox → SIEM / audit store
```

Extract validation behind gRPC/HTTP sidecar for centralized strict enforcement.

---

## Quick Reference

### Public API (`congine_core.__init__.py`)

- **Entry:** `ServiceContainer`, `congine_guard`, `CongineConfig.from_env()`
- **Use cases:** `ValidateContractUseCase`, `SyncContractsUseCase`
- **Domain:** `ValidationResult`, `BreachDetail`, `RuleEngine`, `LocalValidator`, `CompositeValidator`
- **Infra:** `BoundedValidationExecutor`, `LFUCache`, `HttpContractRepository`, `FileContractRepository`, `QueueEventBus`, `NoOpEventBus`, `CircuitBreaker`, `JsonSchemaSemanticValidator`, `KSDriftEngine`

### Critical env vars

| Variable | Default | Notes |
|----------|---------|-------|
| `CONGINE_FAIL_MODE` | `degrade` | `strict` \| `degrade` \| `silent` |
| `CONGINE_TIMEOUT_MS` | `100` | Validation deadline |
| `CONGINE_DEPLOYMENT_MODE` | `single_tenant` | `multi_tenant` disables `get_default()` |
| `CONGINE_SEMANTIC_VALIDATION` | `false` | Full JSON Schema |
| `CONGINE_LOCAL_CONTRACTS_DIR` | — | Offline file mode; no sync worker |
| `CONGINE_TELEMETRY_ENABLED` | `true` | `false` → `NoOpEventBus` |
| `CONGINE_VALIDATION_WORKERS` | `10` | Pool size |
| `CONGINE_VALIDATION_PENDING` | `10` | Load-shed threshold |

### Hot-path guarantees (do not regress)

1. Bounded latency / load shedding — `BoundedValidationExecutor`
2. No control-plane stall on boot — `CircuitBreaker` + snapshot fallback
3. No thundering herd — `sync_once_single_flight`
4. Snapshot integrity — scoped paths, atomic writes, symlink refusal
5. No ReDoS — RE2 + length caps
6. Multi-tenant — `get_default()` disabled in multi_tenant mode
7. PII-safe telemetry — `sanitize_breach_message` + log redaction

### Adding a config field (4-touch change)

1. `CongineConfig` frozen dataclass field
2. `CongineConfig.from_env()` reader
3. `ServiceContainer` wiring to concrete
4. README config-reference table (user-facing doc)

---

## File Inventory

### Source (`src/congine_core/`)

```
config.py, exceptions.py, security_limits.py, pii_sanitize.py, __init__.py
ports/: circuit_breaker, contract_repository, event_bus, logger, schema_storage,
        semantic_validator, validation_runner
domain/: models.py, validator.py
usecases/: validate_contract_usecase.py, sync_contracts_usecase.py
infrastructure/: bounded_executor, circuit_breaker, lfu_cache,
                http_contract_repository, file_contract_repository,
                jsonschema_validator, queue_event_bus, noop_event_bus,
                background_sync, logger, ks_drift, timer (deprecated)
adapters/: dependency_injection.py, guard.py, langchain_handler.py
```

### Tests (`tests/`)

```
unit/, integration/, adversarial/, conftest.py, test_*.py
```

### Config

```
pyproject.toml, project.json, main.py (stub)
examples/LangChain/: agent.py, contracts/*.json
```

---

## Revision History

| Date | Version | Notes |
|------|---------|-------|
| 2026-06-14 | 0.1.0 | Initial enterprise code-level audit |

---

*Re-run audit when: major release, new layer/module, enterprise feature ship, or pre-fundraising/security review.*
