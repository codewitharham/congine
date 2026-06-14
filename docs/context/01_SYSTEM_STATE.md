# CONGINE SYSTEM STATE

Generated: 2026-06-14
Revision: Based on direct code analysis of `libs/congine-sdk/src/congine_core/`. No `.md`/doc files were read; every claim below maps to source.

> Scope note: paths are workspace-relative. The SDK lives under `libs/congine-sdk/`.
> 33 source modules across 6 tiers; 259 test functions across 32 test files.

---

## What Is Fully Implemented and Tested

| Component | File | Test file(s) |
| --- | --- | --- |
| `CongineConfig` + `from_env()` + security policy (`validate`, `is_local_base_url`, `effective_log_safe_fields`) | `config.py` | `tests/unit/test_config.py` (11), `tests/unit/test_config_wiring.py` (10) |
| Exception hierarchy + Tier-2 aliases | `exceptions.py` | `tests/unit/test_exceptions.py` (5) |
| Security limit constants | `security_limits.py` | exercised via `tests/adversarial/test_input_bounds.py`, `test_redos.py` |
| PII breach-message sanitization | `pii_sanitize.py` | `tests/adversarial/test_pii_sanitization.py` (3) |
| Domain models (`BreachDetail`, `ValidationResult`, `DriftResult`, `TelemetryEvent`) | `domain/models.py` | `tests/unit/test_models.py` (6) |
| `RuleEngine` (6 rules) + `LocalValidator` | `domain/validator.py` | `tests/unit/test_validator.py` (31) |
| `CompositeValidator` | `domain/validator.py` | `tests/unit/test_composite_validator.py` (6) |
| `ValidateContractUseCase` (sync + async) | `usecases/validate_contract_usecase.py` | `tests/unit/test_usecase.py` (8), `tests/integration/test_end_to_end.py` (11) |
| `SyncContractsUseCase` (+ single-flight) | `usecases/sync_contracts_usecase.py` | `tests/unit/test_sync_usecase.py` (7), `tests/test_single_flight_boot.py` (3) |
| `BoundedValidationExecutor` | `infrastructure/bounded_executor.py` | `tests/adversarial/test_bounded_executor.py` (10), `tests/test_validation_runner_port.py` (5) |
| `LFUCache` (O(1) LFU + TTL sweeper) | `infrastructure/lfu_cache.py` | `tests/unit/test_cache.py` (14) |
| `CircuitBreaker` | `infrastructure/circuit_breaker.py` | `tests/test_circuit_breaker.py` (11) |
| `QueueEventBus` | `infrastructure/queue_event_bus.py` | `tests/unit/test_event_bus.py` (11) |
| `HttpContractRepository` (+ snapshot security) | `infrastructure/http_contract_repository.py` | `tests/unit/test_repository.py` (14), `tests/adversarial/test_host_bypass.py` (5) |
| `FileContractRepository` | `infrastructure/file_contract_repository.py` | `tests/test_file_contract_repository.py` (10) |
| `JsonSchemaSemanticValidator` | `infrastructure/jsonschema_validator.py` | `tests/unit/test_semantic_validator.py` (7), `tests/adversarial/test_semantic_bounds.py` (3) |
| `KSDriftEngine` | `infrastructure/ks_drift.py` | `tests/unit/test_ks_drift.py` (9) |
| `StructuredLogger` (level + redaction) | `infrastructure/logger.py` | `tests/unit/test_logger.py` (5) |
| `BackgroundSyncWorker` | `infrastructure/background_sync.py` | `tests/unit/test_background_sync.py` (5) |
| `congine_guard` (envelope/output/raise; sync+async) | `adapters/guard.py` | `tests/unit/test_guard.py` (9) |
| `CongineCallbackHandler` (langchain) | `adapters/langchain_handler.py` | `tests/unit/test_langchain_handler.py` (10) |
| Adversarial remediations / tenant isolation | — | `tests/adversarial/test_remediations.py` (13), `test_tenant_isolation.py` (2), `tests/test_agent_workflow.py` (5) |

This is a genuinely well-tested Phase-0 core. The hot-path-critical components (executor, cache, breaker, repository, validator) all have dedicated unit *and* adversarial coverage.

---

## What Is Implemented but Untested (or Under-Tested)

