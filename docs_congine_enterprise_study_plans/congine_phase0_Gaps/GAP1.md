# GAP1 — Per-file narrative material

**Generated:** 2026-08-16 · **Commit:** `49a2f93` (branch `ahmed-main-v2`), working tree clean
**Package root:** `libs/congine-sdk/src/congine_core/` — **38 Python files**, 32 implementation
modules, 6 package `__init__.py`, **5 473 physical lines**.
**Source of structural fact:** `ARCHITECTURE_CURRENT.md` (cited as `§n`) where it is still correct;
the code where it is not. Divergences are flagged inline as **⚠ DRIFT**.

> **Scope note.** `ARCHITECTURE_CURRENT.md` was generated against commit `a561992` plus an
> uncommitted working tree. Commit `49a2f93` landed afterwards and closed all twelve §17 open
> questions. This file describes the tree at `49a2f93`. The complete drift list is at the end of
> this document (§DRIFT) and in the final report.

**Field definitions.**
- *Deletion test* — if this file vanished, what specifically breaks, and how would you notice?
- *Future trajectory* — per `§15`, does a planned capability **touch** this file (must be edited),
  **attach beside** it (new sibling, this file unchanged), or **leave it untouched**?
- *Metaphor candidate* — a role in one coherent world that explains the file's *mechanism*.
  `NONE` where no honest metaphor helps.

**The metaphor world.** The candidates below are drawn from a single frame: **a border-control post
on the outbound side of a country**. Congine inspects what is *leaving* (the function's return
value), not what is arriving. The contract is the published regulation; the rule engine is the
inspector; the cache is the posted copy of the regulations at the booth; the control plane is the
capital that issues regulation; the snapshot is the last printed edition kept in the drawer. The
frame is used only where it explains a mechanism.

---

## L0 — Shared kernel (5 files)

### libs/congine-sdk/src/congine_core/__init__.py
- **Layer / status:** L0 (by directory) · active
- **One-line identity:** The package's public API surface — 46 exported symbols plus `__version__`.
- **Why it exists:** Consumers need one stable import target that does not change when internal
  module paths move. It also single-sources the version from installed distribution metadata
  rather than duplicating a literal.
- **Deletion test:** `import congine_core` yields an empty namespace. Every documented consumer
  import (`from congine_core import congine_guard, ServiceContainer`) raises `ImportError`
  immediately. Loud and instant — the first line of any user's script fails.
- **Load-bearing detail:** This is the one file in the package whose imports point *outward*, and
  the reason `import congine_core` eagerly pulls in `httpx`, `jsonschema`, `re2` and `portalocker`
  (`ARCHITECTURE_CURRENT §4.5`). A consumer wanting a light import must bypass the package surface.
  **⚠ DRIFT:** `__all__` now carries 46 symbols including `IStoppable` and `IObservable` (`:94-95`);
  §3.1 predates both.
- **Future trajectory:** **Touched** by every §15 capability that adds a public symbol — MCP server
  (§15.1), `SqliteEventBus` (§15.2), `HistoryQueryUseCase` (§15.4), CLI (§15.9). Purely additive.
- **Metaphor candidate:** The published index of the border post's services — the only page the
  public is expected to read.

### libs/congine-sdk/src/congine_core/config.py
- **Layer / status:** L0 · active
- **One-line identity:** `CongineConfig`, a frozen dataclass of **47** fields, each mapped 1:1 to a
  `CONGINE_*` environment variable, plus three policy methods.
- **Why it exists:** Every layer needs to read configuration, so configuration cannot live anywhere
  that imports a port or a concrete. Freezing it removes an entire class of race: one object is
  threaded read-only through every thread with no defensive copying.
- **Deletion test:** Nothing constructs. `ServiceContainer.__init__` takes a `CongineConfig` as its
  only argument, so the container, both use cases, and every concrete lose their parameter source.
  You would notice at the first `import congine_core` — `config` is imported by L3, L4 and L5.
- **Load-bearing detail:** `validate()` runs only from `from_env()` (`:316`), never from the
  constructor — so a directly-constructed `CongineConfig(...)` is **never validated**. Tests and
  embedders routinely take that path. Field-by-field semantics are `§12.1`; do not restate them.
  **⚠ DRIFT (four items):** (a) **47 fields, not 46** — `max_contract_file_bytes` was added,
  splitting `§16` debt D21/Q11; (b) `region` is **no longer dead** — `base_url_from_env()`
  (`:203-216`) selects a regional default control plane, closing debt D1/Q1, though the hostnames
  at `:46-50` are self-declared placeholders; (c) `deployment_mode_from_env()` (`:186-201`) is new
  and closes debt D8/Q10; (d) `_env_bool` still fails silently toward `False` (`:382-390`) — debt
  D20 **still present**.
- **Future trajectory:** **Touched** by nearly every §15 capability — each adds config fields
  (`event_store_path` for §15.2, MCP transport settings for §15.1). The 4-touch change rule in
  `.claude/CLAUDE.md` is now machine-enforced by `tests/unit/test_readme_config_table.py`.
- **Metaphor candidate:** The standing orders posted in the guard house — read by everyone on duty,
  amendable only before the shift starts, never mid-shift.

### libs/congine-sdk/src/congine_core/exceptions.py
- **Layer / status:** L0 · active (4 of 11 symbols are dead or alias-only)
- **One-line identity:** One root exception plus six canonical types and four Tier-2 aliases.
- **Why it exists:** So a host can guard the entire SDK with one `except CongineBaseException`
  clause. The aliases exist so `except` clauses written against older names keep working.
- **Deletion test:** `config.py`, both use cases, `http_contract_repository`,
  `jsonschema_validator`, `dependency_injection`, `guard` and `langchain_handler` all fail to
  import. The whole package is unimportable. Fastest possible failure.
- **Load-bearing detail:** The Tier-2 aliases are **assignment-bound, never subclasses** (`:62-65`),
  so `except ValidationTimeoutException` catches *every* `CongineValidationError` — it is not a
  narrower filter. `CongineCacheError` and `CongineTelemetryError` are defined and **never raised**
  anywhere in `src/` (`§16.3`); telemetry failures are counted, not raised.
- **Future trajectory:** **Leaves untouched.** No §15 capability needs a new exception type; the
  root-plus-six shape absorbs additions as subclasses.
- **Metaphor candidate:** The schedule of offence categories — a fixed list every officer cites,
  with some categories on the books that no one has ever charged.

### libs/congine-sdk/src/congine_core/security_limits.py
- **Layer / status:** L0 · active
- **One-line identity:** Nine numeric bounds, centralised so no layer invents its own cap.
- **Why it exists:** The rule engine (L2), the semantic validator (L4) and the use-case input
  guards (L3) all need the same bounds. Any other home would force one of them to import across a
  boundary it must not cross.
- **Deletion test:** `config.py`, `domain/validator.py`, `jsonschema_validator.py` and
  `langchain_handler.py` fail to import. More subtly, if the constants were merely *inlined* rather
  than deleted, the ReDoS caps would drift apart between the rule engine and the semantic
  validator — and nothing would fail loudly.
- **Load-bearing detail:** **⚠ DRIFT:** nine constants, not eight —
  `DEFAULT_MAX_CONTRACT_FILE_BYTES` (`:22`) is new. Its comment states the rationale verbatim: the
  two caps "defaulted to the same value and were wired from a single config field, so tuning one
  silently moved the other." That is debt D21 closed.
- **Future trajectory:** **Touched** by §15.1 (an MCP tool call is untrusted external input and
  needs its own request bound) and §15.2 (an event-store row/batch cap).
- **Metaphor candidate:** The single posted table of weight and size limits, referenced by every
  booth so two booths cannot publish different numbers.

### libs/congine-sdk/src/congine_core/pii_sanitize.py
- **Layer / status:** L0 · active
- **One-line identity:** One function that strips quoted substrings and 4+-digit runs out of breach
  messages before they reach logs or telemetry.
