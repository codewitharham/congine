# PROMPT D2 — FORMAL SUITE AUTHORING (replaces PROMPT_B)

## How to use

**Where:** Claude Code. **Run after D1 completes.**

**Attach:**
1. `V2_DOC_SUITE_SPEC.md` — **binding** (the coverage matrix in §4 is enforced)
2. Your answers to D1's founder questions
3. `Congine_Complete_Reference__2_.md` — narrative and strategic framing
4. `CONGINE_GPT_PROMPT.md` — **for §22–§34 only**: the three domains, MCP, Business Policy DSL,
   Policy IR, Executable Organizational Policy, and the product language contract. Ignore its design
   sections (§35 onward) entirely; they belong to the website task.

Read from repo: `ARCHITECTURE_CURRENT.md`, `docs/_suite/gap/GAP1..GAP4.md`.

**How to run:** paste **the harness (Part 1) + exactly one document spec (Part 2)**. One document per
run. Never two.

**Order:** F03 → F04 → F02 → F06 → F07 → F05 → F08 → F01. (F09 comes from `PROMPT_D3`.)

---

# PART 1 — THE AUTHORING HARNESS (paste every time)

```text
=== BEGIN SUITE AUTHORING HARNESS ===
```

# ROLE

You are a principal engineer and technical author producing one document in the **Congine Formal
Document Suite** — the authoritative record of the system, written to be read by someone encountering
it for the first time or the thousandth.

These documents are the face of the product. They must be complete enough that a reader finishes with
no unanswered questions, precise enough that an engineer can act on them, and honest enough that an
auditor trusts them.

# TIME AND EFFORT

**TAKE AS MUCH TIME AND AS MANY SESSIONS AS YOU NEED. THIS IS EXPLICITLY AUTHORIZED AND EXPECTED.
THERE IS NO TIME PRESSURE.**

Read every named source before writing. Plan the document's structure before drafting. If context runs
low, write what is complete, update the ledger, and report the resume point. **Never thin a section to
fit remaining context.** A document delivered across three sessions is a success; a shallow one
delivered in one is a failure.

# SOURCES AND PRECEDENCE

| Rank | Source | Authoritative for |
|---|---|---|
| 1 | **The codebase** | Any fact about what the code does today |
| 2 | **`ARCHITECTURE_CURRENT.md`** | Structure, flows, invariants, seams, debts, config, contract semantics |
| 2a | **`ARCHITECTURE_CURRENT.md` current-state header block + §16 reconciliation table** | **Override the rest of that document** wherever they disagree. Together they are the reconciliation record against the **P1 CLOSED** commit `b482bc4`, and §16 gives each historical debt a verified status (resolved / open / superseded / deferred) |
| 3 | **`docs/_suite/gap/GAP1–4`** | Per-file narrative, decision rationale, verified examples, measurements |
| 3a | **`docs/_suite/hardening/P0_COMPLETION_REPORT.md`** | The eight P0 findings, the intentional breaking changes, and what was deliberately deferred. **Stated** rationale — rare in this codebase |
| 3b | **`docs/_suite/hardening/P1_COMPLETION_REPORT.md`** (incl. its *Final P1 Closure* section) | The P1 structural decisions and their stated rationale: the explicit layer matrix, the L0 value-contract reclassification, the compatibility re-export, `ISyncRunner`, runtime Protocol validation, transactional composition, terminal lifecycle, RE2 sanitizer, reproducible evidence — **and the list of what P1 deferred** |
| 4 | **Founder answers** | Design rationale that exists nowhere in code |
| 5 | **Complete Reference** | Narrative framing, market context, strategic argument |
| 6 | **GPT prompt §22–§34** | MCP, Business Policy DSL, Policy IR, product language |

Where 5 or 6 makes a technical claim that 1–3 contradict, **1–3 win and you note the contradiction**.

> **Expect stale claims in every source below rank 2a, including this repository's own documents.**
> The codebase moved several times after most of this material was written — through P0 closure and
> then P1 closure. The specific claims to distrust on sight:
>
> - any description of the **union-type defect** as live;
> - any **"46 fields"** / **"47 fields"** (now 48 — and measure, do not quote);
> - any **"37 files"** (now 40 — measure);
> - any **"11 invariants"**;
> - any **"seven ports"** or **"eight ports"** — enumerate `congine_core.ports.__all__`, and never
>   omit **`ISyncRunner`**;
> - any statement that **`region` is read by nothing**;
> - any statement that **load shed and timeout are indistinguishable**;
> - any statement that **unenforced keywords are silently accepted**;
> - any statement that the dependency rule is **"dependencies point inward"** or
>   **"a layer may import any lower-numbered layer"** — it is an **explicit matrix**, and `L4 → L2`
>   and `L4 → L3` are forbidden;
> - any statement that **`TYPE_CHECKING` imports are exempt** from the architecture policy;
> - any statement that the **canonical value contracts live in `domain/models.py` (L2)** — they are
>   in **`congine_core/models.py` (L0)**;
> - any statement that **`BackgroundSyncWorker` depends on `SyncContractsUseCase`**;
> - any test count other than the current baseline (**613 passed / 1 skipped**) presented as current;
> - any claim that **constructor failure leaks threads or `atexit` hooks**, or that the
>   **`QueueEventBus` stop race** is live — both were closed in P1;
> - any claim that **`pii_sanitize` uses stdlib `re`**, or that **`ValidationTimer`** exists.
>
> Each was true and is not.

# ABSOLUTE RULES

0. **Never document unenforceable contract semantics as silently accepted.** For any
   safety-critical contract documentation, keep these five concepts **distinct and separately
   named** — conflating them is how false-safety claims get generated:

   | Concept | What it answers |
   |---|---|
   | **Native rule vocabulary** | which keywords the in-process `RuleEngine` evaluates |
   | **Semantic evaluator vocabulary / capability** | which further keywords the optional JSON Schema evaluator enforces, and under which flags (`format` needs `semantic_format_checking`) |
   | **Contract admission** | whether a contract may become **active policy**, judged against the capability set the wired evaluators actually provide |
   | **Evaluation result** | whether the payload conformed — *and separately* whether it was evaluated at all (`is_pass()` vs `is_enforced()`) |
   | **Enforcement action / posture** | what the host does about it (`fail_mode`) |

   The governing sentence: **a contract with semantics the active evaluator stack cannot enforce
   must not silently become active.** Where current admission refuses such a contract, say so;
   where the `schema_storage.put()` bypass still allows it, say *that*, precisely, and mark it
   deferred. Derive the keyword sets from `domain/schema_vocabulary.py` at HEAD — never hardcode
   them.


