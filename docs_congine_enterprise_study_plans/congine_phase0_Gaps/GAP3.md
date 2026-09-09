# GAP3 — Integration surface & worked examples

**Generated:** 2026-08-16 · **Commit:** `49a2f93` · **Interpreter:** CPython 3.14.5 (win32),
`.venv/Scripts/python.exe` · **Package:** `congine-sdk 0.1.0` (editable install)

**Every example in this file was executed.** Outputs are copied verbatim from the run, not composed.
Where an example produced something other than what `ARCHITECTURE_CURRENT.md` predicts, the executed
result is what is recorded and the divergence is flagged. **One example failed and that failure is a
finding — see §3.8.**

Scripts live in the session scratchpad (`scratchpad/gap3/`); each is reproduced inline so the suite
can copy them without the scratchpad.

**Structured log lines are elided** from transcripts with `grep -v '"level"'` except where the log
line *is* the observable. That is noted where it applies.

---

## 3.1 Public API surface

`congine_core.__all__` exports **46 symbols**. Verified:
`python -c "import congine_core; print(len(congine_core.__all__))"` → `46`.

### Layer 1 — ports (9)

All are `@runtime_checkable typing.Protocol`; `inspect.signature` reports `(*args, **kwargs)` for
all nine, which is expected for a Protocol and is not informative. Method surfaces are in `§5`.

| Symbol | Layer | Method surface | Intended caller |
|---|---|---|---|
| `ISchemaStorage` | L1 | `get`, `put`, `clear`, `exists`, `size`, `stop` | Anyone writing a cache backend |
| `IContractRepository` | L1 | `fetch_active_contracts`, `load_snapshot`, `save_snapshot` | Anyone writing a contract source |
| `IEventBus` | L1 | `publish`, `queue_depth`, `stop(drain)`; `dropped_total` optional | Anyone writing a telemetry sink (incl. §15.2) |
| `ILogger` | L1 | `info`, `error`, `warning`, `debug` | Host wiring its own logging |
| `ISemanticValidator` | L1 | `validate` | Anyone replacing `jsonschema` |
| `IValidationRunner` | L1 | `capacity`, `run_with_timeout`, `run_with_timeout_async`, `health`, `shutdown` | Anyone replacing the executor |
| `ICircuitBreaker` | L1 | `state`, `allow`, `record_success`, `record_failure` | Anyone writing a distributed breaker |
| `IStoppable` | L1 | `stop` | Composed by `ISchemaStorage`; implemented by any stateful component |
| `IObservable` | L1 | `health` | Composed by `IValidationRunner` |

### Layer 2 — domain (7)

| Symbol | Signature | Intended caller |
|---|---|---|
| `BreachDetail` | `(rule: str, field: str, message: Optional[str] = None)` | Read off a result; constructed by custom rules |
| `ValidationResult` | `(status: str, breaches: Tuple[BreachDetail, ...] = (), duration_ms: float = 0.0, degraded: bool = False, degraded_reason: Optional[str] = None)` | **Read by every host** — the primary return type |
| `DriftResult` | `(statistic: float, p_value: float, drift_detected: bool, n_reference: int, n_sample: int)` | Returned by `evaluate_drift` |
| `TelemetryEvent` | `(contract_id: str, contract_version: str, status: str, duration_ms: float, breach_details=None, created_at=None)` | Constructed by L3; consumed by an `IEventBus` implementer |
| `RuleEngine` | `()` — six `@staticmethod` rules | Custom rule authors |
| `LocalValidator` | `(rules: Optional[List[Tuple[str, Callable[..., List[BreachDetail]]]]] = None)` | Direct use for a dependency-light embed |
| `CompositeValidator` | `(rule_validator: IValidator, semantic_validator: ISemanticValidator)` | Advanced wiring |

### Layer 3 — use cases (2)

| Symbol | Signature (abridged) | Intended caller |
|---|---|---|
| `ValidateContractUseCase` | `(schema_storage, validator, event_bus, logger, timer, timeout_ms=15, fail_mode=DEGRADE, max_payload_bytes=1048576, max_schema_bytes=1048576)` | A host building its own container; reached normally via `container.validate_contract_usecase` |
| `SyncContractsUseCase` | `(schema_storage, contract_repository, logger, cache_ttl_seconds=300, circuit_breaker=None, boot_lock_path=None, semantic_validation_enabled=False)` | Same |

> **Note the default drift.** `ValidateContractUseCase`'s own default `timeout_ms` is **15**, while
> `CongineConfig.validation_timeout_ms` is **100**. A host constructing the use case directly gets a
> 15 ms budget; a host going through `ServiceContainer` gets 100 ms. Nothing documents the
> discrepancy.

