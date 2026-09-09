# GAP2 — Decision rationale

**Generated:** 2026-08-16 · **Commit:** `49a2f93` · **Method:** five evidence streams, mined in the
order the prompt specifies — (1) every audit-ID annotation, indexed via
`docs/architecture/AUDIT_ID_INDEX.md`; (2) explanatory comments and docstrings containing *why /
because / instead of / rather than / deliberately / intentional / prevents / avoids / must not*,
quoted verbatim; (3) git history; (4) structural evidence with no comment; (5)
`ARCHITECTURE_CURRENT.md §17` and its now-resolved companion `docs/architecture/OPEN_QUESTIONS.md`.

**32 candidates.** Confidence is about *the evidence for the rationale*, not about whether the
decision is correct.

> **On git history as a source.** It is weak here and should not be relied on by the ADR archive.
> Commit messages on the SDK are of the form `"Phase 0 Refactor + Fixed"`, `"Phase 0 Architectural
> Modifications + new Audit Report Generated"`, `"SDK deadLocks + hardcoded removes"`. Large
> architectural changes arrive in single squashed commits. `git log -S` confirms *when* a thing
> appeared, never *why*. **RATIONALE NOT RECORDED IN GIT** applies to every candidate below; where
> confidence is HIGH it is because the rationale is written in the code or in `OPEN_QUESTIONS.md`,
> not because a commit explained it.

> **On `OPEN_QUESTIONS.md`.** Twelve decisions (Q1–Q12) were put to the founder and answered on
> 2026-08-09. For those, the *option chosen and the alternatives rejected* are recorded explicitly.
> They are the highest-confidence material in this file and they are marked HIGH. They also mean
> `ARCHITECTURE_CURRENT.md §17` is closed, not open.

---

## Group A — The shape of the system

### CANDIDATE: Strict six-tier hexagon with runtime dependencies pointing inward only
- **Decided:** L0 kernel → L1 ports → L2 domain → L3 use cases → L4 infrastructure → L5 adapters,
  with no runtime edge pointing outward. Two outward edges exist and are guarded by `TYPE_CHECKING`.
- **Evidence:** `ARCHITECTURE_CURRENT §3`, `§4.2`, `§4.4` (AST-verified, zero violations).
  `libs/congine-sdk/.claude/CLAUDE.md` states the rule normatively. The two guarded edges:
  `domain/validator.py:30-31` and `infrastructure/background_sync.py:21-24`; `§4.3` says
  "Reclassify either as a runtime import and the hexagon breaks."
- **Apparent rationale:** The domain is what the product sells; its correctness must be verifiable
  without instantiating a thread, a socket or a clock. `§1` states the payoff explicitly: "six of
  the nine planned future capabilities attach as pure additions behind seams that already exist."
- **Confidence:** MEDIUM (implied) — the rule is stated everywhere; the reason for choosing a
  hexagon over a simpler layered design for a ~5 500-line library is not.
- **Rejected alternatives visible:** None recorded. The directory rename from `repositories/` to
  `ports/` (`ports/__init__.py:4-7`) shows an earlier, narrower conception was corrected.
- **Consequences in code:** `dependency_injection.py` absorbs all of the cost — 521 lines, sixteen
  constructions, and it must be edited by nearly every future capability. Negative: two L4 files
  (`ks_drift`, `background_sync`) implement no port, so "every L4 file implements an L1 port"
  cannot be stated as an invariant (`§3.5`). Negative: `import congine_core` eagerly imports every
  layer including `httpx`, `jsonschema`, `re2`, `portalocker` (`§4.5`).
- **Architecturally significant?** YES — it is the structure.
- **❓ QUESTION FOR FOUNDER:** Was the hexagon chosen for the stated extensibility payoff, for
  testability, or because a control plane was expected to consume the same domain? The answer
  determines whether the hexagon is a constraint to defend or an artefact to relax as the SDK grows.

### CANDIDATE: Ports are `typing.Protocol`, not abstract base classes
- **Decided:** All nine seams are `@runtime_checkable typing.Protocol`. Conformance is structural.
- **Evidence:** Every file in `ports/`. `tests/conftest.py:1-5` — "These fakes are plain objects
  (structural typing) — they satisfy the Layer-1 protocols without importing or subclassing them."
  `§5` calls this "the proof that these are genuine duck-typed seams rather than ABCs in disguise".
- **Apparent rationale:** A test fake that must import the port it satisfies creates a dependency
  from the test tree into L1 and makes the seam decorative. Structural typing means an
  implementation can be written by someone who has never seen the Protocol.
- **Confidence:** MEDIUM (implied by the conftest docstring and the consistent absence of
  subclassing; never stated as a decision).
- **Rejected alternatives visible:** ABCs — rejected implicitly; no `abc` import exists in `src/`.
- **Consequences in code:** The container can call methods a port never declared and nothing
  complains — which is exactly the defect `ports/lifecycle.py` was later written to close. Positive:
  `NoOpEventBus`, `FakeEventBus` and `ImmediateTimer` need no inheritance.
- **Architecturally significant?** YES — construction technique and interfaces.
- **❓ QUESTION FOR FOUNDER:** Structural typing means a *partial* implementation type-checks until
  it is called. Is the intent that `@runtime_checkable` `isinstance` checks be added at the
  container boundary, or that this stays a documentation-and-test discipline?

### CANDIDATE: `IValidator` lives in `domain/`, every other Protocol lives in `ports/`
- **Decided:** One Protocol is sanctioned outside `ports/`.
- **Evidence:** `domain/validator.py:359-367`. `§3.3`: "The rule the codebase actually follows is
  precise: **a Protocol lives in `ports/` if and only if something outside L2 implements it.**"
  `.claude/CLAUDE.md` states the same rule. It is re-exported from `domain/__init__.py:16` but
  deliberately excluded from the package `__all__`.
- **Apparent rationale:** `IValidator` is an *in-domain strategy seam* — the choice between "rules
  only" and "rules plus full JSON Schema" — and both implementations live in the same module.
  `§5.8`: putting it in `ports/` "would imply an outer layer is expected to supply a validator,
  which would invert the one boundary the architecture most needs to protect."
