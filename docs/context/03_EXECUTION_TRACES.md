# CONGINE EXECUTION TRACES

Generated: 2026-06-14
Each trace is a method call chain with `file:line` references. Files are under `libs/congine-sdk/src/congine_core/`.

---

## Trace 1 — Happy Path (valid payload, single tenant, HTTP contracts, sync)

Precondition: container bootstrapped, `contract_id` present in cache, `mode="envelope"`, `fail_mode=DEGRADE`.

1. Caller invokes the decorated function. `sync_wrapper` runs (`adapters/guard.py:76-84`).
2. `ctx = _resolve()` → returns the injected `container` (or `ServiceContainer.get_default()`) (`guard.py:57-58`).
3. `output = fn(*args, **kwargs)` — the wrapped function executes (`guard.py:78`).
4. `ctx.validate_contract_usecase.execute(payload=_payload(output), contract_id, contract_version)` (`guard.py:79-83`). `_payload` applies `extractor` if given, else passes `output` through (`guard.py:60-61`).
5. `ValidateContractUseCase.execute` (`usecases/validate_contract_usecase.py:49-84`):
   - `_check_payload_size` → `None` (under budget) (`:56,125-141`).
   - `_resolve_schema(contract_id)` → `schema_storage.get(contract_id)` → `LFUCache.get` returns the schema, bumps frequency (`:60,161-166`; `infrastructure/lfu_cache.py:79-94`).
   - `_check_schema_size` → `None` (`:61,143-159`).
   - `result = self.timer.run_with_timeout(do_validate, timeout_ms)` (`:70`).
6. `BoundedValidationExecutor.run_with_timeout` (`infrastructure/bounded_executor.py:84-109`):
   - Not on a worker thread → `_acquire_and_submit(func)` acquires a semaphore permit, increments `_in_flight`, submits to the pool, registers a done-callback that releases the permit (`:100-103,151-175`).
   - `future.result(timeout=…)` returns the `ValidationResult` (`:105`).
7. `do_validate` → `LocalValidator.validate(payload, schema)` (`usecases/...:65-66`; `domain/validator.py:369-408`): runs all 6 rules, none breach → `ValidationResult(status="pass", breaches=())`.
8. Back in `execute`: `_finalize(result, …)` (`:84,205-230`):
   - Builds a `TelemetryEvent` with sanitized (empty) breach list and `event_bus.publish(event)` (`:211-225`) → `QueueEventBus.publish` enqueues non-blocking (`infrastructure/queue_event_bus.py:99-116`).
   - `result.is_pass()` is `True` → `_handle_failure` is **not** called (`:227-228`).
9. `execute` returns the passing `ValidationResult`.
10. `_finish(output, result)` → returns `{"output": output, "validation_result": result}` (`guard.py:63-72`).

**End:** caller receives the envelope with `validation_result.is_pass() == True`. Telemetry drains asynchronously on the `congine_event_bus` daemon and ships to `{base_url}/api/v1/telemetry` (`queue_event_bus.py:152-296`).

---

## Trace 2 — Validation Failure in DEGRADE Mode

Difference from Trace 1: at least one rule breaches; `fail_mode=DEGRADE`.

1–6. Identical to Trace 1 through `run_with_timeout`.
7. `LocalValidator.validate` accumulates breaches → `ValidationResult(status="fail", breaches=(…))` (`domain/validator.py:397-408`).
8. `_finalize` (`usecases/validate_contract_usecase.py:205-230`):
   - **Telemetry first:** builds `TelemetryEvent` whose `breach_details` are run through `sanitize_breach_message` (`:216-223`) → `event_bus.publish(event)` (`:225`).
   - `result.is_pass()` is `False` → `_handle_failure(result, …)` (`:227-228,232-260`).
   - `fail_mode is DEGRADE` (not SILENT, not STRICT) → `logger.warning("Validation failed (degrade)", contract_id, contract_version, breaches=len, degraded)` (`:254-260`). **No raise.**
9. `execute` returns the failing `ValidationResult`.
10. `_finish`:
    - `mode="envelope"` → returns `{"output": output, "validation_result": result}` with `is_pass()==False` and the breach tuple (`guard.py:72`).

**What gets logged:** one WARNING record `"Validation failed (degrade)"` with breach count.
**What gets queued to telemetry:** one `TelemetryEvent(status="fail", breach_details=[sanitized…])`.
**End:** caller receives the envelope with `is_valid=False` and the breach list; execution continues.

---

## Trace 3 — Validation Failure in STRICT Mode

Difference from Trace 2: `fail_mode=STRICT`.

1–8a. Identical to Trace 2 up to and including `event_bus.publish(event)` (`usecases/validate_contract_usecase.py:225`). **Telemetry is published before any raise** — guarantee preserved.
8b. `_handle_failure` (`:232-252`):
   - `fail_mode is STRICT` → `logger.error("Validation failed (strict)", …)` (`:242-248`).
   - `raise CongineValidationError(f"Contract {contract_id} validation failed with N breach(es)")` (`:249-252`).
9. The exception propagates out of `execute` (it is a `CongineBaseException`; the `except CongineBaseException: raise` in `execute` only matters for exceptions raised *inside* the timed block — this raise happens in `_finalize`, after the try) and out of `guard.sync_wrapper`.

**End:** the caller's `try/except CongineValidationError` (or `CongineBaseException`) catches it. The envelope is never constructed. Note: a **timeout-degraded** failure (`degraded=True`, `status="fail"`) also raises here in STRICT mode.

> Guard `mode="raise"` is a *separate* raise site: even in DEGRADE fail_mode, `_finish` raises `CongineValidationError` when `validation_result.is_pass()` is false (`guard.py:64-69`). So a failure can raise from the use case (STRICT) or from the guard (`mode="raise"`), independently.

