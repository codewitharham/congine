## 14. Invariants and guarantees

The seven guarantees are the ones stated in `libs/congine-sdk/.claude/CLAUDE.md` and re-asserted in
`docs/context/01_SYSTEM_STATE.md`. Each is re-verified against current code below, with the test
that backs it and a status. Four further invariants the system genuinely upholds — but that nobody
has written down — are added in §14.8.

Status: **HOLDS** · **AT RISK** (holds today, with a specific condition that could break it) ·
**BROKEN** · **UNVERIFIED**.

### 14.1 G1 — Bounded latency / load shedding

**Mechanism.** `BoundedValidationExecutor` caps outstanding work at
`capacity = max_workers + max_pending` (default 20) with a `threading.BoundedSemaphore`
(`bounded_executor.py:59-60`). A non-blocking `acquire` failure increments `_rejected_total` and
raises `TimeoutError` immediately (`:161-164`) rather than queueing. The permit is released **only**
by the future's done-callback (`:174`, `:177-180`), so a timed-out zombie continues to occupy
capacity. Sync and async share the same `_acquire_and_submit` (`:103`, `:140`).

**Tests.** `tests/adversarial/test_bounded_executor.py`: `test_saturation_sheds_load` (`:36`),
`test_timeout_raises` (`:27`), `test_in_flight_returns_to_zero` (`:75`),
`test_async_concurrent_saturation_sheds_load` (`:117`), `test_async_timeout_raises` (`:106`),
`test_reentrant_call_runs_inline_no_deadlock` (`:62`), `test_async_reentrant_call_runs_inline`
(`:146`). Also `tests/test_validation_runner_port.py` (5).

**Status: HOLDS.** With two documented caveats, neither of which breaks the bound:
(a) a re-entrant inline run is **not** time-boxed (`:100-101`, `:137-138`) — it takes no permit and
observes no deadline; (b) load shed and genuine overrun are indistinguishable to the caller (both
surface as `degraded_reason="timeout"`), so only `health()["validation_rejected_total"]` separates
them operationally.

### 14.2 G2 — No control-plane stall on boot

**Mechanism.** `_fetch_sync`/`_fetch_async` consult the breaker before every fetch
(`sync_contracts_usecase.py:201`, `:216`). When it does not allow, the network is skipped entirely
and `load_snapshot()` is returned inline (`:202-205`) — the HTTP timeout is never entered. When the
breaker is CLOSED and the plane is dead, one timeout is paid
(`control_plane_http_timeout_seconds`, default 10 s), `CongineSyncError` is caught (`:208`), a
breaker failure is recorded, and the snapshot is used. After 5 consecutive failures the breaker
trips OPEN for 30 s.

**Tests.** `tests/adversarial/test_remediations.py:201` `test_bootstrap_does_not_stall_when_breaker_is_open`;
`:238` `test_breaker_trips_open_after_consecutive_fetch_failures`; `:261`
`test_breaker_success_resets_on_successful_fetch`; `tests/test_circuit_breaker.py` (11).

**Status: HOLDS.** Correction to the prior documentation: the OPEN-breaker path is the inline
`load_snapshot()` in `_fetch_sync`, **not** `load_snapshot_only()` — see §8.3.

### 14.3 G3 — No thundering herd

**Mechanism.** `sync_once_single_flight` (`:123-153`) sleeps a random 0–0.5 s
(`random.uniform`, `:142`), then takes a per-scope `portalocker` lock with
`timeout=0, LOCK_EX|LOCK_NB` (`:183-188`). The winner fetches; losers call `load_snapshot_only()`
and never touch the network (`:151-153`). The lock file is scoped per
`(base_url, project_id, tenant_id)` via `_scope_key` (`http_contract_repository.py:78-80`) and is
**deliberately distinct** from the snapshot-write `.lock` (`:75-77`) so boot coordination and write
serialisation do not contend.

**Tests.** `tests/test_single_flight_boot.py` (3), audit D-7.

**Status: HOLDS, scope-limited.** Two limits worth stating: the lock is a *host-local* advisory file
lock, so it de-duplicates workers on one host, not pods across a cluster — a 100-pod cold start
still issues 100 fetches, one per host. And only `bootstrap()` uses single-flight; the periodic
`BackgroundSyncWorker` calls plain `sync_once` (`background_sync.py:89`), so steady-state fetches
are uncoordinated by design.

### 14.4 G4 — Snapshot integrity

**Mechanism.** Five layers.

| Layer | Where |
|---|---|
| Per-scope path: `snapshot_{sha256(base_url\|project_id\|tenant_id)[:16]}.json` | `http_contract_repository.py:53-58`, `:72-74` |
| Per-user app directory (`%LOCALAPPDATA%` / `$XDG_CACHE_HOME` / `~/.cache`), never a world-shared temp root; `chmod 0o700` best-effort on POSIX | `:43-50`, `:185-189` |
| Atomic write: `tempfile.mkstemp` in the same directory + `os.replace`, temp unlinked on failure | `:199-207` |
| Cross-process serialisation via an advisory `portalocker` lock on a sibling `.lock`; a writer that times out **skips** rather than blocks or raises | `:191-198`, `:212-243` |
| Load-time refusal: symlink rejected, non-owner rejected (POSIX), envelope shape validated, non-dict entries filtered | `:151-156`, `:258-269` |

