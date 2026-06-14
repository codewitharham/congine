# 02 — Failure Paths & Branches (where the real system lives)

> Each branch below is traced through the **actual** code path, cited to file + construct, and classified
> **CORRECT / PARTIAL / BROKEN / ABSENT** with a one-paragraph consequence in human terms. Generated 2026-06-14.

**Classification legend:** CORRECT = handled as a well-built system should. PARTIAL = handled, but with a real
gap or caveat. BROKEN = present but wrong/harmful. ABSENT = not handled at all.

---

## B1. The decorator is used with NO explicit container (the default path) — **CORRECT (with one perf caveat)**

**Path.** `@congine_guard("c")` with no `container=`. At decoration time *nothing* is constructed —
`congine_guard` (`adapters/guard.py:29`) only validates the `mode` string and builds closures. On the **first
call**, `sync_wrapper` → `_resolve()` (line 57) → `ServiceContainer.get_default()`
(`adapters/dependency_injection.py:51`). `get_default` calls `CongineConfig.from_env()`, checks deployment mode,
and under a double-checked lock lazily constructs the one process-wide container if absent. The container's
`__init__` builds the whole graph and starts background daemons (cache sweeper, telemetry drain) **but does not
fetch contracts** — there is no implicit `bootstrap()`.

**Consequence.** The default path is lazy and safe: every default-guarded function shares **one** cache,
telemetry worker, and validation pool (never one per decoration). The catch the founder must know: the singleton
is **not bootstrapped automatically**, so on first use the cache is empty and the very first validation of any
contract raises `CongineContractNotFoundError` unless the host called `ServiceContainer.get_default().bootstrap()`
at startup (the README quickstart does exactly this). **Minor perf caveat:** `get_default()` calls
`CongineConfig.from_env()` on *every* invocation (to re-check deployment mode) even after the singleton exists, so
each default-guarded call re-parses ~45 env vars. Negligible for correctness, a tiny avoidable cost on a hot path.
In `multi_tenant` mode `get_default()` raises by design — so the default path is loud, not silently wrong, when
misused.

---

## B2. The schema cache is cold or misses — **CORRECT**

**Path.** `ValidateContractUseCase._resolve_schema` (`usecases/validate_contract_usecase.py:161`) calls
`schema_storage.get(contract_id)`. `LFUCache.get` (`infrastructure/lfu_cache.py:79`) returns `None` on a true
miss *or* on a TTL-expired entry (which it evicts as a side effect). On `None`, the use case logs an error and
raises `CongineContractNotFoundError`. This exception is **re-raised**, not degraded: `execute` catches
`CongineBaseException` and `raise`s it (line 77), so it propagates regardless of `fail_mode`.

**Consequence.** A missing contract is treated as a *wiring error*, not a validation failure — correctly. It
fails loud even in `degrade`/`silent` mode, so you can never silently "pass" an output you never actually checked.
The README documents this explicitly ("`SchemaCacheMissException` always raises … regardless of `fail_mode`").
The one thing to internalize: the cache is not self-populating on miss — there is no read-through to the control
plane on the hot path (deliberate, to keep latency bounded). Priming is the boot/sync path's job (B3).

---

## B3. The network/backend is unavailable — **CORRECT**

**Path.** `bootstrap()` → `SyncContractsUseCase.sync_once_single_flight()` → `_fetch_sync`
(`usecases/sync_contracts_usecase.py:182`). It first asks the circuit breaker `allow()`; if OPEN, it skips the
network and returns `load_snapshot()` immediately. If allowed, it runs `fetch_active_contracts()`; on
`CongineSyncError` it records a breaker failure and falls back to `load_snapshot()`. `_apply` (line 223) then:
if no contracts could be obtained, **leaves the existing cache untouched** and returns 0 — a dead control plane or
poisoned snapshot never clears healthy cached schemas. The offline snapshot is written by
`HttpContractRepository.save_snapshot` (`infrastructure/http_contract_repository.py:163`): a JSON envelope written
to a **temp file + `os.replace`** (crash-atomic), under a `portalocker` advisory lock, into a **per-user app-owned
directory** (`%LOCALAPPDATA%\congine\snapshots` on Windows, `~/.cache/congine/snapshots` on POSIX), with the
filename scoped by `sha256(base_url|project_id|tenant_id)[:16]`.

