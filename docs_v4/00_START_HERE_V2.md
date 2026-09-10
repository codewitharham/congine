# START HERE — V2 BATCH: DOCUMENT SUITE + THE TWO WEBSITES

Read this first. It contains the honest diagnosis of what went wrong with Claude Design, a correction
to your picture of where you actually stand, and the two decisions that govern everything else in
this batch.

> **Revised 2026-08-17.** This batch was written against commit `a561992`. The codebase has moved
> twice since: `49a2f93` closed all twelve `ARCHITECTURE_CURRENT.md` §17 open questions, and
> `6345a1e` landed the eight-item **P0 Trust-Critical Hardening** pass. `ARCHITECTURE_CURRENT.md`
> has been revised to match. Every file here has been updated; **§6 of this document was reversed
> outright** and is the one change most worth reading.
>
> **Revised again 2026-08-22, at P1 closure.** `ARCHITECTURE_CURRENT.md` is now reconciled against
> the P1 CLOSED commit `b482bc4b2c88273e2a29a0f418a53f7ba3ab0614` and is the current-state spine.
> Read its **"Current state — verified against P1 CLOSED" header block** first, then the
> **§16 reconciliation table**, before running any prompt in this batch. See §7 below for the
> programme state and the corrected phase order.
>
> *Note: earlier revisions of this batch pointed readers at a "§2.5 reconciliation record" in
> `ARCHITECTURE_CURRENT.md`. That section was described but never actually written — it does not
> exist in any commit. The two locations named above carry that content instead.*

---

## 1. YOU ARE FURTHER ALONG THAN YOUR MESSAGE SUGGESTS

You wrote that you have executed none of the prompts. That is not true, and the difference matters.

**`arch_progress.md` shows all 16 passes DONE.** `ARCHITECTURE_CURRENT.md` exists: originally 3,804
lines and ~35,300 words, with 100+ tables, Mermaid diagrams, and every claim carrying `file:line`
evidence. Pass 12 empirically probed contract semantics. Pass 15 re-verified nine prior debts and
found twelve new ones.

**Pass 3's layering result needs one important qualification.** It ran AST analysis across every file
and reported **zero layering violations**. That analysis really ran and its result was correctly
reported — but P1 later established that the *rule it encoded was insufficient*. It approved any edge
where the target layer's number was less than or equal to the source's, which silently permits
`L4 → L2` and `L4 → L3`, and it exempted `TYPE_CHECKING` imports entirely. Seven forbidden edges were
live in the tree while the check reported clean.

P1 replaced it with an **explicit layer dependency matrix**, enforced over runtime *and*
`TYPE_CHECKING` imports, with zero allowlist entries — and falsified the new gate by re-injecting
removed edges. Do not cite "zero violations" as though the two results are equivalent: the old one was
green under a weaker rule. The lesson generalises, and it is the most useful thing in this batch: **a
verification result is only as strong as the rule it encodes.**

**And it has since been kept current, which is the part that matters.** The document has been
reconciled twice: against `49a2f93` / `6345a1e` on 2026-08-17, and against the **P1 CLOSED** commit
`b482bc4b2c88273e2a29a0f418a53f7ba3ab0614` on 2026-08-22. It now carries a current-state header
block, the explicit dependency matrix, the L0 shared-kernel reclassification, and a reconciled debt
register in which every historical item is marked resolved, open, superseded or deferred. That
maintenance is what keeps this document worth building everything else from; the moment it drifts,
every document that cites it inherits the drift.

**Prompt 1 was executed, and it worked.** That document is now the single most valuable asset you
own — more valuable than the codebase in one specific sense: it is the codebase *explained*, verified
against itself, and it is the input every other document should be built from.

**The consequence for Task 1 is immediate and large:** the codebase-recall prompt from the earlier
batch (`PROMPT_A_CODEBASE_RECALL.md`, the eight-pass EX1–EX8 extraction) is now **roughly 80%
redundant**. Its eight passes map almost one-to-one onto sections that already exist:

| PROMPT_A pass | Already covered by |
|---|---|
| EX1 Inventory | `ARCHITECTURE_CURRENT.md` §2, §3, Appendix A |
| EX2 Behavior | §7 Lifecycle, §8 Control flows, §9 Failure paths |
| EX3 Config | §12 Configuration surface (48 fields; no dead configurables) |
| EX4 Contracts | §13 Contract semantics — safety-critical, incl. §13.8 contract admission |
| EX5 Decisions | **Partially** — Appendix B audit-ID index, §16 debt register, §17 resolutions |
| EX6 Security | §14 Invariants and guarantees (13) |
| EX7 Quality | §16 Debt register, §2 drift report |
| EX8 Public API | §5 Ports catalogue, §6 Composition — **partially** |

Running Prompt A now would burn several sessions re-deriving what you already have. **Do not run it.**
It is retired in this batch and replaced by a much smaller gap-fill prompt that extracts only the four
things `ARCHITECTURE_CURRENT.md` genuinely does not contain.

---

## 2. WHY CLAUDE DESIGN DISAPPOINTED — THE HONEST DIAGNOSIS

You asked whether using Claude Design, with those files, was the right decision. Partly yes, mostly no
— and **the problem was not prompt strength.** I read `CONGINE_GPT_PROMPT.md` in full. Here is what it
actually asked for:

- **3,799 lines. 100 numbered sections.**
- **Three distinct products** in one prompt: a marketing landing page (§38–§45), a developer
  documentation portal (§46–§47), and an enterprise control plane (§48–§79).
- **Nine deliverable parts** (§100): understanding → product experience architecture → information
  architecture → stakeholder journeys → process flows → low-fidelity wireframes → design system →
  high-fidelity screens → interactive prototype.
- **~600 lines (§1–§3.7) spent purely on source-of-truth precedence** between the input documents.

Four failure modes follow mechanically from that, and none of them is fixed by writing a stronger prompt.

**Failure 1 — Three products in one brief.** A landing page, a docs portal and a governance dashboard
have different users, different information density, different interaction models and different success
tests. Asking for all three at once guarantees that none receives real attention. The control plane
alone is ten times the surface of the landing page.

**Failure 2 — The entire design pipeline collapsed into one generation.** Wireframes exist so you can
be wrong cheaply *before* the design system is committed. A design system exists so high-fidelity
screens are consistent. An interactive prototype exists to test flows that hi-fi already settled. These
are **sequential acts with review gates between them.** Requesting all nine at once removes every gate,
so errors at stage 1 propagate silently into stage 9. That is precisely the "not the finest UI/UX"
outcome you observed.

**Failure 3 — The precedence machinery is a symptom, not a solution.** If a prompt needs 600 lines to
adjudicate which of seven documents wins on which topic, the real problem is that seven documents are
in the context. Signal-to-instruction ratio collapsed: the genuinely load-bearing constraints (the
determinism invariant, the current-vs-future boundary) were buried under document-arbitration rules.

**Failure 4 — Wrong tool for half the job.** Claude Design produces *designs*. The control plane you
described — live updates, per-tenant interfaces, agent orchestration telemetry, RBAC — is not a design
problem. It is a full-stack application with real-time transport, a database, multi-tenancy and access
control. Claude Design was never going to build that, and asking it to made the docs portion worse too.

**What you got right:** giving it the product language contract (§32), the brand tone (§34), the
current-vs-future boundary (§31) and the "what not to do" section (§94). Those are exactly the right
kind of constraint. They were just drowned.

**Verdict:** sharing relevant files was right in principle and wrong in execution — you shared the
*strategy* documents (business workflow, market research) which serve a different audience, rather than
a tight brief for one surface. The fix is not a better prompt. It is **one surface per prompt, one
stage per run, and the right tool per surface.**

---

## 3. THE THING I MOST NEED YOU TO SEE

**The control plane is a dashboard for data that does not exist yet.**

`ARCHITECTURE_CURRENT.md` §1 states it plainly: *"It is a library, not a service. There is no server,
no database, no CLI, no persistence. Every piece of state … is process-local. If the process dies,
queued telemetry dies with it."* §15 confirms all eight planned capabilities absent — MCP server, CLI,
persistent event store, history queries, correction hints, architecture graph, agent adapters, routing.

So a control plane showing "real live updates around contract making, how well token optimization has
been working, which agent each tenant is using" would today be **100% fabricated data on every screen.**

That does not make it wrong to build. It makes it a decision you must take **deliberately and name
honestly**, because there are only two coherent versions and they have very different costs:

| | **Design prototype** (recommended now) | **Real product** (recommended after Phase C) |
|---|---|---|
| Data | Mock, clearly labelled | Live, from the durable event store |
| Stack | Next.js + mock data layer behind a clean seam | NestJS API + Postgres + WebSocket + auth |
| Effort | Days | Months |
| Honest use | Fundraising, design validation, user testing | Actual customers |
| Risk | None, if labelled | **Building the dashboard before the engine that feeds it** |

Building the real one now inverts the forced dependency order your own roadmap enforces and that
`ARCHITECTURE_CURRENT.md` §15 documents. The event store (Phase C) is what produces every number the
control plane would display. **Build the instrument after the sensor, not before.**

The docs site is the opposite case: it documents things that **already exist** (the SDK, the guard,
contracts, rules, config, the six-layer architecture). It is cheap, real, and it forces the
"can a stranger install this and get a passing validation in five minutes" test. That test is worth
more to you right now than any dashboard.

---

## 4. THE TWO GOVERNING DECISIONS

### Decision A — Documents: retire Prompt A, add a formal suite tier

Your earlier batch produced *repo documentation* (README, CONTRACTS, RULE-VOCAB, CONFIG-REF, SECURITY,
CHANGELOG). What you are now asking for — "POC, ARD etc… the face of the product… extreme depth" — is a
different tier: a **formal engineering document suite** rendered as publishable artifacts.

Both tiers are legitimate and they do not compete. This batch defines the formal tier, specifies nine
documents, and rebuilds the prompts to produce them from `ARCHITECTURE_CURRENT.md` plus a small
gap-fill extraction. Details in `V2_DOC_SUITE_SPEC.md`.

### Decision B — Websites: Claude Code for both, one monorepo, staged

- **Tool:** Claude Code for both sites. It has your codebase, can run and verify what it builds, and can
  produce real applications. Claude Design remains useful for exactly one narrow job — exploring a visual
  direction for the control plane before implementation — and that is optional.
- **Structure:** **one monorepo, not three repos.** Polyglot monorepos are normal and this avoids
  three sets of CI, three dependency graphs and three places to forget things.

  **Corrected 2026-08-22 — the repository already has this, and it is not pnpm.** When this was
  written the Node side was a proposal. It now exists and is in production use: **uv** for the Python
  workspace and dependencies, **npm** for Node dependency installation, and **Nx** for project and
  task orchestration across both. `package.json`, `package-lock.json` and `nx.json` are at the root,
  and CI drives the SDK through Nx targets.

  So: **do not add a pnpm workspace, do not create `pnpm-workspace.yaml`, and do not overwrite the
  root `package.json`.** New web projects join the existing Nx/npm monorepo as additional Nx
  projects. Verified commands: `npm ci`, `npm exec nx -- show projects`,
  `npm exec nx -- run <project>:<target>`.
- **Sequence:** docs site first (real, ships value immediately), control plane prototype second
  (honest mock data, clean seam for the future API). Details in `WEB_ARCHITECTURE_AND_TOOLING.md`.

---

## 5. THE EIGHT FILES IN THIS BATCH

| # | File | Purpose |
|---|---|---|
| 0 | **START_HERE_V2** (this) | Diagnosis, state correction, governing decisions |
| 1 | `V2_DOC_SUITE_SPEC.md` | The nine formal documents: what each contains, what changed from v1, the build order |
| 2 | `PROMPT_D1_GAP_EXTRACTION.md` | The reduced recall prompt — four passes, not eight. **Replaces PROMPT_A** |
| 3 | `PROMPT_D2_SUITE_AUTHORING.md` | Master authoring prompt with a spec block per document. **Replaces PROMPT_B** |
| 4 | `PROMPT_D3_ADR_ARCHAEOLOGY_V2.md` | Decision archaeology, now consuming §16/§17. **Replaces PROMPT_C** |
| 5 | `WEB_ARCHITECTURE_AND_TOOLING.md` | Monorepo layout, stack choices, the mock-data honesty rule, setup commands |
| 6 | `PROMPT_W1_DOCS_SITE.md` | Build the documentation site — staged, real, verifiable |
| 7 | `PROMPT_W2_CONTROL_PLANE.md` | Build the control plane prototype — staged, honest, seam-ready |
| 8 | `CONGINE_GPT_PROMPT.md` | The original single-shot brief. **Reference only** — §22–§34 feed F02; ignore its design sections entirely (see §2 above) |