- **`ServiceContainer` itself has no dedicated `test_container.py`.** Its wiring is exercised indirectly through `test_config_wiring.py`, `test_agent_workflow.py`, and the integration test, but there is no direct test for:
  - `for_tenant()` LRU eviction at `_MAX_TENANTS` (128) — the eviction-and-`close()` branch (`dependency_injection.py:108-114`) is the riskiest code in the container and is not directly asserted.
  - `reset_default()` tearing down the tenant registry.
  - `health()` aggregation shape (`dependency_injection.py:329-344`).
  - `evaluate_drift()` publishing a `__drift__` telemetry event (`dependency_injection.py:294-327`).
- **`bootstrap()`’s in-event-loop guard** (`dependency_injection.py:270-282`, raises `RuntimeError` if called inside a running loop) — no test observed asserting this guard.
- **`ValidationTimer`** (`infrastructure/timer.py`) is covered by `test_timer.py` (4) but is **deprecated and not wired anywhere**; the container uses `BoundedValidationExecutor`. Tests here protect dead-ish code.
- **The LangChain example** (`examples/LangChain/agent.py`) is not under test and contains a contract/enum defect (see Known Bugs).

---

## What Is Partially Implemented

- **Multi-tenant isolation** — *mostly* complete. `get_default()` is correctly disabled in `multi_tenant` mode (`dependency_injection.py:60-65`), snapshot paths are scoped per `(base_url, project_id, tenant_id)` (`http_contract_repository.py:53-58`), and `for_tenant()` scopes config. **Partial:** the registry's LRU eviction can `close()` a container that a caller still holds a live reference to (details below).
- **Drift detection** — engine + container hooks exist (`record_drift_sample`, `evaluate_drift`), but there is no automatic wiring that feeds validation outcomes into the drift window; a host must call `record_drift_sample()` manually. It is a library capability, not an active pipeline.
- **Telemetry transport** — `QueueEventBus` ships to a hard-coded path `"/api/v1/telemetry"` (`queue_event_bus.py:34`). The endpoint shape is assumed; there is no contract test against a real control plane (none exists yet).

---

## What Does Not Exist Yet (Referenced in Roadmap/Comments but Not in Code)

- **MCP server** — no `mcp/` package. `IMCPTransport`, `server.py`, `tools.py` do not exist.
- **CLI tool** — no `cli/` package. No `congine validate`, `validate-diff`, `health`, `list-contracts`.
- **Persistent event store** — no `SqliteEventBus`. `TelemetryEvent` has no `project_id`/`agent_id`/`file_paths`/`git_commit_sha`/`session_id` fields (`domain/models.py:91-96`).
- **Violation history / frequency query methods** on `ValidateContractUseCase` — not present.
- **Architectural component graph / pattern detection / correction hints** (Phase 2) — none.
- **`TenantIsolationViolationException`** and **`ValidationTimeoutException`** are forward-compat *aliases* only (`exceptions.py:62-65`); nothing raises them as distinct types. A timeout degrades to `ValidationResult(degraded=True)` rather than raising.

---

## Known Bugs and Technical Debt

