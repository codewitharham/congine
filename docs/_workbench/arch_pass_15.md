## 16. Debt register

Two parts: the nine debts from `docs/context/01_SYSTEM_STATE.md` re-verified against current code,
then sixteen items this pass found that no prior document records. Severity is this document's
judgement — the one place in this document where judgement is the point.

### 16.1 Prior debts, re-verified

| Prior # | Debt | Status | Evidence |
|---|---|---|---|
| 1 | LangChain example: offline fallback `action="manual_review"` ∉ contract enum | **VERIFIED PRESENT** | `examples/LangChain/agent.py:90` sets `"action": "manual_review"`; `:75` documents the same wrong value in the Pydantic field description; `examples/LangChain/contracts/return_processing.json:7` enum is `["approve_return","reject_return","escalate"]` |
| 2 | Multi-tenant LRU eviction `close()`s a possibly-live container, under the lock | **VERIFIED FIXED** | `dependency_injection.py:157-163` — registry entry removed, `weakref.finalize` armed, no teardown under `_tenant_lock`; 7 tests in `tests/unit/test_container_tenant_lru.py`. Replaced by a smaller debt, D3 below |
| 3 | `requires-python = ">=3.11"` contradicts the stated 3.10 floor | **VERIFIED PRESENT** | `pyproject.toml:6` `>=3.11`; `:18` still classifies 3.10; `:69` `target-version = "py310"`; `.claude/CLAUDE.md` still says "ruff `target-version = py310` is pinned to the supported floor". The comment at `:66-68` now claims 3.10–3.13 is "the declared `requires-python` floor", which contradicts `:6` in the same file |
| 4 | Size guards count characters, undercounting multibyte UTF-8 | **WRONG — direction inverted** | `json.dumps` defaults to `ensure_ascii=True`, so its output is pure ASCII and `len(str)` equals its own byte length exactly. Measured: a payload whose compact UTF-8 form is 29 bytes measures 69. The guard **over**-counts and is conservative. Restated as D6 |
| 5 | Stale `TelemetryEvent` "mutable" docstring | **VERIFIED PRESENT** | `domain/models.py:5` vs `:74` `@dataclass(frozen=True)` |
| 6 | `pii_sanitize` uses stdlib `re`, not `re2` | **VERIFIED PRESENT** | `pii_sanitize.py:9,14`. Restated as D7 |
| 7 | `CompositeValidator` runs the semantic validator on non-dict payloads | **VERIFIED PRESENT** | `domain/validator.py:451-453` — no short-circuit between the rule call and the semantic call |
| 8 | Dual schema vocabulary is implicit; unenforced keywords pass silently | **PARTIALLY ADDRESSED** | Enforcement unchanged (`validator.py:333-367`). Detection added: `domain/schema_vocabulary.py` + `sync_contracts_usecase.py:273-306` emit a load-time WARNING. Gaps remain — the scan runs only on the cache-prime path, so a direct `schema_storage.put()` is never scanned. Restated as D17 |
| 9 | `ValidationTimer` retained as deprecated dead code | **VERIFIED PRESENT** | `infrastructure/timer.py` (81 lines) still present, still tested by `tests/unit/test_timer.py` (4 tests), excluded from `infrastructure/__init__.py:22-25` and never constructed anywhere |

### 16.2 New findings

Ordered by severity, then by blast radius.

---

**D1 — `region` is a dead configurable with compliance connotations. Severity: HIGH.**

`CongineConfig.region` is declared (`config.py:73`), parsed and validated by `from_env()`
(`:154-159`, raising `CongineConfigurationError` on a bad value), assigned (`:181`), and documented
in `README.md` as "`us` | `eu` | `apac`". It is read by **nothing**: `grep -rn "region"
src/congine_core/` returns four hits, all inside `config.py` itself.

The `Region` enum's own comments name "Virginia", "Frankfurt (GDPR)" and "Singapore"
(`config.py:40-42`). A user setting `CONGINE_REGION=eu` to satisfy a data-residency requirement gets
no routing change, no endpoint change, no header, and no warning — the control plane is whatever
`base_url` says. Because the field *validates*, it feels alive.

*Fix:* either wire it (derive a default `base_url` per region, or send it as a header) or remove it
and the README row. A third option — raising if `region` is set inconsistently with `base_url` — is
worse than either.

---

**D2 — The README config table documents 27 of 46 fields. Severity: HIGH.**

