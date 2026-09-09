## 5. Ports and adapters catalogue

Eight seams exist: the seven `ports/` Protocols plus the in-domain `IValidator`. All eight are
`@runtime_checkable` `typing.Protocol`s, so conformance is structural — the test fakes in
`tests/conftest.py` satisfy them without importing or subclassing anything (**CC-7**), which is the
proof that these are genuine duck-typed seams rather than ABCs in disguise.

For each port: the exact method surface (signatures, not paraphrases), every implementation in the
tree, and the obligations a new implementation must satisfy. The obligations column is derived from
what the *callers* actually do, not from the docstrings.

### 5.1 `ISchemaStorage` — `ports/schema_storage.py:14`

```python
def get(self, contract_id: str) -> Optional[Dict[str, Any]]: ...
def put(self, contract_id: str, schema: Dict[str, Any], ttl_seconds: int) -> None: ...
def clear(self) -> None: ...
def exists(self, contract_id: str) -> bool: ...
```

| Implementation | Location | Notes |
|---|---|---|
| `LFUCache` | `infrastructure/lfu_cache.py:24` | production; O(1) LFU + per-entry TTL + daemon sweeper |
| `FakeSchemaStorage` | `tests/conftest.py:59` | dict, no TTL, no LFU |

**Obligations for a new implementation.**

- **Thread safety: required.** `get` is called on the caller's thread on the hot path
  (`validate_contract_usecase.py:162`) while `put` is called from the boot thread and from the
  `congine_background_sync` daemon (`sync_contracts_usecase.py:268`). Concurrent `get`/`put` is the
  normal case, not an edge case.
- **TTL semantics: expired ⇒ absent.** `get` must return `None` for an expired entry; the use case
  translates `None` into `CongineContractNotFoundError` and there is no second chance.
- **Blocking: must not.** `get` sits inside the latency budget before the executor is even entered,
  so it is *outside* the timeout guard. A `get` that blocks blocks the host thread unboundedly.
- **`put` must be individually atomic and must not clear.** `_prime_cache`
  (`sync_contracts_usecase.py:257-271`) updates keys in place precisely so a concurrent hot-path
  `get` always observes a coherent cache. An implementation that internally does clear-then-refill
  would open a window where every validation raises `CongineContractNotFoundError`.
- **Failure: must not raise.** No caller catches from `get`/`put`. `LFUCache` never raises after
  construction.
- **Extra surface the container requires beyond the Protocol:** `size()` (`dependency_injection.py:408`)
  and `stop()` (`:451`). Neither is declared on `ISchemaStorage`. A new implementation that
  satisfies only the declared Protocol will `AttributeError` in `health()` and `close()`. **This is
  a real gap between the declared port and the required port.**

### 5.2 `IContractRepository` — `ports/contract_repository.py:14`

```python
async def fetch_active_contracts(self) -> list[dict[str, Any]]: ...
def load_snapshot(self) -> Optional[list[dict[str, Any]]]: ...
def save_snapshot(self, contracts: list[dict[str, Any]]) -> None: ...
```

| Implementation | Location | Notes |
|---|---|---|
| `HttpContractRepository` | `infrastructure/http_contract_repository.py:61` | HTTP fetch + scoped atomic disk snapshot |
| `FileContractRepository` | `infrastructure/file_contract_repository.py:30` | local directory; snapshot methods are no-ops |
| `FakeContractRepository` | `tests/conftest.py:87` | scripted contracts / errors |

**Obligations for a new implementation.**

- **`fetch_active_contracts` must raise only `CongineSyncError` for expected failure.**
  `_fetch_sync`/`_fetch_async` (`sync_contracts_usecase.py:206-228`) catch exactly that type. Any
  other exception escapes the use case, escapes `bootstrap()`, and reaches the host — turning a
  transport hiccup into a boot crash. `HttpContractRepository` funnels `httpx.HTTPError`, `KeyError`
  and `ValueError` into `CongineSyncError` at `:131-140` for precisely this reason.
- **`fetch_active_contracts` is awaited from two contexts.** `sync_once` drives it with
  `asyncio.run` (`:207`) — so it must not assume a pre-existing loop — while `sync_once_async`
  awaits it directly (`:222`). `FileContractRepository` is declared `async` purely to satisfy this
  (`file_contract_repository.py:53-58`).
- **`load_snapshot` must never raise and must return `None` rather than `[]` when unusable.**
  `_apply` (`:242`) treats any falsy value as "no contracts available; retain current cache".
  `HttpContractRepository.load_snapshot` swallows `FileNotFoundError`, `JSONDecodeError` and `OSError`
  (`:159-160`) and returns `None`.