- **Why it exists:** `jsonschema` embeds the *offending instance value* in its error text. Those
  strings go to telemetry, which leaves the process. Without this, validating a payload containing
  a customer email ships that email to the control plane.
- **Deletion test:** `validate_contract_usecase.py` and `jsonschema_validator.py` fail to import.
  If it were instead stubbed to identity, **nothing would fail** — every test would pass and
  guarantee G7 (`§14.7`) would be silently void. This is the file whose deletion is most dangerous
  precisely because it is least noisy.
- **Load-bearing detail:** It is the **one regex in the codebase using stdlib `re` instead of
  `re2`** (`:9`, `:14`) — the single documented exception to the project-wide linear-time rule
  (`§14.5`, debt D7). It sits on the path handling the least-trusted strings in the system. Still
  present at `49a2f93`.
- **Future trajectory:** **Touched** by §15.5 (`correction_hint`): sanitisation is applied to
  `message` only, so a hint field would bypass it entirely unless this file's contract is widened
  or hints are made structurally value-free.
- **Metaphor candidate:** The redaction stamp applied to an incident report before it is forwarded
  to the capital — the description of the offence survives, the identifying detail does not.

---

## L1 — Ports (9 files)

### libs/congine-sdk/src/congine_core/ports/__init__.py
- **Layer / status:** L1 · active
- **One-line identity:** Aggregate re-export of all seven functional ports plus the two lifecycle
  seams.
- **Why it exists:** So `from congine_core.ports import ISchemaStorage` works without knowing the
  module split.
- **Deletion test:** `congine_core/__init__.py` fails to import, taking the package with it.
  Nothing else imports it — every internal consumer imports the specific port module directly,
  deliberately, to stay import-light.
- **Load-bearing detail:** Its docstring records a naming decision no other file does: the
  directory is `ports/` rather than the historical `repositories/` because it holds *every*
  cross-layer seam, not only repository ones (`:4-7`). **⚠ DRIFT:** exports nine symbols now, not
  seven — `IStoppable` and `IObservable` (`:13`, `:27-29`).
- **Future trajectory:** **Touched** by §15.1 (`IMCPTransport`), §15.4 (an `IEventStore` read port)
  and §15.7 (`IAgentAdapter`). Additive only.
- **Metaphor candidate:** NONE — it is a table of contents.

### libs/congine-sdk/src/congine_core/ports/lifecycle.py
- **Layer / status:** L1 · active · **NEW at `49a2f93`, absent from `ARCHITECTURE_CURRENT.md`**
- **One-line identity:** Two composable protocols — `IStoppable` (has `stop()`) and `IObservable`
  (has `health()`) — that the stateful ports inherit.
- **Why it exists:** `ServiceContainer` called `stop()`, `shutdown()`, `size()`, `queue_depth()`
  and counter properties that **no port declared**. A faithful implementation of `IEventBus` as
  written (one method, `publish`) raised `AttributeError` the first time `close()` or `health()`
  ran. This is `§16` debt D14 / `§17` Q8, closed.
- **Deletion test:** `ports/schema_storage.py` and `ports/validation_runner.py` fail to import
  (both inherit from it), taking `ports/__init__.py` and the package with them. Loud.
- **Load-bearing detail:** The design decision is *composition, not mixing*: keeping lifecycle
  separate means `ISchemaStorage` still describes one job — caching schemas (`:12-14`).
  `IEventBus` deliberately does **not** inherit `IStoppable`, because its teardown takes a `drain`
  argument, so it re-declares a widened `stop(drain=...)` of its own (`:16-19`). The obligations
  are stated as prose contracts — idempotent, never raises, bounded — not as types.
- **Future trajectory:** **Touched** by §15.2 (`SqliteEventBus` must satisfy the widened surface)
  and §15.4. This file is precisely what makes those additions safe.
- **Metaphor candidate:** The standing instruction that every booth must be closable and must be
  able to report its own queue length — separate from the instruction about what each booth
  inspects.

### libs/congine-sdk/src/congine_core/ports/schema_storage.py
- **Layer / status:** L1 · active
- **One-line identity:** `ISchemaStorage` — the cache seam: `get`, `put`, `clear`, `exists`,
  `size`, plus inherited `stop`.
- **Why it exists:** The hot path must read a schema without knowing whether it came from an LFU
  cache, a dict, or something else. It is the seam that makes the validation path testable without
  a cache implementation.
- **Deletion test:** Both use cases fail to import. The hot path has no way to resolve a contract
  id to a schema; every guarded call would need a cache passed by hand.
- **Load-bearing detail:** The obligations are behavioural and unenforceable by the type system:
  `get` sits **outside** the timeout guard so it must never block, and `put` must be individually
  atomic and must **never clear** — a clear-then-refill implementation opens a window in which
  every validation raises `CongineContractNotFoundError` (`:22-25`, and `§5.1`). **⚠ DRIFT:**
  `size()` is now declared (`:73-79`) and `IStoppable` is inherited (`:16`); §5.1's "real gap
  between the declared port and the required port" is closed.
- **Future trajectory:** **Touched** by §15.1 — `list_contracts` would be the first API that
  *enumerates* contracts, and this port has no enumeration method. `§15.1` recommends growing the
  port, which is backward-compatible for `LFUCache`.
- **Metaphor candidate:** The rack at the booth holding the current regulations — the inspector
  reads from it and never waits, and the courier who restocks it swaps sheets one at a time rather
  than emptying the rack first.

### libs/congine-sdk/src/congine_core/ports/event_bus.py
- **Layer / status:** L1 · active
- **One-line identity:** `IEventBus` — `publish`, `queue_depth`, `stop(drain)`; `dropped_total` is
  deliberately optional.
- **Why it exists:** So the hot path can emit telemetry without knowing whether it is being
  queued, shipped, or discarded, and so telemetry can be turned off by swapping one object.
- **Deletion test:** `validate_contract_usecase.py` and `dependency_injection.py` fail to import.
  Telemetry becomes a hard dependency of the validation path rather than an injected one.
- **Load-bearing detail:** Two contracts are recorded here that exist nowhere else. First,
  `dropped_total` is **deliberately not** a protocol member (`:80-88`) because a
  `@runtime_checkable` Protocol member is mandatory under `isinstance` and this one genuinely is
  not — the container probes it with `getattr`/`callable`. Second, and larger: the docstring
  **settles the durability question** (`§17` Q9) in the port itself — the default bus stays
  fire-and-forget forever, and a durable log arrives as a *second implementation of this same
  port*, config-selected, never by making the default bus blocking (`:35-46`). **⚠ DRIFT:** §5.3
  describes this port as declaring `publish` only.
- **Future trajectory:** **Attaches beside** — §15.2's `SqliteEventBus` is a new L4 file
  implementing this unchanged port. This is the cleanest seam in the system.
- **Metaphor candidate:** The outbound dispatch slot — the inspector drops a note in and walks
  away; whether a courier collects it, a clerk files it, or it falls into a bin is not the
  inspector's concern.

### libs/congine-sdk/src/congine_core/ports/validation_runner.py
- **Layer / status:** L1 · active
- **One-line identity:** `IValidationRunner` — `capacity`, `run_with_timeout`,
  `run_with_timeout_async`, `health`, `shutdown`.
- **Why it exists:** Audit D-4: so L3 is typed against an L1 abstraction rather than naming an L4
  concrete. Without it, `ValidateContractUseCase` would import `BoundedValidationExecutor`
  directly — an inner layer naming an outer concrete, the one boundary violation that matters most.
- **Deletion test:** `validate_contract_usecase.py` fails to import. Structurally, the hexagon's
  most load-bearing seam disappears and the domain-facing use case couples to a thread pool.
