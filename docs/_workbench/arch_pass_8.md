## 9. Failure paths

Every failure mode, one row per mode. "Caller-visible" describes what the host application actually
observes at the guard boundary under the default `fail_mode=degrade`; divergences under `strict` and
`silent` are stated where they differ.

### 9.1 Hot-path failures

| # | Trigger | System response | Caller-visible result | Logged | Telemetry |
|---|---|---|---|---|---|
| 1 | **Oversized payload** — `len(json.dumps(payload, default=str)) > max_payload_bytes` | `_check_payload_size` returns a fail result and `execute` jumps straight to `_finalize`; the validator is never invoked (`validate_contract_usecase.py:56-58, 125-141`) | `ValidationResult(status="fail", breaches=(BreachDetail("INPUT_BOUNDS","<root>","Payload exceeds max_payload_bytes budget"),), degraded=False)`. `strict` ⇒ `CongineValidationError` | WARNING `"Validation failed (degrade)"` (`:254`); nothing at the guard | published, `status="fail"`, one `INPUT_BOUNDS` breach |
| 2 | **Unserialisable payload** — `json.dumps` raises `TypeError`/`ValueError` | `size = 0` (`:128-129`), so the guard **passes** and validation proceeds normally | normal validation of the un-measured payload | none | normal |
| 3 | **Oversized schema** — cached schema exceeds `max_schema_bytes` | `_check_schema_size` (`:143-159`) | as row 1 but `field="<schema>"`, message `"Schema exceeds max_schema_bytes budget"` | WARNING | published, one `INPUT_BOUNDS` breach |
| 4 | **Contract not found** — `schema_storage.get()` returns `None` (miss, TTL expiry, or cache never primed) | `_resolve_schema` logs and raises (`:161-165`) | **`CongineContractNotFoundError` propagates to the host in all three fail modes.** No telemetry, no degradation — a missing contract is a wiring error, not a validation outcome | ERROR `"Schema not found"` with `contract_id` | **none** — `_finalize` is never reached |
| 5 | **Validation breach** (any of the six rules) | Rules return `BreachDetail`s; `status="fail"` | `degrade` ⇒ the failing result is returned; `strict` ⇒ ERROR then `CongineValidationError` raised **after** the publish (`:241-252`); `silent` ⇒ returned with no log (`:238-239`). Guard `mode="raise"` raises independently (`guard.py:65-69`) | `degrade` ⇒ WARNING; `strict` ⇒ ERROR; `silent` ⇒ nothing | published with sanitised breach messages |
| 6 | **Validation timeout** — the future overruns `timeout_ms` | `future.result(timeout=…)` raises `concurrent.futures.TimeoutError`, converted to `TimeoutError` (`bounded_executor.py:106-109`); `execute` catches it (`:71-72`) | `ValidationResult(status="fail", breaches=(), degraded=True, degraded_reason="timeout", duration_ms=elapsed)` — **fails closed with zero breach detail** | WARNING `"Validation timeout"` with `contract_id`, `timeout_ms` (`:172-176`) | published, `status="fail"`, empty `breach_details` |
| 7 | **Capacity exhausted (load shed)** — `BoundedSemaphore.acquire(blocking=False)` fails | `_rejected_total += 1`; `TimeoutError("validation capacity exhausted (load shed)")` raised **before any work is submitted** (`bounded_executor.py:161-164`) | indistinguishable from row 6: `degraded_reason="timeout"`. The `rejected_total` counter (`health()["validation_rejected_total"]`) is the **only** way to tell load shed from genuine overrun | WARNING `"Validation timeout"` — the same message as row 6 | published, `status="fail"`, empty breaches |
| 8 | **Pool already shut down** — `submit` raises `RuntimeError` | permit released, `TimeoutError("validation executor unavailable")` (`bounded_executor.py:170-172`) | as row 6 | WARNING `"Validation timeout"` | published |
| 9 | **`MemoryError` / `RecursionError` inside the validator** | caught explicitly (`:73-76`) | `degraded=True, degraded_reason="resource_error"` | ERROR `"Validation error"` with `error_type`, `degraded_reason` (`:192-197`) | published, empty breaches |
| 10 | **Any other exception inside the validator** | caught by the bare `except Exception` (`:79-82`) | `degraded=True, degraded_reason="internal_error"` | ERROR `"Validation error"` with `error_type` | published, empty breaches |
| 11 | **A `CongineBaseException` from inside the validator** | **re-raised unchanged** (`:77-78`) — deliberately not degraded | propagates to the host | whatever the raiser logged | **none** |
| 12 | **Non-dict payload** | `LocalValidator.validate` short-circuits (`domain/validator.py:384-395`) | `status="fail"`, one `TYPE_MATCH`/`<root>` breach `"Payload must be an object/dict"`, `degraded=False` | per fail mode | published, one breach |
| 13 | **Non-dict *schema*** (e.g. a string cached under a contract id) | `_extract_params` calls `schema.get(...)` → `AttributeError` → row 10 | `degraded=True, degraded_reason="internal_error"`. **Verified end-to-end** | ERROR, `error_type="AttributeError"` | published, empty breaches |
| 14 | **Union / list `type` declaration** — e.g. `{"type": ["string","null"]}` | `_type_matches` does `_JSON_TYPE_MAP.get(json_type)` with an unhashable list ⇒ `TypeError: cannot use 'list' as a dict key` → row 10 | `degraded=True, degraded_reason="internal_error"` — **every validation against that contract degrades, silently, forever**. Verified end-to-end. Since P0-2 the *load* is warned about (`schema_vocabulary.py:99-101`, `find_unenforced_keywords` reports `field.type`), but only on the cache-prime path | ERROR `"Validation error"`, `error_type="TypeError"` | published, empty breaches |
| 15 | **Invalid regex pattern** in the schema | `re2.error` caught (`domain/validator.py:272-280`) | a normal `REGEX_PATTERN` breach `"Invalid regex pattern for '<field>'"` — **fails closed, does not degrade** | per fail mode; `re2` itself writes a line to stderr outside Congine's logger | published |
| 16 | **Over-long regex pattern** (> `MAX_PATTERN_LENGTH` = 1000) | length-capped before compilation (`:252-260`) | `REGEX_PATTERN` breach `"Pattern for '<field>' exceeds the safe length budget"` — fail-closed | per fail mode | published |
| 17 | **Over-long value for a regex field** (> `MAX_REGEX_VALUE_LENGTH` = 50 000) | length-capped (`:261-269`) | `REGEX_PATTERN` breach `"Value for '<field>' is too long to match safely"` | per fail mode | published |
| 18 | **Unknown schema dialect** — bad `CONGINE_JSONSCHEMA_DRAFT` | `_resolve_draft` raises `CongineConfigurationError` (`jsonschema_validator.py:64-68`) at **container construction**, not at validation — fail-closed and early, even when semantic validation is off | `ServiceContainer(...)` raises; the process does not start. Note the sweeper and drain threads may already be running (§7.1) | none from Congine | none |
| 19 | **Invalid schema under semantic validation** — `check_schema` raises `SchemaError` | converted to a single `SEMANTIC_SCHEMA`/`<schema>` breach with a sanitised message (`:107-116`) | `status="fail"`, one breach, `degraded=False` | per fail mode | published |
| 20 | **Too many semantic breaches** (> `semantic_max_breaches`, default 100) | drain stops; a `SEMANTIC_TRUNCATED`/`<root>` marker breach is appended (`:135-145`) | `status="fail"` with 101 breaches, the last being the truncation marker | per fail mode | published |