- **`save_snapshot` may raise only `OSError`.** `_apply` catches exactly `OSError` (`:251`). It is
  best-effort: a failure must not fail the sync.
- **Returned contracts must be `{"id": ..., "schema": ...}` mappings.** `_prime_cache` skips any
  entry missing either key (`:267`) silently.
- **Optional property `snapshot_lock_path: str`.** If present, the container passes it as the
  single-flight boot lock (`dependency_injection.py:312` via `getattr(..., None)`). Absent ⇒
  single-flight silently degrades to a plain `sync_once` (`sync_contracts_usecase.py:138-139`).
  `FileContractRepository` deliberately omits it.

### 5.3 `IEventBus` — `ports/event_bus.py:21`

```python
def publish(self, event: "TelemetryEvent") -> None: ...
```

| Implementation | Location | Notes |
|---|---|---|
| `QueueEventBus` | `infrastructure/queue_event_bus.py:37` | bounded queue + daemon drain + batched POST + breaker gate |
| `NoOpEventBus` | `infrastructure/noop_event_bus.py:23` | discards; no thread, no socket |
| `FakeEventBus` | `tests/conftest.py:42` | captures into a list |

**Obligations for a new implementation.**

- **`publish` must be non-blocking and must never raise.** It is called on the hot path from
  `_finalize` (`validate_contract_usecase.py:225`) with no `try` around it. A raise there propagates
  to the host *after* validation succeeded — the worst possible failure shape. `QueueEventBus` uses
  `put_nowait` and catches `queue.Full` (`:105-116`).
- **Dropping under back-pressure is sanctioned.** Telemetry loss is explicitly preferred to hot-path
  latency.
- **Extra surface the container requires beyond the Protocol:** `queue_depth() -> int`
  (`dependency_injection.py:411`), `stop(drain: bool)` (`:452`, `:60`), and optionally
  `dropped_total() -> int` (`:406`, probed with `getattr` and `callable`, so it is genuinely
  optional). `queue_depth` and `stop` are **not** optional and **not** declared on `IEventBus`.
  `NoOpEventBus` implements all three (`:30-40`) purely for container symmetry, and the conftest
  `FakeEventBus` implements `stop` and `queue_depth` but not `dropped_total` — which is exactly why
  the `callable()` probe exists.

### 5.4 `ILogger` — `ports/logger.py:13`

```python
def info(self, message: str, **kwargs: Any) -> None: ...
def error(self, message: str, **kwargs: Any) -> None: ...
def warning(self, message: str, **kwargs: Any) -> None: ...
def debug(self, message: str, **kwargs: Any) -> None: ...
```

| Implementation | Location | Notes |
|---|---|---|
| `StructuredLogger` | `infrastructure/logger.py:43` | one JSON object per line to stdout; level threshold; blocklist + allowlist redaction |
| `FakeLogger` | `tests/conftest.py:17` | captures `(level, message, kwargs)` |

**Obligations for a new implementation.**

- **Must never raise, on any input.** It is called from the hot path, from daemon threads, and from
  inside `except` blocks. `StructuredLogger` coerces with `json.dumps(..., default=str)` (`:95`) so
  a non-serialisable extra cannot raise.
- **Must accept arbitrary keyword extras**, including keys it has never seen.
- **Must be thread-safe.** Four threads log concurrently. `StructuredLogger` relies on `print(...,
  flush=True)` being atomic enough per line; it holds no lock. Interleaving of *whole lines* is
  possible under extreme concurrency but each JSON object is written by a single `print` call.
- **Should honour the redaction contract.** Callers pass values that may contain tenant data;
  `StructuredLogger` enforces an unconditional blocklist (`:32-40`) plus an optional allowlist
  (`:81-84`). A replacement that logs everything verbatim silently voids guarantee G7 (§14.7).

### 5.5 `ISemanticValidator` — `ports/semantic_validator.py:23`

```python
def validate(self, payload: dict[str, Any], schema: dict[str, Any]) -> "List[BreachDetail]": ...
```

| Implementation | Location | Notes |
|---|---|---|
| `JsonSchemaSemanticValidator` | `infrastructure/jsonschema_validator.py:71` | `jsonschema`-backed; draft resolution fail-closed; breach cap; PII-sanitised messages |

**Obligations for a new implementation.**

- **Must return a flat list, never nested, never `None`.** `CompositeValidator` does
  `breaches.extend(...)` with no guard (`domain/validator.py:453`).