**Two repository documents every prompt here now depends on**, neither of which is part of this batch:
`docs/architecture/ARCHITECTURE_CURRENT.md` (the technical spine — **read the current-state header
block and §16 reconciliation table first**) and
`docs/_suite/hardening/P0_COMPLETION_REPORT.md` (the record of the eight P0 findings, and the best
source of *stated* rationale in the repository).

**Run order:** D1 → D2 → D3 for documents; W1 → W2 for websites. The two tracks are independent and can
run in parallel if you have the appetite, but D1 must precede D2, and W1 should precede W2 because it
establishes the shared design tokens the control plane inherits.

---

## 6. ONE CORRECTION TO CARRY FORWARD — **REVERSED 2026-08-17**

**This section previously said the opposite of what it now says. Read it carefully.**

The original instruction was that every document and every docs page teaching contract authoring
**must warn** about the union-type defect:

> ~~A union `type` declaration (`{"type": ["string","null"]}`) — legal, idiomatic JSON Schema — makes
> every validation against that contract degrade silently, forever (§13.6, debt D18).~~

**That defect is fixed.** `49a2f93` made unions a first-class, enforced spelling — matching when any
member matches, with `"null"` a recognised type name. Debt D18 is closed. **Instructing the suite to
warn about it now would tell developers to avoid the correct way to declare a nullable field.**

### What carries forward instead

The underlying concern was never really about unions. It was about **silent non-enforcement** — the
system reporting conformance it had not verified. That concern is still exactly right, and the answer
to it is now a mechanism rather than a warning:

**Contracts are admitted before they can become active policy** (`ARCHITECTURE_CURRENT.md` §13.8).
A contract CONGINE cannot interpret — an unknown type name, an empty union, a dotted property key, an
uncompilable pattern, a clause no active evaluator will execute — is **refused at load** and never
cached. Seven machine-facing refusal codes, each with a specific remediation.

Four things every document and every docs page must carry, replacing the single retired warning:

1. **The native rule engine reads a small keyword set; everything else needs an evaluator** — this
   half is unchanged and still needs stating plainly. Be precise about the three tiers rather than
   quoting one number: the native engine covers 8 distinct keys (10 spellings, counting
   `min`/`minimum` and `max`/`maximum`); the optional semantic evaluator adds 33 more; and `format`
   needs `semantic_format_checking` on top of that. What changed is the consequence: a contract using
   a keyword the **wired** evaluators do not cover is now *refused*, not silently accepted. Derive
   these sets from `domain/schema_vocabulary.py`; do not hardcode them.
2. **Admission runs on the loader path only** (debt D17, renamed **D-ADM** in the reconciled
   register). A direct `schema_storage.put()` bypasses every check, and the false-safety case
   reproduces there. **This is the live warning that replaces D18**, and it is the one genuinely open
   safety gap of this kind. P1 explicitly **deferred** closing it: universal admission behind
   `ISchemaStorage`, an `AdmittedContract`/`CompiledContract` boundary, and version-aware storage
   identity are all still open. Do not describe it as fixed.
3. **`is_pass()` does not tell you whether the policy was evaluated.** A degraded result is
   `status="fail"` with zero breaches, so `is_pass()` is `False` both for a real violation and for a
   validator that never ran. Callers ask `is_enforced()` first.
4. **Refusing a contract trades silent non-enforcement for a loud outage.** On a cold cache, a
   refused contract makes every guarded call against it raise. That is the right direction for a
   governance component and it is a real operational change — state both halves.

### The lesson worth more than the correction

This section was wrong for seven days, and it was wrong in the direction that feels safest: warning
about a hazard. **Overstating a defect is the same class of error as overstating a capability** — both
are a surface that does not match the system, and both cost exactly the credibility this batch exists
to build. The honesty rule in `WEB_ARCHITECTURE_AND_TOOLING.md` §4 now cuts in both directions for
that reason.