- **Load-bearing detail:** This is the most demanding port in the system. The docstring states
  three obligations explicitly (`:27-33`); the fourth and subtlest — *the permit must be held until
  the future genuinely completes, not until the wait is abandoned* — lives in the implementation
  (`§5.6`, `§10.3`). An implementation that releases on timeout reports free capacity that does not
  exist. **⚠ DRIFT:** `shutdown()` is now declared (`:104-114`) and `IObservable` is inherited
  (`:22`).
- **Future trajectory:** **Leaves untouched.** No §15 capability changes execution semantics.
- **Metaphor candidate:** The rule that only N inspections may be open at once, and that a booth
  stays counted as occupied until the officer actually finishes — not until the traveller gives up
  waiting.

### libs/congine-sdk/src/congine_core/ports/contract_repository.py
- **Layer / status:** L1 · active
- **One-line identity:** `IContractRepository` — `fetch_active_contracts` (async), `load_snapshot`,
  `save_snapshot`.
- **Why it exists:** So the sync workflow is identical whether contracts come from a control plane,
  a mounted directory, or a test fake.
- **Deletion test:** `sync_contracts_usecase.py` and `dependency_injection.py` fail to import.
  Boot has no contract source abstraction; the standalone/air-gapped topology becomes impossible
  without editing L3.
- **Load-bearing detail:** The obligations are almost entirely about **error typing**, and they are
  not visible in the signature. `fetch_active_contracts` must raise **only** `CongineSyncError` for
  expected failure — `_fetch_sync` catches exactly that type, so any other exception escapes the
  use case, escapes `bootstrap()`, and turns a transport hiccup into a boot crash (`§5.2`).
  `load_snapshot` must return `None` rather than `[]` when unusable, because `_apply` treats any
  falsy value as "retain current cache". `snapshot_lock_path` is an **optional property**, probed
  with `getattr` — absent means single-flight silently degrades.
- **Future trajectory:** **Leaves untouched.** §15.6's architectural graph is a sibling workflow
  with its own persistence, not a contract source.
- **Metaphor candidate:** The two ways regulations reach the booth — a wire from the capital, and
  the last printed edition in the drawer.

### libs/congine-sdk/src/congine_core/ports/logger.py
- **Layer / status:** L1 · active
- **One-line identity:** `ILogger` — four level methods taking a message plus arbitrary `**kwargs`.
- **Why it exists:** So every layer can log without importing a logging concrete, and so tests can
  capture log records structurally.
- **Deletion test:** Both use cases, `http_contract_repository`, `file_contract_repository`,
  `queue_event_bus` and `background_sync` fail to import — the widest fan-in of any port.
- **Load-bearing detail:** The unstated obligation is the dangerous one: **must never raise, on any
  input**. It is called from the hot path, from three daemon threads, and from inside `except`
  blocks (`§5.4`). A logger that raises inside an `except` block replaces a handled failure with an
  unhandled one. `StructuredLogger` satisfies this via `json.dumps(..., default=str)`.
- **Future trajectory:** **Leaves untouched.**
- **Metaphor candidate:** NONE — a logger is a logger.

### libs/congine-sdk/src/congine_core/ports/semantic_validator.py
- **Layer / status:** L1 · active
- **One-line identity:** `ISemanticValidator` — one method returning a flat list of `BreachDetail`.
- **Why it exists:** So `CompositeValidator`, which lives in L2, can hold a full JSON Schema
  validator without the domain importing `jsonschema`. This is the seam that keeps L2 pure.
- **Deletion test:** `domain/validator.py`'s `TYPE_CHECKING` import breaks under a type checker
  (not at runtime — the edge is guarded). `CompositeValidator` loses its type contract but keeps
  working, which is exactly the point of the guarded edge.
- **Load-bearing detail:** This port is named by L2 **under `TYPE_CHECKING` only**
  (`domain/validator.py:30-31`) — one of the two outward edges that make the hexagon work
  (`§4.3`). Reclassify it as a runtime import and the domain depends on `ports/`. Its obligations
  include one that reads as a bug elsewhere: *must tolerate a non-dict payload*, because
  `CompositeValidator` calls it even after the rule validator has already rejected a non-dict root
  (`§5.5`, debt D7 — **still present** at `domain/validator.py:519`).
- **Future trajectory:** **Leaves untouched.**
- **Metaphor candidate:** The specialist consultant the inspector may call in — reached by
  telephone number, never employed at the booth.

### libs/congine-sdk/src/congine_core/ports/circuit_breaker.py
- **Layer / status:** L1 · active
- **One-line identity:** `ICircuitBreaker` — `state`, `allow`, `record_success`, `record_failure`.
- **Why it exists:** So the sync use case can fast-fail a dead control plane without importing a
  breaker concrete, and so the same breaker instance can be shared with the telemetry bus.
- **Deletion test:** Nothing fails at runtime — both consumers name it under `TYPE_CHECKING` only
  (`sync_contracts_usecase.py:36`, `queue_event_bus.py:31`). A type checker fails; the process runs.
  This is the least load-bearing port at runtime and the most load-bearing at review time.
- **Load-bearing detail:** Two obligations that a new implementer must decide deliberately.
  `allow()` in HALF_OPEN must admit **exactly one** probe (FIX-11) or the moment cooldown elapses
  every caller floods a recovering plane. And **reading `state` may mutate state** — it can
  transition OPEN→HALF_OPEN, so an operator polling `health()` can move the breaker out of OPEN
  (`§5.7`). Harmless, genuinely surprising.
- **Future trajectory:** **Leaves untouched.**
- **Metaphor candidate:** The decision to stop telephoning the capital after five unanswered calls,
  and to try exactly one call — not all of them — when enough time has passed.

---

## L2 — Domain (4 files)

### libs/congine-sdk/src/congine_core/domain/__init__.py
- **Layer / status:** L2 · active
- **One-line identity:** Aggregate re-export of the four value objects, the rule engine, both
  validators, `IValidator`, and `find_unenforced_keywords`.
- **Deletion test:** `congine_core/__init__.py` fails to import. Internal consumers import the
  specific modules, so only the package surface breaks.
- **Load-bearing detail:** It re-exports `IValidator` (`:16`) but the package `__all__`
  deliberately does **not** — the in-domain strategy seam is intentionally not public (`§5.8`).
  Its comment at `:29-31` carries the P0-2/Q4 rule: every path that writes a schema into
  `ISchemaStorage` must call `find_unenforced_keywords`.
- **Why it exists / Future trajectory / Metaphor:** Table of contents; **leaves untouched**; NONE.

### libs/congine-sdk/src/congine_core/domain/models.py
- **Layer / status:** L2 · active
- **One-line identity:** The four frozen value objects — `BreachDetail`, `ValidationResult`,
  `DriftResult`, `TelemetryEvent` — that carry every piece of data in the system.
- **Why it exists:** Every one of these objects is created on one thread and read on another.
  Freezing them removes an entire class of race without a single lock — which is why there is no
  defensive copying anywhere in the codebase.
- **Deletion test:** `domain/validator.py`, both use cases, `jsonschema_validator`, `ks_drift` and
  `dependency_injection` all fail to import. Nothing in the system has a return type. Total.
- **Load-bearing detail:** The single most important thing for a consumer: **a caller that reads
  only `is_pass()` cannot distinguish "the contract was violated" from "the validator crashed and
  nothing was checked."** That distinction lives exclusively in `degraded`/`degraded_reason`
  (`§11.2`). Structurally: `ValidationResult.breaches` is a **tuple**, so the object is deeply
  immutable; `TelemetryEvent.breach_details` is a **list**, so its freeze is shallow and the object
  is not hashable (`§11.5`). **Debt D5 still present** — the module docstring at `:5` still claims
  `TelemetryEvent` "is mutable to allow post-init defaulting"; `:74` is `@dataclass(frozen=True)`.
