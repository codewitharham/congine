## 11. Data model

Four value objects, all in `domain/models.py`, all `@dataclass(frozen=True)`. Nothing else in the
system is a data-carrying type — everything else is either a mechanism, a configuration object
(`CongineConfig`, also frozen), or a plain `dict` schema.

### 11.1 `BreachDetail` — `domain/models.py:15-27`

| Field | Type | Default | Notes |
|---|---|---|---|
| `rule` | `str` | required | One of the seven rule identifiers below |
| `field` | `str` | required | Field name, or the sentinel `"<root>"` / `"<schema>"` |
| `message` | `Optional[str]` | `None` | Human-readable; **may be `None`**, which every consumer must handle |

Frozen. Hashable, since all three fields are hashable — which makes it usable in sets and as a dict
key, though nothing currently does.

**The complete set of `rule` values produced anywhere in the system.** There is no enum; these are
string literals, and this is the authoritative list:

| `rule` | Produced by | Line |
|---|---|---|
| `FIELD_PRESENCE` | `RuleEngine.FIELD_PRESENCE` | `validator.py:111` |
| `TYPE_MATCH` | `RuleEngine.TYPE_MATCH`; also the non-dict-root breach | `validator.py:142`, `:389` |
| `ENUM_VALUES` | `RuleEngine.ENUM_VALUES` | `validator.py:164` |
| `RANGE_CHECK` | `RuleEngine.RANGE_CHECK` | `validator.py:197`, `:205` |
| `NULL_GUARD` | `RuleEngine.NULL_GUARD` | `validator.py:221` |
| `REGEX_PATTERN` | `RuleEngine.REGEX_PATTERN` (four distinct messages) | `validator.py:255`, `:264`, `:275`, `:285` |
| `INPUT_BOUNDS` | `ValidateContractUseCase` size guards | `validate_contract_usecase.py:135`, `:153` |
| `SEMANTIC_SCHEMA` | `JsonSchemaSemanticValidator` (invalid schema, over-long pattern, each violation) | `jsonschema_validator.py:112`, `:130`, `:161` |
| `SEMANTIC_TRUNCATED` | breach-cap marker | `jsonschema_validator.py:138` |

Nine values, six of which correspond to the six rules. `INPUT_BOUNDS` is notable because it is
emitted by **L3**, not by the domain — the only breach the use case manufactures itself.

**Where created:** `domain/validator.py` (6 rules + the non-dict root),
`usecases/validate_contract_usecase.py` (2 size guards),
`infrastructure/jsonschema_validator.py` (3 sites).
**Where consumed:** `ValidationResult.breaches`; `_finalize` serialises `rule`/`field`/sanitised
`message` into `TelemetryEvent.breach_details` (`validate_contract_usecase.py:216-223`); the host
reads them off the returned `ValidationResult`.

**Field ordering and `<root>` semantics.** Breaches accumulate in rule order, then in schema-property
iteration order within a rule (`validator.py:397-400`). The order is therefore deterministic for a
given schema but is *not* a severity ranking.

### 11.2 `ValidationResult` — `domain/models.py:30-52`

| Field | Type | Default | Notes |
|---|---|---|---|
| `status` | `str` | required | `"pass"` or `"fail"` — a bare string, not an enum |
| `breaches` | `Tuple[BreachDetail, ...]` | `()` | **a tuple, not a list** — the immutability is structural, not merely by convention |
| `duration_ms` | `float` | `0.0` | Wall-clock, `time.perf_counter`-derived |
| `degraded` | `bool` | `False` | `True` ⇒ this is a timeout/error fallback, not a real evaluation |
| `degraded_reason` | `Optional[str]` | `None` | `"timeout"`, `"resource_error"`, or `"internal_error"` |

One method: `is_pass()` (`:50-52`) — `return self.status == "pass"`.

**`breaches` being a tuple is the load-bearing design choice here.** `frozen=True` alone would not
prevent `result.breaches.append(...)`; the tuple does. Combined with `BreachDetail` being frozen and
hashable, a `ValidationResult` is deeply immutable and safe to hand to any thread, log, or cache
without defensive copying.

**The three degraded reasons, exhaustively:**

| `degraded_reason` | Set at | Trigger |
|---|---|---|
| `"timeout"` | `validate_contract_usecase.py:180` | `TimeoutError` — either genuine overrun **or** load shed (§9.1 rows 6-8) |
| `"resource_error"` | `:77` via `_degraded_on_error` | `MemoryError`, `RecursionError` |
| `"internal_error"` | `:81` via `_degraded_on_error` | any other exception — including the union-type `TypeError` and the non-dict-schema `AttributeError` (§9.1 rows 13-14) |

Every degraded result carries `status="fail"` and `breaches=()`. **A caller that reads only
`is_pass()` cannot distinguish "the contract was violated" from "the validator crashed and nothing
was checked."** That distinction lives exclusively in `degraded`/`degraded_reason`, and it is the
single most important thing for a consumer of this type to know.

**Where created:** `LocalValidator.validate` (`:385`, `:404`), `CompositeValidator.validate`
(`:456`), `ValidateContractUseCase` size guards (`:131`, `:149`) and degradation helpers (`:177`,
`:198`).
**Where consumed:** `_finalize` (telemetry + enforcement), `guard._finish` (`guard.py:63-72`),
`CongineCallbackHandler` (`:102-104`), and the host.