1. **Status labelling is mandatory.** Every capability is marked `IMPLEMENTED`, `PARTIAL`, or
   `PLANNED — Phase X`. `ARCHITECTURE_CURRENT.md` §15 confirms eight capabilities absent: MCP server,
   CLI, persistent event store, history queries, correction hints, architecture graph, agent adapters,
   adaptive routing. **Never describe any of these as existing.** A document that overstates status is
   worthless to the exact audience it targets.

2. **Cite everything.** Technical claims cite `ARCHITECTURE_CURRENT §n` or `file.py:line`. Measurements
   cite `GAP4`. Examples cite `GAP3` and must be ones that were actually executed.

3. **The safety-critical statements appear wherever relevant, unsoftened.** These were rewritten on
   2026-08-17 against `6345a1e`; the previous three are recorded at the end so you can recognise them
   in older drafts and *not* repeat them.

   - **The rule engine reads eight schema keywords by default.** Everything else — `minLength`,
     `format`, `const`, `additionalProperties`, `items`, `allOf`, … — is not enforced unless semantic
     validation is enabled (§13.1, §13.2). **Since P0-04 a contract using one of them is refused at
     load** rather than loaded and ignored. Both halves must be stated: the vocabulary is still
     narrow, *and* the system no longer pretends otherwise.
   - **A contract CONGINE cannot fully interpret never becomes active policy** (§13.8, invariant
     G12). Unknown type names, empty unions, dotted property keys, uncompilable patterns, malformed
     grammar and unenforceable clauses are all refused before caching. State the **consequence**
     plainly, because it is a real trade: a refused contract is absent, so on a cold cache every
     guarded call against it raises `CongineContractNotFoundError`. Silent non-enforcement was traded
     for a loud outage, deliberately.
   - **Admission runs on the loader path only** (debt D17). A direct `schema_storage.put()` bypasses
     every check, and the false-safety case reproduces there — demonstrated in GAP3.6c. **This is now
     the single most important warning in the suite.** Do not soften it, and do not omit the two
     mitigations (a CI AST guard, and `admit_contract` being public so embedders can run the same
     check).
   - **`is_pass()` alone cannot tell you whether the policy was evaluated** (§11.2, P0-05). A
     degraded result carries `status="fail"` with zero breaches, so `is_pass()` is `False` both for a
     genuine violation and for a validator that never ran. Callers must ask `is_enforced()` first.
   - **`region` is metadata and selects nothing** (§12.4). Setting `CONGINE_REGION` without
     `CONGINE_BASE_URL` raises. Between `49a2f93` and `6345a1e` it briefly selected an endpoint; that
     was reverted because the hostnames were unverified — a governance SDK must never infer a
     credential destination.

   **Three warnings from the v1 batch are now WRONG. Never write them:**

   | Retired warning | Why it is wrong now |
   |---|---|
   | "A union type declaration causes silent permanent degradation (D18)" | **Fixed in `49a2f93`.** Unions are a first-class enforced spelling. Mention only as history, in F02/F05/F09. |
   | "Unenforced keywords are *silently* ignored" | Half wrong. They are still unenforced, but a contract using them is **refused at load**, not silently accepted. |
   | "`region` is a dead configurable that nothing reads" | It is documented metadata and is now enforced *as* configuration — setting it without a base URL raises. |
   | "Dependencies point inward" / "a layer may import any lower-numbered layer" | Insufficient, and this exact formulation caused a real defect. The rule is an **explicit matrix**: `L4 → L2` and `L4 → L3` are forbidden. |
   | "`TYPE_CHECKING` imports are exempt from the layer rules" | No longer true. They are judged by the same matrix, with **zero exemptions and zero allowlist entries**. |
   | "The value objects live in `domain/models.py` (L2)" | They are in **`congine_core/models.py` (L0)**. `domain/models.py` is a compatibility re-export that keeps L2 identity for the gate. |
   | "`BackgroundSyncWorker` holds a `SyncContractsUseCase`" | It depends on the L1 **`ISyncRunner`** port. |
   | "Constructor failure leaks threads and `atexit` hooks" | Closed in P1 — composition is transactional. |
   | "`QueueEventBus.stop()` races its drain thread" | Closed in P1 — shipping and client closure are serialised. |
   | "`pii_sanitize` uses stdlib `re`" / "`ValidationTimer` exists" | Both false: the sanitizer is RE2-only, and `ValidationTimer` was removed in P1. |

4. **Determinism is the governing invariant.** Nothing you write may suggest a model participates in a
   verdict. Where model assistance is discussed (Business Policy DSL authoring), state the design-time
   versus runtime separation explicitly.

5. **Dual voice.** Technical precision, with a metaphor only where it explains a *mechanism*. If the
   metaphor can be deleted without loss, delete it. Keep the metaphorical world consistent across the
   whole suite — establish it in F03 and reuse it.

6. **Enumerate; do not summarise.** No "etc.", no "and others", no capped lists. If there are 48
   config fields, there are 48 rows.

7. **Document the ugly parts.** The debt register (22 findings; **15 closed, 7 open** — report both
   halves), the residual admission bypass (D17), the deferrals P0 recorded rather than solved
   (see the deferrals list in `docs/_suite/hardening/P0_COMPLETION_REPORT.md` and in the P1 completion report: version-aware fail-closed,
   partial-enforcement metadata), and the advisory limitation of
   the MCP surface. A document that hides its gaps is not trusted on its claims.

   **And document the fixes with the same discipline.** A suite that lists only open debt understates
   the system as badly as one that hides it. Where a defect was closed, say so, say when, and — where
   it is instructive — say what the *wrong* first answer was. Two are worth carrying: `region` was
   answered in the wrong direction first (§17 Q1), and the P0 pass hit an L3→L4 and an L0→L2 layering
   violation by hand before catching them in review (the two architectural bugs caught in flight,
   recorded in `docs/_suite/hardening/P0_COMPLETION_REPORT.md`). Both are evidence that the architecture
   is enforced by attention rather than by tooling — which is a real finding, not an embarrassment.

8. **Do not modify source code.** You write to `docs/_suite/` only.

# OUTPUT

Write to `docs/_suite/<ID>_<NAME>.md`. Begin every document with this control block:

```markdown
| | |
|---|---|
| **Document ID** | CGN-F0n |
| **Title** | … |
| **Version** | 1.0 |
| **Date** | … |
| **Source commit** | … |
| **Derived from** | ARCHITECTURE_CURRENT.md §…; GAP…; … |
| **Status** | Draft / Approved |
| **Owner** | … |
```