- **Future trajectory:** **Touched** by §15.3 (extended `TelemetryEvent` — additive defaulted
  fields, backward-compatible because every construction site uses keyword arguments) and §15.5
  (`correction_hint` on `BreachDetail`). These are the two §15 items that cannot be done without
  editing L2.
- **Metaphor candidate:** The carbon-copy forms — once written and torn off, the copy cannot be
  altered by anyone who later handles it.

### libs/congine-sdk/src/congine_core/domain/validator.py
- **Layer / status:** L2 · active — **the file whose correctness the product sells**
- **One-line identity:** `RuleEngine`'s six pure static rules, the `IValidator` seam, and the two
  validators (`LocalValidator`, `CompositeValidator`) that compose them.
- **Why it exists:** This is the deterministic core. Everything else in the codebase exists to make
  this file's execution safe under load, failure and attack.
- **Deletion test:** `validate_contract_usecase.py` and `dependency_injection.py` fail to import.
  Nothing validates anything. If it were instead replaced by a stub returning `status="pass"`,
  every structural test would still pass and the product would silently do nothing — which is the
  failure mode the whole system is built to prevent.
- **Load-bearing detail:** **⚠ DRIFT — the single largest divergence in this document.** `§13.6`
  and debt **D18** describe a union `type` (`{"type": ["string","null"]}`) as raising `TypeError`
  and degrading every validation against that contract permanently. **That is fixed.**
  `_type_matches` (`:91-122`) now recurses over a union and returns true if any member matches;
  `"null"` was added to `_JSON_TYPE_MAP` (`:59`); `_type_label` (`:79-88`) renders a union as
  `'string|null'` rather than a Python list repr. Verified executed in GAP3 §3.6.
  Still true and still important: `pattern` is `fullmatch`, not a search (`:337`); dot-notation
  works in `FIELD_PRESENCE` only (`_path_present`, `:63-76`) and in no other rule (debt D16, still
  present); an unrecognised type name is **not** a breach, it disables type checking for that field
  (`:113-115`) — and by the new union rule, a union containing an unrecognised name therefore
  matches *everything* (`:104` states this explicitly).
- **Future trajectory:** **Touched** by §15.5 — `correction_hint` requires editing every
  `BreachDetail` construction site, and there are seven in this file alone (six rules, with
  `REGEX_PATTERN` having four distinct messages, plus the non-dict-root breach). **Not touched** by
  anything else: `§15` states plainly that nothing requires modifying `RuleEngine`.
- **Metaphor candidate:** The inspector reading the regulation line by line — six checks in a fixed
  order, no discretion, the same verdict for the same traveller every time.

### libs/congine-sdk/src/congine_core/domain/schema_vocabulary.py
- **Layer / status:** L2 · active
- **One-line identity:** A deliberate *mirror* of what the rule engine actually reads, exposing
  `find_unenforced_keywords(schema)` so callers can detect contract keywords that will be silently
  ignored.
- **Why it exists:** Under default configuration the rule engine reads eight schema keywords and
  ignores everything else. A user writing `{"minLength": 10}` sees `status="pass"` and has no
  enforcement and no indication of that fact. This module turns that silent failure into an
  observable warning (audit F-2 / P0-2).
- **Deletion test:** `sync_contracts_usecase.py` and `domain/__init__.py` fail to import. If it
  were instead stubbed to return `[]`, **nothing would fail** — and the only signal a user gets
  that part of their contract is decorative would be gone. Second only to `pii_sanitize.py` in
  danger-per-quietness.
- **Load-bearing detail:** It uses **allowlist** semantics (`:118`) — anything not enforced and not
  metadata is reported — so keywords nobody thought to blocklist are still caught as JSON Schema
  evolves. It is **deliberately non-recursive** (`:120-126`): a nested subtree is reported once at
  its parent, because the whole subtree is unenforced either way, so descending would add noise not
  information. It **deliberately does not import `validator`** (`:11-12`); the duplication is the
  cost and `tests/unit/test_schema_vocabulary.py` is what makes the cost payable.
  **⚠ DRIFT:** `RECOGNISED_TYPE_NAMES` now includes `"null"` (`:76`) and `_type_is_enforceable`
  (`:96-110`) accepts well-formed unions, tracking the Q2 fix. A correct union is no longer
  reported.
- **Future trajectory:** **Touched** by §15.1, §15.9 and any new loader — its own docstring
  (`:14-27`) states the rule that every schema writer must call it, now enforced by
  `test_every_schema_writer_scans_for_unenforced_keywords`.
- **Metaphor candidate:** The notice pinned beside the regulations listing which clauses this booth
  is not equipped to check — the traveller still passes, but is told what was not inspected.

---

## L3 — Use cases (3 files)

### libs/congine-sdk/src/congine_core/usecases/__init__.py
- **Layer / status:** L3 · active
- **One-line identity:** Aggregate re-export of the two use cases.
- **Deletion test:** `congine_core/__init__.py` fails. Nothing else imports it.
- **Load-bearing detail:** Its docstring is stale — it says L3 depends on "repositories (Layer 1),
  domain (Layer 2), and the timer utility"; the timer utility is the deprecated `ValidationTimer`,
  which L3 has not named since audit D-4 introduced `IValidationRunner`.
- **Why it exists / Future trajectory / Metaphor:** Table of contents; **touched** by §15.4
  (`HistoryQueryUseCase`); NONE.

### libs/congine-sdk/src/congine_core/usecases/validate_contract_usecase.py
- **Layer / status:** L3 · active — **the hot path**
- **One-line identity:** The orchestrator that turns a payload and a contract id into a
  `ValidationResult`, publishes telemetry, and applies the fail mode. Sync and async twins.
- **Why it exists:** Someone has to own the *sequence* — size guard, schema resolve, size guard,
  timed execution, telemetry, enforcement — and the error and degradation policy for each step.
  Putting that in the domain would make the domain do I/O; putting it in the adapter would
  duplicate it per entry point.
- **Deletion test:** `dependency_injection.py` fails to import; `container.validate_contract_usecase`
  does not exist, so `guard.py:79` and `langchain_handler.py:97` both `AttributeError` on every
  call. Every guarded function in the host application breaks at call time, not import time.
- **Load-bearing detail:** Two orderings in this file are load-bearing and non-obvious. **Telemetry
  is published (`:225`) before `_handle_failure` (`:228`) raises under strict mode** — so a
  compliance deployment never loses the record of the violation that stopped it (guarantee G9,
  `§14.8`). And **`_resolve_schema` raises before any fail-mode logic is consulted** (`:161-165`) —
  so a missing contract fails closed in *all three* modes; `silent` cannot suppress it (G10).
  Note also `except CongineBaseException: raise` (`:77-78`) sits *between* the resource-error and
  generic handlers, deliberately re-raising SDK exceptions rather than degrading them.
  Still present: `_check_payload_size` sets `size = 0` when `json.dumps` fails (`:128-129`), so an
  unserialisable payload **bypasses the bound entirely** (debt D6).
- **Future trajectory:** **Touched** by §15.3 — this is the only construction site of
  `TelemetryEvent` on the hot path, and it has access to `contract_id`, `contract_version` and the
  result and *nothing else*; it does not hold the config. `§15.3` names this as "the one place where
  'no L3 change' is not achievable." Also touched by §15.5 (`_finalize`'s breach serialisation at
  `:216-223` hard-codes `{rule, field, message}`).
- **Metaphor candidate:** The duty officer's checklist — weigh, fetch the regulation, weigh the
  regulation, inspect under a stopwatch, file the report, *then* decide whether to turn the
  traveller back.

### libs/congine-sdk/src/congine_core/usecases/sync_contracts_usecase.py
- **Layer / status:** L3 · active
- **One-line identity:** The boot/sync orchestrator — fetch contracts, prime the cache, persist a
  snapshot, warn about unenforced keywords. Sync and async twins, with single-flight boot.
- **Why it exists:** The hot path must never fetch. Something off the hot path has to get schemas
  into the cache and decide what happens when the control plane is unreachable.