### Layer 4 — infrastructure (11)

| Symbol | Signature (abridged) | Intended caller |
|---|---|---|
| `LFUCache` | `(capacity=500, ttl_seconds=300, sweep_interval=30.0, start_sweeper=True)` | Container; direct use for embedding |
| `HttpContractRepository` | `(config: CongineConfig, logger=None)` | Container |
| `FileContractRepository` | `(contracts_dir: str, logger=None, max_contract_files=1000, max_file_bytes=1048576)` | Container; direct use in tests |
| `QueueEventBus` | `(config=None, logger=None, max_queue_size=10000, batch_size=100, max_retries=4, backoff_base=0.5, backoff_max=8.0, client_factory=None, start_worker=True, circuit_breaker=None)` | Container |
| `NoOpEventBus` | `()` | Container; **the template for §15.2** |
| `StructuredLogger` | `(name='congine', level='INFO', log_safe_fields=None)` | Container |
| `BackgroundSyncWorker` | `(sync_usecase, interval_seconds=300, logger=None, run_immediately=True, start_worker=False)` | Container |
| `BoundedValidationExecutor` | `(max_workers=10, max_pending=10, register_atexit=True)` | Container |
| `CircuitBreaker` | `(failure_threshold=5, cooldown_seconds=30.0, clock=time.monotonic)` | Container; `clock` is an injectable test seam |
| `JsonSchemaSemanticValidator` | `(validator_cls=None, max_breaches=100, format_checking=False, jsonschema_draft='draft202012')` | Container; `validator_cls` is a test seam |
| `KSDriftEngine` | `(threshold=0.1, max_samples=500)` | Container; **called by the host directly** |

> `BackgroundSyncWorker`'s own default is `run_immediately=True`, but the container passes `False`
> (`dependency_injection.py:353`) because `bootstrap()` has already primed. A host constructing it
> directly gets a duplicate immediate sync.

### Layer 5 — adapters (2) · Layer 0 — config & exceptions (15)

| Symbol | Signature | Intended caller |
|---|---|---|
| `ServiceContainer` | `(config: CongineConfig)` | **Every host.** Plus classmethods `from_env`, `get_default`, `for_tenant`, `reset_default`, `evicted_total` |
| `congine_guard` | `(contract_id, version='latest', container=None, mode='envelope', extractor=None)` | **Every host** — the primary surface |
| `CongineConfig` | 47 fields; `from_env()`, `validate()`, `is_local_base_url()`, `effective_log_safe_fields()`, `deployment_mode_from_env()`, `base_url_from_env()` | Every host |
| `Region`, `FailMode`, `DeploymentMode` | `str`-backed enums | Config construction |
| 7 canonical + 4 alias exceptions | — | Host `except` clauses |

### What is deliberately NOT exported, and why

| Symbol | Where it lives | Why it is not public |
|---|---|---|
| `IValidator` | `domain/validator.py:359` | Re-exported from `domain/__init__.py:16` but excluded from the package `__all__`. It is an *in-domain strategy seam*; exporting it would imply an outer layer is expected to supply a validator, inverting the boundary the architecture most protects (`§5.8`). |
| `ValidationTimer` | `infrastructure/timer.py` | Deprecated. Excluded from `infrastructure/__init__.py` (`:22-25`, audit D-3/D-11) because it is shape-compatible on `run_with_timeout` only — wiring it would satisfy a naive duck-type check and silently void guarantee G1. |
| `find_unenforced_keywords` | `domain/schema_vocabulary.py` | Exported from `domain/__init__.py:12` but **not** from the package `__all__`. Given that `.claude/CLAUDE.md` makes calling it mandatory for every schema writer, this is arguably an omission — see the question at the end of §3.6. |
| `CongineCallbackHandler` | `adapters/langchain_handler.py` | Reachable via `congine_core.adapters.__getattr__` but not in the package `__all__`, so `import congine_core` never requires `langchain-core`. |
| `RuleEngine`'s helpers | `_path_present`, `_type_matches`, `_type_label`, `_JSON_TYPE_MAP`, `_compiled_pattern` | Underscore-private; `_JSON_TYPE_MAP` is mirrored publicly as `RECOGNISED_TYPE_NAMES`. |
| `security_limits` constants | `security_limits.py` | Module is importable but no constant is in `__all__`; `validator.py:34-35` keeps `_MAX_PATTERN_LENGTH`/`_MAX_REGEX_VALUE_LENGTH` aliases "for tests and external references". |

---

## 3.2 Minimal working example — offline / standalone, passing

**Install.** The workspace is an Nx + uv monorepo; the SDK is a `uv` package.