### 9.2 Control-plane and boot failures

| # | Trigger | System response | Caller-visible result | Logged | Telemetry |
|---|---|---|---|---|---|
| 21 | **Contract fetch failure** — transport error, non-2xx, missing `contracts` key, non-list `contracts`, or a body over `max_http_response_bytes` | all funnelled into `CongineSyncError` (`http_contract_repository.py:131-140`); `_fetch_sync` catches it, records a breaker failure, falls back to `load_snapshot()` (`sync_contracts_usecase.py:208-211`) | `bootstrap()` returns normally with the snapshot count (possibly `0`) — **it never raises** | ERROR `"Contract fetch failed"` with `url`, `error_type`; WARNING `"Contract fetch failed; falling back to disk snapshot"` | none |
| 22 | **Breaker OPEN at fetch time** | `_fetch_sync` skips the network entirely and returns `load_snapshot()` (`:201-205`) | `bootstrap()` returns fast — no HTTP timeout is paid | WARNING `"Circuit breaker OPEN; skipping contract fetch (snapshot fallback)"` | none |
| 23 | **Missing snapshot** | `open()` raises `FileNotFoundError`, swallowed; `load_snapshot` returns `None` (`http_contract_repository.py:159-160`) | `_apply` retains the current cache and returns `0` | WARNING `"No contracts available; retaining current cache"` | none |
| 24 | **Corrupt snapshot** — invalid JSON, or a valid-JSON envelope that is not a dict / has no list `contracts` / has no dict entries | `json.JSONDecodeError` swallowed, or `_validate_envelope` returns `None` (`:258-269`) | as row 23 — **a poisoned snapshot never wipes a healthy in-memory cache** | WARNING `"No contracts available; retaining current cache"` | none |
| 25 | **Symlinked snapshot** | refused before opening (`:151-153`) | as row 23 | WARNING `"Refusing symlinked snapshot"` with `path` | none |
| 26 | **Snapshot owned by another user** (POSIX only; always `True` on Windows and where `os.getuid` is absent — `:245-256`) | refused (`:154-156`) | as row 23 | WARNING `"Refusing snapshot not owned by current user"` | none |
| 27 | **Snapshot write lock busy** — another process holds it past `snapshot_lock_timeout_seconds` | the write is **skipped**, not retried or raised (`:191-198`) | none — sync still succeeds; the sibling is writing identical contracts | WARNING `"Snapshot lock busy; skipping write"` | none |
| 28 | **Snapshot write fails** — `OSError` from `mkstemp`/`json.dump`/`os.replace` | the temp file is unlinked and the exception re-raised (`:204-207`), then caught by `_apply` (`:251-252`) | none — the cache is already primed; only persistence failed | ERROR `"Snapshot persist failed"` with `error` | none |
| 29 | **Cold start with an empty cache** (no snapshot, dead plane) | `bootstrap()` returns `0` | every subsequent validation raises `CongineContractNotFoundError` (row 4) in **all** fail modes — the system **fails closed** | WARNING at boot; ERROR per validation | none |
| 30 | **Contracts directory missing / unreadable** (file repo) | `os.path.isdir` false ⇒ return `[]` (`file_contract_repository.py:60-66`) | `bootstrap()` returns `0` ⇒ row 29 | WARNING `"Contracts directory missing"` with `contracts_dir` | none |
| 31 | **Malformed contract file** (bad JSON/YAML, or larger than `max_file_bytes`) | that file is skipped; the scan continues (`:75-82`, `:104-111`, `:134-146`) | the remaining contracts load normally | WARNING `"Skipping malformed contract file"` with `path`, `error_type` | none |
| 32 | **Background sync pass fails** for any reason | `_safe_sync` swallows every exception except `KeyboardInterrupt`/`SystemExit` (`background_sync.py:88-97`) | none — the loop survives and retries next interval | ERROR `"Background sync pass failed"` with `error_type` | none |
| 33 | **`bootstrap()` called inside a running event loop** | pre-empted by an explicit guard (`dependency_injection.py:346-354`) | `RuntimeError("bootstrap() cannot run inside an event loop; await bootstrap_async()")` | none | none |
| 34 | **`get_default()` in multi-tenant mode** | `CongineConfigurationError` (`:90-95`) | raised at guard-call time for any default-container guard | none | none |
| 35 | **Incomplete or cleartext non-local config** | `CongineConfig.validate()` raises `CongineConfigurationError` (`config.py:257-283`) | `from_env()` raises — the process does not start | none | none |
| 36 | **Cleartext explicitly allowed** (`allow_cleartext=true`, non-local, non-HTTPS) | construction proceeds | none | **WARNING at container construction** `"Cleartext control plane in use…"` with `base_url` (`dependency_injection.py:216-223`) | none |