- **Deletion test:** `dependency_injection.py` and `background_sync.py` (TC) fail to import.
  `bootstrap()` disappears, so the cache is never primed and **every** guarded call raises
  `CongineContractNotFoundError` — the loudest possible failure, by design (G10).
- **Load-bearing detail:** The degradation policy is the whole point and it is expressed in two
  lines. `_apply` returns early on falsy contracts (`:242-244`) and `_prime_cache` updates keys
  **in place** rather than clear-then-refill (`:257-271`) — together these mean a dead control
  plane, a corrupt snapshot and a poisoned snapshot are all **incapable of blanking a healthy
  cache**, and there is no window during a successful sync where a concurrent `get` sees a
  partially-empty cache (guarantee G8, `§14.8`). Also: this file performs filesystem I/O directly
  via `portalocker` (`:174-198`) — `§3.4` calls it "the single most arguable file placement in the
  system", a purity violation rather than a layer violation.
- **Future trajectory:** **Touched** by §15.1/§15.9 indirectly — `_warn_unenforced_keywords` is
  called only from `_prime_cache` (`:270`), so every new loader must call the scan itself
  (debt D17 / Q4, now enforced by test rather than by structure).
- **Metaphor candidate:** The courier run to the capital — one runner per host takes the road
  (the boot lock), the others read the drawer copy; and the drawer is never emptied before the new
  edition arrives.

---

## L4 — Infrastructure (13 files)

### libs/congine-sdk/src/congine_core/infrastructure/__init__.py
- **Layer / status:** L4 · active
- **One-line identity:** Aggregate re-export of eleven concretes — deliberately **excluding**
  `ValidationTimer`.
- **Deletion test:** `congine_core/__init__.py` fails.
- **Load-bearing detail:** The exclusion is the content. Its comment (`:22-25`) states that wiring
  `ValidationTimer` directly "defeats the load-shedding / async-symmetric guarantees" (audit
  D-3/D-11). This file is how a deprecation is enforced without deleting code.
- **Why it exists / Future trajectory / Metaphor:** Table of contents; **touched** by §15.2; NONE.

### libs/congine-sdk/src/congine_core/infrastructure/bounded_executor.py
- **Layer / status:** L4 · active
- **One-line identity:** `BoundedValidationExecutor` — a thread pool with a `BoundedSemaphore` that
  **sheds** load instead of queueing it, with sync and async entry points sharing one bound.
- **Why it exists:** Audit H1. A vanilla `ThreadPoolExecutor` has an **unbounded** work queue, and
  because a timed-out callable cannot be killed, a burst of slow validations fills every worker
  with zombies while submissions pile up — silently breaking the latency budget exactly under the
  load it was supposed to survive.
- **Deletion test:** `dependency_injection.py` fails to import. Structurally, guarantee G1
  (`§14.1`) has no mechanism: validations would either queue unboundedly or need a timeout
  implementation invented at the call site.
- **Load-bearing detail:** The subtlest correct thing in the codebase: **the permit is released
  only by the future's done-callback (`:174`), never in the timeout handler.** A timed-out caller
  abandons the *wait*, not the *permit* — so a zombie continues to occupy capacity for as long as
  it runs, and under sustained timeouts capacity **drains** and new work is shed rather than piled
  onto threads that are already stuck (`§10.3`). An implementation that released on timeout would
  report free capacity that does not exist. Second: sync and async both call the same
  `_acquire_and_submit` (`:103`, `:140`) — there is one semaphore, one pool, one bound, which is
  the substance of the H1/H2 closure. Third: `_local` is an *instance* attribute (`:53`), so the
  re-entrancy flag is per-executor — a worker of executor A calling into executor B is correctly
  treated as a non-worker by B.
- **Future trajectory:** **Leaves untouched.**
- **Metaphor candidate:** A fixed number of inspection bays. When all are occupied the next
  traveller is turned away at once rather than joining an invisible queue — and a bay stays marked
  occupied until the officer actually walks out of it, not when the traveller stops waiting.

### libs/congine-sdk/src/congine_core/infrastructure/lfu_cache.py
- **Layer / status:** L4 · active
- **One-line identity:** `LFUCache` — Ketan Shah's O(1) LFU algorithm plus per-entry TTL and a
  daemon sweeper.
- **Why it exists:** The hot path resolves a schema on every guarded call. That lookup must be O(1)
  regardless of how many contracts are cached, and stale schemas must expire without an O(n) scan.
- **Deletion test:** `dependency_injection.py` fails to import. Every validation would need its
  schema passed in by the caller, or would fetch — putting network I/O on the hot path.
- **Load-bearing detail:** Two deliberate non-obvious choices. The lock is an **`RLock`, not a
  `Lock`** — not because of re-entrant public calls but because `get`/`exists` call `_evict_key`
  while already holding it (`:91`, `:151`). And `_evict_key` **deliberately does not recompute
  `_min_freq`** (`:196-210`), which would be an O(n) scan on every TTL expiry; staleness is
  reconciled lazily in `_evict_lfu` (`:177-194`) off the hot path, and `put` resets `_min_freq` to
  1 anyway. That is audit M4 — a considered trade, not an oversight. Also: `capacity=0` **disables
  caching entirely** (`:110-111` makes `put` a no-op), which with G10 means every validation raises.
- **Future trajectory:** **Touched** by §15.1 if `ISchemaStorage` grows enumeration — the addition
  is backward-compatible for this class.
- **Metaphor candidate:** The rack of regulations at the booth, ordered by how often each sheet is
  consulted, with a clerk who walks past every thirty seconds pulling expired sheets.

### libs/congine-sdk/src/congine_core/infrastructure/circuit_breaker.py
- **Layer / status:** L4 · active
- **One-line identity:** A process-local CLOSED/OPEN/HALF_OPEN breaker guarding the control-plane
  boundary.
- **Why it exists:** Its own docstring gives the operational reason precisely: without it "a cold
  control plane can stall application boot up to 10s per attempt — long enough to trip Kubernetes
  liveness/readiness gates" (`:5-8`).
- **Deletion test:** `dependency_injection.py` fails to import. Guarantee G2 (`§14.2`) loses its
  mechanism: every boot against a dead plane pays a full HTTP timeout, and a persistently dead
  plane burns the full backoff window on every sync pass and every telemetry batch.
- **Load-bearing detail:** **One instance is injected into both `SyncContractsUseCase` and
  `QueueEventBus`** (`dependency_injection.py:298`, `:338`). Telemetry-ship failures therefore trip
  the breaker that gates contract fetches, and vice versa. This is deliberate — both are the same
  control plane — but it means a new implementation cannot assume a single caller (`§5.7`). Also:
  `record_failure` in HALF_OPEN goes **straight back to OPEN** (`:111-114`), it does not increment
  toward the threshold.
- **Future trajectory:** **Leaves untouched.** A distributed/Redis breaker is named in the
  docstring as Phase 2+ (`:19-22`).
- **Metaphor candidate:** The rule about telephoning the capital: after five unanswered calls stop
  dialling for half an hour, then permit exactly one test call.

### libs/congine-sdk/src/congine_core/infrastructure/logger.py
- **Layer / status:** L4 · active
- **One-line identity:** `StructuredLogger` — one JSON object per line to stdout, with a level
  threshold and two-stage redaction.
- **Why it exists:** Structured logs are the only observability surface the SDK ships. The
  redaction is why it is not just `print`.
- **Deletion test:** `dependency_injection.py` fails to import. Every component's `logger`
  parameter is `Optional`, so a stub would work — but guarantee G7's third layer (`§14.7`) would be
  gone silently.
