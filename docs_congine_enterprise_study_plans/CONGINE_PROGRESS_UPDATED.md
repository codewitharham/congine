# CONGINE — PROGRESS (Shared Source of Truth)

> This is the durable, re-runnable anchor for the current CONGINE codebase.
>
> - **SYSTEM STATE** and **PHASES** describe the latest verified architecture and roadmap.
> - **DAILY LOG** is append-only. Existing dated entries must never be erased on re-run.
> - Detailed architectural archaeology, GAP evidence, hardening reports, and formal documentation live elsewhere in `docs/`.
>
> This file is intentionally conservative: a capability is called **built and trustworthy** only when the current code and tests support that claim. Planned or partially hardened behavior is labeled accordingly.

---

## SYSTEM STATE AS OF 2026-08-17

CONGINE is currently a **deterministic, synchronous, in-process organizational-policy enforcement library** for governed Python / agent outputs.

The core runtime is still a library rather than a server: there is no MCP server, CLI, durable event database, or control-plane backend implemented in this repository yet.

What changed materially during P0 is the trust model.

The pre-hardening mental model was:

```text
output
  ↓
validate against schema
  ↓
pass / fail
```

The post-P0 model is:

```text
canonical + validated configuration
        ↓
admitted + enforceable contract
        ↓
bounded deterministic evaluation
        ↓
was it actually enforced?
        ↓
if enforced: conforming or non-conforming?
        ↓
configured host consequence
```

The governing invariant is now explicit:

> **CONGINE must never appear to have enforced a policy that it did not actually evaluate.**

P0 Trust-Critical Hardening is **CLOSED**.

Final P0 closeout evidence:

| Check | Final result |
|---|---|
| Tests | **478 passed / 1 skipped** |
| Ruff format | **clean** |
| Ruff check | **clean** |
| Determinism | **N=5000 → 1 verdict**, verdict hash unchanged |
| Admission migration preflight | **3/3 shipped contracts = 100%** under documented configuration |
| Load shedding | **2000/2000 → `LoadShedError`** |
| Deadline expiry | remains plain **`TimeoutError`** |
| False-safety corpus | dotted path / unknown type / unenforced keyword all **refused** |
| Configuration invariant parity | **6/6 PASS** |
| Original dirty working tree | **byte-for-byte untouched** during hardening |
| P0 working tree | detached at `49a2f93`, hardening changes intentionally uncommitted during review |

The final P0 state should be treated as the baseline for all future work. Do **not** reason from the pre-hardening `49a2f93` behavior as though it were still current.

---

### Built and trustworthy after P0

#### 1. Deterministic validation core

The runtime conformance decision remains deterministic and code-based.

The native `RuleEngine` is still the protected center:

- pure Python domain logic;
- no network access;
- no storage I/O;
- no LLM/model decision in the final verdict path;
- stable judgment under repeated execution for the same effective inputs.

P0 deliberately did **not** make the `RuleEngine` responsible for authoring-time contract correctness.

That separation is now important:

```text
contract meaning / admission problem
        → contract admission boundary

runtime payload conformance problem
        → RuleEngine / evaluator path
```

The evaluator remains small and auditable while the surrounding system becomes stricter about what is allowed to reach it.

---

#### 2. Canonical configuration is now a trust boundary

`CongineConfig` is no longer just passive setup data.

The final closeout found that direct Python construction previously bypassed validation and allowed raw strings to survive in enum-backed fields. That created silent enforcement differences.

Examples reproduced during closeout included:

- `CongineConfig(fail_mode="strict")` silently failing to activate strict enforcement;
- raw `"multi_tenant"` bypassing the multi-tenant guard;
- direct construction skipping credential validation;
- direct construction skipping HTTPS / cleartext policy validation.

P0 closeout moved ownership to:

```text
CongineConfig.__post_init__()
        ├─ normalize enum-backed values
        └─ run the existing validate()
```

There is now one instance-level normalization + validation boundary for:

- environment construction;
- direct Python construction;
- tests;
- future CLI/API configuration adapters.