Then a **"How to read this document"** section (one short page: who it is for, how it is organised,
what the status labels mean, where to start).

# QUALITY GATE (verify before declaring done)

- [ ] Every section required by the spec is present.
- [ ] Every concept marked **Deep** for this document in the coverage matrix is genuinely deep.
- [ ] No unbuilt capability described as existing; every capability carries a status label.
- [ ] Every technical claim cites a source.
- [ ] The three safety-critical warnings appear where relevant.
- [ ] Enumerations are complete, not truncated.
- [ ] Cross-references to other suite documents resolve (or are marked `[forthcoming]`).
- [ ] A reader unfamiliar with Congine could follow it start to finish.

# FINAL REPORT (in chat)

```
## DOCUMENT COMPLETE: <path>
- Sections written; approximate length
- Coverage-matrix concepts marked Deep here — confirmed covered: <list>
- Facts I could not verify, and what I did: <list>
- ❓ QUESTIONS FOR THE FOUNDER: <required; things only you know>
- Contradictions found between sources: <list>
- Cross-references other documents must add: <list>
```

Also update `docs/_suite/PROGRESS.md` with document status and the resume point.

```text
=== END HARNESS ===
```

---

# PART 2 — DOCUMENT SPECS (paste exactly ONE)

---

## SPEC F03 — ARCHITECTURE & DESIGN DOCUMENT (write first)

```text
=== DOCUMENT SPEC: F03 ARD ===
Target: docs/_suite/F03_ARCHITECTURE_AND_DESIGN.md
Primary source: ARCHITECTURE_CURRENT.md §3–§11, §14, §15 + GAP1, GAP2
Reader: an engineer who must understand, extend or evaluate the system
Depth: deep technical. This is the longest document after F02.

PURPOSE: The authoritative account of how Congine is built and why it is built that way. It is the
suite's technical spine — every later document reuses its vocabulary.

REQUIRED SECTIONS:
1. Architectural position — a library inside a host process, and every consequence that follows
2. The governing style — hexagonal ports-and-adapters; policy vs mechanism. State the dependency
   rule as an **explicit matrix, not a numeric ordering**: "inward-only" may appear as intuition
   only if immediately qualified. Reproduce the matrix (L0→L0; L1→L0,L1; L2→L0,L1,L2;
   L3→L0..L3; L4→**L0,L1,L4**; L5→all) and state plainly that **`L4 → L2` and `L4 → L3` are
   forbidden** — infrastructure reaches policy through ports, not concrete reverse dependencies.
   A reader must not be able to infer "L4 may import L2 because 2 < 4"
3. The six layers — responsibility, contents, permitted dependencies, and the arguable placements
   (discuss each honestly). **L0 owns the canonical cross-layer value contracts** (`models.py`) as
   well as config/exceptions/limits; **L2 owns deterministic judgment and rules**. Explain the P1
   reclassification and the **L0 admission principle** — pure, dependency-light, cross-layer
   canonical, no I/O, no outer dependencies, not orchestration — so L0 does not become a dumping
   ground. Cover `domain/models.py` as a **compatibility re-export that retains L2 identity for the
   gate**, and be precise: the canonical `__module__` changed; the relocation was *not*
   byte-identical, though public symbols and supported import paths were preserved
4. The dependency graph — runtime **and** `TYPE_CHECKING` edges, judged by the **same** matrix.
   Cover the mechanical gate (`tools/check_architecture.py`), its **zero allowlist entries and zero
   `TYPE_CHECKING` exemptions**, and the fact that it was **falsified** by re-injecting removed
   edges rather than merely observed passing. Include the historical lesson honestly: the previous
   checker encoded `target_layer <= source_layer`, reported zero violations, and was green for the
   wrong reason while seven forbidden edges were live (§4.4)
5. Ports and adapters — **enumerate the `ports/` modules from `congine_core.ports.__all__` at HEAD;
   do not quote a count and do not omit `ISyncRunner`** — plus the in-domain IValidator seam, with
   exact signatures and the obligations of any replacement (§5, GAP3.8). Give **`ISyncRunner`** its
   own treatment as the worked example of the model: `BackgroundSyncWorker` (L4) needed one method
   from `SyncContractsUseCase` (L3), so P1 named that obligation as a port and the edge became
   `L4 → L1`, with the use case unchanged. **State that implementing a Protocol as written is now
   sufficient to be wired** — §5.9 records that gap as closed, and it was a real trap before.
   Cover **runtime `runtime_checkable` Protocol validation** at composition seams, and scope the
   claim correctly: mypy gives static signature compatibility, the runtime check gives **early
   structural compatibility (method presence, not behaviour)**, and behavioural tests give the
   semantic obligations. Do not present the runtime check as proof of behavioural conformance
6. The composition root — sixteen constructions, one file; every configuration branch (§6)
7. Lifecycle — construction order and why it is forced; bootstrap sync/async; background threads;
   teardown; the tenant registry and its eviction semantics post-P0-1 (§7). Cover the P1 lifecycle
   properties: **transactional composition** (partial construction rolls back every acquired
   resource exactly once, leaks no thread/client/hook, keeps the original failure visible, and
   permits a later clean construction) and **terminal close** (`closed`, `ensure_open()`,
   idempotent, thread-safe, bounded by fixed constants, `atexit` hooks unregistered, registries
   replace rather than return closed containers). State explicitly that **use-after-close raises
   `CongineLifecycleError` and is *not* a degraded `ValidationResult`** — degradation means
   enforcement was attempted and could not complete; using a terminal object is a caller error
8. Control flows — the hot path plus boot, sync and telemetry, step-numbered with citations (§8).
   **The boot/sync flow now has an admission gate before the cache write** (§8.2 step 10a)
9. Concurrency and state — threads, locks, permit accounting, the re-entrancy guard, sync/async
   capacity sharing, every piece of shared mutable state (§10)
10. The data model — the **five** canonical value contracts in **L0** (`congine_core/models.py`):
    the four frozen dataclasses, what immutability buys (§11), and `DegradedReason` as a `StrEnum`,
    with the `is_pass()` / `is_enforced()` pair. Explain why `TIMEOUT` and `LOAD_SHED` are distinct
    members and why an over-budget payload is an `INPUT_BOUNDS` **breach** rather than a degradation
11. **Contract admission as an architectural boundary** (§13.8) — why it is L2 and pure, why the
    rule engine was deliberately *not* changed, why the verdict/action split puts judgement in the
    domain and consequence in L3, and why it takes a capability set rather than a feature flag
12. Invariants — all **sixteen**, each with mechanism, evidence and backing test (§14). Draw the
    three-way distinction §14.9 makes: **G1–G11 are mechanical/runtime** (nothing stalls, deadlocks,
    leaks or blocks); **G12–G14 are epistemic/trust invariants** — they constrain what CONGINE may
    claim (policy activation truth, configuration truth, evaluation/enforcement truth); and
    **G15–G16 are structural invariants** — the mechanically enforced layer matrix, and transactional
    composition with terminal close
13. Design decisions — the significant ones from GAP2, each with context, choice, alternatives and
    consequences. Mark `RATIONALE NOT RECORDED` honestly where it applies.
14. Extension seams — where each of the eight planned capabilities attaches; the six that need no
    L2/L3 change and the two that do (§15). **All marked PLANNED.** Note that a ninth seam now
    *exists in code*: `contract_admission.py` is named in §15.10 as where a contract compiler /
    Policy IR grows from
15. Known architectural debt — from §16, with severity and what each blocks. Report **both** the
    closed and open halves (15 closed, 7 open)

MUST COVER (edge cases):
- Why the domain performs no I/O, and what that purchases
- Why the composition root is the sole construction site
- Permit release in a done-callback rather than on timeout ("honest accounting")
- Nested validation running inline rather than deadlocking the pool
- Prime-in-place rather than clear-then-refill, and the race it prevents
- Telemetry emitted before fail-mode enforcement, and why that ordering is a guarantee
- Guard mode and fail mode as independent raise sites
- What is NOT created in the standalone/offline topology
- **Why `LoadShedError` lives in L0 and not beside the executor that raises it** — placing it in
  `infrastructure/` would force an L3→L4 import. Same question, same answer, for
  `ContractAdmissionMode` living in L0 `config.py` rather than in the domain that applies it
- **Why `except LoadShedError` must precede `except TimeoutError`** — it subclasses it, so reversing
  the two silently reinstates the conflation P0-06 removed
- **Why `CongineConfig.__post_init__` normalizes and then calls `validate()` rather than
  reimplementing it** — one owner for the invariants, and an AST test that proves `from_env` does
  not validate twice (§12.2, G13)
- **Why the P0-era enums are `enum.StrEnum` while `Region`/`FailMode`/`DeploymentMode` are not** —
  a `(str, Enum)` serialises correctly through `json.dumps` but renders as `Class.MEMBER` under
  `str()` and f-strings; the older three are left alone because changing them would alter output
  elsewhere

ESTABLISH HERE: the metaphorical world the rest of the suite reuses. Name it, assign each major
component a stable role, and record the cast in an appendix.
=== END SPEC ===
```