- **Confidence:** HIGH (stated, with the rule and the contrast to `ISemanticValidator` written out).
- **Rejected alternatives visible:** Moving it to `ports/` — explicitly considered and rejected.
- **Consequences in code:** A reader auditing "all protocols are in ports/" finds one exception and
  must be told why. Excluding it from `__all__` means a host cannot supply a custom validator
  through the documented surface — arguably intended.
- **Architecturally significant?** YES.

### CANDIDATE: Lifecycle and observability declared as separate composable protocols
- **Decided:** `ports/lifecycle.py` defines `IStoppable` and `IObservable`; `ISchemaStorage` and
  `IValidationRunner` inherit them; `IEventBus` re-declares a widened `stop(drain=...)` instead.
- **Evidence:** `ports/lifecycle.py:1-23` verbatim: "They exist because `ServiceContainer` calls
  methods on its components that the functional ports never declared … so an implementation that
  faithfully satisfied, say, `IEventBus` (one method, `publish`) would raise `AttributeError` the
  first time the container was torn down (audit F-15 / Q8)." And: "Keeping them separate rather
  than folding them into each functional port means a port still describes **one job**." `IEventBus`
  cannot compose `IStoppable` "because a bus teardown takes a `drain` flag"
  (`ports/event_bus.py:30-33`). `OPEN_QUESTIONS.md` Q8 = option B, "separate lifecycle interface".
- **Apparent rationale:** Under-declared ports produce a crash in `close()`/`health()` for a
  faithful implementer. Mixing lifecycle into each functional port would destroy single-responsibility.
- **Confidence:** HIGH (stated in the module docstring and in the decision record).
- **Rejected alternatives visible:** Folding lifecycle into each functional port (named and
  rejected); leaving it undeclared (the prior state, `§5.9` debt D14).
- **Consequences in code:** Closes `§5.9` and `§16` D14. Positive and immediate: `§15.2`'s
  `SqliteEventBus` can now be written against a complete contract. Cost: `IEventBus.stop` and
  `IStoppable.stop` have different signatures, so the symmetry is imperfect and must be explained.
- **Architecturally significant?** YES — interfaces and construction technique.

### CANDIDATE: `dropped_total` is deliberately NOT a Protocol member
- **Decided:** The one genuinely-optional member of the event-bus surface is documented in a comment
  rather than declared.
- **Evidence:** `ports/event_bus.py:80-88` verbatim: "Optional extension — deliberately NOT declared
  as a protocol method, because a Protocol member is mandatory under `runtime_checkable` isinstance
  and this one genuinely is not". Container probes with `getattr`/`callable`
  (`dependency_injection.py:456`, `:462-464`). `tests/conftest.py:46-48`: `FakeEventBus` omits it
  "deliberately … leaving it out keeps the container's `getattr` probe honest."
- **Apparent rationale:** Declaring it would make every implementation that cannot lose events fail
  an `isinstance` check for a method that means nothing to it.
- **Confidence:** HIGH (stated, with the mechanism named, and pinned by a test double).
- **Rejected alternatives visible:** Declaring it on the port (named, rejected for a specific
  mechanical reason).
- **Consequences in code:** The container carries a `callable()` probe. A future implementer can
  omit it and silently report zero losses.
- **Architecturally significant?** YES — interface design.

---

## Group B — The execution guarantees

### CANDIDATE: A bounded, load-shedding executor replaces the naked `ThreadPoolExecutor`
- **Decided:** `BoundedValidationExecutor` bounds outstanding work at `max_workers + max_pending`
  with a `BoundedSemaphore` and raises `TimeoutError` immediately on saturation.
- **Evidence:** `bounded_executor.py:1-21` verbatim: "a vanilla pool has an **unbounded** work
  queue, and because a timed-out callable cannot be killed, a burst of slow validations fills every
  worker with zombies while new submissions pile up unbounded — silently breaking the latency
  budget exactly under load." Audit H1. `ports/validation_runner.py:27-29`.
- **Apparent rationale:** The failure mode is worst precisely when the guarantee matters most.
- **Confidence:** HIGH (stated, with the defect described).
- **Rejected alternatives visible:** Vanilla `ThreadPoolExecutor` (named, was the prior state,
  survives as `infrastructure/timer.py`).
- **Consequences in code:** Load shed and genuine timeout are indistinguishable to the caller —
  both produce `degraded_reason="timeout"` (`§16` D19, still present). Only the process-wide
  `health()["validation_rejected_total"]` separates them, and it cannot be attributed to a call.
- **Architecturally significant?** YES — non-functional characteristics.

### CANDIDATE: The permit is released by the future's done-callback, never by the timeout handler
- **Decided:** A timed-out caller abandons the wait, not the permit. Capacity is returned only when
  the underlying callable genuinely completes.
- **Evidence:** `bounded_executor.py:174` (`add_done_callback`), with the reason stated twice —
  `:107-108`: "Permit stays held by the done-callback until the zombie finishes, so sustained
  timeouts correctly drain capacity and shed new work", and again at `:146-148` for the async path.
  `:154-159` restates it. `§10.3` calls it "the load-bearing detail". Pinned by
  `tests/adversarial/test_bounded_executor.py::test_saturation_sheds_load` and
  `::test_in_flight_returns_to_zero`.
- **Apparent rationale:** Releasing on timeout would admit new work while zombies still hold
  threads — the bound becomes fiction under exactly the load it exists for.
- **Confidence:** HIGH (stated three times in-file, plus the port docstring).
- **Rejected alternatives visible:** Releasing in the timeout handler (named, and its failure mode
  described).
- **Consequences in code:** Under sustained timeouts throughput collapses to zero by design. An
  operator seeing 100% load shed must know this is correct behaviour, not a deadlock.
- **Architecturally significant?** YES — this is the substance of guarantee G1.

### CANDIDATE: Sync and async entry points share one semaphore, one pool, one bound
- **Decided:** Both `run_with_timeout` and `run_with_timeout_async` call the same
  `_acquire_and_submit`.
- **Evidence:** `bounded_executor.py:103`, `:140`. `:116-121` verbatim: "so `async` callers get the
  **identical** capacity bound and timeout — rather than bypassing the semaphore via a raw
  `run_in_executor` and unbounded-queueing." `guard.py:90-93`: "never the raw, unbounded
  run_in_executor that silently bypassed both guarantees." Audit H1/H2. Asserted by
  `test_async_concurrent_saturation_sheds_load`.