Five enum-backed fields are canonicalized centrally:

- `contract_source`
- `contract_admission`
- `fail_mode`
- `deployment_mode`
- `region`

Valid strings normalize to canonical members. Invalid values fail loudly.

The composition root receives already-canonical, already-validated configuration.

This is now part of the security/enforcement model, not just ergonomics.

---

#### 3. Contract admission now protects production activation

P0 introduced a pure L2 contract admission boundary.

The normal production sync path is now conceptually:

```text
retrieve contract
      ↓
admit_contract(...)
      ↓
ADMIT ─────────────→ active schema storage
REJECT ────────────→ do not activate
```

Admission rejects contracts whose meaning CONGINE cannot safely determine or whose claimed semantics the active evaluator set cannot actually enforce.

The admitted grammar checks include the trust-critical cases P0 targeted:

- malformed root/property structures;
- unknown scalar type names;
- unions containing unknown types;
- empty type unions;
- invalid patterns;
- ambiguous dotted property keys;
- recognized-but-unenforced keywords when no active evaluator can enforce them;
- accidental grammar such as bare-string property specs or `required="email"`.

The native engine's defensive unknown-type behavior remains intact at runtime, but production contract activation no longer relies on that fail-open fallback.

---

#### 4. Admission is capability-aware, not just syntax-aware

A contract can be valid JSON and still be unsafe to activate under the currently wired evaluator set.

Example:

```text
minLength / maxLength
```

are not native RuleEngine constraints.

A shipped contract using those constraints is:

```text
native-only evaluator set
    → REJECT

semantic evaluator enabled and capable
    → ADMIT
```

The final migration preflight confirmed exactly this behavior for the three shipped contracts.

Acceptance was:

> **100% of shipped contracts intentionally documented as valid are admitted under the configuration in which they are documented to operate.**

Admission was not weakened to make the preflight green.

This is now a core product invariant:

> **A contract must not be active if CONGINE cannot execute the semantics it claims.**

---

#### 5. Evaluation truth is explicit

Before P0, callers could inspect `is_pass()` but could not directly ask:

> "Was this policy actually evaluated?"

P0 added:

```python
ValidationResult.is_enforced()
```

The correct reading order is now:

```python
if not result.is_enforced():
    # conformance is unknown; inspect degraded_reason
elif result.is_pass():
    # evaluated and conforming
else:
    # evaluated and non-conforming
```

The critical distinction is:

```text
not evaluated
    ≠ conforming
    ≠ violating
```

An inability to evaluate must not fabricate a breach.

---

#### 6. Degraded reasons are typed machine-facing semantics

P0 separated operational failure classes that previously collapsed together.

Important current wire meanings include:

- `"timeout"` — admitted work exceeded the validation deadline;
- `"load_shed"` — no bounded-executor capacity was available;
- `"resource_error"` — resource failure path such as `MemoryError` / `RecursionError`;
- `"internal_error"` — internal evaluation failure;
- `"invalid_payload"` — payload could not be safely measured/evaluated;
- `"invalid_contract"` — schema/contract could not be safely measured/evaluated.

The P0 design rule is:

> **A machine-facing degradation value must correspond to a real emitting path. Name the path or do not add the member.**

`LoadShedError` subclasses `TimeoutError`, preserving compatibility for existing broad timeout handlers while exposing the more precise reason to CONGINE.

---

#### 7. Size guards now fail closed honestly

Previously, serialization/measurement failure could become:

```text
size = 0
```

and bypass the input bound entirely.

Now:

```text
cannot measure payload
    → degraded
    → INVALID_PAYLOAD
    → is_enforced() == False
    → zero fabricated breaches
```

and:

```text
cannot measure schema
    → INVALID_CONTRACT
```

while:

```text
successfully measured and too large
    → real INPUT_BOUNDS breach
    → is_enforced() == True
```

The broad exception handling used for measurement was verified during final closeout to wrap exactly the measurement statement, not surrounding business logic or orchestration.

---