---

## SPEC F04 — SOFTWARE REQUIREMENTS SPECIFICATION

```text
=== DOCUMENT SPEC: F04 SRS ===
Target: docs/_suite/F04_SOFTWARE_REQUIREMENTS_SPECIFICATION.md
Primary source: ARCHITECTURE_CURRENT.md §12, §13, §14 + existing CGN-DOC-02 draft + GAP4
Reader: engineers, QA, and any evaluator verifying the system against its claims
Depth: formal and exhaustive

PURPOSE: State what the system must do, in a form permitting direct verification. A prior SRS draft
exists (CGN-DOC-02); this rebuilds it against verified reality rather than intent.

REQUIRED SECTIONS:
1. Introduction — purpose, scope, definitions, references
2. Overall description — product perspective, principal functions, user classes, operating environment,
   constraints and assumptions
3. Functional requirements — FR-nn, grouped: contract management, validation, enforcement,
   integration, observation. **Each carries a status label**, because several previously-listed FRs
   (CLI, durable events, MCP service) are PLANNED, not implemented.
4. Non-functional requirements — NFR-nn: performance, reliability, security, maintainability,
   portability. Each with its verification method **and, where GAP4 measured it, the measured value**.
5. Configuration requirements — all **48** fields with env var, type, default, effect, wiring target
   (§12). Cover the **construction-path parity requirement** explicitly (G13, §12.2): configuration
   must mean the same thing whether it came from `from_env()`, direct construction, a test, or a
   future CLI/API adapter, and validation has exactly one owner. State `region`'s status correctly —
   documented metadata that selects nothing, and an error if set without a base URL.
6. Contract requirements — what a contract may express; **what it may express and have unenforced**
   (§13.1–13.2); and **what it may not express at all**, because admission refuses it (§13.8). The
   seven `ContractAdmissionCode` values belong here as a requirements table, since they are the
   normative statement of the admitted contract grammar.
7. Interface requirements — the public API surface (GAP3.1); both integration modes; the advisory
   limitation of the tool-based mode
8. Requirements traceability matrix — requirement → satisfying component → verifying test

MUST COVER:
- Requirements that the current code does NOT satisfy — state them with status, do not omit them.
  Three are recorded as deliberate deferrals rather than oversights (see the deferrals lists in
  `docs/_suite/hardening/P0_COMPLETION_REPORT.md` and the P1 completion report) and should be stated as
  such: admission on every write path (D17), version-aware fail-closed, partial-enforcement metadata
- Every documented limit and its value
- Determinism as a requirement, with the GAP4.3 measurement as its evidence
- **The result-semantics requirement**: a caller must be able to distinguish "evaluated and
  conforming" / "evaluated and violated" / "not evaluated" (P0-05), and must be able to distinguish
  a saturated system from a slow one (P0-06). Both are verifiable from `ValidationResult` alone
- **Fail-closed on unmeasurable input** (P0-02) — and the distinction the requirement turns on:
  a *measurable* oversize is a genuine `INPUT_BOUNDS` breach; an *unmeasurable* input is a
  degradation with zero breaches, because CONGINE cannot claim a limit was exceeded by something it
  never measured
=== END SPEC ===
```

---

## SPEC F02 — DOMAIN COMPENDIUM (the centrepiece)