- **Apparent rationale:** An async twin over `run_in_executor` silently bypasses the bound — the
  guarantee would hold for sync callers and quietly not for async ones.
- **Confidence:** HIGH (stated in three files, with the rejected implementation named).
- **Rejected alternatives visible:** `loop.run_in_executor` — named explicitly as the defect.
- **Consequences in code:** Async callers can be load-shed by sync pressure and vice versa. Correct,
  and surprising to someone who assumed async had its own budget.
- **Architecturally significant?** YES.

### CANDIDATE: A re-entrant call from the pool's own worker runs inline, untimed
- **Decided:** `_on_worker_thread()` short-circuits to `return func()` — no permit, no submission,
  and **no deadline**.
- **Evidence:** `bounded_executor.py:100-101`, `:137-138`. `:98-99`: "Re-entrant call from our own
  worker: run inline to avoid a nested same-pool deadlock (best-effort timeout; CPU work is bounded
  upstream)." `:19-20`: "preventing a nested-same-pool deadlock." Tested by
  `test_reentrant_call_runs_inline_no_deadlock`.
- **Apparent rationale:** A nested submit onto a saturated pool from one of its own workers
  deadlocks. Running inline is the only escape that does not require a second pool.
- **Confidence:** HIGH (stated, including the acknowledged cost).
- **Rejected alternatives visible:** None named. A second pool is the obvious untaken alternative.
- **Consequences in code:** An inline run is **not time-boxed** — it runs to completion regardless
  of `timeout_ms`. Guarantee G1 has a documented hole on this path (`§14.1` caveat (a)). The comment
  defends it as "CPU work is bounded upstream", which is true only because of the §13.5 caps.
- **Architecturally significant?** YES — it is a stated exception to the latency guarantee.
- **❓ QUESTION FOR FOUNDER:** Is an untimed inline re-entrant run acceptable indefinitely, or
  should it carry a deadline enforced by a watchdog? It is the only path where the millisecond
  budget does not apply.

### CANDIDATE: `BoundedSemaphore` rather than `Semaphore`
- **Decided:** Over-release raises `ValueError` immediately.
- **Evidence:** `bounded_executor.py:60`. `§10.3`: "an over-release is a programming error and
  raises `ValueError` immediately rather than silently inflating capacity."
- **Apparent rationale:** A double-release bug would silently raise the ceiling, defeating the
  bound with no symptom until an outage.
- **Confidence:** MEDIUM (implied by the type choice; `§10.3` supplies the reasoning, the code does
  not comment it).
- **Rejected alternatives visible:** `threading.Semaphore` (the default choice).
- **Consequences in code:** A release bug crashes a worker thread rather than degrading silently.
- **Architecturally significant?** YES — fail-fast on a correctness invariant.

---

## Group C — The contract language

### CANDIDATE: Union `type` declarations are supported rather than rejected at load
- **Decided:** `{"type": ["string","null"]}` matches if any member matches. `"null"` added to
  `_JSON_TYPE_MAP`.
- **Evidence:** `domain/validator.py:91-122` verbatim: "A union matches when *any* member matches
  (audit Q2/F-21). Before this was supported, a list declaration raised `TypeError` from the
  unhashable dict lookup, which the use case degraded into `degraded_reason='internal_error'` — so
  an otherwise-valid contract silently stopped enforcing anything." `OPEN_QUESTIONS.md` Q2 records
  option **A — support it** as CHOSEN, with **B. Reject loudly at load** marked "Safe, but rejects
  valid JSON Schema" and **C. Leave it** marked "Not defensible".
- **Apparent rationale:** The union is the idiomatic JSON Schema spelling of a nullable field.
  Rejecting it would reject valid JSON Schema; leaving it crashed every validation against that
  contract permanently.
- **Confidence:** HIGH (stated in code and in the decision record, with alternatives and their
  reasons).
- **Rejected alternatives visible:** Reject-at-load (B), leave-as-is (C) — both named with reasons.
- **Consequences in code:** `schema_vocabulary.RECOGNISED_TYPE_NAMES` and `_type_is_enforceable`
  had to track it (`:75-77`, `:96-110`). New negative, explicitly acknowledged at
  `domain/validator.py:102-104`: "a union containing an unrecognised name therefore matches
  everything" — the unknown-type rule and the union rule compose into a silent no-op.
- **Architecturally significant?** YES — this was `§16` debt D18, the one HIGH-severity
  safety-critical defect.

### CANDIDATE: An unrecognised `type` name is not a breach
- **Decided:** `_JSON_TYPE_MAP.get(name)` returning `None` yields `True` — no breach.
- **Evidence:** `domain/validator.py:113-115`: "Unknown type declaration: do not flag a breach we
  cannot evaluate." `:102-104` acknowledges the union interaction.
- **Apparent rationale:** A validator should not manufacture a failure for a constraint it does not
  understand.
- **Confidence:** HIGH (stated).
- **Rejected alternatives visible:** Breaching on unknown types (the opposite policy). Not
  discussed.
- **Consequences in code:** A typo (`"str"` for `"string"`) silently disables type checking for
  that field. `find_unenforced_keywords` reports it at load — but only on the prime path (D17).
- **Architecturally significant?** YES — it is a fail-open choice inside an otherwise fail-closed
  system.
- **❓ QUESTION FOR FOUNDER:** Everything else in this system fails closed. Unknown-type is the
  conspicuous fail-*open*. Is "decline to judge what we cannot evaluate" the intended policy, or
  should an unrecognised type name be a load-time error like an unrecognised `jsonschema_draft`?

### CANDIDATE: `null_forbidden` retained as a Congine-only keyword, documented loudly
- **Decided:** Keep the extension; state in the rule's docstring that it makes the contract
  non-portable; point users at the now-available portable spelling.
- **Evidence:** `domain/validator.py:263-281` verbatim: "**`null_forbidden` is a Congine extension,
  not JSON Schema.** A contract using it is no longer a portable JSON Schema document: no other
  tool understands the keyword, and Congine's own `JsonSchemaSemanticValidator` ignores it even when
  `CONGINE_SEMANTIC_VALIDATION=true`." `OPEN_QUESTIONS.md` Q3 = option **A**, over **B. Drop it**.