---

## Trace 4 — Load Shedding (pool saturated)

Precondition: `capacity = max_workers + max_pending` permits already held by in-flight/zombie validations.

1–5. As Trace 1 through `execute` calling `self.timer.run_with_timeout(do_validate, timeout_ms)` (`usecases/validate_contract_usecase.py:70`).
6. `BoundedValidationExecutor.run_with_timeout` → `_acquire_and_submit` (`bounded_executor.py:103,151-164`):
   - `self._sem.acquire(blocking=False)` returns `False` (saturated).
   - `_rejected_total += 1` under lock; `raise TimeoutError("validation capacity exhausted (load shed)")` (`:161-164`).
7. Back in `execute`, the `except TimeoutError:` arm (`:71-72`) → `result = self._degraded_on_timeout(contract_id, started)` (`:168-182`):
   - `logger.warning("Validation timeout", contract_id, timeout_ms)` (`:172-176`).
   - returns `ValidationResult(status="fail", degraded=True, degraded_reason="timeout", duration_ms=…)`.
8. `_finalize` publishes a `TelemetryEvent(status="fail")` and then:
   - **DEGRADE** → WARNING, returns degraded result (caller gets an envelope, *no crash*).
   - **STRICT** → raises `CongineValidationError` (load shed becomes a hard failure by policy).
   - **SILENT** → returns degraded result, no log.

**End (DEGRADE):** caller receives a degraded fallback `ValidationResult`, never an unbounded queue or a process stall. The async path is identical via `run_with_timeout_async` → `_acquire_and_submit` (same semaphore) (`bounded_executor.py:111-149`).

---

## Trace 5 — Cold Boot on a Fresh Container (HTTP mode)

Entry: `ServiceContainer.bootstrap()` (`dependency_injection.py:270-282`).

1. `bootstrap()` checks it is **not** inside a running event loop; if it is, raises `RuntimeError("… await bootstrap_async()")` (`:271-278`).
2. `loaded = self.sync_contracts_usecase.sync_once_single_flight()` (`:279`).
3. `SyncContractsUseCase.sync_once_single_flight` (`usecases/sync_contracts_usecase.py:105-135`):
   - `boot_lock_path` was wired from `HttpContractRepository.snapshot_lock_path` and `portalocker` is available → proceed (`:120`).
   - Sleep a random 0–0.5s jitter (`:124-128`).
   - `_try_boot_lock()` attempts a non-blocking `portalocker LOCK_EX | LOCK_NB` on the per-scope boot lock (`:156-181`):
     - **Winner (lock acquired):** `return self.sync_once()` (`:131-132`).
     - **Loser (lock busy):** `logger.info("Boot lock held by sibling worker; loading snapshot only")` then `return self.load_snapshot_only()` (`:133-135`).
4. Winner path → `sync_once` → `_fetch_sync` (`:70-84,182-195`):
   - `_breaker_allows()` (`:212-213`): if breaker CLOSED → `asyncio.run(contract_repository.fetch_active_contracts())` (`:189`).
   - `HttpContractRepository.fetch_active_contracts` GETs `{base_url}/api/v1/contracts/active` with tenant/project/api-key headers, enforces `max_http_response_bytes`, validates `contracts` is a list (`http_contract_repository.py:93-130`).
   - On success: `_breaker_record_success()`, return `(contracts, fetched=True)` (`:194-195`).
5. `_apply(contracts, fetched=True)` (`:223-237`):
   - `_prime_cache` does `schema_storage.put(id, schema, ttl)` per contract — **in-place updates**, never clear-then-refill, so concurrent `get` always sees a coherent cache (`:239-252`).
   - `fetched=True` → `contract_repository.save_snapshot(contracts)` writes the atomic, locked, scoped snapshot (`:230-234`; `http_contract_repository.py:163-207`).
   - `logger.info("Schema cache synced", count=loaded)`; returns `loaded`.
6. Back in `bootstrap`: if `config.sync_enabled` → `start_background_sync()` → `sync_worker.start()` launches the `congine_background_sync` daemon (`dependency_injection.py:280-292`; `infrastructure/background_sync.py:55-66`). The daemon wakes every `sync_interval_seconds` and runs `sync_once` (`background_sync.py:79-97`).

**End:** cache is primed; if `sync_enabled`, the background sync worker is running. (Cache sweeper + telemetry drain daemons started earlier in `__init__` when `start_background_services=True`.)

### If the HTTP fetch fails during boot

- `fetch_active_contracts` raises `CongineSyncError` → caught in `_fetch_sync` (`:190-193`): `_breaker_record_failure()` (5 consecutive → breaker OPEN), `logger.warning("Contract fetch failed; falling back to disk snapshot")`, return `(load_snapshot(), fetched=False)`.
- If a valid snapshot exists → `_apply` primes the cache from it but **skips** `save_snapshot` (`fetched=False`).
- If no snapshot → `_apply` sees empty contracts → `logger.warning("No contracts available; retaining current cache")`, returns `0`. The existing cache is never wiped (`:223-225`).
- If the breaker is already OPEN at boot, `_fetch_sync` short-circuits to `load_snapshot()` without touching the network, avoiding the HTTP timeout entirely (`:183-187`). `bootstrap()` therefore returns fast even against a dead control plane.

**Consequence for a truly cold container with a dead plane and no snapshot:** the cache stays empty, so the first guarded call hits `_resolve_schema` → `CongineContractNotFoundError` (`usecases/validate_contract_usecase.py:161-166`). This is the cold-start gap to be aware of (see `05_QUICKSTART_TEST.md`).