```text
=== DOCUMENT SPEC: F02 DOMAIN COMPENDIUM ===
Target: docs/_suite/F02_DOMAIN_COMPENDIUM.md
Primary source: ARCHITECTURE_CURRENT.md §13, §15; Complete Reference Part III; GPT prompt §22–§34;
                GAP3.6
Reader: anyone who must understand what Congine actually thinks — the deepest reader
Depth: THE DEEPEST DOCUMENT IN THE SUITE. Expect it to be the longest.

PURPOSE: This is the document that carries the "no gaps" requirement. It takes each of the product's
key ideas to the bottom — the ideas are the product's intellectual content and they do not belong
scattered through an architecture document.

REQUIRED PARTS (each a major section):

PART A — CONTRACTS: THE STANDARD
- What a contract is; why human-authored; why machine-readable; why version-controlled
- The exact eight keywords the rule engine reads (§13.1) — enumerate them
- THE COMPLETE LIST OF KEYWORDS NOT ENFORCED BY DEFAULT (§13.2) — still a safety-critical table,
  but its meaning has changed: these are no longer *silently* ignored. A contract using one is
  refused at load under default configuration, and admitted when an evaluator that enforces it is
  wired. Show both outcomes (GAP3.6b)
- **THE CONTRACT ADMISSION BOUNDARY (§13.8) — the centre of Part A.** The seven
  `ContractAdmissionCode` values as the normative grammar; why a contract CONGINE cannot interpret
  is a *publication error* rather than a runtime condition; why the rule engine stays defensive
  while authoring errors moved to load time; what `strict` and `warn` each can and cannot do — and
  specifically why a permissive mode that could admit an unenforceable contract would rebuild the
  exact failure the boundary removes; what happens to a refused contract (skipped, not cleared, so
  last-known-good keeps serving; absent on a cold cache, so calls fail closed)
- **The residual bypass (D17)**, with the GAP3.6c demonstration. **Do not soften this** — it is the
  one open false-safety path, and Part A is where a reader learns to care about it
- Dot-notation asymmetry: where it works, and why a dotted `properties` key is now refused rather
  than silently matching nothing
- Rule ordering and why each rule defers to its predecessors
- Contract authoring methodology; versioning; the graduated enforcement ladder
  (observational → permissive → strict) as an adoption mechanism
- **Historical, and worth one honest paragraph:** the union-type defect (D18). It caused silent
  permanent degradation, it was the most safety-critical fact in the v1 corpus, and it is **fixed** —
  unions are enforced. Include it because it is the clearest motivation for why the admission
  boundary exists at all: the fix alone would have traded a loud total failure for a quiet partial
  one, since a union containing an unrecognised name matches everything. Both changes were needed.
  **Past tense throughout.**

PART B — THE VERDICT: JUDGMENT
- The six rules, in evaluation order, each with semantics and edge cases (null handling, the
  bool-is-not-a-number decision, unrecognised type names, regex anchoring, length caps)
- Determinism: what it means, what it purchases, and precisely what would destroy it
- Breach structure and why it is designed for machine consumption
- **Conformance vs enforcement — `is_pass()` and `is_enforced()` (§11.2).** The three-state model,
  why a degraded result is `status="fail"` with zero breaches, and why a caller reading only
  `is_pass()` believes a policy was enforced when it was not. Include the six `DegradedReason`
  values, and the distinction between *"we evaluated too slowly"* (`timeout`) and *"we did not
  evaluate"* (`load_shed`). State the posture guidance: "not enforced" is unknown conformance, not
  a pass
- The three enforcement policies and their interaction with the three guard modes (independent
  raise sites — make this a matrix)
- Why no model sits on the verdict path — the argument, not the assertion

PART C — TOKEN OPTIMIZATION
- LLM statelessness as root cause; the consultant-with-amnesia framing
- Where expenditure actually occurs: the retry loop, not the successful call
- The four levers, **ranked honestly**: deterministic detection (largest) > correction hints >
  delta protocol > provider prompt caching (smallest)
- Why prompt caching is a provider-side KV-reuse mechanism Congine *cooperates with* rather than
  implements
- Tiered validation and why almost nothing should reach a model
- Measurement methodology — how savings would be instrumented (status: PLANNED — Phase D)

PART D — HISTORY & INSTITUTIONAL MEMORY
- The two distinct causes: human context loss and machine context loss, and that both stem from
  statelessness
- The three stores: append-only event log; architectural graph; violation pattern index
- Payload hashing and privacy-by-design; content-addressing
- Selective recall and its connection to Part C (the recalled material is the material whose
  transmission cost must be controlled)
- Tamper-evidence via hash chaining
- The GDPR-erasure versus immutability tension and its resolution
- Status: PLANNED — Phase C. There is no persistence today (§1).

PART E — MULTI-AGENT NORMALIZATION
- Why agents diverge
- **Why training is rejected** — three reasons, the third being that it would destroy determinism
- Mechanism 1: the contract as equalizer (exists today)
- Mechanism 2: per-agent adapters as an anti-corruption layer (PLANNED — Phase E)
- Mechanism 3: capability profiles as statistics over the event log, not learned models
- Why this ordering is forced by data dependency

PART F — MCP: THE INTEGRATION SURFACE
- What MCP is, at the right altitude for a mixed audience
- Why the tool-call model rather than a proxy: closed agents write files, they do not call your
  functions — there is no wire to intercept
- The advisory limitation stated plainly, and the enforcement ladder that compensates
  (pre-commit hook, CI gate) — defence in depth, not alternatives
- The intended tool surface
- Where it attaches: L5, a peer of the existing adapters, no L0–L4 change (§15.1)
- **Status: PLANNED — Phase B. Confirmed absent (§15.1).**

PART G — BUSINESS POLICY DSL & POLICY IR
- The problem: organizational rules live in prose, wikis and heads
- The compilation pipeline: authoring → formal DSL → intermediate representation → deterministic
  evaluator
- **THE CRITICAL SEPARATION:** a model may assist *authoring* (design time, human-reviewed); a model
  never renders a *verdict* (runtime, audited). The model's output is an input to review, never a
  decision. This is what makes the pipeline defensible to an auditor.
- Why an IR at all — one evaluator, many authoring surfaces
- **The seam already exists, and this is the one place Part G touches shipped code.**
  `domain/contract_admission.py` is named in §15.10 as where a contract compiler grows from: a pure
  L2 function that already parses a contract, knows the vocabulary, emits typed machine-facing codes,
  and distinguishes *"this is invalid"* from *"nothing will execute this"* — which is precisely the
  judgement a compiler front-end makes. Say clearly that it is **not** a compiler: it validates and
  judges, it does not lower a contract into an IR. Its purity constraint is what keeps that door open
- Relation to policy-as-code precedent (OPA/Rego, Cedar) and where Congine differs
- The ladder to Executable Organizational Policy
- **Status: PLANNED — beyond Phase F. Conceptual.**

PART H — HOW THE DOMAINS INTERLOCK
- The layered dependency: enforcement → history → normalization; token economics as a consequence
- Why the build order is forced, not preferred
- What breaks if inverted (profiles over an empty log are noise)
- The single-proposition statement of the whole system

MUST COVER: every "Deep" cell for F02 in the coverage matrix. This document is where the reader
either gains complete understanding or does not.
=== END SPEC ===
```

---