### 11.3 `DriftResult` — `domain/models.py:55-71`

| Field | Type | Default | Notes |
|---|---|---|---|
| `statistic` | `float` | required | KS *D* statistic (max ECDF distance) |
| `p_value` | `float` | required | Asymptotic two-sample KS p-value, clamped to `[0,1]` |
| `drift_detected` | `bool` | required | `statistic > threshold` — **the D statistic, not the p-value** |
| `n_reference` | `int` | required | Reference-window size used |
| `n_sample` | `int` | required | Current-sample size used |

All five required, no defaults. Frozen.

**Note the documentation divergence.** `README.md` describes `drift_threshold` as "KS-test p-value
below which drift is flagged". The code compares the **D statistic** against the threshold
(`ks_drift.py:131`); `p_value` is computed and reported but never used in the decision. The README
is wrong about the semantics of a user-facing knob. Recorded as debt D15 in §16.

**Where created:** `KSDriftEngine.detect` (`ks_drift.py:128-134`) — the only site.
**Where consumed:** `ServiceContainer.evaluate_drift` (`dependency_injection.py:373-403`), which
returns it to the caller and, on detection, flattens four of the five fields into a `__drift__`
`TelemetryEvent`.

### 11.4 `TelemetryEvent` — `domain/models.py:74-102`

| Field | Type | Default | Notes |
|---|---|---|---|
| `contract_id` | `str` | required | `"__drift__"` for synthetic drift events |
| `contract_version` | `str` | required | `"n/a"` for drift events; `"latest"` by guard default |
| `status` | `str` | required | `"pass"`, `"fail"`, or `"drift"` |
| `duration_ms` | `float` | required | Copied verbatim from `ValidationResult.duration_ms` |
| `breach_details` | `list[dict[str, Any]]` | `field(default=None)` → `[]` in `__post_init__` | **a mutable list inside a frozen dataclass** |
| `created_at` | `datetime` | `field(default=None)` → `datetime.now(timezone.utc)` in `__post_init__` | UTC-aware |

Frozen (audit L7) so that, once enqueued for the drain worker, a caller cannot mutate it and race
the worker. Post-init defaulting uses `object.__setattr__` (`:98-102`), the standard escape hatch
for frozen dataclasses.

**Two caveats on the immutability.**

First, `breach_details` is a `list` — the dataclass is frozen (you cannot rebind the attribute) but
the list itself is mutable. The audit-L7 guarantee is therefore *shallow*. In practice
`_finalize` builds a fresh list per event (`validate_contract_usecase.py:216-223`) and no one
retains a reference to it, so nothing exploits the gap; but "frozen" here does not mean "deeply
immutable", unlike `ValidationResult.breaches`, which is a tuple.

Second, `TelemetryEvent` is **not hashable**: `eq=True` (the dataclass default) plus a `list` field
means `__hash__` computation would fail. Frozen dataclasses are normally hashable; this one is not,
in practice, for any instance.

**Stale docstring.** The module docstring at `:5-6` still says "the outbound `TelemetryEvent` is
mutable to allow post-init defaulting". It has been `frozen=True` since audit L7. Prior debt #5,
still present, recorded as debt D5 in §16.

**Where created:** `ValidateContractUseCase._finalize` (`:211-224`) — one per validation, on every
path including degraded ones — and `ServiceContainer.evaluate_drift` (`:388-401`).
**Where consumed:** `IEventBus.publish` → `QueueEventBus._queue` → `_serialize` (`:283-296`),
which emits exactly these six keys and ISO-formats `created_at`. `NoOpEventBus.publish` drops it.

**What it does not carry.** No `project_id`, `agent_id`, `file_paths`, `git_commit_sha`,
`session_id`, `payload_hash`, or tenant identifier. The isolation identifiers travel as HTTP headers
(`queue_event_bus.py:235-239`), not in the event body. Everything `docs_v2` describes as an extended
telemetry event is §15 material.

### 11.5 Cross-cutting properties

| Property | `BreachDetail` | `ValidationResult` | `DriftResult` | `TelemetryEvent` |
|---|---|---|---|---|
| `frozen=True` | yes | yes | yes | yes |
| Deeply immutable | yes | **yes** (tuple of frozen) | yes | **no** (mutable `list`) |
| Hashable | yes | yes | yes | **no** |
| Has defaults | 1 of 3 | 4 of 5 | 0 of 5 | 2 of 6 |
| Has `__post_init__` | no | no | no | **yes** |
| Crosses a thread boundary | yes (pool → caller) | yes (pool → caller) | no | **yes** (caller → drain daemon) |
| Serialised to the wire | as a dict inside `TelemetryEvent` | no | no | yes (`_serialize`) |

**What immutability buys, concretely.** Every one of these objects is created on one thread and read
on another — `ValidationResult` is built on a `congine_validation_N` worker and returned to the
caller's thread; `TelemetryEvent` is built on the caller's thread and read by the
`congine_event_bus` daemon. Freezing them removes an entire class of race without a single lock:
there is no defensive copying anywhere in the codebase, and none is needed. It is also why
`_prime_cache` can update the schema cache in place while a validation is running — the schema dict
handed to `do_validate` is captured by the closure, and although the *dict itself* is not frozen
(schemas are plain dicts from JSON), the cache never mutates a dict in place, only rebinds keys.