```bash
# from the workspace root
uv sync --package congine-sdk                      # core only
uv sync --package congine-sdk --extra langchain --extra stats --extra dev   # everything
# standalone consumer, outside this repo:
pip install congine-sdk
```
Verified installed: `congine-sdk 0.1.0`, core requires
`google-re2>=1.0`, `httpx>=0.28`, `jsonschema>=4.23`, `portalocker>=2.8`.

**Environment** — three variables give a fully offline validator with no network, no threads:

```bash
CONGINE_LOCAL_CONTRACTS_DIR=./contracts   # file repo AND no sync worker at all
CONGINE_TELEMETRY_ENABLED=false           # NoOpEventBus: no drain thread, no socket
CONGINE_START_BACKGROUND_SERVICES=false   # no cache sweeper, no atexit hooks
```

**Contract** — `contracts/sentiment-v1.json`:

```json
{
  "id": "sentiment-v1",
  "version": "1.0.0",
  "schema": {
    "type": "object",
    "required": ["label", "score"],
    "null_forbidden": ["label"],
    "properties": {
      "label": { "type": "string", "enum": ["positive", "negative", "neutral"] },
      "score": { "type": "number", "min": 0, "max": 1 }
    }
  }
}
```

**Program** — `ex_32_pass.py`:

```python
import os
os.environ["CONGINE_LOCAL_CONTRACTS_DIR"] = "./contracts"
os.environ["CONGINE_TELEMETRY_ENABLED"] = "false"
os.environ["CONGINE_START_BACKGROUND_SERVICES"] = "false"

from congine_core import ServiceContainer, congine_guard, CongineConfig

container = ServiceContainer(CongineConfig.from_env())
loaded = container.bootstrap()
print("contracts_loaded =", loaded)

@congine_guard("sentiment-v1", container=container, mode="envelope")
def classify(text: str) -> dict:
    return {"label": "positive", "score": 0.91}

result = classify("congine is good")
vr = result["validation_result"]
print("output          =", result["output"])
print("status          =", vr.status)
print("is_pass()       =", vr.is_pass())
print("breaches        =", vr.breaches)
print("degraded        =", vr.degraded)
print("degraded_reason =", vr.degraded_reason)
container.close()
```

**Executed output — verbatim** (the two JSON lines are the structured logger on stdout):

```
{"timestamp": "2026-08-16T12:56:08.886515+00:00", "level": "INFO", "logger": "congine", "message": "Loaded contracts from directory", "count": 1, "contracts_dir": "...\\gap3\\contracts"}
{"timestamp": "2026-08-16T12:56:08.887140+00:00", "level": "INFO", "logger": "congine", "message": "Schema cache synced", "count": 1}
contracts_loaded = 1
output          = {'label': 'positive', 'score': 0.91}
status          = pass
is_pass()       = True
breaches        = ()
degraded        = False
degraded_reason = None
```

**Note.** `import congine_core` succeeded with no control plane, no `CONGINE_API_KEY` and no
`CONGINE_BASE_URL`, because the default `base_url` is loopback and `validate()` returns early for a
local URL (`config.py:321-322`). This is the "local development needs no credentials" path.

---

## 3.3 Minimal working example — failing validation

Same setup; only the payload changes. Three payloads, each exercising a different rule.

```python
@congine_guard("sentiment-v1", container=container, mode="envelope")
def classify(text: str) -> dict:
    return {"label": "ecstatic", "score": 1.7}   # not in enum; above max
```

**Executed output — verbatim, the exact breach structure returned:**

```
status    = fail
is_pass() = False
degraded  = False
n_breaches= 2
  BreachDetail(rule='ENUM_VALUES', field='label', message="Value for 'label' is not an allowed enum value")
  BreachDetail(rule='RANGE_CHECK', field='score', message="Value for 'score' is above maximum 1")

--- missing required field ---   payload = {"score": 0.5}
  BreachDetail(rule='FIELD_PRESENCE', field='label', message="Required field 'label' is missing")

--- null_forbidden ---           payload = {"label": None, "score": 0.5}
  BreachDetail(rule='ENUM_VALUES', field='label', message="Value for 'label' is not an allowed enum value")
  BreachDetail(rule='NULL_GUARD',  field='label', message="Field 'label' must not be null")
```

**Three things worth extracting for the suite.**

1. **Breaches accumulate in rule order** — `FIELD_PRESENCE`, `TYPE_MATCH`, `ENUM_VALUES`,
   `RANGE_CHECK`, `NULL_GUARD`, `REGEX_PATTERN` — not in severity order (`§11.1`). Confirmed by the
   third case, where `ENUM_VALUES` precedes `NULL_GUARD`.