## SPEC F06 — USE CASE & EDGE CASE COMPENDIUM

```text
=== DOCUMENT SPEC: F06 USE & EDGE CASES ===
Target: docs/_suite/F06_USE_AND_EDGE_CASES.md
Primary source: ARCHITECTURE_CURRENT.md §8, §9, §13; GAP3
Reader: engineers, QA, integrators
Depth: exhaustive enumeration

PURPOSE: Every way the system is used and every way it can be pushed to a boundary. Completeness is
the entire value; a missing edge case is a defect in this document.

REQUIRED SECTIONS:
1. Actors and their goals
2. Primary use cases — actor, precondition, trigger, main flow, alternate flows, postcondition,
   status label. Cover at minimum: guard-decorated function validation; explicit container use;
   LangChain callback validation; offline/standalone operation; multi-tenant operation;
   in-loop agent validation (PLANNED); pipeline gating (PLANNED)
3. **Every failure path** from §9 — trigger, response, caller-visible result, what is logged,
   what telemetry is emitted. §9 was 50 rows at `a561992` and has grown: it now includes
   unmeasurable payload and schema (rows 2, 2a), load shed as distinct from timeout (row 7),
   admission rejection and advisory (rows 36a–36c), and malformed configuration (row 36d). Count
   them yourself rather than repeating a number from an older document
4. Contract edge cases — the complete set from §13 and GAP3.6: keywords not enforced by default and
   what admission now does about them; **each of the seven admission codes as its own edge case**;
   union types (now enforced — including the union-with-an-unrecognised-member case that *is*
   refused); dot-notation asymmetry; null handling; bool-vs-number; unrecognised type names;
   over-long patterns and values (fail-closed at admission *and* at runtime); non-dict payloads and
   the `<root>` breach; `null_forbidden` as top-level rather than per-property, and its `warn`-mode
   portability advisory
5. Concurrency edge cases — saturation, nested validation, sync/async contention, tenant eviction
   under load
6. Lifecycle edge cases — bootstrap inside a running event loop; cold start with an empty cache;
   **cold start where the contract was refused at admission** (the call raises rather than passing);
   double close; use after close
7. Configuration edge cases — malformed env values (**they now raise rather than defaulting**);
   `region` set without a base URL; empty-string directory paths; non-local base URL without
   credentials; incoherent combinations. **Cover the construction-path cases explicitly**: a
   directly constructed config is now normalized and validated exactly as an environment-derived
   one is, and a raw enum string is canonicalized rather than silently taking the wrong branch
8. Boundary matrix — every documented limit, its value, and the behaviour at and beyond it

MUST COVER:
- The fail-mode × guard-mode matrix as a table, not prose. A degraded (timeout/load-shed) result
  RAISES under strict mode — state this explicitly; it surprises everyone.
- **The three shapes of "fails closed"** (§9.6): missing contract raises always; broken validation
  degrades; **an unsafe contract is refused before it is ever active**. The third is new and changes
  how a deployment behaves on a bad *contract* rather than a bad payload.
- **The availability trade admission makes, stated plainly.** Refusing a contract converts silent
  non-enforcement into a loud outage. That is the right direction for a governance component, and it
  is a real operational change — which is why a rejected update never evicts a previously admitted
  version. An operations reader needs both halves.
=== END SPEC ===
```

---

## SPEC F07 — SECURITY & THREAT MODEL

```text
=== DOCUMENT SPEC: F07 SECURITY ===
Target: docs/_suite/F07_SECURITY_AND_THREAT_MODEL.md
Primary source: ARCHITECTURE_CURRENT.md §14, §13.5, §16; F03 boundaries; F06 failures
Reader: a security reviewer or enterprise evaluator
Depth: deep technical, and honest about gaps

PURPOSE: State what Congine defends against, by what mechanism, and where it does not. A governance
component that is itself insecure is worse than none, because it manufactures confidence.

REQUIRED SECTIONS:
1. Security posture and trust assumptions
2. Trust boundaries — every point where data crosses in: output under validation, contract
   definitions (untrusted — they carry regex patterns), remote responses, locally cached snapshots,
   configuration. What validates and bounds each. **Contract admission is now the primary control on
   the contract-definition boundary** (§13.8) and should be documented as such: it is where an
   untrusted schema is checked for interpretability and enforceability before it can become policy.
3. STRIDE per boundary — threat and mitigation, or `UNMITIGATED` stated plainly
4. The **sixteen** invariants as security properties (§14) — mechanism, evidence, backing test,
   status. **G12–G14, the epistemic/trust invariants, are the most security-relevant**: *an
   uninterpretable contract never becomes active policy* (G12), *configuration cannot mean two
   different things depending on who constructed it* (G13), and *"not evaluated" is never reported as
   "conforming"* (G14). **G15–G16 are structural** and matter here too: an unenforced architecture
   rule and a leaking teardown are both security-relevant. Note that the second was genuinely false before `6345a1e` — a directly
   constructed `fail_mode="strict"` degraded instead of raising, which is a security-relevant silent
   downgrade of enforcement.
5. ReDoS defence — why re2 is a structural rather than heuristic solution; the length caps; every
   remaining stdlib `re` usage named as an exception with its risk assessment
6. Input bounding — the complete table of limits
7. Secrets and PII — where credentials live; the logger's unconditional blocklist versus the
   non-local redaction allowlist and when each applies; every sanitisation point
8. Multi-tenant isolation — what is isolated, the snapshot path derivation, and the post-P0-1
   eviction semantics
9. Snapshot integrity — atomic write, advisory lock, symlink and ownership refusal, envelope
   validation; the TOCTOU posture
10. Supply chain — dependency surface, pinning, optional extras, scan results (GAP4.8)
11. **Known gaps and accepted risks** — MANDATORY and specific. Include debts from §16 with security
    relevance. The headline item is **D17, the residual admission bypass**, framed as what it is: a
    *silent non-enforcement* path that survives on a direct `schema_storage.put()`, demonstrated in
    GAP3.6c, with two partial mitigations (a CI AST guard; `admit_contract` exported for embedders)
    and a known cost to close (a port change). Also cover D7 — `pii_sanitize` still uses stdlib `re`,
    and the RE2 rewrite is *blocked* because the current pattern uses a backreference RE2 does not
    support. That is a specific, nameable blocker, not an outstanding intention.
12. Reporting a vulnerability — mark as a founder TODO if no channel exists

MUST COVER:
- Contract schemas are untrusted input — and admission is now the control that acts on that fact
- Fail-closed behaviour on over-long and uncompilable patterns, at **both** admission and runtime,
  and why moving the check earlier matters: a runtime `REGEX_PATTERN` breach reports the *output* as
  violating a policy when the real fault is in the *policy*
- **Fail-closed on unmeasurable input** (P0-02): an input could previously evade a size control
  precisely by being malformed. Note that the catch is deliberately broad, and why — a narrow catch
  let objects whose own `__repr__` raises escape uncaught into the host, bypassing telemetry and
  fail-mode entirely
- Load shedding as a DoS defence, and its now-explicit signal (`LoadShedError` / `load_shed`) so an
  operator can distinguish an attack from a slow contract
- Telemetry-before-raise as an audit property
- **The P0-08 finding as a security decision worth its own paragraph:** region-based endpoint
  defaulting was removed because it could send an API key to an unverified host. The general rule —
  *a governance SDK must never infer a credential destination* — is the kind of principle a security
  reviewer will want stated explicitly.
=== END SPEC ===
```