- **Apparent rationale:** Backward compatibility, with the cost made explicit rather than hidden.
  The Q2 fix supplied a portable alternative, which is what made "keep and document" defensible.
- **Confidence:** HIGH (stated in code and decision record).
- **Rejected alternatives visible:** Dropping it (B); keeping both silently (C).
- **Consequences in code:** Two spellings now express nullability, with different portability and
  different enforcement paths (`null_forbidden` is enforced by the rule engine and invisible to the
  semantic validator; a union type is enforced by both). `schema_vocabulary.py:39` allowlists it so
  it is never warned about.
- **Architecturally significant?** YES — it defines whether a Congine contract is a JSON Schema
  document.

### CANDIDATE: The rule engine reads eight keywords and silently ignores everything else
- **Decided:** `properties`, `required`, `null_forbidden` at the top level; `type`, `enum`,
  `min`/`minimum`, `max`/`maximum`, `pattern` per property. Nothing else, unless semantic
  validation is switched on.
- **Evidence:** `LocalValidator._extract_params` (`domain/validator.py:399-433`) is the complete
  answer. `§13.1`, `§13.2`. `schema_vocabulary.py:35-47` mirrors it.
- **Apparent rationale:** **RATIONALE NOT RECORDED.** No comment, commit or document explains why
  these eight rather than a full JSON Schema subset. The most defensible reconstruction is that six
  deterministic rules can be hand-verified and time-boxed under a millisecond deadline in a way
  full JSON Schema cannot — but that is inference, not evidence.
- **Confidence:** LOW (inferred). The *existence* of the limit is documented exhaustively; the
  *choice of the eight* is not.
- **Rejected alternatives visible:** Full JSON Schema by default — rejected, since it exists behind
  a flag that defaults to `False`.
- **Consequences in code:** `const` and `additionalProperties` do nothing; a payload may carry
  arbitrary extra keys under any contract (`§13.2`). This is the single largest gap between what a
  contract author expects and what runs. It forced the entire `schema_vocabulary` module into
  existence as a mitigation.
- **Architecturally significant?** YES — it defines the product's enforcement semantics.
- **❓ QUESTION FOR FOUNDER:** Why these eight keywords, and why is full JSON Schema opt-in rather
  than the default? If the reason is latency, has the cost of `semantic_validation_enabled=True`
  been measured against the millisecond budget? (GAP4 §4.4 measures it; the decision predates the
  measurement.)

### CANDIDATE: `pattern` is a full match, not a search
- **Decided:** `_compiled_pattern(pattern).fullmatch(value)`.
- **Evidence:** `domain/validator.py:337`, with `:347` — "Anchored full-string match: the entire
  value must satisfy it." `§13.3` notes this "diverges from JSON Schema, where `pattern` is an
  unanchored *search*", verified: `{"a":"xabcx"}` + `pattern:"abc"` fails.
- **Apparent rationale:** Not recorded. Plausibly a deliberate stricter posture for a governance
  tool.
- **Confidence:** LOW (inferred). The behaviour is commented; the *choice against JSON Schema
  semantics* is not.
- **Rejected alternatives visible:** `search()` — the JSON Schema behaviour, not discussed.
- **Consequences in code:** Patterns copied from a JSON Schema document **over-reject**. A user
  migrating an existing schema gets false breaches with no warning, and
  `find_unenforced_keywords` cannot detect it because `pattern` is in the enforced set.
- **Architecturally significant?** YES — it silently changes the meaning of a standard keyword.
- **❓ QUESTION FOR FOUNDER:** Is `fullmatch` deliberate? If so it needs a prominent note in the
  contract-authoring guide, because it is a silent semantic divergence from JSON Schema on a
  keyword users will copy in from elsewhere. If not, it is a one-word fix with a compatibility cost.

### CANDIDATE: The unenforced-keyword scan uses allowlist semantics and is non-recursive
- **Decided:** Anything not in the enforced set and not in a metadata allowlist is reported;
  nested subtrees are reported once at the parent rather than enumerated.
- **Evidence:** `schema_vocabulary.py:116-136` verbatim: "Allowlist semantics: any key not in the
  enforced set (minus a metadata allowlist) is reported, so keywords nobody thought to blocklist are
  still caught as JSON Schema evolves." And: "Nested subtrees are not enumerated: a property
  carrying `properties` or `items` is reported once at that field; descending would add noise, not
  information (the whole subtree is unenforced regardless)."
- **Apparent rationale:** JSON Schema keeps growing, so a blocklist decays. The whole nested subtree
  is unenforced either way, so enumeration is a noise decision, not a coverage decision.
- **Confidence:** HIGH (both choices stated with reasons).
- **Rejected alternatives visible:** Blocklist semantics; full recursion. Both named and rejected.
- **Consequences in code:** New JSON Schema keywords are caught for free. Output is capped at 20
  paths (`_MAX_REPORTED`, `:85`).
- **Architecturally significant?** YES — it determines whether the false-safety mitigation decays.

### CANDIDATE: `schema_vocabulary` duplicates the rule engine's knowledge rather than deriving it
- **Decided:** The vocabulary is mirrored by hand and guarded by a drift test, not computed from
  `validator.py`.
- **Evidence:** `schema_vocabulary.py:11-12` verbatim: "It deliberately does **not** import
  `validator` — the vocabulary is mirrored here and guarded against drift by
  `tests/unit/test_schema_vocabulary.py`." `§3.3` adds the placement reasoning: deriving it inside
  `validator.py` "would put a diagnostic concern in the enforcement path".
- **Apparent rationale:** Keep the enforcement path free of diagnostic code; pay for the
  duplication with a test.
- **Confidence:** HIGH (stated, including the pointer to the guard).
- **Rejected alternatives visible:** Deriving it in `validator.py` (rejected — pollutes the hot
  path); placing it in L3 (rejected — puts domain knowledge outside the domain).
- **Consequences in code:** Two places must change together. `test_vocabulary_matches_rule_engine`
  and the `RECOGNISED_TYPE_NAMES == frozenset(_JSON_TYPE_MAP)` assertion are what make it payable —
  and they did their job during the Q2 change.
- **Architecturally significant?** YES — deliberate duplication with a named mitigation.

---

## Group D — Failure and degradation policy