`.claude/CLAUDE.md` designates the README table "the canonical, user-facing config doc" and the
mandatory fourth touch of any config change. Nineteen fully-wired fields are missing (§12.5),
including the three most operationally consequential: `local_contracts_dir` (the entire
standalone/air-gapped topology), `telemetry_enabled` (removes a thread and a socket), and
`jsonschema_draft` (fail-closed — a typo prevents process start). The table's preamble asserts that
every field is env-settable, which is true and makes the omissions read as intentional.

*Fix:* complete the table, or generate it from `dataclasses.fields(CongineConfig)` in a test so it
cannot drift again.

---

**D3 — An evicted-but-referenced tenant container leaks its threads indefinitely. Severity: MEDIUM.**

P0-1 correctly stopped eviction from breaking live containers, but the replacement leaks them. After
eviction the container is off-registry and invisible to any `health()` aggregation, yet a caller
holding a reference keeps its `congine_cache_sweeper`, `congine_event_bus` and validation pool alive
for as long as the reference lives (`dependency_injection.py:157-163`, `:422-437`). With tenant
churn a process can hold well over `_MAX_TENANTS` live containers and thread sets. `evicted_total()`
(`:197-200`) counts evictions but nothing counts *live-but-evicted* containers.

Related and narrower: `_arm_deferred_teardown` is called **only** from the eviction path (`:163`).
A container that is simply dropped — never registered, never evicted, never closed — arms no
finalizer at all and leaks the same threads permanently (§7.8 row 6).

*Fix:* arm the finalizer in `__init__` rather than at eviction, so every container tears down when
unreferenced regardless of how it was created.

---

**D4 — `QueueEventBus._client` is unguarded across the stop race. Severity: MEDIUM.**

`stop()` closes the client and sets it to `None` (`:139-141`) after a 2 s join that can expire while
the daemon is mid-`_ship`. Two outcomes: the daemon uses a closed client, `httpx` raises
`RuntimeError`, `_ship` does not catch it (it catches only `httpx.HTTPError`, `:256`), the exception
escapes `_drain_loop` and the daemon dies with a stderr traceback outside the structured logger; or
the daemon calls `_get_client()` after the null-out and builds a fresh client nothing will close.

*Fix:* guard `_client` with a lock, or have `stop()` only close it after a successful join, or widen
`_ship`'s except clause to `Exception`.

---

**D5 — Stale `TelemetryEvent` docstring, and a shallow-immutability caveat. Severity: LOW.**