#### 8. Load shedding and deadline timeout are distinguishable

Before P0:

```text
executor saturated
and
validation exceeded deadline
```

both looked like:

```text
degraded_reason = "timeout"
```

After P0:

```text
capacity saturated
    → LoadShedError
    → "load_shed"

work admitted but deadline exceeded
    → TimeoutError
    → "timeout"
```

Final closeout evidence:

```text
2000 / 2000 saturated attempts → LoadShedError
deadline path                  → plain TimeoutError
```

The last measured load-shed p50 was ~3.50 µs.

Do not treat that exact workstation number as an SLA. The executor was unchanged between the prior 1.50 µs and final 3.50 µs measurements; the useful invariant is classification + fast rejection, not matching a specific noisy microbenchmark.

---

#### 9. Port health is now consumed through the port

Before P0, `ServiceContainer.health()` reached into concrete validation-runner properties not declared by `IValidationRunner`.

A faithful Protocol implementation could therefore pass structural expectations and still crash health reporting.

P0 changed the dependency to the declared capability:

```text
validation_executor.health()
```

rather than:

```text
validation_executor.in_flight
validation_executor.rejected_total
```

The existing public health payload shape was preserved.

The GAP3 minimal runner now supports validate / health / close without concrete-only knowledge.

This is the correct ports-and-adapters rule:

> **If a consumer needs a capability, consume it through the declared abstraction.**

---

#### 10. Rejected contract updates are operationally visible

If a valid last-known-good contract is cached and a later incoming contract is rejected by admission:

- the rejected contract is not written;
- the previously cached contract survives;
- the rejection is logged with stable issue information;
- admission/sync health exposes the refusal;
- the rejected incoming version is not represented as successfully activated.

This preserves availability without pretending an invalid update became policy.

However, this does **not** mean exact contract-version enforcement exists. See the deferred section below.

---

#### 11. Placeholder regional routing is gone

The previous placeholder mapping:

```text
region → https://api.<region>.congine.dev
```

was removed.

Current rule:

- `region` is validated metadata;
- explicit `CONGINE_BASE_URL` selects the control-plane endpoint;
- `CONGINE_REGION` without an explicit base URL fails configuration rather than inventing a remote endpoint;
- local development with neither may use the local/loopback default.

This prevents CONGINE from sending credentials to an unverified hostname inferred from metadata.

---

#### 12. Machine-facing enums/codes are serialized intentionally

P0 caught a real serialization leak where an enum rendered as:

```text
ContractAdmissionMode.STRICT
```

instead of:

```text
strict
```

New machine-facing values are now tested through the actual serialization/logging/event paths.

The rule is:

```text
machines branch on stable codes
humans read prose
```

This matters for future:

- MCP responses;
- CLI output contracts;
- CI integrations;
- evidence events;
- control-plane APIs.

---

#### 13. The hot path remains bounded and shared by sync + async

The runtime path still routes sync and async validation through the same bounded validation machinery.

Conceptually:

```text
guard / adapter
    ↓
ValidateContractUseCase
    ↓
size/measurement boundary
    ↓
ISchemaStorage
    ↓
BoundedValidationExecutor
    ↓
native RuleEngine
(+ optional semantic evaluator)
    ↓
ValidationResult
    ↓
telemetry
    ↓
fail-mode / guard consequence
```

The bounded executor controls both:

```text
capacity
    → load shedding

deadline
    → timeout
```

A timed-out worker may continue running, and its permit remains held until actual completion. This is honest capacity accounting rather than pretending a timed-out thread no longer consumes resources.

---

### Built, but not yet fully enterprise-hardened

The following capabilities exist, but should **not** be described more strongly than the code/evidence supports.

#### Snapshot / offline resilience

The system already has:

- local snapshot fallback;
- atomic snapshot write behavior;
- tenant scoping;
- symlink / ownership checks where supported;
- `FileContractRepository`;
- `NoOpEventBus`;
- standalone/offline validation topology.

These are meaningful capabilities.