---

## SPEC F05 — PROOF OF CONCEPT & EVIDENCE REPORT

```text
=== DOCUMENT SPEC: F05 POC & EVIDENCE ===
Target: docs/_suite/F05_PROOF_OF_CONCEPT_AND_EVIDENCE.md
Primary source: GAP4 (all measurements); ARCHITECTURE_CURRENT.md §14 (incl. §14.10-§14.12), §16;
the committed evidence harnesses `libs/congine-sdk/tools/p0_evidence/`; and
docs/_suite/hardening/P1_COMPLETION_REPORT.md (Final P1 Closure)
Reader: an evaluator, investor or technical due-diligence reader asking "is this real?"
Depth: empirical. Every claim carries a measurement.

PURPOSE: Demonstrate what has been built and what it provably does. This document's authority comes
entirely from measurement — nothing may be asserted that was not measured.

REQUIRED SECTIONS:
1. What was built — scope of Phase 0, the P0-1/P0-2 items, the **eight-item P0 Trust-Critical
   Hardening pass** (P0-01…P0-08, `6345a1e`), and **P1 Structural Hardening** (closed at
   `b482bc4`): the explicit architecture gate, strict blocking mypy, runtime Protocol validation,
   transactional composition, terminal lifecycle, the RE2 sanitizer, and the `ISyncRunner` port.
   State what is deliberately absent, and that **"P1 CLOSED" is not "enterprise-release ready"**
2. The central claim and its proof — determinism, demonstrated by the GAP4.3 repeat measurement,
   **re-measured with the admission boundary in the path** (GAP4.11)
3. Verification method — test strategy, categories, counts, coverage (GAP4.1, 4.2). Report the
   trajectory honestly — 293 → 350 → 436 → 478 (P0) → 540 → **613 passed / 1 skipped** (P1) — and
   say what the added tests buy. Cover the **five blocking Nx gates** (lint, strict typecheck,
   architecture, examples, test) and scope the typing claim precisely: **production `congine_core`
   source is blocking under strict mypy**; the tests/examples tree is not claimed strict-typed.
   Note that CI no longer contains `mypy ... || true`, and that the 90-test architecture suite
   verifies the *gate itself*, not merely the tree.

3a. **The P0 evidence is reproducible, and its provenance must be stated honestly.** The harnesses
   in `tools/p0_evidence/` were **reconstructed after P0 closed** — from the committed P0 tests, the
   P0 completion evidence and the recorded methodology — and did **not** exist as committed scripts
   during original P0. Run them (`uv run --package congine-sdk python -m tools.p0_evidence`) and
   report: determinism 1 verdict at N=5000; admission preflight 3/3; false-safety 4/4 refused with
   0 false PASS; load shed 2000/2000 with the deadline path staying a plain `TimeoutError`;
   configuration parity 5/5.

   **Do not claim the determinism hash matches P0's.** P0's canonical serialisation was not
   preserved and its hash survives only as `3ab5ce02…`. The truthful statement is that P0
   established one deterministic verdict in its measured environment, and P1 closure established a
   stable committed methodology with
   `715725383efa751299422a3dbe990c34c4c47d657e73ca90a03088ddf7f36dfa` as the reproducible baseline
   for future identical-methodology comparison.
4. Guarantee verification — all **sixteen** invariants: mechanism, backing test, status (§14),
   grouped mechanical (G1–G11) / epistemic (G12–G14) / structural (G15–G16)
5. Performance evidence — latency distribution, load-shedding behaviour, cache behaviour, bounded
   boot (GAP4.4–4.7). Report the measured load-shed p50 **as observed**; do not reconcile it against
   a figure from an earlier run
6. Worked demonstrations — the verified examples from GAP3. Three carry the document:
   - the failing-validation example (what a breach looks like);
   - **GAP3.6c, the residual bypass** — a `pass` on a contract that enforces nothing, reached by a
     direct `put()`. **This is the most important demonstration in the document**, because a suite
     that only showed the controls working would be marketing. It proves the team can find and state
     its own remaining gap;
   - GAP3.6a/b, admission refusing and admitting the *same* contract under different evaluator
     configuration — the cleanest evidence that the boundary reasons about capability rather than
     about a flag
7. **Contract admission evidence** — the repository-wide preflight (GAP4.10): every tracked contract
   judged under its documented configuration, with the admit/reject counts and codes. Report the
   native-configuration column too, and explain why refusals there are correct rather than
   regressions
8. Scale and quality facts — file counts, LOC, module distribution, test counts, static analysis
9. What is NOT proven — honest limits: no persistence, no distributed operation, no production
   deployment history, no third-party audit. **Add: no static type gate and no automated layer-import
   gate.** The P0 pass hit an L3→L4 and an L0→L2 violation by hand; only review caught them, and mypy
   would not have — a type checker does not know the hexagon's direction. State this plainly; it is
   exactly the kind of limit a due-diligence reader is entitled to
10. Known defects — the debt register with severity (§16), reporting **both** halves: what is
    closed and what remains. **Take each item's status from §16's reconciliation table and do not
    hardcode a count** — several further items were closed by P1, so any "15 of 22"-style figure is
    historical. Include the standing P0 and P1 deferrals explicitly
11. Conclusion — what a reader may reasonably conclude, and what they may not

MUST COVER: every number cites the command that produced it. Where a measurement could not be taken,
say `NOT MEASURED` and why. Do not estimate. **Where a defect was found and closed, say what it was**
— a report that shows only the current clean state is less credible than one that shows the finding
and the fix.
=== END SPEC ===
```

---

## SPEC F08 — ROADMAP & EXECUTION PLAN