2. **`label: None` produces TWO breaches.** `ENUM_VALUES` does *not* skip `None` while `TYPE_MATCH`
   does (`validator.py:177-179` skips `None`; `:202-206` does not). `§13.3` calls this "a genuine
   inconsistency across rules" — confirmed executed. A nullable enumerated field will always breach
   on `None`.
3. **Messages name the field and the constraint, never the value.** That is what makes the built-in
   surface PII-safe by construction (`§14.7`) — before `sanitize_breach_message` is even applied.

---

## 3.4 One example per enforcement posture

`fail_mode` selects the posture. Same contract, same violating payload, only the mode differs.

**Executed output — verbatim:**

```
observational (silent): returned  status=fail breaches=1 (no raise)
permissive   (degrade): returned  status=fail breaches=1 (no raise)
strict       (strict) : RAISED    CongineValidationError: Contract k validation failed with 1 breach(es)
```

| Posture | `fail_mode` | Caller observes | Logged | Telemetry |
|---|---|---|---|---|
| **Observational** | `silent` | The failing `ValidationResult` is returned. No exception, **no log line**. | nothing | published |
| **Permissive** | `degrade` (default) | The failing `ValidationResult` is returned. | `WARNING "Validation failed (degrade)"` | published |
| **Strict** | `strict` | `CongineValidationError` raised — **after** the telemetry publish (G9). | `ERROR "Validation failed (strict)"` | published **first** |

The ladder is genuinely graduated: the *verdict is identical* in all three (`status="fail"`,
one breach); only the consequence differs. A deployment can move up the ladder without changing a
single contract.

**The exception to the ladder.** A missing contract ignores it entirely — verified below.

---

## 3.5 One example per guard mode, against fail-mode

Guard `mode` and `fail_mode` are **independent raise sites**. Both can fire for one call. The full
3×3 matrix was executed.

**Executed output — verbatim:**

```
guard mode fail_mode observed
----------------------------------------------------------------------
envelope   silent    returned dict(output={'label': 'nope'}, validation_result=<fail>)
envelope   degrade   returned dict(output={'label': 'nope'}, validation_result=<fail>)
envelope   strict    RAISED CongineValidationError: Contract k validation failed with 1 breach(es)
output     silent    returned raw output {'label': 'nope'}
output     degrade   returned raw output {'label': 'nope'}
output     strict    RAISED CongineValidationError: Contract k validation failed with 1 breach(es)
raise      silent    RAISED CongineValidationError: Contract k validation failed
raise      degrade   RAISED CongineValidationError: Contract k validation failed
raise      strict    RAISED CongineValidationError: Contract k validation failed with 1 breach(es)
```

**Reading the matrix.**

- **The two raise sites are distinguishable by message.** `fail_mode=strict` raises from
  `validate_contract_usecase.py:249` with `"... with N breach(es)"`. `mode="raise"` raises from
  `guard.py:66-68` with no breach count. In the bottom-right cell the *use case* wins — it raises
  first, before the guard ever reaches `_finish`.
- **`mode="raise"` overrides an observational posture.** `raise` + `silent` still raises. A team
  running the SDK observationally at the container level can be surprised by a single decorator.
- **`mode="output"` is not "no enforcement"** — validation still runs and `fail_mode` still applies.
  It only changes the *return shape*.
- Only four of nine cells return normally.

---

## 3.6 A contract that looks enforced but is not

**This is the most important example in the corpus.** Two constructions were run: an ignored
keyword (`minLength`) and a union type (`{"type": ["string","null"]}`).

### Case A — `minLength`: an ignored keyword. **STILL UNENFORCED.**

```python
schema_a = {"type": "object", "required": ["summary"],
            "properties": {"summary": {"type": "string", "minLength": 10}}}
container.schema_storage.put("looks-enforced", schema_a, 300)
r = uc.execute({"summary": "hi"}, "looks-enforced", "1.0")   # 2 chars vs minLength 10
```

**Executed output — verbatim:**

```
payload           = {'summary': 'hi'}   # 2 chars vs minLength 10
status            = pass
is_pass()         = True
breaches          = ()
degraded          = False
find_unenforced_keywords -> ['summary.minLength']
```

A two-character string satisfies a contract demanding ten. **`status="pass"`, zero breaches, no
warning at validation time.** The only signal is `find_unenforced_keywords`, and — because this
schema was written with `schema_storage.put()` rather than through the repository — **even the
load-time WARNING did not fire.** That is debt D17 demonstrated: the scan runs only from
`_prime_cache`.

### Case A remedy — the same contract with semantic validation on