However, P1 still has lifecycle and shutdown hardening work, and Windows security parity is not equivalent to POSIX behavior. Do not market the current snapshot/lifecycle story as fully hardened cross-platform enterprise durability.

---

#### Telemetry

Current telemetry is:

```text
best-effort runtime observability
```

not:

```text
durable compliance evidence
```

`QueueEventBus` remains in-memory/asynchronous.

Events do not become a durable organizational audit trail merely because they are emitted before strict enforcement raises.

Durable evidence/history is a later phase.

---

#### PII sanitization

CONGINE has breach sanitization and logging redaction mechanisms.

But the telemetry PII sanitizer still uses a pattern with a backreference that RE2 cannot compile.

Therefore the old blanket statement:

> "PII-safe telemetry is fully hardened"

is too strong.

The P1 task is not "swap the sanitizer to RE2."

It requires:

1. redesigning the pattern;
2. proving behavioral equivalence with tests;
3. only then changing engines.

---

#### Regex/ReDoS safety

Contract pattern enforcement uses RE2-safe mechanisms and length caps for governed regex rules.

Do not generalize that into:

> "every regex in the codebase uses RE2."

The PII sanitizer is the explicit exception currently awaiting P1 redesign.

---

#### Multi-tenant behavior

P0 closeout fixed a real configuration-path bypass where raw `"multi_tenant"` could evade an identity-based guard.

Canonical config now prevents that silent bypass.

But broader multi-tenant lifecycle behavior still needs P1 review/hardening. Do not treat config normalization alone as proof that all multi-tenant isolation/lifecycle questions are permanently closed.

---

### Remaining known debt / deferred architecture

#### 1. Direct `schema_storage.put()` can bypass admission

Production sync is admission-gated, and an AST guard prevents new production writers from appearing silently.

But an external embedder or test can still call raw storage directly:

```python
schema_storage.put(...)
```

and bypass admission.

Current mitigations:

- production-writer AST guard;
- `admit_contract` exported publicly.

Full structural closure requires a later evolution such as:

```text
RawContract
    ↓
ContractCompiler / Admission
    ↓
AdmittedContract
    ↓
ISchemaStorage.put(AdmittedContract)
```

or admission behind the storage boundary.

Do not claim universal admission until that port boundary changes.

---

#### 2. Contract-version enforcement is still absent

The cache is keyed by `contract_id`, not `(contract_id, version)`.

`contract_version` currently reaches telemetry but is not matched against the cached schema.

P0 protects last-known-good from invalid replacement, but cannot guarantee:

```text
caller requested version X
    → exactly X was evaluated
```

Version-aware storage identity is still required before enterprise evidence can make that stronger claim.

---

#### 3. Partial-enforcement metadata is not modeled

`ContractAdmissionMode.WARN` is intentionally close to a no-op for unsafe semantics.

P0 does **not** allow:

```text
partially enforced contract
    → still report is_enforced() == True
```

without explicit coverage semantics.

A future richer model may need:

- evaluation state;
- conformance;
- enforcement coverage;
- action.

Until then, unsupported semantics without an active capable evaluator are refused rather than approximated.

---

#### 4. Mechanical type and architecture enforcement is not complete

P0 found two layer-direction mistakes by review during implementation.

That proves the architecture rule is understood, but not yet automatically enforced strongly enough.

P1 must add two different gates:

```text
blocking mypy
    → static type / Protocol correctness

separate import/layer dependency gate
    → hexagonal dependency direction
```

Mypy does **not** know that:

```text
L3 → L4
L0 → L2
```

is forbidden if the imports are otherwise type-correct.

---

#### 5. Composition-root and lifecycle hardening remains

P1 still includes:

- transactional composition-root construction;
- cleanup if construction fails midway;
- `atexit.unregister`;
- deterministic/idempotent close behavior;
- telemetry shutdown ordering;
- bounded coordinated shutdown.

The final P0 state is safe enough to proceed into this work, but this work is not already done.

---

#### 6. Semantic validation cost architecture remains