| # | Issue | Location | Severity | Fix effort |
| --- | --- | --- | --- | --- |
| 1 | **Example contract/enum mismatch.** Offline fallback returns `action="manual_review"`, which is NOT in the contract enum `["approve_return","reject_return","escalate"]`. With `mode="raise"`, the "clean" Scenario 1 raises `CongineValidationError` whenever `GOOGLE_API_KEY` is unset. The Pydantic field description also lists `manual_review` instead of `escalate`. | `examples/LangChain/agent.py:75,91` vs `examples/LangChain/contracts/return_processing.json:7` | MEDIUM | SMALL |
| 2 | **Multi-tenant LRU is keyed on `for_tenant()` *lookups*, not validation activity, and eviction calls `close()` on a possibly-live container.** A heavily-used tenant that fetched its container once and never re-requests it can be evicted; eviction stops that container's cache sweeper, telemetry drain, and validation pool out from under any code still holding the reference. | `dependency_injection.py:84-118` | MEDIUM | MEDIUM |
| 3 | **`requires-python = ">=3.11"` contradicts the stated 3.10 floor.** Classifiers list 3.10, `ruff target-version = py310`, and `.claude/CLAUDE.md` claim 3.10 support, but the package metadata forbids 3.10 installs. | `pyproject.toml:6` vs `:18`, `:69` | MEDIUM | SMALL |
| 4 | **Payload/schema size guards count *characters*, not bytes.** `len(json.dumps(...))` measures string length and adds JSON-encoding overhead; multibyte UTF-8 undercounts vs the byte-named budget `max_payload_bytes`. | `validate_contract_usecase.py:127,145` | LOW | SMALL |
| 5 | **Stale module docstring.** Says `TelemetryEvent` is "mutable to allow post-init defaulting"; the class is `frozen=True`. | `domain/models.py:5-6` vs `:74` | LOW | SMALL |
| 6 | **`pii_sanitize` uses stdlib `re`, not `re2`.** The pattern is not catastrophic and inputs are bounded, but it is the one regex on (schema-derived) untrusted-ish content that bypasses the project-wide `re2` rule. | `pii_sanitize.py:9,14` | LOW | SMALL |
| 7 | **`CompositeValidator` runs the semantic validator even on non-dict payloads.** `LocalValidator` short-circuits a non-dict to a fail result, but `CompositeValidator` still calls `semantic_validator.validate(payload, schema)` afterward (`validator.py:451-453`). Harmless today (merged result already fails), but a latent assumption. | `domain/validator.py:451-453` | LOW | SMALL |
| 8 | **Dual schema vocabulary is implicit.** The rule engine understands `min`/`max` *and* `minimum`/`maximum`, plus `null_forbidden`, but **not** `minLength`/`maxLength`. JSON-Schema-only keywords (`minLength`, `format`, etc.) are silently ignored unless `CONGINE_SEMANTIC_VALIDATION=true`. Easy to author a contract that looks enforced but isn't. | `domain/validator.py:333-367` | MEDIUM | (doc/validation) |
| 9 | **`ValidationTimer` retained as deprecated dead code.** Emits `DeprecationWarning` on construction; not wired by the container. | `infrastructure/timer.py` | LOW | SMALL (delete) |

> TODO/FIXME scan: no literal `TODO`/`FIXME` comments remain in `src/`. The codebase instead annotates remediations with audit IDs (`FIX-01`..`FIX-14`, `H1`–`H4`, `M2`–`M5`, `D-3`..`D-11`, `C2`, `L4`–`L7`), which are present and consistent with the implemented behavior.

---

## Hot Path Guarantees: Verified Against Code

- [x] **Bounded latency / load shedding** — `BoundedValidationExecutor` caps `capacity = max_workers + max_pending` via `BoundedSemaphore`, sheds with `TimeoutError` on `acquire(blocking=False)` failure, and holds the permit until the future genuinely completes so zombies keep occupying capacity. Sync *and* async go through the same `_acquire_and_submit` (`bounded_executor.py:59-60,142-175`). **CONFIRMED.**
- [x] **No control-plane stall on boot** — `bootstrap()` → `sync_once_single_flight()`; `_fetch_sync` consults the breaker and falls back to `load_snapshot()` when OPEN, bypassing the HTTP timeout (`sync_contracts_usecase.py:182-195`, `circuit_breaker.py`). **CONFIRMED.**
- [x] **No thundering herd** — `sync_once_single_flight` adds 0–0.5s jitter then takes a non-blocking `portalocker` boot lock; losers load the snapshot the winner wrote (`sync_contracts_usecase.py:105-181`). **CONFIRMED.**
- [x] **Snapshot integrity** — per-scope SHA-256 path under a per-user app dir, `tempfile + os.replace` atomic write under an advisory cross-process lock, symlink/non-owner refusal + envelope validation on load (`http_contract_repository.py:43-269`). **CONFIRMED.**
- [x] **No ReDoS** — `REGEX_PATTERN` length-caps pattern (1000) and value (50 000), caches compiled patterns, and uses `re2.fullmatch`; the semantic validator pre-rejects over-long schema patterns (`domain/validator.py:248-290`, `jsonschema_validator.py:148-168`). **CONFIRMED**, with the caveat that `pii_sanitize.py` uses stdlib `re` (bounded input, non-catastrophic pattern).
- [x] **Multi-tenant isolation in MULTI_TENANT mode** — `get_default()` disabled, snapshot/config scoped per tenant. **CONFIRMED**, with the eviction-`close()` debt in item #2.
- [x] **PII-safe telemetry** — breach messages sanitized before publish (`validate_contract_usecase.py:220`) and inside the semantic validator; logger enforces an unconditional blocklist plus a non-local auto-redaction allowlist (`logger.py:31-40,76-87`, `config.py:297-318`). **CONFIRMED.**

**Net:** all seven guarantees are real and code-backed. The only asterisks are the `pii_sanitize` stdlib-`re` exception (low risk) and the multi-tenant eviction lifecycle bug (real, medium).