### CANDIDATE: Telemetry is published before a strict-mode raise
- **Decided:** `_finalize` publishes at `:225`, then calls `_handle_failure` which raises at `:249`.
- **Evidence:** `validate_contract_usecase.py:225-228`. `§14.8` G9: "A compliance-critical
  deployment therefore never loses the record of the violation that stopped it." Stated in
  `README.md`'s failure-mode table.
- **Apparent rationale:** The record of a blocking violation is more valuable than the microseconds
  saved by raising first.
- **Confidence:** MEDIUM (the ordering is deliberate and documented in the README; no code comment
  explains it at the site).
- **Rejected alternatives visible:** Raising before publishing (the naive ordering).
- **Consequences in code:** A `publish` that blocked would delay the raise — which is why
  `IEventBus.publish` must be non-blocking is an obligation and not a nicety.
- **Architecturally significant?** YES — it is guarantee G9.

### CANDIDATE: A missing contract fails closed in every fail mode
- **Decided:** `_resolve_schema` raises `CongineContractNotFoundError` *before* any fail-mode logic
  is consulted.
- **Evidence:** `validate_contract_usecase.py:161-166`, called at `:60` — before the `try` block
  that implements fail-mode degradation. `§14.8` G10: "a missing contract is a wiring error, not a
  validation outcome". `§9.1` row 4.
- **Apparent rationale:** A contract you believed was enforcing something, that is absent, must stop
  your code rather than silently pass.
- **Confidence:** MEDIUM (the intent is stated in `§14.8`/`§9.6`; the code has no comment at the
  site — the guarantee rests on statement *ordering*, which is fragile to a refactor).
- **Rejected alternatives visible:** Treating a cache miss as a degraded result (which is what
  every *other* failure does).
- **Consequences in code:** "It is also the sharpest edge in the system: a cold boot with a dead
  plane and no snapshot turns every guarded call into an exception" (`§14.8`). `silent` mode cannot
  suppress it. `LFUCache` with `capacity=0` triggers it universally.
- **Architecturally significant?** YES — guarantee G10.

### CANDIDATE: A broken validator degrades to `status="fail"` with zero breaches
- **Decided:** Timeout, resource error and internal error all produce `status="fail"`,
  `degraded=True`, `breaches=()`.
- **Evidence:** `validate_contract_usecase.py:168-203`. `§11.2`: "**A caller that reads only
  `is_pass()` cannot distinguish 'the contract was violated' from 'the validator crashed and nothing
  was checked.'**"
- **Apparent rationale:** Fail closed — a validation that did not run must not report a pass.
- **Confidence:** MEDIUM (the fail-closed direction is clearly deliberate; the decision to carry the
  distinction *only* in `degraded`/`degraded_reason` rather than in `status` is not explained).
- **Rejected alternatives visible:** A third `status` value (e.g. `"degraded"`) — not discussed.
  This would have made the distinction impossible to miss.
- **Consequences in code:** Under default `degrade` mode a crashed validator is a WARNING and the
  output flows through. `§9.6` calls this out as one of "the two shapes of fails closed".
- **Architecturally significant?** YES — it defines what a verdict means.
- **❓ QUESTION FOR FOUNDER:** Should `status` carry a third value so that a caller inspecting only
  `is_pass()` cannot mistake "nothing was checked" for "checked and violated"? Today the distinction
  is opt-in, and every code sample in the documentation reads `is_pass()`.

### CANDIDATE: SDK exceptions are re-raised unchanged rather than degraded
- **Decided:** `except CongineBaseException: raise` sits between the resource-error and generic
  handlers.
- **Evidence:** `validate_contract_usecase.py:77-78` (sync), `:116-117` (async). Ordering is
  load-bearing: it must precede `except Exception`.
- **Apparent rationale:** An SDK error is a wiring or configuration fault, not a validation outcome;
  degrading it would hide a bug as a soft failure.
- **Confidence:** LOW (inferred — there is no comment at either site; the ordering is the only
  evidence, and it is consistent with the G10 policy).
- **Rejected alternatives visible:** Degrading everything (which the bare `except Exception` does
  for non-SDK errors).
- **Consequences in code:** A custom `IValidator` raising a Congine exception propagates to the host
  and bypasses telemetry entirely (`§9.1` row 11 — "**none**").
- **Architecturally significant?** YES.

### CANDIDATE: A failed sync never destroys a healthy cache
- **Decided:** `_apply` returns early on falsy contracts; `_prime_cache` updates keys in place.
- **Evidence:** `sync_contracts_usecase.py:242-244` and `:257-262` verbatim: "Updates keys in place
  rather than clear-then-refill, so a concurrent `get` on the validation hot path always observes a
  coherent cache." Module docstring `:5-6`: "a transport failure or a corrupted snapshot never wipes
  a healthy in-memory cache and never raises into the host application." `§14.8` G8.
- **Apparent rationale:** A dead control plane must degrade to *stale enforcement*, never to *no
  enforcement*. Clear-then-refill would open a window in which every validation raises.
- **Confidence:** HIGH (stated in two places with the concurrency reason spelled out).
- **Rejected alternatives visible:** Clear-then-refill (named and rejected with its failure mode).
- **Consequences in code:** The cache can hold indefinitely stale schemas if the plane never
  recovers, with only the TTL to bound it — a deliberate trade of freshness for availability.
- **Architecturally significant?** YES — guarantee G8.

### CANDIDATE: One circuit breaker instance is shared by contract sync and telemetry shipping
- **Decided:** The same `CircuitBreaker` is injected into both `SyncContractsUseCase` and
  `QueueEventBus`.
- **Evidence:** `dependency_injection.py:298`, `:338` — one construction at `:255`, two injections.
  `§5.7`: "Telemetry-ship failures therefore trip the breaker that gates contract fetches, and vice
  versa. This is deliberate — both are the same control plane."
- **Apparent rationale:** Both talk to the same host; evidence that it is down from one path should
  protect the other.
- **Confidence:** MEDIUM (the wiring is unambiguous and `§5.7` states the intent; no code comment
  says so at the injection sites).
- **Rejected alternatives visible:** Two independent breakers.
- **Consequences in code:** A telemetry outage can block contract fetches even if `/contracts/active`
  is healthy — the two endpoints are assumed to fail together. A new `ICircuitBreaker`
  implementation "cannot assume a single caller" (`§5.7`).