Semantic validation can be much more expensive than native RuleEngine checks.

Future P1.5 work still needs:

- separate native vs semantic budgets;
- contract complexity admission;
- honest semantic-cost warnings;
- possible compiled-validator caching only after thread-safety proof;
- short-circuit opportunities where structural failure already determines the outcome.

---

#### 7. LangChain example mismatch remains

The shipped example still has the known `manual_review` enum mismatch.

This is intentionally deferred to P1 rather than mixed into P0 hardening.

Examples should eventually run in CI so future first-impression defects cannot drift silently.

---

#### 8. Deprecated / stale cleanup remains

Still deferred:

- `ValidationTimer` dead/deprecated code;
- stale `TelemetryEvent` mutable docstring;
- largely superseded unenforced-keyword warning path.

These are cleanup candidates after the structural gates are in place.

---

### Absent — still not built

The following remain product-roadmap items, not Phase 0 capabilities:

- no MCP server;
- no CLI;
- no git-hook / CI enforcement surface;
- no durable event store;
- no persistent history query layer;
- no production control-plane backend in this repo;
- no architecture graph;
- no multi-agent adapter normalization layer;
- no correction-hint loop exposed through MCP;
- no version-aware contract cache;
- no Policy IR;
- no Business Policy DSL;
- no Redis/distributed cache;
- no distributed circuit breaker;
- no RBAC/ABAC control-plane system;
- no Prometheus/OpenTelemetry adapter;
- no durable compliance WAL/SIEM pipeline.

These should not be pulled forward merely because P0 is closed.

---

## PHASES

The roadmap below separates **trust hardening** from **product expansion**.

The key sequencing rule after P0 is:

```text
P0 trust-critical semantics
        CLOSED
          ↓
P1 structural/mechanical hardening
          ↓
product integration phases
```

Do not immediately jump from P0 into MCP/control-plane feature growth without first establishing the development gates that P0 showed are still partly review-enforced.

---

### Phase 0 — Trust-critical deterministic foundation

**Status: CLOSED**

#### Problem

The original enforcement core worked, but contained trust-critical cases where CONGINE could:

- silently accept malformed/ambiguous contracts;
- silently ignore unsupported policy;
- confuse timeout and load shedding;
- bypass size controls when measurement failed;
- rely on concrete implementation details behind a port;
- silently weaken behavior because raw config strings bypassed enum identity branches;
- infer unverified regional endpoints;
- expose machine-facing enum representations inconsistently.

#### What P0 closed

- runner health through declared port capability;
- fail-closed unmeasurable payload/schema handling;
- dotted-key false-safety via admission rejection;
- unknown-type false-safety via admission rejection;
- `ValidationResult.is_enforced()`;
- `LoadShedError` vs deadline `TimeoutError`;
- strict boolean / enum / directory configuration parsing;
- single timeout default source;
- removal of placeholder regional routing;
- contract admission boundary;
- capability-aware admission;
- stable admission issue codes;
- machine-facing enum serialization;
- last-known-good preservation on rejected incoming contracts;
- configuration canonicalization + validation through `CongineConfig.__post_init__`;
- direct-vs-env configuration parity.

#### Final done evidence

```text
478 passed / 1 skipped
Ruff clean
N=5000 deterministic → 1 verdict
admission preflight 3/3 → 100%
2000/2000 load sheds → LoadShedError
deadline remains TimeoutError
false-safety corpus → all refused
configuration invariant parity → 6/6 PASS
```

#### Explicitly not claimed by P0

- universal admission behind storage;
- version-aware exact contract enforcement;
- partial-enforcement coverage metadata;
- fully hardened lifecycle;
- fully hardened PII sanitizer;
- mechanical architecture enforcement;
- durable evidence/history.

---

### P1 — Structural / mechanical enterprise hardening

**Status: NEXT**

#### Problem

P0 established the correct semantics, but some architecture/lifecycle guarantees are still protected by review and tests rather than mechanical repository gates.

Two potential layer-direction violations were caught manually during P0 implementation.