**Executed output — verbatim:**

```
semantic ON : status= fail  breaches= [('SEMANTIC_SCHEMA', 'summary', "'<redacted>' is too short")]
semantic OFF: status= pass  breaches= []  <-- DEFAULT
```

The remedy works, and note that the instance value is already redacted in the message — G7 holding
on the semantic path.

### Case B — union type. **⚠ FIXED SINCE `ARCHITECTURE_CURRENT.md`.**

`§13.6` and debt **D18** state that `{"type": ["string","null"]}` raises `TypeError`, degrades every
validation against that contract *permanently*, and is the system's one HIGH-severity
safety-critical defect. **That is no longer true.**

```python
schema_b = {"type": "object", "properties": {"a": {"type": ["string", "null"]}}}
```

**Executed output — verbatim:**

```
payload={'a': 'x'}       status=pass  degraded=False  reason=None            breaches=[]
payload={'a': None}      status=pass  degraded=False  reason=None            breaches=[]
payload={'a': 5}         status=fail  degraded=False  reason=None            breaches=[('TYPE_MATCH', 'a', "Expected type 'string|null' for field 'a'")]
find_unenforced_keywords -> []
```

The union is now **meaningfully enforced**: a string passes, `None` passes, an integer fails with
one clean breach, and the message renders the union as `'string|null'` rather than a Python list
repr. `find_unenforced_keywords` correctly reports nothing. `degraded` is `False` throughout.

### Case B residue — the composed hazard the fix introduced

A union containing an **unrecognised** name matches everything, because the union rule composes with
the unknown-type rule. `validator.py:102-104` acknowledges this explicitly.

**Executed output — verbatim:**

```
--- union containing an UNRECOGNISED name (matches everything) ---
payload={'a': 12345}  status= pass  breaches= ()
find_unenforced_keywords -> ['a.type']
```

An integer satisfies `{"type": ["string", "wat"]}`. Detection works — `a.type` is reported — but
again only on the prime path.

### Case B shape 2 — a non-dict schema. **NOT FIXED.**

`§13.6` Shape 2 (a cached value that is not a mapping) still degrades exactly as documented.

**Executed output — verbatim, log line included because it *is* the observable:**

```
{"level": "ERROR", "message": "Validation error", "contract_id": "bad-schema", "error_type": "AttributeError", "degraded_reason": "internal_error"}
{"level": "WARNING", "message": "Validation failed (degrade)", "contract_id": "bad-schema", "breaches": 0, "degraded": true}
status= fail degraded= True reason= internal_error breaches= ()
```

`status="fail"` with **zero breaches** and `degraded=True` — the shape `§9.6` warns about. A caller
reading only `is_pass()` sees a failure and cannot tell that nothing was checked.

### Case C — dot-notation. **STILL UNENFORCED AND STILL UNDETECTED (D16).**

Added because it is the same class of trap and is *not* caught by the P0-2 scan at all.

**Executed output — verbatim:**

```
payload {'user':{'email':12345}} (an int, not a string, no @)
status = pass  breaches = []  <-- type+pattern NOT enforced
find_unenforced_keywords -> []  <-- does not flag it
```

The contract `{"required": ["user.email"], "properties": {"user.email": {"type": "string",
"pattern": "^.+@.+$"}}}` enforces **presence only**. An integer with no `@` passes. `FIELD_PRESENCE`
walks the dotted path and finds it; `TYPE_MATCH` and `REGEX_PATTERN` do a flat lookup for a
top-level key literally named `"user.email"`, do not find it, and skip silently. And
`find_unenforced_keywords` returns `[]` because it inspects keyword *names*, and `user.email.type`
and `user.email.pattern` are both in the enforced set.

**This is now the sharpest remaining false-safety edge**, because unlike `minLength` there is no
detection at all — not even on the prime path.

### Summary of §3.6

| Construction | Enforced? | Detected by the load scan? | Status |
|---|---|---|---|
| `minLength` (and every other ignored keyword) | **No** | Yes (`summary.minLength`) — prime path only | Open (F-2 / D17) |
| `{"type": ["string","null"]}` | **Yes** | N/A — correctly not reported | **FIXED (Q2)** |
| `{"type": ["string","wat"]}` | No — matches everything | Yes (`a.type`) — prime path only | Known, acknowledged in code |
| Non-dict schema | No — degrades | No | Open (D18 shape 2) |
| `"user.email"` dotted property | **Presence only** | **No** | Open (D16) — worst of the four |

**❓ QUESTION FOR FOUNDER:** `find_unenforced_keywords` is documented in `.claude/CLAUDE.md` as
mandatory for every schema writer, but it is **not in the package `__all__`**. An external
integrator writing a loader against the public API cannot reach it without importing
`congine_core.domain.schema_vocabulary` directly. Should it be exported?

