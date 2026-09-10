## 10. Concurrency and state

### 10.1 Every thread

| Thread | Name prefix | Count | Daemon | Created at | Started by | Stopped by | Loop body |
|---|---|---|---|---|---|---|---|
| Validation workers | `congine_validation_` | `validation_max_workers` (10) | **False** | `bounded_executor.py:54-58` | `ThreadPoolExecutor`, lazily on first `submit` | `shutdown(wait=False)` (`:206-208`) — prevents new work, does not abandon running futures | runs one submitted callable |
| Cache TTL sweeper | `congine_cache_sweeper` | 1 per container | True | `lfu_cache.py:68-73` | `LFUCache.__init__` iff `start_sweeper` | `stop()` sets `_stop_event`, joins with `sweep_interval + 1.0` (`:240-245`) | `while not _stop_event.wait(sweep_interval): sweep_expired()` |
| Telemetry drain | `congine_event_bus` | 1 per container | True | `queue_event_bus.py:88-93` | `QueueEventBus.__init__` iff `start_worker` | `stop(drain)` sets `_stop_event`, flushes, joins with 2.0 s (`:127-141`) | `while not _stop_event.is_set(): ship(collect_batch())` |
| Periodic sync | `congine_background_sync` | 1 per container | True | `background_sync.py:60-65` | `BackgroundSyncWorker.start()` | `stop()` sets `_stop_event`, joins with `interval + 1.0` (`:72-77`) | `while not _stop_event.wait(interval): _safe_sync()` |
| *(deprecated)* | `congine_timer` | — | False | `timer.py:45-48` | `ValidationTimer.__init__` | never wired | — |

Verified at runtime by `threading.enumerate()`.

Three consequences of this table:

**The only non-daemon threads are the validation workers.** Every Congine-*owned* thread is a daemon
and cannot block interpreter exit. But a validation callable that hangs holds a non-daemon
`ThreadPoolExecutor` thread, which Python joins at exit. Because a timed-out callable cannot be
killed, a pathological validation can delay process exit even though the SDK's own design is
exit-safe. The `re2` linear-time guarantee and the length caps (§13.5) are what make this
theoretical rather than practical.

**Each container owns its own threads.** In multi-tenant mode with 128 registered tenants and
telemetry on, the process holds up to 128 sweepers + 128 drain threads + up to 128 sync workers +
up to 128×10 pool threads. There is no global pool and no cross-container sharing of anything.

**Every daemon loop uses `threading.Event.wait` rather than `time.sleep`,** so `stop()` wakes it
promptly instead of waiting out a full interval. The one exception is the drain loop, which blocks
on `queue.get(timeout=1.0)` — that 1 s poll is its responsiveness bound.

### 10.2 Every lock

| # | Lock | Type | Owner | Protects | Held across a blocking call? |
|---|---|---|---|---|---|
| 1 | `LFUCache._lock` | `RLock` | per cache | `_key_to_value`, `_key_to_freq`, `_freq_to_keys`, `_min_freq` | no — pure in-memory dict work |
| 2 | `BoundedValidationExecutor._lock` | `Lock` | per executor | `_in_flight`, `_rejected_total` | **no** — `submit` (`:169`) is deliberately outside the lock |
| 3 | `CircuitBreaker._lock` | `Lock` | per breaker | `_state`, `_consecutive_failures`, `_opened_at`, `_probe_in_flight` | no |
| 4 | `QueueEventBus._dropped_lock` | `Lock` | per bus | `_dropped_total` | no |
| 5 | `ServiceContainer._default_lock` | `Lock` (ClassVar) | class | `_default_instance` | **yes — `cls(config)` at `:99`** |
| 6 | `ServiceContainer._tenant_lock` | `Lock` (ClassVar) | class | `_tenant_registry`, `_evicted_total` | **yes — `cls(config)` at `:165`** |
| 7 | `ServiceContainer._close_lock` | `Lock` | per container | `_closed`, `_finalizer` | no |
| 8 | `CongineCallbackHandler._lock` | `Lock` | per handler | `_buffers`, `_buffer_lengths` | no — released before validating (`:87-89`, then `:97`) |