The mechanism that would have caught it is already specified: **executable examples run in CI**
(`WEB_ARCHITECTURE_AND_TOOLING.md` §1, `PROMPT_W1` Stage 3). An example asserting that unions degrade
would have failed the moment `49a2f93` landed. Treat that CI job as load-bearing, not as hygiene — it
is the same argument the product makes about contracts, applied to its own documentation.

**That mechanism now exists.** `npm exec nx -- run congine-sdk:examples` executes the real offline
LangChain example through the real public guard in CI, and P1 added four more blocking gates beside
it (`lint`, `typecheck`, `architecture`, `test`). The same lesson recurred at a larger scale during
P1: the architecture gate *claimed* to enforce inward dependencies while encoding a weaker rule, and
passed for that reason. Both times the fix was the same — **make the claim mechanically checkable.**

---

## 7. CURRENT PROGRAMME STATE — READ BEFORE SEQUENCING ANYTHING

Added 2026-08-22, at P1 closure.

| | |
|---|---|
| P0 source commit | `1258a982b7dca2caac38de07256a8339575edbf6` |
| **P1 CLOSED commit** | **`b482bc4b2c88273e2a29a0f418a53f7ba3ab0614`** (branch `P1_CLOSED_PHASE1`) |
| Test baseline | **613 passed, 1 skipped** |
| Architecture gate | 40 source files · 90 tests · **0 allowlist entries · 0 `TYPE_CHECKING` exemptions** |
| Strict mypy | 0 issues across 40 production source files, blocking |
| P0 trust baseline | **5 / 5** categories green, reproducible via `tools/p0_evidence/` |

**The phase order is not what earlier documents in this batch assume.** They step from "Phase 0"
straight to **Phase A**. Three phases now precede it:

```
P0 CLOSED → P1 CLOSED → P1.5 (NEXT) → P2 → P3 → Phase A → B → C → D → E → F → beyond
```

- **P1.5 — Semantic validation safety** *(next)*: honest semantic-validation cost communication ·
  separate native/semantic budget policy · complexity/admission prototype · compiled-validator
  caching investigation.
- **P2 — Verification/release gates**: Python support matrix · Linux release CI · golden determinism
  corpus · branch coverage · pip-audit · SBOM · security gates · reproducible performance evidence.
- **P3 — Formal documentation + ADR reconciliation**: D1 · D2 · D3 · F01–F09 · ADR stabilization.
- **Post-P3 / downstream web surfaces**: **W1** documentation site · **W2** prototype control-plane site. They *depend on* the reconciled documentation and do **not** define P3 completion.

  **This run is none of the above.** It is the **post-P1 context-source reconciliation** —
  aligning `ARCHITECTURE_CURRENT.md` and `docs_v4/` with the P1 CLOSED tree. P3 remains
  **NOT STARTED**.
- **Phase A** — SDK productization + CLI. **Phase B** — MCP. **Phase C** — durable evidence/history.
  **D/E/F** — deterministic correction, architecture intelligence, optional adaptive routing.

**P1 CLOSED is not "enterprise-release ready."** Still open and not to be claimed otherwise: the raw
`schema_storage.put()` admission bypass, version-aware storage identity, richer three-axis result
semantics, semantic budget architecture, supply-chain gates and SBOM, and cross-version release
evidence.

**Two architectural facts every downstream document must now carry:**

1. **The dependency rule is an explicit matrix, not numeric ordering.** `L4 → L2` and `L4 → L3` are
   forbidden even though 2 and 3 are numerically inward; infrastructure reaches policy only through
   ports. Internal `TYPE_CHECKING` imports obey the same matrix.
2. **The canonical value contracts live in L0**, not L2. `BreachDetail`, `ValidationResult`,
   `TelemetryEvent`, `DriftResult` and `DegradedReason` are in `congine_core/models.py`;
   `congine_core/domain/models.py` remains a compatibility re-export that keeps L2 identity for the
   gate. Also new: the L1 `ISyncRunner` port — never describe `BackgroundSyncWorker` as depending on
   the concrete `SyncContractsUseCase`.

**Before running any prompt in this batch, check its warnings against `ARCHITECTURE_CURRENT.md`
the current-state header block and §16.** Most historical debts are closed; §16's reconciliation
table gives each item's verified status (resolved / open / superseded / deferred) — use it rather
than a headline count.