---

## 3.7 Non-dict output handling — the `extractor=` pattern

**Executed output — verbatim:**

```
raw output        = 'Hello world'   <- type: str
validated payload = {'text': 'Hello world'}
status            = pass

lowercase -> status = fail breach = [('REGEX_PATTERN', "Value for 'text' does not match pattern")]

--- WITHOUT extractor, a bare string reaches LocalValidator directly ---
status= fail degraded= False breaches= [('TYPE_MATCH', '<root>', 'Payload must be an object/dict')]
```

```python
@congine_guard("text-v1", container=c, mode="envelope", extractor=lambda s: {"text": s})
def summarise() -> str:
    return "Hello world"          # a bare string, not a dict
```

**What the example establishes.**

1. `extractor` maps the raw output to the dict payload that is validated. The **raw output is what
   the caller gets back** (`result["output"]` is the string, not the wrapped dict) — the extractor
   affects validation only.
2. Constraints apply to the extracted shape: `pattern: "^[A-Z].*"` fails on `"lowercase start"`,
   and — note — `fullmatch` semantics mean `^[A-Z].*` must match the *entire* string, which `.*`
   happens to allow here.
3. **Without an extractor, a non-dict output is not an error — it is a breach.**
   `LocalValidator.validate` short-circuits at `:450-461` with a single `TYPE_MATCH`/`<root>`
   breach, `degraded=False`. It fails *closed and cleanly*, which is the correct design: a
   forgotten extractor produces an actionable breach rather than a crash or a silent pass.

---

## 3.8 What a new port implementation must provide

Derived from the Protocol **and** from what the container actually calls **and** from the test fakes
in `tests/conftest.py`, which are the working proof that structural conformance is achievable.

### ⚠ FINDING — an example failed, and the failure is the result

I wrote three minimal implementations (`MinimalStorage`, `MinimalBus`, `MinimalRunner`) from the
port docstrings alone, with no imports of Congine and no subclassing, then substituted them into a
live container.

**Executed output — verbatim:**

```
=== runtime_checkable isinstance conformance (no imports in the impls) ===
  isinstance(MinimalStorage , ISchemaStorage    ) = True
  isinstance(MinimalBus     , IEventBus         ) = True
  isinstance(MinimalRunner  , IValidationRunner ) = True
  isinstance(MinimalStorage , IStoppable        ) = True
  isinstance(MinimalRunner  , IObservable       ) = True

=== substitute them into a live container and run health() + close() ===
  validate -> status = pass
  health() AttributeError: 'MinimalRunner' object has no attribute 'in_flight'
  close()  OK
```

**All three satisfy their Protocols. `health()` still crashes.**

`IValidationRunner` declares `health()` and its docstring says the container "reports `in_flight`
and `rejected_total` in `health()`" (`ports/validation_runner.py:39-42`) — but
`ServiceContainer.health()` does **not** call `health()`. It reads the properties directly:

```python
# adapters/dependency_injection.py:459-460
"validation_in_flight": self.validation_executor.in_flight,
"validation_rejected_total": self.validation_executor.rejected_total,
```

`in_flight` and `rejected_total` are properties on `BoundedValidationExecutor` (`:185-195`) and are
**not declared on the port**. So `§16` debt **D14 is only partially closed by Q8**: two of the three
under-declared surfaces (`ISchemaStorage.size`, `IEventBus.queue_depth`/`stop`) are fixed, and the
third is not.

**Control case, confirming Q8 did fix the rest.** A pre-Q8-shaped bus (`publish` only) now fails an
`isinstance` check *before* it can be wired — which is the improvement Q8 delivered:

```
isinstance(PublishOnlyBus(), IEventBus) = False  <- now False; the port declares the full surface
health() with publish-only bus -> AttributeError: 'PublishOnlyBus' object has no attribute 'queue_depth'
close()  with publish-only bus -> AttributeError: 'PublishOnlyBus' object has no attribute 'stop'
```

**❓ QUESTION FOR FOUNDER:** Should `ServiceContainer.health()` call
`self.validation_executor.health()` and merge the result, rather than reading two undeclared
properties? That would finish Q8. As it stands, a faithful `IValidationRunner` still crashes
`health()`, which is the exact defect Q8 set out to eliminate.

### The obligations, per port

Signatures are in §3.1 and `§5`. Below is only what a signature cannot express.