Plus two non-lock synchronisation primitives with lock-like roles: the `threading.BoundedSemaphore`
in the executor (§10.3) and the `queue.Queue` in the bus (thread-safe by construction).

**Locks held across a potentially blocking call — the honest answer.**

Rows 5 and 6 are the only ones, and both are the same shape: the class-level lock is held across
full `ServiceContainer` construction. Construction does no network and no disk I/O, but it **does
start up to two daemon threads** (`LFUCache.__init__`, `QueueEventBus.__init__`) and register
`atexit` hooks. `threading.Thread.start()` blocks until the new thread has begun, which is fast but
not free.

The practical consequence: **`for_tenant()` calls for distinct new tenants fully serialise behind
one another.** Under a cold burst of N new tenants, tenant N waits for N−1 container constructions.
This is not a bug and it is far better than the pre-P0-1 behaviour (which held the same lock across
a `close()` that could block on a telemetry drain), but it is the remaining contention point and it
is worth knowing before the registry is put under load.

Rows 5 and 6 are also where the P0-1 fix is most visible: `_arm_deferred_teardown` (`:422-437`) is
called under the lock precisely *because* it only registers a `weakref.finalize` and does no
teardown, and both the eviction warning (`:169-175`) and every `close()` in `reset_default`
(`:192-195`) are deliberately moved outside the locks.

### 10.3 Semaphore and permit accounting

`BoundedValidationExecutor` uses a `threading.BoundedSemaphore(max_workers + max_pending)` — default
20 (`:59-60`). `BoundedSemaphore` rather than `Semaphore` is deliberate: an over-release is a
programming error and raises `ValueError` immediately rather than silently inflating capacity.

Permit lifecycle:

```
acquire   : _acquire_and_submit  :161   sem.acquire(blocking=False)
              failure -> _rejected_total += 1, raise TimeoutError   (LOAD SHED)
              success -> _in_flight += 1                            :166-167
submit    :                       :169   thread_pool.submit(func)
              RuntimeError -> _release() and raise TimeoutError     :170-172
release   :                       :174   future.add_done_callback(lambda _f: self._release())
_release  :                       :177-180  _in_flight -= 1 ; sem.release()
```

**How timed-out work is handled — the load-bearing detail.** When
`future.result(timeout=…)` raises, the caller abandons the *wait*. It does **not** release the
permit. The permit is released only by the done-callback, i.e. when the underlying callable
genuinely finishes. A "zombie" therefore continues to occupy capacity for as long as it runs.

This is the correct behaviour and it is counter-intuitive enough to be worth stating twice: under
sustained timeouts, capacity **drains** and new work is shed rather than piled on top of threads
that are already stuck. An implementation that released on timeout would report free capacity that
does not exist and would degrade into exactly the unbounded-queue failure this class was written to
prevent (audit H1). Both comments at `:107-108` and `:146-148` call this out, and
`tests/adversarial/test_bounded_executor.py:36` (`test_saturation_sheds_load`) and `:75`
(`test_in_flight_returns_to_zero`) pin it.

**Sync/async capacity sharing.** Both `run_with_timeout` (`:103`) and `run_with_timeout_async`
(`:140`) call the *same* `_acquire_and_submit`. There is one semaphore, one pool, one bound. An
async caller cannot obtain capacity a sync caller could not, and vice versa. This is the substance
of the H1/H2 closure and is asserted by `test_async_concurrent_saturation_sheds_load`.

**The re-entrancy guard.** `self._local = threading.local()` (`:53`); the pool's `initializer`
(`_init_worker`, `:75-76`) sets `is_worker = True` on each worker thread. `_on_worker_thread()`
(`:78-79`) reads it with a `getattr` default of `False`, so a non-worker thread is never mistaken
for one. Both entry points check it first (`:100`, `:137`) and run inline when true — no permit is
taken and no submission occurs, so a nested same-pool call cannot deadlock.