- **Load-bearing detail:** Redaction is **two independent stages**: an unconditional blocklist
  (`api_key`, `authorization`, `x-api-key`, `payload`, `breach_details` — `:32-40`) that applies
  always, and an optional allowlist that replaces everything else. The allowlist is supplied by
  `config.effective_log_safe_fields()`, which turns it on automatically for non-local deployments
  (FIX-08) — so production gets PII-safe logging **without configuration**. It holds **no lock**,
  relying on one `print(..., flush=True)` per record; whole lines can interleave under extreme
  concurrency but individual JSON objects are not torn (`§10.7`). `_DEFAULT_SAFE_FIELDS` (`:27-29`)
  is defined and never referenced — dead (`§16.3`).
- **Future trajectory:** **Leaves untouched.**
- **Metaphor candidate:** The day book — every entry timestamped, with a standing instruction that
  certain columns are always inked out before the book leaves the building.

### libs/congine-sdk/src/congine_core/infrastructure/http_contract_repository.py
- **Layer / status:** L4 · active
- **One-line identity:** Fetches contracts from the control plane over HTTP and persists a
  scoped, atomic, permission-checked on-disk snapshot.
- **Why it exists:** The snapshot is what makes "boot succeeds with a dead control plane" true.
  The scoping and the permission checks are what make it safe on a shared host.
- **Deletion test:** `dependency_injection.py` fails to import. The default (control-plane)
  topology has no repository; only the file-based topologies remain usable.
- **Load-bearing detail:** Snapshot integrity is **five independent layers** (`§14.4`), and the
  least obvious is the two *different* lock files: `<snapshot>.lock` serialises writes, while
  `boot_<scope>.lock` (`:78-80`) coordinates single-flight boot — deliberately distinct "so boot
  coordination and write serialization do not contend" (`:75-77`). A writer that cannot acquire the
  write lock **skips** rather than blocking or raising (`:191-198`), because the sibling is writing
  the identical contracts. On load the file is refused if it is a symlink or not owned by the
  current user — but `_owned_by_current_user` returns `True` unconditionally off POSIX (`:248-249`),
  so **the ownership check is a no-op on Windows** (G4 is AT RISK there, `§14.4`).
- **Future trajectory:** **Leaves untouched.** `§15.7` names this file as the *template* for an
  agent adapter's input discipline — bound it, validate it, funnel every failure into one exception
  type.
- **Metaphor candidate:** The courier to the capital, plus the locked drawer holding the last
  printed edition — refused if the seal is broken or the handwriting is someone else's.

### libs/congine-sdk/src/congine_core/infrastructure/file_contract_repository.py
- **Layer / status:** L4 · active
- **One-line identity:** Reads contracts from a local directory (JSON always, YAML if `PyYAML`
  happens to be importable); snapshot methods are no-ops.
- **Why it exists:** The local-first / GitOps entry point — commit contracts to a repo, mount the
  directory, and the SDK never touches a network.
- **Deletion test:** `dependency_injection.py` fails to import. Both file topologies vanish; the
  air-gapped deployment shape becomes impossible.
- **Load-bearing detail:** `load_snapshot` returns `None` **by design** (`:122-124`) — the file
  source *is* the snapshot, so returning `None` forces a re-read next boot. It also deliberately
  omits `snapshot_lock_path`, which is why single-flight silently degrades to a plain `sync_once`
  in file mode. YAML support is genuinely optional and detected by a bare `try: import yaml`
  (`:86-89`) — the same directory yields different contracts depending on whether an unrelated
  package is installed, and nothing warns.
- **Future trajectory:** **Leaves untouched.**
- **Metaphor candidate:** Regulations kept in a filing cabinet at the booth rather than wired from
  the capital — nothing to fetch, nothing to cache, re-read each morning.

### libs/congine-sdk/src/congine_core/infrastructure/queue_event_bus.py
- **Layer / status:** L4 · active
- **One-line identity:** Bounded in-memory queue + daemon drain thread + batched POST + breaker
  gate + exponential backoff.
- **Why it exists:** Guarantee G11 — telemetry must never block or break the hot path. The queue is
  the mechanism that decouples "record this" from "send this".
- **Deletion test:** `dependency_injection.py` fails to import. With telemetry enabled there is no
  bus; the product loses its only outbound observability channel.
- **Load-bearing detail:** **No network call ever happens on the hot path** — `publish` is
  `put_nowait` + `except queue.Full` (`:99-116`) with no re-raise. The corollary is that telemetry
  is **not durable**: queue-full drops, retry-exhausted drops, breaker-OPEN drops and process death
  all lose events, visible only through `dropped_total`. The breaker gate (`:221-231`) discards a
  whole batch **without a network attempt**, so a persistently dead plane costs no backoff on the
  bus thread. Note the asymmetry at `:264-266`: the breaker records a failure only after the
  *entire* retry budget is exhausted — one batch consumes one breaker failure, not four.
  **Debt D4 still present:** `stop()` closes `_client` and nulls it (`:139-141`) after a 2 s join
  that can expire mid-`_ship`; `_ship` catches only `httpx.HTTPError` (`:256`), so a `RuntimeError`
  from a closed client escapes `_drain_loop` and kills the daemon with a stderr traceback.
- **Future trajectory:** **Touched** by §15.3 — `_serialize` (`:283-296`) hard-codes exactly six
  keys, so new `TelemetryEvent` fields are silently dropped from the wire until it is updated. It
  uses `getattr(..., None)` throughout, so it will not crash; it will just omit them, which is the
  quiet failure mode. Also the **template** for §15.2: `SqliteEventBus` is closer to "swap `_ship`'s
  POST for an INSERT" than to a from-scratch implementation.
- **Metaphor candidate:** The outbound mailbag — the inspector drops notes in and walks away; a
  courier empties it on a schedule, retries a failed delivery a few times, and burns the bag rather
  than let it slow the booth.

### libs/congine-sdk/src/congine_core/infrastructure/noop_event_bus.py
- **Layer / status:** L4 · active
- **One-line identity:** An `IEventBus` that discards everything — no thread, no socket, no queue.
- **Why it exists:** So `telemetry_enabled=false` removes a thread and a socket rather than merely
  suppressing sends. Air-gapped deployments and test suites incur genuinely zero overhead.
- **Deletion test:** `dependency_injection.py` fails to import. `telemetry_enabled=false` would have
  to be handled by branching inside `QueueEventBus`, putting a dead configuration path inside a
  threaded component.
- **Load-bearing detail:** It implements `queue_depth`, `dropped_total` and `stop` **purely for
  container symmetry** and says so in its own docstring (`:10-12`). Before `ports/lifecycle.py`
  existed, this file was the clearest evidence that the port declarations were incomplete rather
  than the container being over-eager (`§5.9`). It is now the template `§15.2` names for
  `SqliteEventBus`. Note `queue_depth()` is a constant `0` — not "0 because it drained".
- **Future trajectory:** **Leaves untouched.**
- **Metaphor candidate:** A mailbag with no bottom — deliberately, so nobody waits for a courier
  who is never coming.

### libs/congine-sdk/src/congine_core/infrastructure/jsonschema_validator.py
- **Layer / status:** L4 · active
- **One-line identity:** The `jsonschema`-backed `ISemanticValidator` — full JSON Schema
  enforcement, off by default.
- **Why it exists:** It is the answer to the eight-keyword limitation. Everything
  `schema_vocabulary` warns about is enforced when this is switched on.
- **Deletion test:** `dependency_injection.py` fails to import. `CONGINE_SEMANTIC_VALIDATION=true`
  becomes impossible, and with it the only remedy for the unenforced-keyword warning.
- **Load-bearing detail:** `_resolve_draft` is **fail-closed** (`:54-68`) — an unrecognised dialect
  raises `CongineConfigurationError` at **container construction**, not at validation. Because the
  container builds this object unconditionally (`dependency_injection.py:301`), a typo in
  `CONGINE_JSONSCHEMA_DRAFT` prevents process start **even for a deployment that never uses
  semantic validation**. Deliberate; asserted by `test_config_wiring.py`. Its output is bounded
  (`_max_breaches`, FIX-03) and every message is PII-sanitised at the source (`:114`, `:132`)
  because these strings reach telemetry. `validator_cls` (`:76`) is a test seam the container never
  passes.