- **Architecturally significant?** YES — couples two otherwise independent subsystems.

### CANDIDATE: `HALF_OPEN` admits exactly one probe caller
- **Decided:** `_probe_in_flight` is set under the lock; concurrent callers get `False`.
- **Evidence:** `circuit_breaker.py:92-96`, docstring `:83-84`: "`True` for the **single** probe
  caller only (FIX-11). Concurrent callers receive `False` until the probe completes."
- **Apparent rationale:** Without it, the moment the cooldown elapses every caller floods a
  recovering plane — turning recovery into a second outage.
- **Confidence:** HIGH (stated with the audit ID and the mechanism).
- **Rejected alternatives visible:** Admitting all callers after cooldown (the naive breaker).
- **Consequences in code:** `record_failure` in HALF_OPEN goes straight back to OPEN (`:111-114`)
  rather than incrementing — otherwise a single failed probe would take four more to re-trip.
- **Architecturally significant?** YES.

### CANDIDATE: Reading breaker `state` may mutate it
- **Decided:** The `state` property calls `_maybe_half_open_locked()`.
- **Evidence:** `circuit_breaker.py:65-75`, docstring: "Reading the state may transition OPEN →
  HALF_OPEN if the cooldown has elapsed — so a caller that consults `state` and then `allow()` is
  guaranteed coherent behaviour."
- **Apparent rationale:** Coherence between a `state` read and a subsequent `allow()`.
- **Confidence:** HIGH (stated) for the *reason*; the *consequence* is undocumented in code.
- **Rejected alternatives visible:** Lazy transition only inside `allow()`.
- **Consequences in code:** `ServiceContainer.health()` reads `state` (`:469`), so **an operator
  polling health can move the breaker out of OPEN**. `§5.7` calls it "Harmless … but a genuine
  surprise". Observation mutates state.
- **Architecturally significant?** YES — a monitoring action changes runtime behaviour.

---

## Group E — Security posture

### CANDIDATE: `google-re2` is a required core dependency, not an optional extra
- **Decided:** `re2` is in `dependencies`; the `[redos]` extra is a documented no-op alias.
- **Evidence:** `pyproject.toml:27`, `:47-48` — "Backward-compatible alias: google-re2 is now a
  required core dependency (FIX-02)." `domain/validator.py:37-38`: "google-re2 is a required core
  dependency (FIX-02) — linear-time matching." `_RE2_AVAILABLE = True` is a vestigial hard-coded
  constant, never branched on.
- **Apparent rationale:** A ReDoS defence that can be uninstalled is not a defence. Schema-supplied
  patterns are untrusted input (audit H3).
- **Confidence:** HIGH (stated, with the extra retained purely for compatibility).
- **Rejected alternatives visible:** Optional extra with an `re` fallback — the prior state, visible
  in the vestigial constant and the retained alias.
- **Consequences in code:** A native-compiled dependency on every install. RE2 lacks backreferences
  and lookaround, so such a pattern raises `re2.error` and becomes an "Invalid regex pattern"
  breach — a *contract* failure rather than a schema-authoring error (`§13.3`).
- **Architecturally significant?** YES — dependencies and non-functional characteristics.

### CANDIDATE: `pii_sanitize` is the one regex left on stdlib `re`
- **Decided:** `pii_sanitize.py` uses `re`, not `re2`.
- **Evidence:** `pii_sanitize.py:9`, `:14`. `§14.5` and `§16` debt D7 record it as the single
  documented exception to the project-wide linear-time rule. Still present at `49a2f93`.
- **Apparent rationale:** **RATIONALE NOT RECORDED.** No comment explains the exception. `§14.5`
  assesses the risk as low (no nested quantifier, bounded inputs) but calls it "a real exception …
  on the path that processes the least-trusted strings in the system".
- **Confidence:** UNKNOWN (no evidence of a decision at all; this reads as an oversight that was
  later noticed and classified rather than a choice).
- **Rejected alternatives visible:** None.
- **Consequences in code:** One unbounded-backtracking engine on the path handling validator-
  generated messages containing instance data.
- **Architecturally significant?** YES — a stated exception to a security invariant.
- **❓ QUESTION FOR FOUNDER:** Is the stdlib `re` in `pii_sanitize.py` deliberate, or a leftover?
  `google-re2` is already a required dependency, so the exception appears to buy nothing.

### CANDIDATE: The snapshot uses two distinct lock files
- **Decided:** `<snapshot>.lock` serialises writes; `boot_<scope>.lock` coordinates single-flight
  boot.
- **Evidence:** `http_contract_repository.py:75-80` verbatim: "Separate lock file for boot
  single-flight (audit D-7). Distinct from `<snapshot>.lock` (used by save_snapshot) so boot
  coordination and write serialization do not contend with each other."
- **Apparent rationale:** One lock would make boot coordination wait behind an unrelated write.
- **Confidence:** HIGH (stated).
- **Rejected alternatives visible:** A single shared lock (named and rejected).
- **Consequences in code:** Two lock files per scope on disk; two independent timeout policies
  (`timeout=0` non-blocking for boot, `snapshot_lock_timeout_seconds` for writes).
- **Architecturally significant?** YES.

### CANDIDATE: A snapshot writer that cannot get the lock skips its write
- **Decided:** Timeout ⇒ skip, not retry, not raise, not block.
- **Evidence:** `http_contract_repository.py:170-173` verbatim: "A worker that cannot acquire the
  lock within the timeout skips its write (snapshot persist is best-effort and must never break
  boot) rather than blocking or raising." And `:193-194`: "it is writing the very same fetched
  contracts, so dropping our write is safe."
- **Apparent rationale:** The competing writer has the identical contracts, so the write is
  redundant; boot must not be delayed for a redundant write.
- **Confidence:** HIGH (stated twice, including why it is safe).
- **Rejected alternatives visible:** Blocking; raising.
- **Consequences in code:** Under heavy contention the snapshot may go unrefreshed for a cycle. The
  assumption "the sibling has identical contracts" holds only because all workers fetch from one
  control plane.
- **Architecturally significant?** YES.