Two properties of this design that are easy to miss. Because `_local` is an *instance* attribute,
the flag is per-executor: a worker of executor A calling into executor B is correctly treated as a
non-worker by B and does take a B permit. And an inline re-entrant run is **not time-boxed** — it
runs to completion regardless of `timeout_ms`; the comment at `:98-99` acknowledges this
("best-effort timeout; CPU work is bounded upstream"). Tested by
`test_reentrant_call_runs_inline_no_deadlock` (`:62`) and `test_async_reentrant_call_runs_inline`
(`:146`).

### 10.4 Every piece of shared mutable state

| # | State | Where | Scope | Guarded by | Mutated from |
|---|---|---|---|---|---|
| 1 | `_key_to_value`, `_key_to_freq`, `_freq_to_keys`, `_min_freq` | `lfu_cache.py:55-60` | per container | `_lock` (RLock) | hot path (`get`), boot + sync daemon (`put`), sweeper daemon (`sweep_expired`) |
| 2 | `_in_flight`, `_rejected_total` | `bounded_executor.py:62-63` | per container | `_lock` | caller threads (acquire), pool threads (done-callback release) |
| 3 | `_local.is_worker` | `bounded_executor.py:53` | per thread | thread-local — no lock needed | pool `initializer` only |
| 4 | Semaphore permits | `bounded_executor.py:60` | per container | the semaphore itself | caller threads, pool threads |
| 5 | `_state`, `_consecutive_failures`, `_opened_at`, `_probe_in_flight` | `circuit_breaker.py:60-63` | per container | `_lock` | boot thread, sync daemon, bus daemon — **three writers** |
| 6 | `_queue` | `queue_event_bus.py:68` | per container | `queue.Queue` internals | hot path (`put_nowait`), bus daemon (`get`), `stop()` caller (`_flush_remaining`) |
| 7 | `_dropped_total` | `queue_event_bus.py:84` | per container | `_dropped_lock` | hot path, bus daemon |
| 8 | `_client` | `queue_event_bus.py:76` | per container | **nothing** | bus daemon (`_get_client`), `stop()` caller (`:139-141`) — **unguarded, see §10.6** |
| 9 | `_stop_event` (×3) | cache, bus, sync worker | per container | `threading.Event` | any thread |
| 10 | `_thread`, `_daemon`, `_sweeper` handles | the three workers | per container | **nothing** | `start()`/`stop()` callers |
| 11 | `_default_instance` | `dependency_injection.py:68` | **process-wide class state** | `_default_lock` | any thread |
| 12 | `_tenant_registry` | `dependency_injection.py:72` | **process-wide class state** | `_tenant_lock` | any thread |
| 13 | `_evicted_total` | `dependency_injection.py:79` | **process-wide class state** | `_tenant_lock` (incremented at `:161`) | any thread |
| 14 | `_MAX_TENANTS` | `dependency_injection.py:76` | **process-wide class state** | none — read-only in production; monkeypatched by tests | tests only |
| 15 | `_closed`, `_finalizer` | `dependency_injection.py:206-208` | per container | `_close_lock` | any thread, incl. a GC finalizer |
| 16 | `_warned_unenforced` | `sync_contracts_usecase.py:86` | per use case | **nothing** | boot thread and sync daemon — **unguarded, see §10.6** |
| 17 | `_compiled_pattern` LRU cache | `domain/validator.py:41-44` | **process-wide module state** | `functools.lru_cache` internals (thread-safe) | every pool thread |
| 18 | `_buffers`, `_buffer_lengths` | `langchain_handler.py:67-68` | per handler | `_lock` | LangChain callback threads |
| 19 | `_results`, `last_result` | `langchain_handler.py:69-70` | per handler | **nothing** — written at `:102-103` *outside* the lock | LangChain callback threads |
| 20 | `KSDriftEngine._reference` deque | `ks_drift.py:66` | per container | **nothing** | whichever host thread calls `record_drift_sample` |