### 9.3 Telemetry failures

| # | Trigger | System response | Caller-visible result | Logged | Telemetry |
|---|---|---|---|---|---|
| 37 | **Telemetry queue full** (`telemetry_queue_size`, default 10 000) | `queue.Full` caught; `_dropped_total += 1` (`queue_event_bus.py:107-116`) | **none — the hot path is unaffected.** The event is lost | WARNING `"Event queue full, dropping event"` with `contract_id`, `dropped_total` | the event is dropped |
| 38 | **Telemetry ship failure, retries remaining** | WARNING; interruptible backoff (`_stop_event.wait(delay)`), delay doubles to `backoff_max` (`:256-280`) | none | WARNING `"Telemetry ship failed"` with `attempt`, `max_retries`, `error` | retried |
| 39 | **Telemetry ship failure, budget exhausted** | `circuit_breaker.record_failure()`; `_dropped_total += len(batch)`; the batch is dropped (`:264-276`) | none | ERROR `"Telemetry chunk dropped after retries"` with `count`, `dropped_total` | whole batch lost |
| 40 | **Breaker OPEN at ship time** | the batch is dropped **without** a network attempt; `_dropped_total += len(batch)` (`:221-231`) | none | WARNING `"Circuit breaker OPEN; dropping telemetry batch"` | whole batch lost |
| 41 | **Stop requested during backoff** | `_stop_event.wait(delay)` returns `True` ⇒ `_ship` returns `False` immediately (`:278-279`) | none | none extra | that batch lost |
| 42 | **Process exit with a non-empty queue** | `atexit` `_drain_on_exit` sets the stop flag and flushes with `max_attempts=1` (`:173-180`) | none | per attempt | best-effort; whatever fails is lost — **telemetry is not durable** |
| 43 | **`stop()` join times out while the daemon is mid-`_ship`** | `stop()` closes `self._client` and sets it to `None` (`:139-141`). The daemon's next client use raises `RuntimeError`, which `_ship` does **not** catch (it catches only `httpx.HTTPError`, `:256`), so it escapes `_drain_loop` and the daemon thread dies with a traceback on stderr | none — the container is closing anyway | an unhandled-thread-exception traceback, outside the structured logger | remaining events lost |