**Tests.** `tests/adversarial/test_host_bypass.py` (5, snapshot poisoning);
`tests/adversarial/test_remediations.py:183` `test_symlinked_snapshot_is_refused`;
`tests/unit/test_repository.py` (14).

**Status: HOLDS on POSIX; AT RISK on Windows.** `_owned_by_current_user` returns `True`
unconditionally when `os.name != "posix"` (`:248-249`). On Windows the ownership check is a no-op,
so integrity there rests on the per-user `%LOCALAPPDATA%` path plus the symlink refusal. That is a
reasonable posture (the default directory is already per-user and ACL-protected) but the guarantee
is weaker than on POSIX, and the codebase does not say so. Also note `os.path.islink` does not
detect NTFS junctions.

### 14.5 G5 — No ReDoS

**Mechanism.** `google-re2` is a **required core dependency** (`pyproject.toml:28`, FIX-02) — never
an optional extra — giving linear-time matching with no catastrophic backtracking. On top of that:
patterns over 1 000 chars are refused before compilation (`validator.py:252-260`), values over
50 000 chars are refused before matching (`:261-269`), compiled patterns are cached in a 512-entry
`lru_cache` (`:41-44`), and the semantic validator pre-rejects over-long schema patterns
independently (`jsonschema_validator.py:148-168`). All refusals are fail-closed breaches.

**Tests.** `tests/adversarial/test_redos.py` (5), audit H3.

**Status: HOLDS, with one documented exception.** `pii_sanitize.py:9,14` uses **stdlib `re`**, not
`re2` — the one regex in the codebase outside the project-wide linear-time rule. The risk is low:
the pattern `(['\"])(.*?)\1|(\b\d{4,}\b)` has no nested quantifier and the inputs are bounded breach
messages (themselves capped by `semantic_max_breaches`). But it is a real exception and it sits on
the path that processes the least-trusted strings in the system — validator-generated messages
containing instance data. Recorded as debt D7.

### 14.6 G6 — Multi-tenant isolation

**Mechanism.** Four independent parts.

| Part | Where |
|---|---|
| `get_default()` raises in `multi_tenant` mode | `dependency_injection.py:90-95` (FIX-05) |
| `CongineCallbackHandler` requires an explicit `container=` in `multi_tenant` mode | `langchain_handler.py:42-51` |
| Snapshot paths and boot-lock paths scoped per `(base_url, project_id, tenant_id)` | `http_contract_repository.py:53-58` |
| Per-tenant containers, each with its own cache, breaker, bus, pool | `for_tenant()` `:102-176` |

**Tests.** `tests/adversarial/test_tenant_isolation.py` (2, FIX-05);
`tests/test_agent_workflow.py` (5); `tests/unit/test_container_tenant_lru.py` (7, P0-1).

**Status: HOLDS.** The prior asterisk — eviction `close()`ing a live container — is **resolved**
(§2.4). One process-wide structure is shared across tenants: the `_compiled_pattern` `lru_cache`
(`validator.py:41`). It is keyed on the pattern string and stores only compiled regexes, so no
tenant data crosses; a tenant can observe a marginal timing difference on a pattern another tenant
already compiled, which is not a meaningful isolation break for this threat model. Recorded for
completeness, not as debt.

The residual issue is *resource* isolation, not data isolation: an evicted-but-referenced container
keeps its threads alive off-registry (§7.7, debt D3).

### 14.7 G7 — PII-safe telemetry

**Mechanism.** Three layers.

| Layer | Where |
|---|---|
| Every breach message passes `sanitize_breach_message` before entering a `TelemetryEvent` | `validate_contract_usecase.py:220` |
| The semantic validator sanitises at the source too | `jsonschema_validator.py:114`, `:132` |
| The logger enforces an unconditional blocklist (`api_key`, `authorization`, `x-api-key`, `payload`, `breach_details`) plus, for non-local URLs, an automatic 12-key allowlist | `logger.py:31-40`, `:76-87`; `config.py:297-318` (FIX-08) |

`sanitize_breach_message` (`pii_sanitize.py:14-26`) replaces quoted substrings and 4+-digit runs
with `'<redacted>'`, preserving the constraint description.

**Tests.** `tests/adversarial/test_pii_sanitization.py` (3, FIX-04); `tests/unit/test_logger.py` (5).

**Status: HOLDS.** Structural note: the isolation identifiers travel as HTTP headers
(`queue_event_bus.py:235-239`), not in the event body, so `_serialize` emits exactly six keys and
cannot leak tenant identity into the payload. Sanitisation is conservative but not exhaustive — an
unquoted, non-numeric instance value embedded in a custom rule message would survive. Every
*built-in* rule message names only the field and the constraint, never the value
(`validator.py:113`, `:143`, `:166`, `:199`, `:224`, `:287`), so the built-in surface is clean by
construction; a caller supplying custom rules via `LocalValidator(rules=…)` could break it.