**Is the scoping safe across tenants on one host?** **Yes.** The path is keyed on the tenant/project hash and the
directory is per-OS-user; on POSIX the dir is `chmod 0o700` best-effort. On **load**, `load_snapshot` (line 142)
refuses the file if it is a **symlink** or **not owned by the current user** (POSIX `st_uid` check), then validates
the envelope shape. So two tenants on one host get distinct snapshot files, and a local attacker cannot pre-plant
a predictable `/tmp/congine_snapshot.json`.

**Consequence.** This is the strongest part of the system. A cold/hung control plane cannot stall boot (breaker
fast-fails to snapshot), cannot crash the host (errors degrade), and cannot corrupt a healthy cache. Cross-tenant
snapshot collision and snapshot-poisoning are both defended. The only residual is operational, not safety:
`HttpContractRepository.load_snapshot`'s owner check is a POSIX no-op on Windows (returns `True`), which is
acceptable because Windows per-user `LOCALAPPDATA` already isolates by user.

---

## B4. Validation exceeds its time budget — **PARTIAL (correct by design; the design has a hard limit)**

**Path.** `BoundedValidationExecutor.run_with_timeout` (`infrastructure/bounded_executor.py:84`) submits the work
to a `ThreadPoolExecutor` and blocks on `future.result(timeout=timeout_ms/1000)`. On
`concurrent.futures.TimeoutError` it raises `TimeoutError`. The use case catches that and returns
`_degraded_on_timeout` → `ValidationResult(status="fail", degraded=True, degraded_reason="timeout")`.

**Can the work actually be cancelled? No — and the code is honest about it.** A running Python thread cannot be
forcibly killed. The timed-out callable keeps running to completion in the background as a "zombie." The crucial
design choice: the semaphore **permit is released by the future's done-callback** (line 174), *not* when the
caller times out. So a zombie **keeps occupying capacity** until it genuinely finishes. This is deliberate
(`bounded_executor.py:14-16` docstring): it means sustained slow validations correctly drain capacity and shed
new load, rather than the pool lying that a slot is free.