Prior debt #5, still present (`domain/models.py:5` vs `:74`). Worth extending: the class is frozen
but `breach_details` is a `list`, so the audit-L7 guarantee ("a caller cannot mutate it and race the
worker") is **shallow** — the attribute cannot be rebound but the list can be mutated in place. And
because a `list` field is unhashable, this frozen dataclass is not hashable, unlike the other three.

*Fix:* make it a tuple (matching `ValidationResult.breaches`) and correct the docstring.

---

**D6 — Size guards measure JSON-encoded characters, not payload bytes. Severity: LOW.**

`len(json.dumps(value, default=str))` at `validate_contract_usecase.py:127` and `:145`. Because
`ensure_ascii=True`, the count equals the byte length of the *escaped* representation, which can be
several times the compact UTF-8 size of the same data. The guard is conservative — it never
under-rejects — but the field name `max_payload_bytes` promises something it does not measure, and a
user sizing the budget against real payload sizes will be surprised by early rejections on
non-ASCII data.

Separately, `json.dumps` failing (`TypeError`/`ValueError`) sets `size = 0` (`:128-129`), so an
unserialisable payload **bypasses the bound entirely**.

*Fix:* measure `len(json.dumps(v, ensure_ascii=False).encode("utf-8"))`, and treat a serialisation
failure as oversize rather than zero.

---

**D7 — `pii_sanitize` is the one regex outside the linear-time rule. Severity: LOW.**

`pii_sanitize.py:9,14` uses stdlib `re` with `(['\"])(.*?)\1|(\b\d{4,}\b)`. No nested quantifier and
bounded inputs, so the practical ReDoS risk is negligible — but it sits on the path handling the
least-trusted strings in the system (validator messages containing instance data), and `google-re2`
is already a required core dependency, so the exception buys nothing.

*Fix:* switch to `re2`.

---

**D8 — Default-container guards re-read and re-validate the environment on every call. Severity: MEDIUM.**

`ServiceContainer.get_default()` calls `CongineConfig.from_env()` **before** the singleton cache
check (`dependency_injection.py:89`), so every call parses ~46 environment variables, constructs a
frozen dataclass, and runs `validate()`. `@congine_guard` with no explicit `container=` resolves
through `get_default()` on **every guarded invocation** (`guard.py:57-58`, called at `:77` and
`:88`). That is a full environment re-read and re-validation on the hot path — and it can raise
`CongineConfigurationError` mid-request even though a perfectly good singleton exists.

*Fix:* check `_default_instance` first and only call `from_env()` when constructing. The multi-tenant
guard can be re-derived from the cached container's `config.deployment_mode`.

---

**D9 — `CONGINE_LOCAL_CONTRACTS_DIR=""` silently selects a broken standalone mode. Severity: MEDIUM.**

The branch is `config.local_contracts_dir is not None` (`dependency_injection.py:243`), so an empty
string — the common shell/orchestrator idiom for "unset this" — selects standalone mode. Verified:
`_standalone=True`, `FileContractRepository`, `sync_worker=None`. `fetch_active_contracts` then
fails `os.path.isdir("")`, logs "Contracts directory missing", and returns `[]`. The cache is never
primed, every validation raises `CongineContractNotFoundError`, and there is neither a network
fallback nor a sync worker to recover.

*Fix:* treat empty as unset (`if config.local_contracts_dir:`), or reject an empty value in
`from_env()`.

---

**D10 — A mid-constructor failure leaks two threads and two atexit hooks. Severity: MEDIUM.**

`LFUCache.__init__` (`lfu_cache.py:67-74`) and `QueueEventBus.__init__` (`queue_event_bus.py:87-94`)
each start a daemon thread and register an `atexit` hook *inside the constructor*, at
`dependency_injection.py:229` and `:267`. There is no `try/except` covering the remaining steps. The
realistic trigger is `:281`: an invalid `CONGINE_JSONSCHEMA_DRAFT` makes
`JsonSchemaSemanticValidator` raise `CongineConfigurationError` **after** both threads are running.
No container object is returned, so nothing can ever `close()` them.

*Fix:* wrap the constructor body so a partial graph is torn down on failure, or validate the draft
string in `CongineConfig.validate()` before construction begins.

---

**D11 — `atexit` hooks are registered and never unregistered. Severity: LOW.**

Five registration sites: `bounded_executor.py:65`, `lfu_cache.py:74`, `queue_event_bus.py:94`,
`background_sync.py:66` (inside `start()`, so it re-registers on every restart), and
`timer.py:49`. None calls `atexit.unregister`, and `close()` does not either. A long-lived process
that creates and closes many containers accumulates hooks bound to dead objects, each running at
interpreter exit. Bounded in practice by `_MAX_TENANTS`; unbounded in principle for a host that
constructs containers directly.

*Fix:* `atexit.unregister` in each component's `stop()`/`shutdown()`.

---

**D12 — `SyncContractsUseCase._warned_unenforced` is mutated from two threads without a lock. Severity: LOW.**

`sync_contracts_usecase.py:86`, mutated at `:293-294` from the boot thread and the
`congine_background_sync` daemon. The GIL makes `set.add`/`set.clear` atomic so nothing corrupts;
the worst outcome is a duplicated warning or a clear racing an add. Documented because §10.4 lists
every piece of shared mutable state and this is the one with no guard and no note.

*Fix:* a `threading.Lock`, or accept it and say so in a comment.

---

**D13 — `CongineCallbackHandler._results` / `last_result` are written outside the lock. Severity: LOW.**

`langchain_handler.py:102-103` writes both after releasing `_lock` at `:89`. Concurrent runs can
interleave so that `last_result` reflects a different run than the caller expects. `result_for(run_id)`
(`:129-131`) is the race-free accessor; `last_result` is inherently ambiguous under concurrency and
is not documented as such.

*Fix:* write under the lock, and document `last_result` as single-run-only.

---

**D14 — Three ports declare less than the container requires. Severity: MEDIUM.**

`ISchemaStorage` additionally needs `size()` and `stop()`; `IEventBus` additionally needs
`queue_depth()` and `stop(drain)`; `IValidationRunner` additionally needs `in_flight`,
`rejected_total` and `shutdown(wait)` (§5.9). None is declared. A conforming implementation of the
*declared* Protocol will `AttributeError` in `health()` or `close()`. `NoOpEventBus` implements the
undeclared surface purely for container symmetry and says so (`noop_event_bus.py:10-12`), which is
the clearest evidence that the port declarations are incomplete rather than the container being
over-eager. This matters directly for §15.2 (`SqliteEventBus`).

*Fix:* declare the lifecycle/observability methods on the ports, or split them into an
`ILifecycle`/`IObservable` protocol the container composes.

---

**D15 — `drift_threshold` is documented as a p-value; the code uses the D statistic. Severity: LOW.**

`README.md` says "KS-test p-value below which drift is flagged". `ks_drift.py:131` computes
`drift_detected=statistic > self.threshold` — the D statistic. `p_value` is calculated and reported
but never used in the decision. The two have opposite directionality, so a user tuning by the
documentation tunes backwards.

*Fix:* correct the README, or add a `drift_p_value_threshold` if p-value semantics were intended.

---

**D16 — Dot-notation is supported by exactly one rule, and nothing warns. Severity: MEDIUM.**

`FIELD_PRESENCE` walks dotted paths via `_path_present` (`validator.py:59-72`); the other five rules
use flat `field_name in payload` lookups (`:129`, `:158`, `:182`, `:219`, `:239`). A contract with
`{"required": ["user.email"], "properties": {"user.email": {"type": "string", "pattern": "..."}}}`
enforces presence only — type and pattern are evaluated against a top-level key literally named
`"user.email"`, which does not exist, so both skip silently.

The P0-2 warning does **not** catch this: `find_unenforced_keywords` inspects keyword *names*, and
`user.email.type` / `user.email.pattern` are both in the enforced set.

*Fix:* either support dotted paths in all six rules, or have `find_unenforced_keywords` flag any
property key containing a `.` as unenforced-beyond-presence.

---

**D17 — The P0-2 warning covers only the cache-prime path. Severity: MEDIUM.**

`_warn_unenforced_keywords` is called from `_prime_cache` (`sync_contracts_usecase.py:270`) and
nowhere else. A schema written directly via `schema_storage.put(...)` — which tests, embedders, and
any future non-repository loader (an MCP server, a CLI, a direct-injection API) will do — is never
scanned. The silent-keyword trap remains fully open on those paths, and every one of them is a path
the roadmap in `docs_v2/05_IMPLEMENTATION_ROADMAP.md` intends to add.

*Fix:* move the scan behind the `ISchemaStorage.put` boundary, or expose it as a public helper every
loader is required to call.

---

**D18 — A union `type` declaration degrades every validation, permanently. Severity: HIGH.**

`{"type": ["string","null"]}` is legal JSON Schema and the idiomatic nullable-field spelling.
`_type_matches` does `_JSON_TYPE_MAP.get(json_type)` with an unhashable `list`, raising `TypeError`
(`validator.py:77`). Verified end-to-end: `status="fail"`, `degraded=True`,
`degraded_reason="internal_error"`, `breaches=()`. **Every** validation against that contract
degrades, for as long as the schema is cached. Under `fail_mode=silent` there is not even a
use-case-level log.

The same shape occurs for a non-dict schema (`AttributeError` from `schema.get`), also verified.

P0-2 mitigates discovery — `find_unenforced_keywords` reports `field.type` for a non-string type
(`schema_vocabulary.py:99-101`) — but only on the prime path (D17), and only as a warning.

*Fix:* make `_type_matches` handle a list of type names (`any(...)`), which is both the correct JSON
Schema semantics and removes the crash. Guard `_extract_params` against a non-mapping schema.

---

**D19 — Load shed and genuine timeout are indistinguishable to the caller. Severity: LOW.**

Both produce `degraded_reason="timeout"` and both log the same WARNING `"Validation timeout"`
(`validate_contract_usecase.py:172-176`), yet they mean different things: "your validation was too
slow" versus "the system is saturated and did not run your validation at all". The only signal is
the process-wide `health()["validation_rejected_total"]` counter, which cannot be attributed to a
specific call.

*Fix:* a distinct `degraded_reason="load_shed"`, propagated from
`bounded_executor.py:164`'s already-distinct exception message.

---

**D20 — Silent-`False` boolean env parsing. Severity: LOW.**

`_env_bool` (`config.py:320-328`) returns `False` for any value outside the two recognised sets. So
`CONGINE_TELEMETRY_ENABLED=TRUE!`, `=yes please`, or `=1 ` (with a stray character) silently disable
telemetry. Numeric fields fail loudly (`_env_int`/`_env_float` raise naming the variable); booleans
fail silently in one direction. For `require_https` the direction is safe; for `telemetry_enabled`
and `start_background_services` it silently disables a subsystem.

*Fix:* raise `CongineConfigurationError` on an unrecognised boolean, matching the numeric helpers.

---

**D21 — `max_schema_bytes` is one knob with two meanings. Severity: LOW.**

It bounds the cached-schema size check in L3 (`validate_contract_usecase.py:148`) **and** is passed
as `max_file_bytes` to `FileContractRepository` (`dependency_injection.py:250`, `:257`), where it
caps per-file reads. Tuning one raises or lowers the other. The README documents neither.

*Fix:* a distinct `max_contract_file_bytes`, or document the coupling.

---

**D22 — `contract_source` accepts any value and silently means HTTP. Severity: LOW.**

`from_env()` lower-cases it (`config.py:201`) and the container tests `== "file"`
(`dependency_injection.py:252`). `CONGINE_CONTRACT_SOURCE=files` or `=local` silently selects the
HTTP repository. Unlike `region`, `fail_mode` and `deployment_mode` — all of which validate against
an enum — this string field has no validation at all.

*Fix:* validate against `{"http","file"}` in `from_env()`.

### 16.3 Dead and deprecated code

| Item | Location | Status | Notes |
|---|---|---|---|
| `ValidationTimer` | `infrastructure/timer.py` (81 lines) | **deprecated, unwired, tested** | `DeprecationWarning` on construction (`:39-44`); excluded from `infrastructure/__init__.py:22-25`; never constructed anywhere in `src/`. `tests/unit/test_timer.py` (4 tests) exercises it, so the suite protects code the container will never run |
| `region` / the `Region` enum | `config.py:34-42`, `:73` | **dead configurable** | D1 |
| `ValidationTimeoutException` | `exceptions.py:64` | **alias, never raised as a distinct type** | bound to `CongineValidationError`; a timeout degrades rather than raising. Documented at `:57-61` (audit L4) |
| `TenantIsolationViolationException` | `exceptions.py:65` | **alias, never raised at all** | forward-compat placeholder, documented as such |
| `CongineCacheError` | `exceptions.py:45` | **defined, never raised** | `grep` finds no `raise CongineCacheError` in `src/` |
| `CongineTelemetryError` | `exceptions.py:49` | **defined, never raised** | telemetry failures are swallowed and counted, never raised |
| `_DEFAULT_SAFE_FIELDS` | `logger.py:27-29` | **defined, never referenced** | a six-key frozenset the logger never reads; the effective allowlist comes from `config.effective_log_safe_fields()` |
| `_RE2_AVAILABLE` | `domain/validator.py:38` | **vestigial constant** | hard-coded `True` since `google-re2` became a required core dependency (FIX-02); never branched on |
| `_MAX_PATTERN_LENGTH` / `_MAX_REGEX_VALUE_LENGTH` | `domain/validator.py:34-35` | **back-compat aliases** | re-export `security_limits` constants "for tests and external references" |
| `main.py` | `libs/congine-sdk/main.py` (95 bytes) | **stub outside the package** | prints a greeting; not importable as part of the SDK |
| `redos` extra | `pyproject.toml:49` | **no-op extra** | documented as a backward-compatible alias since `google-re2` is a core dependency |
| `QueueEventBus(config=None)` path | `queue_event_bus.py:213-217` | **unreachable in production** | drain-and-observe mode; the container always passes a config (`:268`) |
| `validator_cls` parameter | `jsonschema_validator.py:76` | **test seam only** | the container never passes it (`:281-285`); it exists so tests can inject a class directly |

### 16.4 Severity roll-up

| Severity | Count | Items |
|---|---|---|
| HIGH | 3 | D1 (dead `region`), D2 (README covers 27/46), D18 (union type degrades everything) |
| MEDIUM | 8 | D3, D4, D8, D9, D10, D14, D16, D17 |
| LOW | 11 | D5, D6, D7, D11, D12, D13, D15, D19, D20, D21, D22 |
| Prior debts still present | 6 | #1, #3, #5, #6, #7, #9 |
| Prior debts fixed | 1 | #2 (P0-1) |
| Prior debts partially addressed | 1 | #8 (P0-2 — detection only) |
| Prior debts found to be wrong | 1 | #4 (direction inverted) |
| Dead / deprecated items | 13 | §16.3 |

**The pattern worth naming.** Nine of the twenty-two new findings (D1, D2, D5, D9, D15, D16, D20,
D21, D22) are **documentation or configuration drifting away from behaviour**, not defects in the
mechanisms. The mechanisms — the executor, the cache, the breaker, the repository, the rule engine —
are in good shape and their guarantees hold (§14). The risk in this codebase is concentrated in the
gap between what a user is told and what the code does, and D18 is the sharpest instance: a contract
written in perfectly ordinary JSON Schema silently stops enforcing anything at all.