That must become mechanically enforceable before large feature expansion.

#### Required order

1. **Blocking mypy**
   - Protocol/type correctness must fail CI.
   - Do not keep `mypy ... || true`.

2. **Separate architecture/import dependency gate**
   - Enforce the actual six-layer dependency matrix.
   - This is separate from mypy.
   - Prevent examples such as `L3 → L4` and `L0 → L2`.

3. **Runtime composition-boundary Protocol checks**
   - Validate supplied implementations where useful at the assembly boundary.
   - Do not make the domain depend on concrete adapters.

4. **Transactional composition root**
   - validate config before starting resource owners;
   - construct passive components first;
   - if later construction fails, close everything already created;
   - start background services only after successful assembly.

5. **Lifecycle cleanup**
   - idempotent bounded `close()`;
   - `atexit.unregister` on normal shutdown;
   - use-after-close behavior explicit;
   - no mid-constructor thread/client leak.

6. **Telemetry shutdown ordering**
   - coordinated stop/ack;
   - worker finishes or exits before HTTP client closes;
   - broad exception catch only as a final safety net.

7. **Contract admission facade evolution**
   - reduce residual direct-`put()` bypass risk;
   - do not jump prematurely to full Policy IR unless the port change justifies it.

8. **PII sanitizer redesign**
   - redesign the current backreference pattern;
   - equivalence-test behavior;
   - only then migrate to RE2-safe implementation.

9. **Remove dead/stale structural debt**
   - `ValidationTimer`;
   - stale `TelemetryEvent` docstring;
   - review superseded warning paths.

10. **Repair and CI-gate examples**
    - fix LangChain `manual_review` mismatch;
    - run examples as part of CI so docs/examples cannot silently drift.

#### Done condition

P1 is done when structural correctness is no longer dependent primarily on reviewer memory.

At minimum:

```text
mypy blocks type/Protocol regressions
architecture gate blocks forbidden imports
composition failures clean up resources
normal close unregisters lifecycle hooks
telemetry shutdown is coordinated
examples execute in CI
PII sanitizer redesign is behaviorally proven
```

---

### P1.5 — Semantic validation safety and cost hardening

**Status: PLANNED AFTER P1**

#### Problem

The semantic validator is useful but materially more expensive than the native deterministic engine.

Increasing the global timeout would hide the problem rather than solve it.

#### Work

- separate native and semantic execution budgets;
- expose honest semantic-validation cost warnings;
- reject pathological semantic complexity during contract admission;
- investigate validator preprocessing/compilation caching;
- prove thread safety before sharing compiled validators;
- short-circuit semantic work where earlier deterministic structure already decides the outcome;
- establish reproducible benchmark thresholds.

#### Done condition

Semantic validation can be enabled without turning "more validation" into unpredictable degradation/silent non-enforcement behavior.

---

### Product Phase A — CLI / developer boundary

**Status: NOT STARTED**

#### Problem

Coding agents and developers modify repositories; they do not naturally call a Python decorator around every change.

The first product expansion must expose the existing deterministic semantics at a developer-controlled boundary.

#### Direction

Build a CLI/pre-commit/CI-friendly surface that invokes the same core validation semantics.

Examples:

```text
congine validate ...
congine validate-diff ...
```

The CLI must not invent a second meaning for:

- contract admission;
- degraded state;
- breach codes;
- strict enforcement.

#### Done condition

A repository change can be deterministically validated from the command line with machine-readable output and stable exit behavior.

---

### Product Phase B — MCP / agent-loop integration

**Status: NOT STARTED**

#### Problem

An AI coding agent needs the result before it finishes or commits a bad change.

#### Direction

Expose the same evaluator through MCP.

The target workflow:

```text
agent proposes change
      ↓
CONGINE validates
      ↓
BLOCK
      ↓
stable breach information
      ↓
agent corrects
      ↓
revalidate
      ↓
PASS
```

MCP is an early feedback surface, not the sole enforcement boundary.

Defense in depth remains:

```text
MCP
  → interactive earliest feedback

CLI / pre-commit
  → developer boundary

CI
  → authoritative repository boundary
```

#### Done condition

Claude Code / Cursor / another MCP client can call CONGINE and receive deterministic, machine-readable results derived from the same core semantics as CLI/SDK validation.

---

### Product Phase C — Durable evidence and history spine

**Status: NOT STARTED**

#### Problem

Current telemetry is in-memory/best-effort and disappears with the process.

Without durable records there is no reliable project memory, audit history, convergence analysis, or later Control Plane.

#### Direction

Introduce a durable event-store abstraction.

Target topology:

```text
IEventStore / evidence port
    ├─ SQLite local/offline
    └─ PostgreSQL shared/enterprise later
```

Important design constraints from day one:

- version event schema;
- tenant scope every durable record;
- separate metadata/hash evidence from optional human content;
- design retention/erasure deliberately;
- distinguish best-effort telemetry from durable evidence;
- append path separate from query projections where useful;
- do not make the future control plane query the validation hot path directly.

#### Done condition

Validation/evidence records survive restart and can be queried reliably without changing deterministic verdict semantics.

---

### Product Phase D — Deterministic correction + context/token economics

**Status: NOT STARTED**

#### Problem

A breach that is only human-readable may cause an agent to retry with full context repeatedly.

#### Direction

Add deterministic, table-driven correction hints.

No LLM in the verdict/correction-decision core.

Then add:

- diff/context compression;
- relevant-rule injection;
- convergence/retry instrumentation;
- token-cost measurement.

#### Done condition

A blocked agent can repair a deterministic breach using concise machine-readable guidance, and the system can measure retries/tokens/convergence.

---

### Product Phase E — Architecture/history intelligence + agent adapters

**Status: NOT STARTED**

#### Problem

Durable events are raw evidence; they do not automatically become architecture intelligence.

Different agents/frameworks also need normalized interaction without contaminating the core.

#### Direction

Two tracks:

**History / architecture intelligence**
- architecture graph;
- forbidden-edge/cycle/reachability validation;
- recurring violation patterns;
- project hotspots.

**Agent adapters**
- normalize provider/framework behavior into canonical requests/results;
- treat every agent as untrusted;
- keep provider identity outside the RuleEngine;
- isolate per-agent credentials/context/cache;
- do not train/learn inside the verdict path.

#### Done condition

Multiple agents can use the same CONGINE semantics, and durable history can produce deterministic architecture/pattern signals.

---

### Future — Executable Organizational Policy / Policy IR

**Status: LONG-TERM, NOT CURRENT IMPLEMENTATION**

The long-term authoring model may become:

```text
JSON contracts ─────┐
UI authoring ───────┤
API policy ─────────┤
Business DSL ───────┘
        ↓
Contract / Policy Compiler
        ↓
versioned Policy IR
        ↓
deterministic evaluator
```

P0's contract admission boundary is the seed of this compiler-like architecture.

It is **not** yet a full Policy IR.

Do not build the Business Policy DSL until the current contract/admission semantics and versioning model justify it.

---

### Enterprise / distributed capabilities — directional only

Do not start these before a concrete deployment/compliance signal exists:

- Redis/distributed cache;
- distributed circuit breaker;
- multi-pod coordination;
- RBAC/ABAC control-plane enforcement;
- OpenTelemetry/Prometheus adapter;
- SIEM/audit export;
- durable compliance WAL;
- advanced tenant-level distributed registry.

Each should attach through ports/adapters rather than rewrite the deterministic evaluator.

---

## DEVELOPMENT INVARIANTS AFTER P0

These are now part of the constitutional layer of CONGINE.

1. **Deterministic judgment**  
   No probabilistic model enters the final verdict path.

2. **No silent non-enforcement**  
   If CONGINE cannot execute claimed policy semantics, it must refuse activation or expose not-enforced truth explicitly.

3. **Admission before production activation**  
   Raw contract text is not automatically active policy.