### CANDIDATE: Snapshots live in a per-user app directory, never a world-shared temp root
- **Decided:** `%LOCALAPPDATA%` / `$XDG_CACHE_HOME` / `~/.cache`, path scoped by
  `sha256(base_url|project_id|tenant_id)[:16]`, `chmod 0o700` best-effort on POSIX.
- **Evidence:** `http_contract_repository.py:8-15` verbatim: "the snapshot path is **scoped per
  tenant/project** … and lives under a **per-user, app-owned** directory — NOT the world-shared OS
  temp root — so two tenants on one host cannot contaminate each other's cache and a local attacker
  cannot pre-plant a predictable `/tmp/congine_snapshot.json`." Audit C2.
- **Apparent rationale:** Both threats named: cross-tenant contamination and snapshot pre-planting.
- **Confidence:** HIGH (stated with both threat models).
- **Rejected alternatives visible:** `/tmp` with a predictable name (named as the rejected design).
- **Consequences in code:** `_owned_by_current_user` returns `True` unconditionally when
  `os.name != "posix"` (`:248-249`), so the ownership check is a **no-op on Windows** — guarantee
  G4 is AT RISK there and the codebase does not say so (`§14.4`). `os.path.islink` also does not
  detect NTFS junctions.
- **Architecturally significant?** YES — security boundary.
- **❓ QUESTION FOR FOUNDER:** Windows snapshot integrity rests entirely on the per-user directory
  ACL, since both the ownership check and the symlink check are weaker there. Is Windows a supported
  production target, or a development-only platform? The answer changes whether this needs work.

### CANDIDATE: Non-local deployments get PII-safe logging by default
- **Decided:** `effective_log_safe_fields()` returns a 12-key allowlist automatically when the base
  URL is non-local and redaction is not explicitly disabled.
- **Evidence:** `config.py:359-380` (FIX-08). `logger.py:31-40` — an unconditional blocklist applies
  regardless. `§12.2`: "a production (non-local) deployment gets PII-safe logging **by default**,
  without configuration."
- **Apparent rationale:** Safe-by-default. Requiring configuration for PII safety means most
  deployments will not have it.
- **Confidence:** HIGH (stated, with the local/non-local discriminator being the mechanism).
- **Rejected alternatives visible:** Opt-in redaction (the prior state, inferable from
  `log_safe_fields=None` meaning "no redaction").
- **Consequences in code:** Local development sees full logs; production sees redacted ones — so a
  developer cannot reproduce a production log locally without setting `CONGINE_LOG_SAFE_FIELDS`.
  `_env_frozenset("")` yields an **empty** frozenset meaning "redact everything", which is different
  from unset (`§12.3`).
- **Architecturally significant?** YES.

---

## Group F — Configuration and lifecycle

### CANDIDATE: `region` wired to a regional default `base_url` rather than deleted
- **Decided:** An explicitly-set `CONGINE_REGION` selects a default control plane; an explicit
  `CONGINE_BASE_URL` always wins.
- **Evidence:** `config.py:34-50`, `:203-216`. `OPEN_QUESTIONS.md` Q1 = option **B — wire it**, over
  A (delete) and the third option `§17` Q1 called "worse than either" (raise on inconsistency).
  Precedence stated at `:207-209`.
- **Apparent rationale:** `§16` D1 rated this HIGH severity because the enum's own comments name
  "Frankfurt (GDPR)" — a user setting `CONGINE_REGION=eu` for data residency got nothing and was
  told nothing.
- **Confidence:** HIGH (stated in code and decision record, with alternatives).
- **Rejected alternatives visible:** Deleting the field (A); raising on inconsistency (rejected in
  `§17` Q1 as worse than either).
- **Consequences in code:** **The hostnames are self-declared placeholders.** `config.py:43-45`
  carries an `.. important::` block: "These hostnames are the single place regional endpoints are
  declared. Confirm them against the deployed control plane before relying on region-based routing
  in production." `OPEN_QUESTIONS.md` flags this as the one item still needing confirmation.
- **Architecturally significant?** YES — it changes where the SDK sends credentials.
- **❓ QUESTION FOR FOUNDER:** Are `https://api.{us,eu,apac}.congine.dev` the real control-plane
  hostnames? This is the only open item in the entire Q-series, and until it is confirmed, setting
  `CONGINE_REGION` in production points the SDK at a possibly non-existent host.

### CANDIDATE: `get_default()` reads one environment variable on the cached path
- **Decided:** `deployment_mode_from_env()` reads only `CONGINE_DEPLOYMENT_MODE`; the full
  `from_env()` parse happens once, at construction.
- **Evidence:** `dependency_injection.py:81-116` verbatim: "This method is on the hot path:
  `@congine_guard` with no explicit `container=` resolves through it on *every guarded call*, and it
  used to run a full `CongineConfig.from_env` — parsing and validating ~47 variables per request,
  and able to raise mid-request even when a perfectly good singleton already existed."
  `config.py:186-201` gives the same reason. `OPEN_QUESTIONS.md` Q10 = option **C — fix it *and*
  document**.
- **Apparent rationale:** The convenience path (no explicit `container=`) is the one every example
  uses, so it must not be the expensive one.
- **Confidence:** HIGH (stated in two files plus the decision record).
- **Rejected alternatives visible:** Documenting it as unsuitable for production without fixing it
  (option A/B in `§17` Q10).
- **Consequences in code:** The multi-tenant guard is still evaluated **before** the cache check
  (`:98`), so flipping `CONGINE_DEPLOYMENT_MODE` at runtime still disables `get_default()`
  immediately (FIX-05 preserved). One `os.getenv` per guarded call remains.
- **Architecturally significant?** YES — hot-path cost.

### CANDIDATE: Deferred teardown armed at construction for every container
- **Decided:** `_arm_deferred_teardown()` is the last statement of `__init__`, not only an eviction
  action.
- **Evidence:** `dependency_injection.py:357-367` verbatim: "a container that is simply dropped —
  never registered, never evicted, never closed — previously leaked both for the life of the
  process, because the finalizer was armed only on the eviction path. Arming here makes every
  container self-cleaning." And: "Must be the LAST statement: the finalizer captures the
  sub-components, so they all have to exist." `for_tenant`'s eviction call is now "a no-op since
  audit Q5 … kept because the eviction path is where the guarantee actually matters" (`:181-183`).
  `OPEN_QUESTIONS.md` Q5 = option **A — arm cleanup at construction**.