### 14.8 Invariants discovered, not previously documented

These are genuine, code-backed properties the system upholds that no prior document states.

**G8 — A failed sync never destroys a healthy cache.**
`_apply` returns early on falsy contracts, logging `"No contracts available; retaining current
cache"` (`sync_contracts_usecase.py:242-244`), and `_prime_cache` updates keys **in place** rather
than clear-then-refill (`:257-271`, with an explicit comment). So a dead control plane, a corrupt
snapshot and a poisoned snapshot are all incapable of blanking the in-memory cache, and there is no
window during a successful sync in which a concurrent hot-path `get` sees a partially-empty cache.
**Tests:** `tests/unit/test_sync_usecase.py:57` `test_failure_does_not_clear_existing_cache`, `:46`
`test_sync_once_corrupt_snapshot_returns_zero`, `:84` `test_repeatable_sync_updates_in_place`.
**Status: HOLDS.**

**G9 — Telemetry is published before a strict-mode raise.**
`_finalize` publishes (`validate_contract_usecase.py:225`) and only then calls `_handle_failure`
(`:227-228`), which is what raises under `STRICT` (`:249`). A compliance-critical deployment
therefore never loses the record of the violation that stopped it. Stated in `README.md`'s
failure-mode table; **not** stated in either audit document. **Test:** exercised via
`tests/integration/test_end_to_end.py`. **Status: HOLDS.**

**G10 — A missing contract fails closed regardless of `fail_mode`.**
`_resolve_schema` raises `CongineContractNotFoundError` (`:161-165`) *before* any fail-mode logic is
consulted. `silent` mode cannot suppress it; `degrade` cannot downgrade it. This is deliberate — a
missing contract is a wiring error, not a validation outcome — and it means an empty cache is loud
rather than quiet. **Status: HOLDS.** It is also the sharpest edge in the system: a cold boot with a
dead plane and no snapshot turns every guarded call into an exception (§9.2 row 29).

**G11 — Telemetry can never block or break the hot path.**
`publish` is `put_nowait` + `except queue.Full` (`queue_event_bus.py:105-116`) with no re-raise; the
`NoOpEventBus` alternative is a bare `return None`. No network call occurs on the hot path under any
configuration — shipping happens exclusively on the `congine_event_bus` daemon. **Tests:**
`tests/unit/test_event_bus.py` (11). **Status: HOLDS.** The corollary is that telemetry is
**not durable**: queue-full drops, retry-exhausted drops, breaker-OPEN drops and process death all
lose events silently apart from the `dropped_total` counter.

### 14.9 Summary

| # | Guarantee | Mechanism | Test | Status |
|---|---|---|---|---|
| G1 | Bounded latency / load shedding | `BoundedValidationExecutor` + `BoundedSemaphore`, permit-until-completion | `test_bounded_executor.py` (10) | **HOLDS** |
| G2 | No boot stall | breaker gate + inline snapshot fallback | `test_remediations.py:201,238,261`; `test_circuit_breaker.py` (11) | **HOLDS** |
| G3 | No thundering herd | jitter + non-blocking `portalocker` boot lock | `test_single_flight_boot.py` (3) | **HOLDS** (per host; boot only) |
| G4 | Snapshot integrity | scoped path, per-user dir, atomic write, cross-process lock, load-time refusal | `test_host_bypass.py` (5); `test_repository.py` (14) | **HOLDS** (POSIX) / **AT RISK** (Windows ownership check is a no-op) |
| G5 | No ReDoS | `re2` core dep + length caps + pattern cache | `test_redos.py` (5) | **HOLDS** (except `pii_sanitize` stdlib `re`) |
| G6 | Multi-tenant isolation | `get_default()` disabled, scoped snapshots, per-tenant containers, safe eviction | `test_tenant_isolation.py` (2); `test_container_tenant_lru.py` (7) | **HOLDS** — prior asterisk resolved |
| G7 | PII-safe telemetry | breach sanitisation ×2 + logger blocklist + auto-allowlist | `test_pii_sanitization.py` (3); `test_logger.py` (5) | **HOLDS** |
| G8 | Failed sync never clears the cache | early return + in-place `put` | `test_sync_usecase.py:57,46,84` | **HOLDS** *(newly documented)* |
| G9 | Telemetry precedes a strict raise | publish at `:225`, raise at `:249` | `test_end_to_end.py` | **HOLDS** *(newly documented)* |
| G10 | Missing contract fails closed in every mode | raise before fail-mode logic | `test_usecase.py` | **HOLDS** *(newly documented)* |
| G11 | Telemetry never blocks the hot path | `put_nowait` + `except Full`; no hot-path I/O | `test_event_bus.py` (11) | **HOLDS** *(newly documented)* |

**Net: eleven invariants, all holding. One is weaker on Windows than on POSIX, and one carries a
narrow, documented exception.** None is broken.