- **Must not raise on a malformed payload or schema.** It runs inside the executor; a raise becomes a
  `degraded_reason="internal_error"` result and the breach detail is lost.
  `JsonSchemaSemanticValidator` converts `SchemaError` into a `BreachDetail` (`:109-116`) rather
  than propagating.
- **Must bound its output.** `_max_breaches` (default 100) caps `iter_errors` drain and appends a
  `SEMANTIC_TRUNCATED` marker (`:135-145`). An unbounded implementation lets a hostile schema
  generate unbounded work inside the timeout budget.
- **Must sanitise messages.** Every message goes through `sanitize_breach_message` before leaving
  (`:114`, `:132`) because these strings reach telemetry.
- **Must be callable concurrently** — it runs on pool worker threads. The `jsonschema` validator
  class is constructed fresh per call (`:121`), so no state is shared.
- **Must tolerate a non-dict payload.** `CompositeValidator` calls it even after `LocalValidator` has
  already rejected a non-dict root (see §16, debt D7).

### 5.6 `IValidationRunner` — `ports/validation_runner.py:20`

```python
@property
def capacity(self) -> int: ...
def run_with_timeout(self, func: Callable[[], Any], timeout_ms: int) -> Any: ...
async def run_with_timeout_async(self, func: Callable[[], Any], timeout_ms: int) -> Any: ...
def health(self) -> Dict[str, Any]: ...
```

| Implementation | Location | Notes |
|---|---|---|
| `BoundedValidationExecutor` | `infrastructure/bounded_executor.py:32` | bounded semaphore, load shed, permit-until-completion, re-entrancy inline |
| `ValidationTimer` | `infrastructure/timer.py:26` | **DEPRECATED** — shape-compatible on `run_with_timeout` only; no `capacity`, no async twin, no `health`, no bounding |
| `ImmediateTimer` | `tests/conftest.py:80` | runs inline; implements `run_with_timeout` only |

**Obligations for a new implementation.** This is the most demanding port in the system, and the
port docstring (`:23-36`) states three of the four explicitly.

- **Capacity bounding.** Saturation must raise `TimeoutError` immediately rather than queueing.
  Unbounded queueing is the exact failure this port exists to prevent (audit H1).
- **Hard deadline.** Overrun must raise `TimeoutError`. Because Python cannot kill a thread, the
  implementation may not actually stop the work — it must only stop *waiting*.
- **The permit must be held until the future genuinely completes, not until the wait is abandoned.**
  `_acquire_and_submit` releases via `future.add_done_callback` (`:174`), never in the timeout
  handler. This is the subtle obligation: an implementation that releases capacity on timeout would
  admit new work while zombies still hold threads, and the bound becomes fiction under exactly the
  load it exists for.
- **Re-entrancy safety.** A call arriving on one of the implementation's own worker threads must run
  inline (`:100-101`, `:137-138`) or the pool deadlocks on nested use.
- **Sync and async must share one capacity pool.** Both entry points call the same
  `_acquire_and_submit` (`:103`, `:140`). An async twin implemented over a raw `run_in_executor`
  would silently bypass the bound — the defect audit H1/H2 closed.
- **The async twin must not block the event loop.** `asyncio.wrap_future` + `asyncio.wait_for`
  (`:142-144`).
- **Exception transparency.** `func`'s own exceptions must propagate unchanged;
  `ValidateContractUseCase` classifies them (`:73-82`).
- **Shutdown must be idempotent and non-blocking by default** (`:206-208`, called with `wait=False`).
- **Extra surface the container requires beyond the Protocol:** `in_flight` and `rejected_total`
  properties (`dependency_injection.py:409-410`) and `shutdown(wait)` (`:453`). None is declared.

### 5.7 `ICircuitBreaker` — `ports/circuit_breaker.py:14`

```python
@property
def state(self) -> str: ...
def allow(self) -> bool: ...
def record_success(self) -> None: ...
def record_failure(self) -> None: ...
```

| Implementation | Location | Notes |
|---|---|---|
| `CircuitBreaker` | `infrastructure/circuit_breaker.py:37` | in-process CLOSED/OPEN/HALF_OPEN with single-flight probe |

**Obligations for a new implementation.**

- **`allow()` must be cheap and non-blocking.** It is consulted before every fetch
  (`sync_contracts_usecase.py:201`) and before every telemetry batch
  (`queue_event_bus.py:221`).
- **`allow()` in HALF_OPEN must admit exactly one probe.** `CircuitBreaker` sets
  `_probe_in_flight` under the lock (`:93-96`) — audit FIX-11. Without it, the moment the cooldown
  elapses every caller floods the recovering plane.