4. **Configuration canonical before composition**  
   Direct, environment, future CLI, and API configuration must converge on one `CongineConfig` semantics.

5. **Failure to evaluate is not a breach**  
   Infrastructure/resource/input-evaluation failure must not fabricate organizational violations.

6. **Same meaning across all entry points**  
   SDK, CLI, MCP, CI, and future adapters must invoke the same contract/evaluation semantics.

7. **Dependencies point inward**  
   Future features grow around the deterministic core.

8. **Ports are real boundaries**  
   Consumers must not reach into undeclared concrete properties because today's adapter happens to expose them.

9. **Stable machine-facing codes**  
   Future automation must not parse English or Python enum representations.

10. **Evidence over claims**  
    Unmeasured behavior must be labeled planned/partial rather than promoted to a guarantee.

---

## DAILY LOG

<!-- Append dated entries below this line. NEVER erase existing entries on re-run. -->

### 2026-06-14
- Ran the deep system-analysis prompt (Document 2). Read all 36 source modules, config, docs, the three audits,
  key tests, the LangChain example, and the prior `docs/context/` analysis. Produced
  `docs/system-analysis/{00_SYSTEM_MAP,01_FILE_INVENTORY,02_FAILURE_PATHS,03_SPEC_RECONCILIATION}.md` and created
  this file. **Findings:** architecture is a real, disciplined 6-tier hexagon; all 7 hot-path guarantees hold and
  none has regressed; top correctness items remain (in order) the multi-tenant eviction lifecycle (B9), the
  `requires-python` floor (A1), and silently-ignored schema keywords (B14). No source code was modified (read-only
  analysis).

### 2026-08-17 — P0 trust-critical hardening completed and closed
- P0 hardening executed in isolated worktree `C:/Users/USER/Documents/CONGINE_V2/congine-p0-hardening`,
  detached at source commit `49a2f93`. The original dirty working tree remained byte-for-byte untouched.
- Closed the eight trust-critical P0 findings: port-health abstraction leak; fail-open unmeasurable size guard;
  dotted-path false safety; unknown type fail-open activation; missing explicit `is_enforced()` signal; load-shed
  collapsed into timeout; permissive/ambiguous configuration parsing; placeholder regional routing.
- Added pure L2 contract admission before the production cache. Unknown/ambiguous/unenforced contract semantics are
  refused rather than silently activated. Admission is based on the active evaluator capability set.
- Added stable machine-facing admission/degradation semantics and verified real serializer/log/event boundaries.
- Final closeout broadened the configuration finding: all five enum-backed `CongineConfig` fields could accept raw
  strings, and four affected identity-based behavior. Two pre-existing severe cases were reproduced:
  `fail_mode="strict"` could silently lose hard enforcement, and raw `deployment_mode="multi_tenant"` could bypass
  the multi-tenant guard.
- Moved configuration ownership to `CongineConfig.__post_init__`: normalize first, then execute the existing
  `validate()`. Removed the redundant `from_env()` validation owner. Direct and environment construction now share
  one canonical validation boundary.
- The closeout exposed 35 tests whose configs had been invalid but silently accepted. Tests were repaired by
  declaring their intended cleartext behavior (`allow_cleartext=True`) where appropriate; a mistaken bulk change
  that would have weakened the HTTPS-enforcement test was caught and removed.
- Final evidence: **478 passed / 1 skipped**, Ruff clean, determinism **N=5000 → one unchanged verdict hash**,
  admission preflight **3/3 = 100%**, false-safety corpus fully refused, configuration invariant parity **6/6 PASS**,
  and **2000/2000** saturation attempts classified as `LoadShedError`.
- P0 is now **CLOSED**. Three explicit structural deferrals remain: direct raw `schema_storage.put()` admission
  bypass, version-aware fail-closed enforcement, and partial-enforcement metadata.
- Next required work is **P1 structural/mechanical hardening**, beginning with blocking mypy **and a separate
  import/layer dependency gate**. Mypy must not be described as enforcing the hexagonal dependency direction by
  itself.