```text
=== DOCUMENT SPEC: F08 ROADMAP ===
Target: docs/_suite/F08_ROADMAP_AND_EXECUTION_PLAN.md
Primary source: ARCHITECTURE_CURRENT.md §15, §16; Complete Reference Part IV
Reader: the team, and any stakeholder asking "what next and when"
Depth: strategic, with technical grounding

REQUIRED SECTIONS:
1. Where the program stands — **P0 CLOSED** (`1258a98`) and **P1 CLOSED** (`b482bc4`), with
   **P1.5 NEXT**; P2 and P3 not started; Phase A onwards not started. State what that does and does
   not mean, and say plainly that P1 CLOSED is **not** enterprise-release ready
2. The forced dependency order — **P1.5 → P2 → P3 → Phase A → B → C → D → E → F → beyond**, with the
   *reason* each stage requires its predecessor. Not a preference; a data dependency. State what
   breaks if inverted. **Earlier drafts of this suite stepped from "Phase 0" straight to Phase A —
   that sequence is superseded and must not be reproduced.** The stages:
   - **P1.5 — Semantic validation safety**: P1.5-01 honest semantic-validation cost communication ·
     P1.5-02 separate native/semantic budget policy · P1.5-03 complexity/admission prototype ·
     P1.5-04 compiled-validator caching investigation
   - **P2 — Verification/release gates**: Python support matrix · Linux release CI · golden
     determinism corpus · branch coverage · pip-audit · SBOM · security gates · reproducible
     performance evidence
   - **P3 — Formal documentation + ADR reconciliation**: D1 · D2 · D3 · F01–F09 · ADR stabilization
   - **Post-P3 / downstream web surfaces**: **W1** documentation site · **W2** prototype control-plane site. They *depend on* the reconciled documentation and do **not** define P3 completion
   - **Phase A** SDK productization + CLI · **B** MCP · **C** durable evidence/history ·
     **D** deterministic correction/convergence/context economics · **E** architecture intelligence
     + agent adapters · **F** optional adaptive routing if evidence justifies it · beyond F:
     Policy IR, Business Policy DSL, Executable Organizational Policy
3. Per phase: focus, deliverables, the seam it attaches to (§15), exit criteria, status
4. The attachment analysis — six of eight capabilities need no L2/L3 change; the two that do, and
   what exactly they change (§15.10)
5. Debt remediation plan — derive current debt status from **§16's reconciliation table**, which
   marks each item resolved / open / superseded / deferred. **Do not hardcode a debt count** (the
   "21 debts" and "15 of 22 closed" figures are historical). Say which open items block which stage,
   and what the closed ones unblocked
6. Risk register — technical and program risks with responses
7. The demonstration milestone — what Phase B makes showable, and why that specific moment matters
8. What must NOT be built yet, and why

MUST COVER:
- Every capability marked PLANNED with its phase.
- **The residual admission bypass (D17, renamed D-ADM) as the Phase-A blocker.** It replaces D18 in
  that role: D18 is fixed, and this is now the one path on which silent non-enforcement still
  reproduces. Closing it requires a port change — admission behind `ISchemaStorage`, or `put` taking
  an `AdmittedContract` — and that decision should be made *before* the roadmap adds more schema
  writers, because MCP, the CLI and direct injection each add one. **P1 explicitly deferred it**,
  along with the `AdmittedContract`/`CompiledContract` boundary and version-aware storage identity;
  record it as deferred, never as fixed.
- **The other standing P1 deferrals**, so no document implies otherwise: richer three-axis result
  semantics, the semantic/native budget architecture, semantic complexity admission, compiled
  semantic-validator caching, cross-version release evidence, and supply-chain gates / SBOM.
- **Two P0 deferrals with concrete, nameable blockers**, both of which shape sequencing:
  version-aware fail-closed needs `ISchemaStorage.put` to carry a version (today `_prime_cache`
  ignores any version field and `contract_version` reaches telemetry only); partial-enforcement
  metadata needs admission results carried into `ValidationResult`.
- **The P1 sequencing note, stated as a requirement rather than a preference:** a static type gate
  (mypy) and a **separate import/layer dependency gate** are two different things. mypy does not know
  that L3→L4 or L0→L2 is forbidden. Two such violations were written by hand during P0 and caught
  only by review. Do not record mypy as enforcing hexagonal direction.
=== END SPEC ===
```

---

## SPEC F01 — CONCEPT & RATIONALE BRIEF (write LAST)

```text
=== DOCUMENT SPEC: F01 CONCEPT BRIEF ===
Target: docs/_suite/F01_CONCEPT_AND_RATIONALE.md
Primary source: Complete Reference Part I–II; ARCHITECTURE_CURRENT.md §1; all preceding suite documents
Reader: ANYONE — first encounter. The most widely read document in the suite.
Depth: conceptual, dense, no jargon without definition
Length: shorter than the others. This is the summary; discipline is the point.

PURPOSE: Explain what Congine is, why it exists, and why now — to a reader with no context. Written
last because you cannot summarise well until the detail is settled.

REQUIRED SECTIONS:
1. What Congine is — three sentences, then a paragraph
2. The change that created the need — generation became elastic; review did not
3. Functional versus organizational correctness — the central conceptual wedge, made vivid
4. Why existing tools cannot close the gap — per category, what each knows and cannot know
5. Why not "use an AI to check the AI" — the argument, stated fully. This is the objection every
   reader raises.
6. The proposition — "outputs conform to our rules, or they are stopped"
7. How it works, conceptually — the firewall analogy; the contract; the verdict; the enforcement ladder
8. The five key ideas in brief — contracts, token economics, memory, normalization, the policy surface
   — each one paragraph, each pointing into F02
9. Who it is for and what changes for them
10. What exists today and what does not — honest, with the status labels
11. Where to go next — the reading map for the rest of the suite

MUST COVER: the reader finishes knowing what this is, why it is needed, why determinism is
non-negotiable, and where to read more. No unbuilt capability implied as existing.
=== END SPEC ===
```

---

## After each run — your checklist

- [ ] Read the document fully — not the headings.
- [ ] Verify no PLANNED capability is described as existing.
- [ ] Verify the safety-critical statements appear and are not softened — and that **none of the
      three retired warnings** has crept back in. Grep each draft for `D18`, `union`, `dead
      configurable`, `46 fields`, `eleven invariants`, `thirteen invariants`, `silently ignored`.
      Every hit needs checking
      against the current-state header block and §16 reconciliation table.
- [ ] Check the coverage matrix cells this document owns are genuinely Deep.
- [ ] **Answer the founder questions** before the next document — they compound.
- [ ] After F01 is done, run a final consistency pass across all nine for contradictions and
      terminology drift.