### 9.4 Drift

| # | Trigger | System response | Caller-visible result | Logged | Telemetry |
|---|---|---|---|---|---|
| 44 | **`evaluate_drift()` without `[stats]`** | `ImportError` from `_require_numpy` converted to `CongineConfigurationError` with an install hint (`dependency_injection.py:376-380`, `ks_drift.py:38-46`) | raises to the caller | none | none |
| 45 | **`evaluate_drift()` with an empty reference window or empty sample** | `ValueError` from `detect` (`ks_drift.py:114-118`) — **not** converted | raw `ValueError` propagates | none | none |
| 46 | **Drift detected** (`statistic > threshold`) | WARNING plus a synthetic `TelemetryEvent(contract_id="__drift__", contract_version="n/a", status="drift", duration_ms=0.0)` carrying the statistic (`:381-402`) | the `DriftResult` is returned normally | WARNING `"Distribution drift detected"` with `statistic`, `p_value` | a `__drift__` event enters the normal telemetry pipeline |

### 9.5 LangChain adapter

| # | Trigger | System response | Caller-visible result | Logged | Telemetry |
|---|---|---|---|---|---|
| 47 | **`CongineCallbackHandler` without `[langchain]`** | explicit `ImportError` with an install hint (`langchain_handler.py:33-37`) | raises at construction | none | none |
| 48 | **No `container=` in multi-tenant mode** | `CongineConfigurationError` (`:42-51`) | raises at construction | none | none |
| 49 | **Any exception during `on_llm_end` validation** | caught (`:105-119`); `KeyboardInterrupt`/`SystemExit` re-raised; everything else — including `CongineValidationError` from `strict` mode and `CongineContractNotFoundError` — swallowed, `last_result = None`, returns `None` | **the LLM callback never propagates a validation failure.** `strict` mode is effectively neutralised on this surface | ERROR `"LangChain validation failed"` with `contract_id`, `error_type` | the publish already happened inside `_finalize` |
| 50 | **Stream exceeds `max_stream_buffer_chars`** (default 500 000) | further tokens are clipped/discarded under the lock (`:75-82`) | the completion is validated **truncated**, silently | none | normal |

### 9.6 The two shapes of "fails closed"

Worth stating plainly, because they are different and both matter:

- **Missing contract ⇒ raise, always** (row 4). Not degraded, not silenced, not affected by
  `fail_mode`. A contract you thought was enforced but is absent will stop your code.
- **Broken validation ⇒ `degraded=True`, `status="fail"`, no breaches** (rows 6-10, 13, 14). Under
  the default `degrade` mode this is a WARNING and the output flows through. Under `strict` it
  raises. The information that *nothing was actually checked* is carried only in the `degraded` and
  `degraded_reason` fields — a caller inspecting only `is_pass()` cannot distinguish "the payload
  violated the contract" from "the validator crashed". Row 14 makes this concrete and permanent for
  a whole class of otherwise-legal schema.