**Consequence.** Classify PARTIAL not because anything is wrong, but because the founder must understand the
ceiling: *timeout ≠ cancellation.* If a pathological validation hangs (it shouldn't — see B6), the thread is
occupied until it returns, and enough simultaneous zombies will saturate `capacity = max_workers + max_pending`
and shed all further work as `TimeoutError`/degrade. That is the *correct* failure (graceful degradation, host
survives) but it is a real capacity limit, not magic cancellation. The true defense against runaway validations is
upstream: bounded inputs (B6) + linear-time regex make a genuinely-hung pure-rule validation effectively
impossible; the timeout is the backstop, and the zombie-holds-capacity behavior is the honest accounting of that
backstop. A true hard kill would require subprocess/WASM isolation (Phase 3, and the audits agree it's premature).

---

## B5. The decorated function is async — validation runs OFF the event loop — **CORRECT**

**Path.** `async_wrapper` (`adapters/guard.py:87`) awaits the user function, then calls
`execute_async` → `timer.run_with_timeout_async`. `BoundedValidationExecutor.run_with_timeout_async`
(`bounded_executor.py:111`) acquires a permit on the **same** `BoundedSemaphore` (non-blocking, shed on
saturation), submits to the **same** thread pool, and awaits `asyncio.wait_for(asyncio.wrap_future(future), …)`.
The CPU-bound validation therefore runs on a pool worker thread, off the event loop, with the identical capacity
bound and millisecond deadline as the sync path.

**Consequence.** Correct and verified. A slow validation cannot stall concurrent asyncio tasks, and async callers
cannot bypass load-shedding via a raw `run_in_executor` (which was the original H1/H2 defect; the fix is proven by
`tests/adversarial/test_bounded_executor.py::test_async_concurrent_saturation_sheds_load` and
`::test_async_reentrant_call_runs_inline`). The re-entrancy guard (`_on_worker_thread()`) makes a nested call from
within a pool worker run inline, avoiding a same-pool deadlock — also tested.

---

## B6. A regex rule receives a pathological pattern or input — **CORRECT (one low-risk asterisk)**

**Path.** `RuleEngine.REGEX_PATTERN` (`domain/validator.py:230`). Before matching, it **fail-closes** on length:
a pattern longer than `MAX_PATTERN_LENGTH` (1000) or a value longer than `MAX_REGEX_VALUE_LENGTH` (50 000) becomes
a breach without ever compiling/matching. It compiles via `_compiled_pattern` (an `lru_cache` over
`re2.compile`) — **`google-re2`, a linear-time engine with no catastrophic backtracking** — and uses
`fullmatch`. An invalid pattern raises `re2.error`, caught and turned into a breach. The semantic validator
independently pre-rejects over-long schema patterns (`jsonschema_validator.py:148`).

**Consequence.** ReDoS is structurally neutralized: even a deliberately evil pattern can't burn unbounded CPU,
because the engine is linear-time *and* inputs are length-capped *and* compiled patterns are cached. `re2` is a
**required** core dependency (not optional), so this guarantee is always on. **The one asterisk:** `pii_sanitize.py`
uses the **stdlib `re`** module (not `re2`) for its redaction pattern `(['\"])(.*?)\1|(\b\d{4,}\b)`. That pattern
is non-catastrophic and runs on already-bounded breach messages, so the risk is low — but it is the single regex
in the project operating on schema-derived content that bypasses the project-wide `re2` rule. Worth converting for
consistency (Phase 0 polish), not urgent.

---

## B7. Credentials are missing or malformed — fails LOUD — **CORRECT**

**Path.** `CongineConfig.validate()` (`config.py:257`), run at the end of `from_env()`. If the base URL is **not**
local (`is_local_base_url()` is `False`), it requires `api_key`, `project_id`, and `tenant_id` to be present —
missing any raises `CongineConfigurationError`. It then enforces HTTPS for non-local URLs unless
`allow_cleartext=true`, again raising on violation. For **local** base URLs (exact loopback hosts only, by parsed
hostname), credentials and HTTPS are not required (dev ergonomics). If `allow_cleartext` is set and the plane is
non-local cleartext, the container logs a loud warning at construction (`dependency_injection.py:141`).

**Consequence.** The system fails loud, early, and at the right boundary: you cannot accidentally ship to a
production control plane with no API key or over plaintext. The hostname parsing (FIX-01) means
`localhost.evil.com` is correctly treated as non-local and subjected to the policy. The deliberate exemption is
exact loopback only, which is the right call. There is no silent-proceed path here.

---

## B8. Two requests arrive concurrently — shared mutable state is protected — **CORRECT**

**The shared mutable structures and their guards:**

| Structure | File | Protection |
|-----------|------|------------|
| LFU cache maps (`_key_to_value`, `_key_to_freq`, `_freq_to_keys`, `_min_freq`) | `lfu_cache.py` | a single `threading.RLock`; **every** public op (`get/put/clear/exists/size/sweep`) takes it |
| Executor counters + semaphore (`_in_flight`, `_rejected_total`, `_sem`) | `bounded_executor.py` | `threading.Lock` for counters; `BoundedSemaphore` for capacity; thread-local for re-entrancy |
| Breaker state (`_state`, `_consecutive_failures`, `_opened_at`, `_probe_in_flight`) | `circuit_breaker.py` | a single `threading.Lock` on every method; HALF_OPEN single-flight probe via `_probe_in_flight` |
| Telemetry queue + drop counter | `queue_event_bus.py` | `queue.Queue` (internally locked); `_dropped_lock` for the counter |
| Tenant registry (`_tenant_registry`) | `dependency_injection.py` | `_tenant_lock` (class-level) around lookup/insert/evict; default singleton via `_default_lock` double-checked |
| LangChain per-run buffers | `langchain_handler.py` | `threading.Lock` around buffer mutation, keyed per `run_id` |

**Consequence.** Concurrency is taken seriously and consistently. The cache primes in-place (update keys, never
clear-then-refill — `sync_contracts_usecase.py:239`) so a concurrent hot-path `get` always sees a coherent cache.
The validators are **stateless pure functions**, so there is no shared mutable state inside validation at all —
concurrency safety there is structural. The one concurrency-adjacent debt is *lifecycle*, not data race: see B9.

---

## B9. Multi-tenant LRU eviction can `close()` a still-referenced container — **PARTIAL / BROKEN-leaning**

**Path.** `ServiceContainer.for_tenant` (`dependency_injection.py:72`). On a registry hit it moves the entry to
the end (LRU-on-lookup). When the registry reaches `_MAX_TENANTS` (128) and a **new** tenant arrives, it pops the
oldest entry and calls `oldest_container.close()` (line 114) — stopping that container's cache sweeper, telemetry
drain, and validation pool.

**Consequence.** Two coupled problems. (1) The "recency" is keyed on `for_tenant()` **lookups**, not validation
**activity**: a heavily-used tenant that fetched its container once and cached the reference locally (the
documented production pattern!) can be evicted while still serving traffic. (2) Eviction calls `close()` on a
container a caller may still hold — pulling the cache, telemetry, and pool out from under live code; subsequent
guard calls on that reference would hit a shut-down pool (`run_with_timeout` raises `TimeoutError("validation
executor unavailable")`) and a stopped sweeper. This is the riskiest code in the container and it has **no direct
test**. Classify PARTIAL because it only bites past 128 concurrent tenants and only when references are held
across the eviction — but the consequence (a live tenant's engine torn down mid-use) is severe enough to treat as
the top Phase-0 correctness item. The Cursor and both Gemini audits independently flagged it; the fix is
refcount/idle-policy eviction + a direct test.

---

## B10. Payload/schema size bounds count characters, not bytes — **PARTIAL**

**Path.** `_check_payload_size` / `_check_schema_size` (`validate_contract_usecase.py:125,143`) compute
`len(json.dumps(payload, default=str))`. `len()` on a `str` is a **character** count; the budget is named
`max_payload_bytes`.

**Consequence.** For ASCII payloads the two coincide and the bound holds. For multibyte UTF-8 content, a payload
just over the byte budget can be under the character budget and slip through — the byte-named limit under-counts.
Low severity (the cap is generous at 1 MiB and `json.dumps` adds escaping overhead that partly compensates), but
it is a correctness gap relative to the field name. Fix: `len(json.dumps(...).encode("utf-8"))`. Secondary note:
`json.dumps` itself runs synchronously on the calling thread *before* the bounded executor — a deeply nested
hostile payload pays a serialization cost on the hot path (bounded by the 1 MiB cap, so finite, but real).

---

## B11. `CompositeValidator` runs the semantic validator even on a non-dict payload — **PARTIAL (latent, harmless today)**

**Path.** `CompositeValidator.validate` (`domain/validator.py:436`) calls `rule_validator.validate` (which
short-circuits a non-dict to a fail result) and **then unconditionally** calls
`semantic_validator.validate(payload, schema)` and merges. `LocalValidator` alone would have stopped at the
non-dict.

**Consequence.** Today this is harmless: the merged result already fails from the rule side, and `jsonschema`
tolerates a non-dict instance. But it is a latent assumption — a future semantic validator that assumes a dict
could raise on a non-dict payload, and that raise would propagate into the executor as an `internal_error`
degrade. Cheap to harden (short-circuit on non-dict before the semantic call). Documented in the prior
`docs/context/01_SYSTEM_STATE.md` as item #7.

---

## B12. Telemetry loss on saturation / process death — **PARTIAL (by design) → ABSENT (durability)**

**Path.** `QueueEventBus.publish` (`queue_event_bus.py:99`) does `put_nowait`; on `queue.Full` it increments
`_dropped_total` and logs a warning — the event is dropped. After `max_retries` ship failures a batch is dropped
and counted. The `_dropped_total` is surfaced in `ServiceContainer.health()` as `telemetry_dropped_total`.

**Consequence.** Loss is **silent-but-counted** by design (telemetry must never block or crash the hot path), and
the drop counter closes the *observability* gap (audit D-10) so operators have a loss signal. What is **ABSENT** is
**durability**: the queue is in-memory, so if the process dies, queued/unshipped events are lost. There is no WAL,
no SQLite spool, no transactional outbox. This is correct for Phase 0 (telemetry is fire-and-forget analytics, not
an audit trail) but is exactly the gap the Builder's Codex Phase-1 "make it remember" work and the Gemini-Flash
"Durable Local Outbox (SQLite WAL)" recommendation target. Fine for now; named so no one mistakes the queue for an
audit store.

---

## B13. Contract version is recorded but not resolved — **ABSENT (acknowledged scope edge)**

**Path.** `@congine_guard(version="latest")` threads `version` into telemetry only. The cache key is
`contract_id` **alone** (`lfu_cache.py`, `_resolve_schema`). There is no `(tenant, project, contract_id, version)`
keying and no version negotiation with the control plane.

**Consequence.** Two different versions of the same `contract_id` cannot coexist in cache, and "validated against
v1.0" in telemetry is an unverified label, not an enforced selection. ABSENT, and correctly out of Phase 0 scope —
but it means version provenance is currently aspirational. The Builder's Codex names this directly
("Contract versioning … cache key is `contract_id` only"); it is the first Phase-1 "extend contracts" item.

---

## B14. JSON-Schema keywords the rule engine silently ignores — **PARTIAL (the highest-leverage real-user trap)**

**Path.** `LocalValidator._extract_params` (`domain/validator.py:333`) understands `required`, `properties`
(type), `enum`, `min`/`max`/`minimum`/`maximum`, `pattern`, and `null_forbidden`. It does **not** understand
`minLength`, `maxLength`, `format`, `$ref`, nested `object` properties, `additionalProperties`, etc. Those are only
enforced when `CONGINE_SEMANTIC_VALIDATION=true` routes through `CompositeValidator` + `JsonSchemaSemanticValidator`.

**Consequence.** With semantic validation **off** (the default), a contract author can write
`{"summary": {"type": "string", "minLength": 10}}`, see it "load," and believe length is enforced — when it
silently is not. This is visible in the shipped example: `examples/LangChain/contracts/return_processing.json`
declares `summary.minLength: 10` and `ticket_id.pattern`, but in standalone file mode with semantic off, only the
pattern/enum/type/range rules fire; `minLength` is ignored. No data is corrupted, but a user can author a contract
that *looks* enforced and isn't. Highest-leverage correctness item for real adoption: either warn at sync time when
an unenforced keyword is present (semantic off), or document the rule-engine vocabulary as authoritative.

---

## B15. The shipped LangChain example raises on its own "clean" path — **BROKEN (example only, not the SDK)**

**Path.** `examples/LangChain/agent.py`. The guard is `@congine_guard(RETURN_CONTRACT, mode="raise")`. When
`GOOGLE_API_KEY` is unset, the offline fallback (line 88) returns `action="manual_review"`. The contract enum
(`return_processing.json:7`) is `["approve_return","reject_return","escalate"]` — `manual_review` is **not** in it.
The rule engine's `ENUM_VALUES` rule produces a breach → `is_pass()` is `False` → `mode="raise"` raises
`CongineValidationError` on Scenario 1, the "clean/compliant" demo. The Pydantic field description also misstates
the enum (`manual_review` instead of `escalate`).

**Consequence.** This is a defect in the **example**, not the SDK — but it is the first thing a new developer runs,
and it raises on the path labelled "Clean, Compliant Customer Input" whenever no API key is set (the common
first-run state). It actively undermines the 5-minute-quickstart credibility the Builder's Codex says is essential.
Fix is small: align the offline fallback `action` (and the Pydantic description) to the contract enum (use
`escalate`). Ground-truth confirmed by reading both `agent.py` and the contract JSON.

---

## Summary table

| # | Branch | Classification | Severity |
|---|--------|----------------|----------|
| B1 | No-container default path | CORRECT | — (perf nit) |
| B2 | Cache cold / miss | CORRECT | — |
| B3 | Network unavailable / snapshot fallback / tenant scoping | CORRECT | — |
| B4 | Time-budget overrun (timeout ≠ cancel) | PARTIAL (by design) | Med (capacity ceiling) |
| B5 | Async validation off the loop | CORRECT | — |
| B6 | Pathological regex / input | CORRECT | Low (pii_sanitize stdlib `re`) |
| B7 | Missing/malformed credentials | CORRECT | — |
| B8 | Concurrency / shared mutable state | CORRECT | — |
| B9 | Multi-tenant eviction `close()`s live container | PARTIAL→BROKEN | **High** (top P0) |
| B10 | Size bounds count chars not bytes | PARTIAL | Low |
| B11 | Composite runs semantic on non-dict | PARTIAL (latent) | Low |
| B12 | Telemetry loss / durability | PARTIAL → ABSENT | Med (Phase 1) |
| B13 | Contract version resolution | ABSENT | Med (Phase 1 scope) |
| B14 | Silently-ignored schema keywords | PARTIAL | **Med-High** (real-user trap) |
| B15 | Example raises on clean path | BROKEN (example) | Med (first impression) |