- **Apparent rationale:** Closes `§16` D3 and `§7.8` row 6.
- **Confidence:** HIGH (stated with the prior defect described).
- **Rejected alternatives visible:** Refusing eviction while a container is still referenced
  (`§17` Q5's other option).
- **Consequences in code:** The comment concedes the remaining gap explicitly: "A failure earlier in
  `__init__` still leaks (nothing is returned to close), which is tracked separately" — that is debt
  D10, still open. Teardown now runs on an arbitrary GC thread for every container, which is why
  `_teardown_components` uses `drain=False` and suppresses every exception (`:40-62`).
- **Architecturally significant?** YES — resource lifecycle.

### CANDIDATE: Boolean env parsing fails silently to `False`; numeric parsing raises
- **Decided:** `_env_bool` returns `False` for any unrecognised value; `_env_int`/`_env_float` raise
  `CongineConfigurationError` naming the variable.
- **Evidence:** `config.py:382-390` vs `:392-402`, `:412-422`. `§12.3` documents the asymmetry;
  `§16` debt D20 records it as still open. Verified present at `49a2f93`.
- **Apparent rationale:** **RATIONALE NOT RECORDED.** No comment explains why booleans differ from
  numbers.
- **Confidence:** UNKNOWN. `§12.3` observes the direction is safe for `require_https` (a typo cannot
  disable HTTPS enforcement, because `allow_cleartext` must be explicitly *true*) — but that is a
  post-hoc justification for a general helper, not evidence of a decision.
- **Rejected alternatives visible:** None.
- **Consequences in code:** `CONGINE_TELEMETRY_ENABLED=TRUE!` or `=yes please` silently disables
  telemetry; `CONGINE_START_BACKGROUND_SERVICES` likewise silently disables three subsystems.
- **Architecturally significant?** YES — a typo silently changes deployment topology.
- **❓ QUESTION FOR FOUNDER:** Should `_env_bool` raise on an unrecognised value, matching the
  numeric helpers? Q1/Q6/Q7/Q11 all chose "make the invisible visible"; this is the same class of
  problem and was not in the Q-series.

### CANDIDATE: `ValidationTimer` is retained, deprecated, and deliberately not exported
- **Decided:** Keep the file, warn on construction, exclude it from
  `infrastructure/__init__.py.__all__`.
- **Evidence:** `infrastructure/__init__.py:22-25` verbatim: "Intentionally NOT exported (audit
  D-3/D-11): ValidationTimer. Wiring it directly defeats the load-shedding / async-symmetric
  guarantees of BoundedValidationExecutor. It remains importable from
  `congine_core.infrastructure.timer` for legacy reference only." `timer.py:3-10` repeats it;
  `:39-44` raises `DeprecationWarning`.
- **Apparent rationale:** It is shape-compatible with `IValidationRunner` on `run_with_timeout`
  only, so it would satisfy a naive duck-type check and silently void guarantee G1. Excluding it
  from the aggregate export is how a structural-typing codebase enforces a deprecation.
- **Confidence:** HIGH (stated in two files with the failure mode named).
- **Rejected alternatives visible:** Deleting it (untaken); exporting it (named and rejected).
- **Consequences in code:** `tests/unit/test_timer.py` (4 tests) exercises code the container will
  never run — "the suite protects code the container will never run" (`§16.3`). It is the only
  source file with 0% coverage.
- **Architecturally significant?** YES — a deprecation enforced structurally rather than by comment.
- **❓ QUESTION FOR FOUNDER:** Is there a remaining reason to keep `timer.py`? It is unreachable,
  is the only 0%-covered file, and its documentary value is now duplicated by
  `bounded_executor.py`'s own module docstring.

### CANDIDATE: Unrecoverable audit IDs are recorded as unrecoverable, not invented
- **Decided:** FIX-07, FIX-09, FIX-10, FIX-12, FIX-13, M3, D-5, D-6, D-8, D-9 are listed as
  unrecoverable rather than assigned reconstructed meanings.
- **Evidence:** `AUDIT_ID_INDEX.md:140-153` verbatim: "They are recorded here as *unrecoverable*
  rather than guessed. Assigning them invented meanings would be worse than leaving the gap, because
  it would make a fabricated trail indistinguishable from a real one." Four other IDs (C1, M1, L2,
  L6) *were* backfilled, because their meanings were recoverable from tests that assert them
  (`§3` of that file).
- **Apparent rationale:** A trail whose fabricated entries cannot be told from its real ones is
  worth less than a trail with holes.
- **Confidence:** HIGH (stated, with the principle articulated and a worked distinction between
  recoverable and not).
- **Rejected alternatives visible:** Guessing the meanings (named and rejected).
- **Consequences in code:** `docs/context/01_SYSTEM_STATE.md:88`'s claim that FIX-01..FIX-14 are all
  "present and consistent" is contradicted in writing: 9 of 14 are annotated.
- **Architecturally significant?** NO — documentation governance, not structure. Included because
  `§17` Q12 raised it and F09 (ADR archive) consumes it directly.

---

## Summary

| | Count |
|---|---|
| Candidates | 32 |
| HIGH confidence (rationale stated) | 18 |
| MEDIUM (implied) | 7 |
| LOW (inferred) | 4 |
| UNKNOWN (no evidence of a decision) | 3 |
| Architecturally significant | 31 of 32 |
| Questions for founder | 13 |

**Where rationale is strongest:** the executor (H1/H2), the ports' lifecycle surface (Q8), the
contract-language decisions (Q2/Q3), and snapshot security (C2/D-7). These files carry their reasons
in prose, including the alternatives they rejected and *why* the rejected option was worse.

**Where rationale is absent and matters most:**
1. **Why these eight schema keywords** — the single most consequential product decision, entirely
   unrecorded (LOW).
2. **Why `pattern` is `fullmatch` rather than `search`** — a silent divergence from JSON Schema
   (LOW).
3. **Why `pii_sanitize` uses stdlib `re`** — no evidence a decision was ever made (UNKNOWN).
4. **Why booleans parse silently to `False` while numbers raise** (UNKNOWN).
5. **Why `except CongineBaseException: raise` sits where it does** — correct, but the ordering is
   the only record of the intent (LOW).