Everything in this table is **process-local**. There is no distributed state, no shared cache, no
external coordination beyond the two advisory `portalocker` files. If the process dies, queued
telemetry, cache contents, breaker state and drift samples die with it.

### 10.5 Immutable / effectively-immutable state

Deliberately not in the table above, because immutability is what makes them safe to share freely
across every thread:

- `CongineConfig` — `frozen=True` (`config.py:60`), constructed once, threaded read-only everywhere.
- All four domain value objects — `frozen=True` (§11).
- `LocalValidator.rules` — assigned once in `__init__` and never mutated.
- `security_limits` constants and the `schema_vocabulary` frozensets.
- `_JSON_TYPE_MAP` (`domain/validator.py:49-56`) — module-level, read-only.

### 10.6 Concurrency findings

Three places where the analysis above turns up something a reader should not have to re-derive.

**F1 — `QueueEventBus._client` is unguarded across a stop race** (state row 8). `stop()` closes the
client and sets it to `None` (`:139-141`) after a 2 s join timeout that may expire while the daemon
is mid-`_ship`. Two outcomes: the daemon uses a closed client and `httpx` raises `RuntimeError`,
which `_ship` does not catch (it catches only `httpx.HTTPError`, `:256`), so the exception escapes
`_drain_loop` and kills the daemon thread with a stderr traceback; or the daemon calls
`_get_client()` after the null-out and constructs a fresh client that nothing will ever close. Both
occur only during teardown of a bus with a slow in-flight POST. Recorded as debt D4 in §16.

**F2 — `SyncContractsUseCase._warned_unenforced` is unguarded** (state row 16). It is a plain `set`
mutated at `:293-294` from both the boot thread and the `congine_background_sync` daemon. CPython's
GIL makes `set.add` and `set.clear` atomic, so this cannot corrupt, but a benign race can emit a
duplicate warning or clear the set concurrently with an add. It is a diagnostic-only structure and
the consequence is at worst a repeated log line. Recorded as debt D12.

**F3 — `CongineCallbackHandler._results` / `last_result` are written outside the lock** (state row
19). `on_llm_end` takes `_lock` only to pop the buffers (`:87-89`), then writes `_results[run_id]`
and `last_result` unguarded at `:102-103`. Concurrent runs can interleave such that `last_result`
reflects a different run than the caller expects. `result_for(run_id)` (`:129-131`) is the correct,
race-free accessor; `last_result` is inherently ambiguous under concurrency. Recorded as debt D13.

### 10.7 What is *not* a concurrency problem

Stated explicitly because each looks like one on a first read:

- **`LFUCache` uses an `RLock`, not a `Lock`.** Not because of re-entrant public calls but because
  `get`/`exists` call `_evict_key` while already holding it (`:91`, `:151`). Correct as written.
- **`_evict_key` deliberately does not recompute `_min_freq`** (`:196-210`). That would be an O(n)
  scan on every TTL expiry. Staleness is reconciled off the hot path in `_evict_lfu` (`:184-189`),
  and `put` resets `_min_freq` to 1 anyway (`:129`). This is audit M4 and it is a considered
  trade, not an oversight.
- **`ValidateContractUseCase` has no mutable state at all** — nine constructor-assigned attributes,
  never written after `__init__`. One instance safely serves every thread.
- **The `_compiled_pattern` `lru_cache`** (state row 17) is process-wide and shared across
  containers and tenants. It is keyed on the pattern string and holds only compiled regexes — no
  tenant data — so cross-tenant sharing is safe, and `functools.lru_cache` is thread-safe.
- **`StructuredLogger` holds no lock.** It relies on a single `print(..., flush=True)` per record.
  Whole lines can interleave under extreme concurrency but individual JSON objects are not torn.