- **Future trajectory:** **Leaves untouched.**
- **Metaphor candidate:** The specialist consultant — reads the whole regulation rather than the
  six checks, is expensive, and is only called in when the booth is told to.

### libs/congine-sdk/src/congine_core/infrastructure/ks_drift.py
- **Layer / status:** L4 · active but **wired to nothing**
- **One-line identity:** A two-sample Kolmogorov–Smirnov drift detector over a strictly bounded
  reference window.
- **Why it exists:** A library capability hanging off the container, not a component of the
  architecture. Nothing feeds it; the host must call `record_drift_sample()` by hand.
- **Deletion test:** `dependency_injection.py` fails to import. `record_drift_sample()` and
  `evaluate_drift()` disappear. **No other behaviour changes at all** — no pipeline is interrupted,
  because it is in no pipeline.
- **Load-bearing detail:** `numpy` is imported **lazily inside `detect()`** (`:31-46`), so
  constructing the engine and adding samples never require the `[stats]` extra — which is why the
  container can build it unconditionally for free. The reference window is a `deque(maxlen=...)`,
  so the bound is structural rather than checked. **Debt D15 still present:** `drift_detected` is
  `statistic > threshold` (`:131`) — the **D statistic**, not the p-value; `p_value` is computed
  and reported but never used in the decision, while the README describes the knob as a p-value
  threshold. The two have opposite directionality, so tuning by the documentation tunes backwards.
- **Future trajectory:** **Attaches beside** — `§15.8` notes the engine needs no change to serve
  adaptive routing; only a caller that feeds it. The `__drift__` telemetry event already flows
  through the normal bus, so drift signals land in a persistent store for free once §15.2 exists.
- **Metaphor candidate:** A tally of yesterday's traveller profiles kept in a drawer, compared by
  hand when someone thinks to — never consulted during an inspection.

### libs/congine-sdk/src/congine_core/infrastructure/background_sync.py
- **Layer / status:** L4 · active
- **One-line identity:** A daemon thread that calls `sync_once()` every `interval_seconds`.
- **Why it exists:** It is the *mechanism* that drives the sync *policy*. Separating them is what
  lets the policy be tested without a thread and the thread be replaced without touching policy.
- **Deletion test:** `dependency_injection.py` fails to import. Contracts are primed at boot and
  then never refreshed — a contract change at the control plane never reaches a running process
  until it restarts. Silent and slow to notice.
- **Load-bearing detail:** It is the **only L4 file that depends on L3**, and it does so under
  `TYPE_CHECKING` only (`:21-24`) — one of the two outward edges that make the hexagon work
  (`§4.3`). The conceptual direction is genuinely outward-driving-inward, which is what a scheduler
  is. Two behaviours matter operationally: `_safe_sync` swallows **every** exception except
  `KeyboardInterrupt`/`SystemExit` (`:86-97`) so one bad pass never kills the loop; and it calls
  `sync_once`, **not** `sync_once_single_flight` (`:89`) — the boot lock is a boot-time concern
  only, so steady-state fetches across N processes are uncoordinated by design (`§14.3`).
  `atexit.register` sits inside `start()` (`:66`), so it re-registers on every restart (debt D11).
- **Future trajectory:** **Leaves untouched.**
- **Metaphor candidate:** The standing order to send a courier to the capital every five minutes —
  and to carry on sending couriers even if one comes back empty.

### libs/congine-sdk/src/congine_core/infrastructure/timer.py
- **Layer / status:** L4 · **deprecated, unwired, never constructed — but tested**
- **One-line identity:** The predecessor of `BoundedValidationExecutor`: a plain thread pool with a
  timeout and no bounding.
- **Why it exists:** Retained for legacy reference. Its docstring is the clearest single statement
  of what `BoundedValidationExecutor` adds (`:3-10`).
- **Deletion test:** **Nothing in `src/` breaks.** No runtime edge reaches this file (`Appendix A`).
  Only `tests/unit/test_timer.py` (4 tests) fails — the suite protects code the container will
  never run. It is the one file whose deletion test is "nothing happens."
- **Load-bearing detail:** It is excluded from `infrastructure/__init__.py` **on purpose**
  (`:22-25`, audit D-3/D-11) and raises a `DeprecationWarning` on construction (`:39-44`). It is
  shape-compatible on `run_with_timeout` only — no `capacity`, no async twin, no `health`, no
  bounding — so wiring it would satisfy a naive duck-type check and silently void guarantee G1.
  That near-miss is exactly why the exclusion is enforced in code rather than in a comment.
- **Future trajectory:** **Leaves untouched.** A candidate for deletion, not extension.
- **Metaphor candidate:** The old booth left standing beside the new one, doors chained, kept so
  everyone can see what was wrong with it.

---

## L5 — Adapters (4 files)

### libs/congine-sdk/src/congine_core/adapters/__init__.py
- **Layer / status:** L5 · active
- **One-line identity:** Re-exports `ServiceContainer` and `congine_guard` eagerly;
  `CongineCallbackHandler` lazily via `__getattr__`.
- **Why it exists:** So `from congine_core.adapters import CongineCallbackHandler` works without
  `langchain-core` being installed for users who never touch it.
- **Deletion test:** `congine_core/__init__.py` fails.
- **Load-bearing detail:** The `__getattr__` (`:18-26`) is only meaningful because
  `langchain_handler.py` performs all its Congine imports *inside methods* — the laziness is a
  two-file collaboration, and breaking either half silently makes `langchain-core` a hard
  dependency of `import congine_core`.
- **Future trajectory:** **Touched** by §15.1 — `§15.1` explicitly prescribes exposing an MCP
  server through this same lazy `__getattr__` pattern.
- **Metaphor candidate:** NONE.

### libs/congine-sdk/src/congine_core/adapters/dependency_injection.py
- **Layer / status:** L5 · active — **the composition root**
- **One-line identity:** `ServiceContainer` — the sole construction site for all sixteen objects,
  plus lifecycle, the default singleton, the tenant registry, and drift/health surfaces.
- **Why it exists:** So "when X is configured, port Y is implemented by Z" is answerable by reading
  one function. Every other file can then name only abstractions.
- **Deletion test:** `guard.py` and `langchain_handler.py` fail to import, so both entry points
  die. Nothing in the system constructs anything — the object graph has no assembler. The layers
  survive as libraries; the product does not.
- **Load-bearing detail:** Construction order is **forced, not stylistic** (`§7.1`): logger first,
  breaker before bus, semantic validator before composite validator, use cases before the worker.
  Two things start daemon threads *inside* the constructor (`LFUCache`, `QueueEventBus`), so a
  later failure — realistically a bad `CONGINE_JSONSCHEMA_DRAFT` at `:301` — leaks two threads and
  two `atexit` hooks with no object returned to close them (debt D10, **still present**; the new
  `_arm_deferred_teardown()` at `:367` is explicitly the *last* statement and its comment at
  `:365-366` acknowledges the remaining gap).
  **⚠ DRIFT (three items):** (a) `get_default()` (`:81-111`) no longer calls `from_env()` on the
  cached path — it reads one variable via `_deployment_mode_is_multi_tenant()`, closing debt D8/Q10;
  (b) `_arm_deferred_teardown()` is now called at the end of **every** `__init__` (`:367`), not
  only on eviction, closing debt D3/Q5 — the eviction-time call at `:183` is now an idempotent
  no-op retained for clarity, and says so; (c) `max_contract_file_bytes` is passed to both
  `FileContractRepository` branches (`:270`, `:277`), closing debt D21/Q11.
  Still true: `_tenant_lock` is held across full `cls(config)` construction (`:185`), which starts
  threads — so `for_tenant()` calls for distinct new tenants fully serialise (`§10.2`).