#### `ISchemaStorage`
| Obligation | Why | Evidence |
|---|---|---|
| **Thread-safe** — required | `get` on the caller's thread, `put` from boot thread and sync daemon, concurrently | `§5.1` |
| **`get` must not block** | It sits *outside* the timeout guard; a blocking `get` blocks the host unboundedly | `ports/schema_storage.py:22-23` |
| **Expired ⇒ absent** | `None` becomes `CongineContractNotFoundError`; there is no second chance | `validate_contract_usecase.py:163-165` |
| **`put` atomic, must never clear** | Clear-then-refill opens a window where every validation raises | `ports/schema_storage.py:23-25` |
| **Must not raise** | No caller wraps `get`/`put` | `§5.1` |
| **`size()` and `stop()`** | Now declared. `stop()` must be idempotent, never raise, bounded | `ports/lifecycle.py:34-42` |
| Reference | `FakeSchemaStorage` (`conftest.py:65-90`) — a dict with `size` and a no-op `stop`; 26 lines | |

#### `IEventBus`
| Obligation | Why | Evidence |
|---|---|---|
| **`publish` non-blocking, never raises** | Called on the hot path with no `try` around it; a raise propagates *after* validation succeeded | `ports/event_bus.py:52-54` |
| **Dropping under back-pressure is sanctioned** | Telemetry loss is explicitly preferred to latency | `ports/event_bus.py:53-54` |
| **`stop(drain)`** — `drain=False` must be prompt | A finalizer runs on an arbitrary GC thread; an unreachable plane must not stall collection | `ports/event_bus.py:72-77` |
| **`queue_depth()`** returns `0` if not buffering | `NoOpEventBus` precedent | `noop_event_bus.py:30-32` |
| **`dropped_total()` optional** | Deliberately not a Protocol member; probed with `getattr`/`callable` | `ports/event_bus.py:80-88` |
| **Durability is an implementation choice** | A durable log is a *second implementation of this port*, config-selected — never a blocking default bus | `ports/event_bus.py:35-46` (audit Q9) |
| Reference | `NoOpEventBus` (40 lines) is the template `§15.2` names; `FakeEventBus` omits `dropped_total` on purpose | |

#### `IValidationRunner`
| Obligation | Why | Evidence |
|---|---|---|
| **Capacity bounding** — saturation raises immediately, never queues | The exact failure H1 exists to prevent | `ports/validation_runner.py:27-29` |
| **Hard deadline** — may not stop the work, must stop *waiting* | Python cannot kill a thread | `§5.6` |
| **Permit held until the future completes**, not until the wait is abandoned | Otherwise capacity is fiction under load | `bounded_executor.py:107-108` |
| **Re-entrancy** — a call on the runner's own worker must run inline | Otherwise nested use deadlocks | `bounded_executor.py:100-101` |
| **Sync and async share one pool** | Otherwise async silently bypasses the bound | `bounded_executor.py:103`, `:140` |
| **Async twin must not block the loop** | `wrap_future` + `wait_for` | `bounded_executor.py:142-144` |
| **Exception transparency** — `func`'s own exceptions propagate unchanged | L3 classifies them | `validate_contract_usecase.py:71-82` |
| **`shutdown(wait=False)` must not block** | Teardown cannot wait on uncancellable work | `ports/validation_runner.py:106-110` |
| **⚠ Undeclared: `in_flight`, `rejected_total` properties** | `health()` reads them directly — see the finding above | `dependency_injection.py:459-460` |
| Reference | `ImmediateTimer` (`conftest.py:93-103`) is **deliberately partial** — `run_with_timeout` only — and its docstring says so, pointing at `FakeRunner` in `tests/test_validation_runner_port.py` for the full protocol | |

#### `IContractRepository`
| Obligation | Why | Evidence |
|---|---|---|
| **`fetch_active_contracts` raises only `CongineSyncError`** | Anything else escapes `bootstrap()` and turns a transport hiccup into a boot crash | `sync_contracts_usecase.py:206-213` |
| **Awaited from two contexts** — `asyncio.run` and direct `await` | Must not assume a pre-existing loop | `:207` vs `:222` |
| **`load_snapshot` never raises; returns `None`, not `[]`** | `_apply` treats falsy as "retain current cache" | `:242` |
| **`save_snapshot` may raise only `OSError`** | `_apply` catches exactly that; best-effort | `:249-252` |
| **Contracts must be `{"id":…, "schema":…}`** | `_prime_cache` skips entries missing either key, silently | `:265-267` |
| **`snapshot_lock_path` optional property** | Absent ⇒ single-flight silently degrades | `dependency_injection.py:332` |
| Reference | `FakeContractRepository` (`conftest.py:106-138`); `FileContractRepository` deliberately omits `snapshot_lock_path` | |