- **Reading `state` may transition OPEN→HALF_OPEN.** `state` calls `_maybe_half_open_locked()`
  (`:73-75`). This is documented as making `state`-then-`allow()` coherent, but it also means
  **observation mutates state**: `ServiceContainer.health()` reads `state` (`:419`), so an operator
  polling health can move the breaker out of OPEN. Harmless (it only makes recovery slightly
  eager) but a genuine surprise, and a new implementation must decide the same question.
- **Thread safety: required.** Consulted from the boot thread, the `congine_background_sync` daemon
  and the `congine_event_bus` daemon simultaneously. All four methods hold `self._lock`.
- **`record_failure` in HALF_OPEN must go straight back to OPEN**, not increment toward the
  threshold (`:111-114`).
- **The breaker is shared, and its two users interact.** One `CircuitBreaker` instance is injected
  into both `SyncContractsUseCase` and `QueueEventBus` (`dependency_injection.py:278`, `:318`).
  Telemetry-ship failures therefore trip the breaker that gates contract fetches, and vice versa.
  This is deliberate — both are the same control plane — but it means a new implementation cannot
  assume a single caller.

### 5.8 `IValidator` — `domain/validator.py:294` (in-domain seam)

```python
def validate(self, payload: dict[str, Any], schema: dict[str, Any]) -> ValidationResult: ...
```

| Implementation | Location | Notes |
|---|---|---|
| `LocalValidator` | `domain/validator.py:304` | the six rules |
| `CompositeValidator` | `domain/validator.py:411` | `LocalValidator` + `ISemanticValidator`, merged |

**Why it is sanctioned to live outside `ports/`.** The rule the codebase follows is: *a Protocol
lives in `ports/` if and only if something outside L2 implements it.* Both `IValidator`
implementations live in the same L2 module; nothing in L3, L4 or L5 implements it. It is a strategy
seam **within** the domain — the choice between "rules only" and "rules plus full JSON Schema" — not
a boundary seam. Putting it in `ports/` would imply an outer layer is expected to supply a
validator, which would invert the one boundary the architecture most needs to protect. By contrast
`ISemanticValidator` *is* implemented outside L2, so it correctly lives in `ports/`. Consistent with
its private status, `IValidator` is re-exported from `domain/__init__.py:27` but deliberately
excluded from the package `__all__` (`congine_core/__init__.py:83-135`).

**Obligations for a new implementation.**

- **Must be pure and side-effect free.** It runs on a pool worker; no I/O, no shared mutable state.
- **Must never raise on well-formed input**, and should tolerate malformed input. Any raise becomes
  `degraded_reason="internal_error"` and the specific breach information is lost. Today
  `LocalValidator` violates this for two malformed-schema shapes — see §13.6.
- **Must return a `ValidationResult` whose `status` is `"pass"` only when `breaches` is empty.**
  `is_pass()` compares the status string; a result claiming `"pass"` with breaches would be enforced
  as a pass.
- **Should populate `duration_ms`.** It is copied into the telemetry event verbatim
  (`validate_contract_usecase.py:215`).

### 5.9 Summary: the declared port surface vs. the required port surface

The gap between what the Protocols declare and what `ServiceContainer` actually calls is worth
stating once, plainly, because it is the trap a would-be extender falls into.

| Port | Declared methods | Additionally required by the container | Consequence of implementing only the Protocol |
|---|---|---|---|
| `ISchemaStorage` | `get`, `put`, `clear`, `exists` | `size()`, `stop()` | `health()` and `close()` raise `AttributeError` |
| `IEventBus` | `publish` | `queue_depth()`, `stop(drain)`; `dropped_total()` optional | `health()` and `close()` raise `AttributeError` |
| `IValidationRunner` | `capacity`, `run_with_timeout`, `run_with_timeout_async`, `health` | `in_flight`, `rejected_total`, `shutdown(wait)` | `health()` and `close()` raise `AttributeError` |
| `IContractRepository` | `fetch_active_contracts`, `load_snapshot`, `save_snapshot` | `snapshot_lock_path` (genuinely optional — `getattr` guarded) | single-flight degrades silently, nothing raises |
| `ILogger`, `ISemanticValidator`, `ICircuitBreaker`, `IValidator` | as declared | none | — |

Three of the eight seams have an undeclared lifecycle/observability surface. `NoOpEventBus`
documents this in its own docstring (`noop_event_bus.py:10-12`) — it implements `queue_depth`,
`dropped_total` and `stop` for no reason other than container symmetry. Recorded as debt D14 in §16.