- **Future trajectory:** **Touched** by every §15 capability that adds a component — §15.2 adds one
  branch at the bus selection, §15.4/§15.6/§15.7 each add a construction and an attribute. This is
  the file that absorbs the cost of the hexagon's flexibility.
- **Metaphor candidate:** The morning roster — the one document that says which officer staffs
  which booth today, written once before the gates open and never amended while they are open.

### libs/congine-sdk/src/congine_core/adapters/guard.py
- **Layer / status:** L5 · active
- **One-line identity:** `@congine_guard` — the decorator that is the product's entire public
  ergonomics, with three return modes and an optional extractor.
- **Why it exists:** So adopting Congine is one line above a function rather than a rewrite of that
  function's call sites.
- **Deletion test:** `adapters/__init__.py` and the package surface fail to import. Every user's
  code that says `@congine_guard(...)` fails at import. The most user-visible possible break.
- **Load-bearing detail:** **The decorated function runs first** (`:78`, `:89`) — Congine is an
  *output* firewall, not an input gate; the side effects of the guarded function have already
  happened by the time validation runs. Mode selection is resolved once at decoration and
  `inspect.iscoroutinefunction` picks the wrapper (`:101-103`), so the async path is chosen
  statically. Note `mode="raise"` raises **independently of `fail_mode`** (`:64-69`): they are two
  separate raise sites and both can fire for one call. With no explicit `container=`, `_resolve()`
  (`:57-58`) hits `get_default()` on **every** call — now cheap (one env var) since the Q10 fix,
  where it previously re-parsed ~47.
- **Future trajectory:** **Touched** by §15.3 if extended telemetry needs per-call context —
  `§15.3` notes that widening `execute()` "also touches `guard.py` and every caller."
- **Metaphor candidate:** The gate itself — the traveller has already packed and left the building;
  this is the last point at which anyone looks in the bag.

### libs/congine-sdk/src/congine_core/adapters/langchain_handler.py
- **Layer / status:** L5 · active, optional (gated on `[langchain]`)
- **One-line identity:** A LangChain callback handler that buffers streamed tokens per run and
  validates the assembled completion on `on_llm_end`.
- **Why it exists:** LangChain does not return a value a decorator can wrap; it emits callbacks. A
  second entry-point shape was needed for the framework that most of the target audience uses.
- **Deletion test:** Nothing in `src/` breaks — `adapters/__init__.py` reaches it only through
  `__getattr__`. LangChain users lose their integration; everyone else is unaffected.
- **Load-bearing detail:** It is the **reference implementation of "optional L5 adapter"** and
  `§15.1` prescribes copying it for MCP: module-level try/except for the dependency (`:8-16`),
  function-local Congine imports (`:38-40`, `:57`), a directed `ImportError` in the constructor
  (`:33-37`), and a multi-tenant guard (`:42-51`). The behavioural trap: `on_llm_end` swallows
  **every** exception including `CongineValidationError` from strict mode and
  `CongineContractNotFoundError` (`:105-119`) — so **`strict` mode is effectively neutralised on
  this surface**. Debt D13 still present: `_results` and `last_result` are written outside the lock
  (`:102-103`); `result_for(run_id)` is the race-free accessor.
- **Future trajectory:** **Leaves untouched**, but is the pattern §15.1 copies.
- **Metaphor candidate:** A second gate for travellers who arrive in pieces — the officer holds the
  bag open until the last item is handed over, then inspects the whole.

---

## DRIFT — where the code and `ARCHITECTURE_CURRENT.md` disagree

The code is ground truth. Every row below was verified against the tree at `49a2f93`.

| # | `ARCHITECTURE_CURRENT.md` says | Code at `49a2f93` | Evidence |
|---|---|---|---|
| 1 | 37 Python files, 31 impl modules, 5 075 lines (`§head`, `§2.1`) | **38 files, 32 impl modules, 5 473 lines** | `find`/`wc`; `ports/lifecycle.py` is new |
| 2 | `ports/` contains exactly seven modules (`§3.2`, `§15.1`) | **eight** (+ `lifecycle.py`) | `ports/lifecycle.py` |
| 3 | `CongineConfig` has exactly 46 fields (`§12`) | **47** (+ `max_contract_file_bytes`) | `dataclasses.fields()` = 47 |
| 4 | D18/Q2 — union `type` degrades every validation permanently (`§13.6`, `§16.2`) | **FIXED** — unions supported, `"null"` in type map | `domain/validator.py:91-122`, `:59` |
| 5 | D1/Q1 — `region` is read by nothing (`§12.4`) | **FIXED** — selects default `base_url` | `config.py:203-216`, `:46-50` |
| 6 | D14/Q8 — three ports under-declare their surface (`§5.9`) | **FIXED** — `IStoppable`/`IObservable` composed in | `ports/lifecycle.py`; `schema_storage.py:16,73`; `validation_runner.py:22,104`; `event_bus.py:61,69` |
| 7 | D8/Q10 — `get_default()` re-reads ~46 env vars per guarded call (`§7.6`) | **FIXED** — one variable on the cached path | `dependency_injection.py:98-116`; `config.py:186-201` |
| 8 | D3/Q5 — finalizer armed only on the eviction path (`§7.8` row 6) | **FIXED** — armed at end of every `__init__` | `dependency_injection.py:357-367` |
| 9 | D21/Q11 — `max_schema_bytes` is one knob with two meanings (`§16.2`) | **FIXED** — split into `max_contract_file_bytes` | `config.py:179`; `security_limits.py:22` |
| 10 | D2/Q7 — README documents 27 of 46 fields (`§12.5`) | **FIXED** — enforced by test | `tests/unit/test_readme_config_table.py` (new, 160 lines) |
| 11 | Q6 — Python floor contradicts itself four ways (`§17`) | **FIXED** — 3.11 in all four places | `pyproject.toml:6,18,72`; `.claude/CLAUDE.md` |
| 12 | Q3 — `null_forbidden` undocumented as an extension | **FIXED** — stated in the rule docstring | `domain/validator.py:263-281` |
| 13 | Q4 — P0-2 scan covers only the prime path (D17) | **PARTIALLY** — still only `_prime_cache`, but now test-enforced for new writers | `schema_vocabulary.py:14-27`; `sync_contracts_usecase.py:270` |
| 14 | Q9 — telemetry durability unresolved | **DECIDED** — recorded in the port docstring; no code change | `ports/event_bus.py:35-46` |
| 15 | Q12 — audit-ID trail's status undecided | **DECIDED** — maintained; `AUDIT_ID_INDEX.md` is canonical | `docs/architecture/AUDIT_ID_INDEX.md` |
| 16 | Test suite: 293 passed, 1 skipped, 34 files (`§head`) | **350 passed, 1 skipped, 35 files** | measured, GAP4 §4.1 |
| 17 | `§2.2` — P0-2 is uncommitted in the working tree | Committed in `49a2f93`; **working tree is clean** | `git status --short libs/` → empty |

**Debts that are NOT fixed and remain verified present at `49a2f93`:** D4 (`_client` stop race),
D5 (stale `TelemetryEvent` docstring), D6 (size guards measure encoded chars; unserialisable
payload bypasses the bound), D7 (`pii_sanitize` uses stdlib `re`), D9 (`LOCAL_CONTRACTS_DIR=""`),
D10 (mid-constructor thread leak), D11 (`atexit` never unregistered), D12
(`_warned_unenforced` unguarded), D13 (`last_result` outside the lock), D15 (`drift_threshold` is
the D statistic, README says p-value), D16 (dot-notation in one rule only), D17 (scan on the prime
path only), D19 (load shed indistinguishable from timeout), D20 (silent-`False` boolean parsing),
D22 (`contract_source` accepts anything), plus prior debts #1 (LangChain example enum mismatch),
#5, #6, #7, #9.