#### `ILogger`
| Obligation | Why | Evidence |
|---|---|---|
| **Must never raise, on any input** | Called from the hot path, three daemons, and inside `except` blocks | `§5.4` |
| **Must accept arbitrary keyword extras** | Including keys it has never seen | `ports/logger.py:14-18` |
| **Must be thread-safe** | Four threads log concurrently | `§5.4` |
| **Should honour the redaction contract** | A replacement that logs verbatim silently voids G7 | `logger.py:31-40` |
| Reference | `FakeLogger` (`conftest.py:17-39`), 23 lines | |

#### `ISemanticValidator`
| Obligation | Why | Evidence |
|---|---|---|
| **Flat list, never nested, never `None`** | `CompositeValidator` does `breaches.extend(...)` with no guard | `validator.py:519` |
| **Must not raise** | It runs inside the executor; a raise becomes `internal_error` and the detail is lost | `jsonschema_validator.py:107-116` |
| **Must bound its output** | An unbounded implementation lets a hostile schema generate unbounded work inside the budget | `:125` (FIX-03) |
| **Must sanitise messages** | These strings reach telemetry | `:114`, `:132` |
| **Must be callable concurrently** | Runs on pool workers; the validator class is constructed fresh per call | `:121` |
| **Must tolerate a non-dict payload** | `CompositeValidator` calls it even after the rule validator rejected a non-dict root — debt D7, still present | `validator.py:517-519` |
| Reference | No fake in `conftest.py`; `tests/unit/test_semantic_validator.py` exercises the real one | |

#### `ICircuitBreaker`
| Obligation | Why | Evidence |
|---|---|---|
| **`allow()` cheap and non-blocking** | Consulted before every fetch and every telemetry batch | `sync_contracts_usecase.py:201`; `queue_event_bus.py:221` |
| **HALF_OPEN admits exactly one probe** | Otherwise every caller floods a recovering plane | `circuit_breaker.py:92-96` (FIX-11) |
| **Decide whether reading `state` transitions** | The reference implementation does — so polling `health()` can move it out of OPEN | `circuit_breaker.py:65-75` |
| **Thread-safe** — three writers | Boot thread, sync daemon, bus daemon | `§10.4` row 5 |
| **`record_failure` in HALF_OPEN ⇒ straight to OPEN** | Not an increment toward the threshold | `circuit_breaker.py:111-114` |
| **Cannot assume a single caller** | One instance is shared by sync and telemetry | `dependency_injection.py:298`, `:338` |
| Reference | No fake; `CircuitBreaker` takes an injectable `clock` for deterministic tests (`:44`) | |

#### `IValidator` (in-domain seam)
| Obligation | Why | Evidence |
|---|---|---|
| **Pure and side-effect free** | Runs on a pool worker | `§5.8` |
| **Must never raise on well-formed input** | Any raise becomes `internal_error` and the breach detail is lost | `validate_contract_usecase.py:79-82` |
| **`status="pass"` only when `breaches` is empty** | `is_pass()` compares the string; a result claiming pass with breaches is enforced as a pass | `models.py:50-52` |
| **Should populate `duration_ms`** | Copied verbatim into telemetry | `validate_contract_usecase.py:215` |
| **Custom rules must be PII-safe** | `sanitize_breach_message` is conservative; an unquoted non-numeric instance value would survive | `§14.7` |
| Reference | `LocalValidator`, `CompositeValidator` — both L2 | |

---

## Examples executed — index

| § | Example | Result |
|---|---|---|
| 3.2 | Offline standalone, passing | ✅ ran, `status="pass"` |
| 3.3 | Failing validation ×3 payloads | ✅ ran, breach structures recorded verbatim |
| 3.4 | Three enforcement postures | ✅ ran, all three |
| 3.5 | 3×3 guard mode × fail mode | ✅ ran, all nine cells |
| 3.6A | `minLength` ignored | ✅ ran — **passes when it should fail** |
| 3.6A′ | Same contract, semantic validation on | ✅ ran — correctly fails, message redacted |
| 3.6B | Union type | ✅ ran — **enforced; D18 fixed** |
| 3.6B′ | Union with unrecognised member | ✅ ran — matches everything, detected at load |
| 3.6B″ | Non-dict schema | ✅ ran — still degrades |
| 3.6C | Dot-notation property | ✅ ran — **presence only, undetected** |
| 3.7 | `extractor=`, with and without | ✅ ran |
| 3.8 | Minimal port implementations | ⚠ **ran and FAILED — `health()` AttributeError; recorded as a finding, example not adjusted** |
| — | G10 missing contract, all three modes | ✅ ran — raises in all three |
