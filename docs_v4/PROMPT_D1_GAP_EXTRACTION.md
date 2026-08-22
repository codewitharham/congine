# PROMPT D1 — GAP EXTRACTION (replaces PROMPT_A)

## How to use

**Where:** Claude Code, inside the Congine repository.
**Attach:** `V2_DOC_SUITE_SPEC.md` (so it knows what the documents will need).
`ARCHITECTURE_CURRENT.md` is read from the repo.
**Produces:** `docs/_suite/gap/GAP1_NARRATIVE.md` … `GAP4_MEASUREMENTS.md`
**Expect:** one to two sessions. Four passes, not eight — the rest already exists.

> **Why this is short.** `ARCHITECTURE_CURRENT.md` already contains the inventory, layer model,
> dependency graph, ports catalogue, wiring, lifecycle, control flows, failure paths, concurrency
> model, data model, configuration surface, contract semantics, invariants, seams and debt register.
> This prompt extracts **only what it does not contain** and the document suite genuinely needs.

> **Revised 2026-08-17 against commit `6345a1e`.** `ARCHITECTURE_CURRENT.md` has itself been revised
> and now carries a **current-state header block plus a §16 reconciliation table** covering the
> commits that landed after it was
> first written: `49a2f93` (closed all twelve §17 open questions) and `6345a1e` (the eight-item P0
> Trust-Critical Hardening pass), and it is now reconciled against **P1 CLOSED** `b482bc4`.
> **Read the current-state header block immediately after §0, then §16** — they tell you which of the
> document's own earlier sections have been amended and why, and it will save you re-deriving
> fifteen closed debts from scratch.
>
> Three consequences for this prompt specifically, each reflected below:
> **(a)** the drift-hunting directive is now about finding drift *since* `6345a1e`, not re-finding
> the drift those sections already record; **(b)** the GAP3 "contract that looks enforced but is not" pass
> has a different subject, because the contract that used to demonstrate it is now **refused at
> load**; **(c)** the GAP4 baselines have moved.

---

```text
=== BEGIN PROMPT D1 ===
```

# ROLE

You are a technical analyst preparing raw material for a formal document suite about the Congine
codebase. A comprehensive architecture document already exists. Your job is **not** to reproduce it.
Your job is to extract the four categories of material it deliberately does not contain.

# INPUTS

1. **`docs/architecture/ARCHITECTURE_CURRENT.md`** — read it **completely and first**. It is
   verified, evidence-backed, and reconciled to the **P1 CLOSED** commit
   `b482bc4b2c88273e2a29a0f418a53f7ba3ab0614`. Treat it as ground truth for anything it covers. **Read the current-state header block and §16 before the body**: together they are the
   reconciliation record for every commit that post-dates the original draft, and where they and an
   earlier section disagree, **they are current**.
2. The codebase — for anything it does not cover.
3. `V2_DOC_SUITE_SPEC.md` — tells you which documents consume your output.
4. **`docs/_suite/hardening/P0_COMPLETION_REPORT.md`** — the completion record for the P0
   Trust-Critical Hardening pass. It contains material GAP2 needs and cannot recover from code:
   what was found, what was deliberately *not* fixed, the two architectural bugs caught in flight,
   and the measured evidence. Treat its §4 (each P0 item) as a HIGH-confidence rationale source.
5. **`docs/_suite/hardening/P1_COMPLETION_REPORT.md`** — the same for **P1 Structural Hardening**,
   including its **Final P1 Closure** section. This is the HIGH-confidence rationale source for the
   layer matrix, the L0 value-contract reclassification, the compatibility re-export strategy, the
   `ISyncRunner` port, runtime Protocol validation, transactional composition, terminal lifecycle,
   the RE2 sanitizer, and the reconstructed evidence harnesses. It also lists what P1 **deferred**.
6. **`libs/congine-sdk/tools/p0_evidence/`** — the committed, runnable P0 evidence harnesses. GAP4
   should **run these** rather than inventing a fresh methodology:
   `uv run --package congine-sdk python -m tools.p0_evidence`.

# TIME AND EFFORT

**TAKE AS MUCH TIME AND AS MANY SESSIONS AS YOU NEED. THIS IS EXPLICITLY AUTHORIZED. THERE IS NO TIME
PRESSURE.** Read `ARCHITECTURE_CURRENT.md` in full before beginning Pass 1 — skipping it guarantees
duplicated work. Write each pass file to disk on completion. If context runs low, checkpoint and
report the resume point; never compress or skip.

# PRIME DIRECTIVES

1. **Do not duplicate `ARCHITECTURE_CURRENT.md`.** If a fact is there, cite it as `§n` rather than
   restating it. Duplication is the specific failure this prompt exists to avoid.
2. **The code is ground truth where the two disagree** — and report any disagreement, because that
   means the architecture document has drifted since its verified commit. **Start by recording HEAD
   (`git rev-parse HEAD`, `git branch --show-current`) and comparing it to the commit named in the
   architecture document's current-state header block (`b482bc4`).** If HEAD is that commit, drift
   should be minimal and anything you find is genuinely new; if HEAD is ahead, inspect the delta
   (`git log --oneline b482bc4..HEAD`, `git diff --stat b482bc4 HEAD`) and treat those changes as
   the most likely source of any disagreement. Do
   **not** re-report drift already recorded in the current-state header block or the §16
   reconciliation table — that is resolved and cited, and re-listing it wastes a pass. Report only
   what those sections do not already cover.
3. **Never fabricate rationale.** `RATIONALE NOT RECORDED` is a correct and valuable answer.
4. **Enumerate; do not summarise.** No "etc.", no "and others", no capped lists.
4a. **MEASURE every count at HEAD; never copy one from a document — including this one.** Numbers in
   the prose of any prompt or architecture document are dated snapshots. At minimum, measure and
   record the command used for: source-file count and per-layer module counts; the current port
   exports (`congine_core.ports.__all__`); the `CongineConfig` field count
   (`dataclasses.fields(CongineConfig)`); the root public surface (`congine_core.__all__`); the test
   count; the architecture-test count; and mypy's configured scope. Specifically **do not** carry
   forward "seven ports", "eight ports", "46 fields", "37 files", or any historical pass count as a
   current figure.
5. **Read-only** except for files under `docs/_suite/gap/`.
6. **A fixed defect is history, not a finding.** D18 (union-type degradation) is the case that will
   trip you: it is fixed, and several documents in this repository still describe it as live. If you
   encounter such a claim, record it as a **documentation** finding against *that* document — never
   as a defect in the code.

---

# PASS GAP1 — PER-FILE NARRATIVE MATERIAL

**What's missing:** `ARCHITECTURE_CURRENT.md` describes the system structurally. The documents need
*per-file* material — what each file is for, what breaks without it, what it becomes later.

For **every** source module (**39** at last count, of which 33 are implementation modules — verify),
produce:

```
### <path>
- **Layer / status:** L<n> · active | deprecated | dead
- **One-line identity:** what it is, in plain language
- **Why it exists:** the problem that forced it into being
- **Deletion test:** if this file vanished, what specifically breaks and how would you notice?
- **Load-bearing detail:** the one non-obvious thing a reader must know (cite `ARCHITECTURE_CURRENT §n`
  where covered rather than re-explaining)
- **Future trajectory:** per §15, does any planned capability touch this file, attach beside it, or
  leave it untouched?
- **Metaphor candidate:** a role in a coherent metaphorical world that would explain its *mechanism*
  (not decoration). One line. Say `NONE` if no honest metaphor helps.
```

Keep each entry tight. The deletion test and the future trajectory are the two fields that matter most
and do not exist anywhere today.

**Several modules are new since the architecture document was first drafted and have no per-file
narrative anywhere.** Give each a full entry and expect them to be among the longest:

- **`ports/lifecycle.py`** (L1, `49a2f93`) — `IStoppable` / `IObservable`. Its deletion test is
  unusually interesting: nothing *breaks* without it, which is exactly why the debt it closes (D14)
  survived so long.
- **`domain/contract_admission.py`** (L2, `6345a1e`) — the publication boundary. Its future
  trajectory is the most consequential in the codebase: §15.10 names it as the seam a future
  contract compiler / Policy IR grows from.
- **`models.py`** (**L0**, P1 `b482bc4`) — the canonical cross-layer value contracts
  (`BreachDetail`, `ValidationResult`, `TelemetryEvent`, `DriftResult`, `DegradedReason`). **Moved
  from `domain/models.py` (L2) to the L0 kernel in P1.** Record why: as L2 they forced `L1 → L2` and
  `L4 → L2` edges that the architecture gate had to ignore. Note the canonical path is
  `congine_core.models`, and that `__module__` changed.
- **`domain/models.py`** (L2, P1) — now a **compatibility re-export only**. Its entry should be
  short but explicit: it keeps the historical import path working, and it deliberately retains **L2
  identity** for the architecture gate, so an L1/L4 module importing through it still fails.
- **`ports/sync_runner.py`** (L1, P1) — `ISyncRunner`, the one-method port that replaced
  `BackgroundSyncWorker`'s `L4 → L3` dependency on the concrete `SyncContractsUseCase`. The worked
  example of the ports model; give it a full entry.
- **`tools/check_architecture.py`** (tooling, P1) — the architecture gate. Its deletion test is the
  strongest in the tree: without it, the layer matrix is a claim rather than a constraint. Record
  that its predecessor rule was insufficient and passed while seven forbidden edges were live.
- **`tools/p0_evidence/`** (tooling, P1) — the committed P0 evidence harnesses. Record their
  provenance honestly: they were **reconstructed after P0 closed**, from the committed P0 tests, the
  P0 completion evidence and the recorded methodology. They did **not** exist as committed scripts
  during original P0.

---

# PASS GAP2 — DECISION RATIONALE

**What's missing:** Appendix B indexes the audit IDs and §16 lists debts, but the *reasoning* behind
the design decisions is largely unrecorded.

Mine, in this order:

1. **Every audit-ID annotation** (`FIX-*`, `H1`–`H4`, `M2`–`M5`, `D-*`, `C2`, `L4`–`L7`, `P0-*`,
   `Q*`, `F-*`) — use Appendix B as the index, then read the surrounding code for each. **Note the
   two distinct `P0-` series**, documented at the head of Appendix B.1: `P0-1`/`P0-2` (single digit)
   are the original priority items; `P0-01`…`P0-08` (zero-padded) are the Trust-Critical Hardening
   findings. They are unrelated series. `docs/architecture/AUDIT_ID_INDEX.md` is canonical and is
   maintained (§17 Q12), so check it against what you find in `src/`.
2. **Explanatory comments and docstrings** containing "why", "because", "instead of", "rather than",
   "deliberately", "intentional", "prevents", "avoids", "must not". Quote verbatim with location.
3. **Git history** — commit messages describing choices; blame on architecturally significant lines.
4. **Structural evidence** — choices visible in code with no comment (a required dependency chosen over
   an obvious alternative, a guard that raises rather than degrades, a consistently applied pattern).
5. **`ARCHITECTURE_CURRENT.md` §17** — twelve questions raised for the founder. **All twelve are
   now ANSWERED**, and each answer is a decision worth an entry. Two are especially valuable:
   - **Q1 (`region`)** was answered *twice, in opposite directions* — `49a2f93` made it select an
     endpoint; `6345a1e` (P0-08) reverted that because the hostnames were unverified placeholders.
     This is the single best-documented reversal in the codebase and belongs in the ADR archive.
   - **Q2 (union types)** was answered "support them" rather than "reject them loudly", which is
     what closed D18.
6. **`docs/_suite/hardening/P0_COMPLETION_REPORT.md`** — eight findings, each with an explicit
   *before / now / evidence* structure. This is **stated** rationale (confidence HIGH), which is rare
   in this codebase; most of GAP2's other material will be MEDIUM or LOW. Mine especially:
   - §6, the intentional breaking changes and what each silent failure was traded for;
   - §9, the two architectural bugs caught in flight (an L3→L4 and an L0→L2 violation, and the
     `(str, Enum)` serialization trap) — these are rationale for *placement* decisions that look
     arbitrary in the code;
   - §10, what was deliberately **not** fixed, and why. A recorded non-decision is still a decision.

Output one entry per candidate decision:

```
### CANDIDATE: <title>
- **Decided:** <what, factually>
- **Evidence:** <file:line; verbatim quotes; commit refs; ARCHITECTURE_CURRENT §n>
- **Apparent rationale:** <what the evidence suggests>
- **Confidence:** HIGH (stated) | MEDIUM (implied) | LOW (inferred) | UNKNOWN (no evidence)
- **Rejected alternatives visible:** <if any>
- **Consequences in code:** <what it forces elsewhere, including negatives>
- **Architecturally significant?** YES/NO — affects structure, non-functional characteristics,
  dependencies, interfaces, or construction technique?
- **❓ QUESTION FOR FOUNDER:** <required unless confidence is HIGH>
```

Expect 20–35 candidates. This pass feeds both F03 (ARD) and F09 (ADR archive).

---

# PASS GAP3 — INTEGRATION SURFACE & WORKED EXAMPLES

**What's missing:** §5 catalogues ports and §6 documents wiring, but there are no *verified worked
examples* — and both the document suite and the documentation website need them badly.

Produce:

**3.1 Public API surface.** Every symbol in `__all__` (**56** at last count — verify): name, layer,
signature, intended caller. Plus what is deliberately **not** exported and why (`IValidator` is the
standing example).

Eleven symbols are new since the v1 pass and have no documentation anywhere — cover each:
`DegradedReason` · `LoadShedError` · `ValidationResult.is_enforced()` · `admit_contract` ·
`ContractAdmissionResult` · `ContractAdmissionIssue` · `ContractAdmissionCode` ·
`ContractAdmissionLevel` · `ContractAdmissionMode` · `ContractSource` ·
`DEFAULT_VALIDATION_TIMEOUT_MS`. Also `find_unenforced_keywords`, which existed but was reachable
only through a private module path despite the project's own conventions making it mandatory for
every contract loader.

For `ContractAdmissionCode` and `DegradedReason` specifically, record that both are `enum.StrEnum`
and **published vocabularies**: their values cross process boundaries into logs today and into the
planned MCP surface and evidence store later. An integration switches on the code and never parses
the message. Note the constraint that follows — members may be added, never renamed or repurposed.

**3.2 Minimal working example — offline/standalone.** The complete, shortest path from nothing to a
passing validation: install command, environment variables, a contract file, the guarded function, the
result. **Verify it actually runs.** Record the exact output.

**3.3 Minimal working example — failing validation.** Same, but the payload violates the contract.
Record the exact breach structure returned, verbatim.

**3.4 One example per enforcement posture.** Observational, permissive, strict — what the caller
observes in each. Verified.

**3.5 One example per guard mode.** Envelope, output, raise — with the interaction against fail-mode
made explicit (they are independent raise sites).

**3.6 The false-safety demonstrations.** This pass's subject has changed since the v1 batch, because
the contracts that used to demonstrate false safety are now **refused at load**. There are three
parts, and the third is the one that matters most.

**3.6a — What admission refuses, and how.** Load each of the following **through the production
loader** (`SyncContractsUseCase`, not a direct cache write), and record the exact ERROR line, the
machine-facing `ContractAdmissionCode`, and the `path`:

| Contract | Expected code |
|---|---|
| `{"properties": {"a": {"type": "str"}}}` | `unknown_type` |
| `{"properties": {"a": {"type": []}}}` | `empty_type_union` |
| `{"properties": {"a": {"type": ["string","mystery"]}}}` | `unknown_type` |
| `{"properties": {"user.email": {"type": "string"}}}` | `ambiguous_property_path` |
| `{"properties": {"a": {"type":"string","pattern":"(a)\\1"}}}` | `invalid_pattern` *(RE2 has no backreferences)* |
| `{"properties": {"a": {"type":"string","minLength":3}}}` *(default config)* | `unsupported_keyword` |
| `{"required": "email"}` | `invalid_structure` |
| `{"properties": {"a": {"enum": "yes"}}}` | `invalid_structure` |

Then validate against one of the refused ids and record what the caller sees. Expected:
`CongineContractNotFoundError` — the system fails closed rather than passing. **Verify this; do not
assume it.**

**3.6b — The same `minLength` contract, admitted.** Re-run the `minLength` case with
`CONGINE_SEMANTIC_VALIDATION=true`. It should now be **admitted**, because an evaluator that enforces
it is wired. Record both outcomes side by side: this is the empirical proof that admission judges
against a *capability set* rather than a flag, and it is the cleanest demonstration in the corpus of
why that design was chosen.

**3.6c — The residual bypass. THE MOST IMPORTANT EXAMPLE IN THE CORPUS.** Take the dotted-path
contract from 3.6a — the one admission refuses — and write it **directly** with
`container.schema_storage.put(...)`, bypassing the loader. Then validate `{"user": {"email": 12345}}`
against it.

Expected: `status="pass"`. An integer passes a contract that appears to require a string matching an
email pattern. **Run it. Record the verbatim output.** This is debt D17, it is the one genuinely open
safety gap in the system, and F05/F06/F07 all need it demonstrated rather than asserted. Also record
the two mitigations and verify each: the AST test that fails CI when production code adds an
unadmitted writer, and the fact that `admit_contract` is exported from the package root so an
embedder can run the same check by hand.

**3.6d — Union types, for the record.** `{"type": ["string","null"]}` was the single most
safety-critical example in the v1 corpus; it caused permanent silent degradation. **It is fixed.**
Run it with a string, with `None`, and with an integer, and record all three. It should enforce
correctly — matching any member, breaching on none. Keep this example: F02 and F09 need it to explain
why the admission boundary exists, and F05 needs it as a closed finding. **Label it clearly as
historical.**

**3.6e — Enforcement vs conformance.** Produce, and record verbatim, all three states of the P0-05
model on real results:

```
is_enforced() and is_pass()        -> evaluated, conforming
is_enforced() and not is_pass()    -> evaluated, violated
not is_enforced()                  -> NOT evaluated (see degraded_reason)
```

For the third, produce **two distinguishable causes** — a deadline overrun
(`degraded_reason == "timeout"`) and a saturated executor (`"load_shed"`) — and show that
`except TimeoutError` still catches both while `except LoadShedError` catches only the second. Show
that a degraded result carries `status="fail"` with **zero breaches**, so `is_pass()` alone cannot
distinguish "violated" from "never checked". That is the whole reason `is_enforced()` exists.

**3.7 Non-dict output handling.** The `extractor=` pattern, verified.

**3.8 What a new port implementation must provide.** For each `ports/` module plus the in-domain
`IValidator` — **enumerate them from `congine_core.ports.__all__` at HEAD rather than working from a
count; do not reuse "seven ports" or "eight ports", and do not omit `ISyncRunner`** —: the minimum contract a replacement must
satisfy (thread safety, blocking behaviour, failure semantics), derived from the test fakes in
`conftest.py` as well as the Protocol.

**Verify the claim that makes this section worth writing.** `ARCHITECTURE_CURRENT.md` §5.9 now
asserts that **implementing a Protocol as written is sufficient to be wired** — the gap between
declared and required surface is closed (D14 / §17 Q8, plus P0-01). Test it: write a minimal
`IValidationRunner` from the port docstring alone, with no Congine imports, inject it, and call
`container.health()` and `container.close()`. Both must succeed. This exact test is what caught the
P0-01 defect, and it is the cheapest guard against the gap reopening.

For `IValidationRunner`, record the obligation that is easiest to get wrong and hardest to detect:
saturation must raise **`LoadShedError`** and deadline overrun must raise plain `TimeoutError`. Since
the former subclasses the latter, an implementation that raises only `TimeoutError` passes every
existing test while silently reinstating the conflation P0-06 removed.

**Every example in this pass must be executed, not composed.** If an example fails, that is a finding —
record it rather than fixing the example to look good.

---

# PASS GAP4 — EMPIRICAL MEASUREMENTS

**What's missing:** F05 (Proof of Concept & Evidence Report) needs numbers, and numbers must be
measured rather than asserted.

Measure and record, with the exact command used:

**4.1 Test suite.** Full run: pass/fail/skip counts, duration. Break down by category (unit,
integration, adversarial, concurrency, **architecture**). The baseline to compare against is
**613 passed / 1 skipped** at the P1 CLOSED commit `b482bc4`; report any drift.

*(History, for labelled comparison only — never as a current-state claim: 293/1 at `a561992`,
350/1 at `49a2f93`, 436/1 mid-P0, 478/1 at `6345a1e` (P0 closure), 540/1 at P1 implementation.)*

Test modules worth calling out by size, because they are the evidence base for the newest
invariants: `test_contract_admission.py`, `test_p0_result_semantics.py`,
`test_config_construction_parity.py`, and — added in P1 —
`tests/architecture/test_layer_dependencies.py` (90 tests), `test_p1_lifecycle.py`,
`test_runtime_protocol_validation.py`.

**4.2 Coverage.** Overall and per-module, especially hot-path modules. Note anything uncovered.

**4.3 Determinism, demonstrated.** Run the same payload/contract pair N times (N ≥ 1000) and confirm
byte-identical verdicts. This is the product's central claim; it should be measured, not assumed.

**4.4 Validation latency.** Measure the hot path across a representative spread of payload and contract
sizes. Report distribution, not just a mean.

**4.5 Load-shedding behaviour.** Saturate the executor and measure rejection latency. Confirm it sheds
rather than queues. **Additionally confirm the P0-06 separation empirically**: every rejection under
saturation is a `LoadShedError` carrying `degraded_reason="load_shed"`, a deadline overrun is a plain
`TimeoutError` carrying `"timeout"`, and a bare `except TimeoutError` still catches both. Report the
measured p50 as observed — **do not tune toward a previously reported figure.**

> **Harness warning, from experience.** The obvious way to write this measurement — start N threads
> that hold permits, then fire the probe — fails silently if the holding threads die on an exception
> (e.g. a name referenced before definition). The pool is then *not* saturated, every call is
> accepted, and the transcript looks like a load-shedding failure rather than a broken harness.
> Assert that the executor is actually saturated before measuring, and record that assertion.

**4.6 Cache behaviour.** Demonstrate the O(1) claim empirically across cache sizes.

**4.7 Boot behaviour with a dead control plane.** Time initialisation against an unreachable endpoint.
Confirm the bounded-initialisation guarantee.

**4.8 Static analysis.** Linter, type checker, `bandit`, `pip-audit` — results, or recorded as a gap if
unconfigured.

**4.9 Scale facts.** Source file count, LOC, module count per layer, test count, config field count,
port count, `__all__` symbol count. These are cited throughout the suite; establish them once,
authoritatively. Expected at `6345a1e`, to be **verified not copied**: 39 files · 33 implementation
modules · ~6 700 lines · 48 config fields · 8 `ports/` modules + `IValidator` · 56 exported symbols ·
38 test files.

**4.10 Contract admission, measured.** New, and F05 needs it:

- **Repository-wide preflight.** Run `admit_contract` over every contract tracked in the repo
  (`examples/LangChain/contracts/*.json`), each judged under the configuration it is **documented**
  to run in. Report the admit/reject count and every code. The expectation is **100% admitted under
  documented configuration**; if it is not, that is a finding — **do not weaken admission to make
  the number look good.**
- **The same contracts under native (rule-only) configuration.** Some will be refused, and that is
  the correct answer rather than a false positive: run them with semantic validation off and those
  clauses genuinely are not enforced. Report both columns side by side. This is the measurement that
  demonstrates the capability-set design.

**4.11 Determinism under the new boundary.** §4.3's repeat measurement should be re-run *after*
admission is in the path, to confirm the gate did not introduce variance. Same payload, same
contract, same configuration, N ≥ 1000 → exactly one canonical verdict.

If a measurement cannot be taken, record `NOT MEASURED: <why>`. Do not estimate.

---

# FINAL REPORT (in chat)

- The four file paths written; COMPLETE or PARTIAL with resume point.
- Counts: files covered, decision candidates, examples verified, measurements taken.
- **Any disagreement found between `ARCHITECTURE_CURRENT.md` and the code** — this means the
  architecture document has drifted and must be corrected before authoring begins.
- **Every ❓ QUESTION FOR FOUNDER**, consolidated and numbered.
- Every `UNKNOWN`, `NOT MEASURED` and `RATIONALE NOT RECORDED` item.
- **Any example that failed to run**, with what happened.

```text
=== END PROMPT D1 ===
```

---

## After it runs — your checklist

- [ ] **GAP3.6c exists and shows a `pass` on an unenforced contract via a direct `put()`.** This is
      now the most important example in the corpus — the one genuinely open safety gap (D17). If it
      is missing or asserted rather than executed, the pass is not done.
- [ ] GAP3.6a covers all seven admission codes, run through the **production loader**, and shows that
      validating a refused contract raises rather than passes.
- [ ] GAP3.6b shows the same contract admitted and refused under different evaluator configuration.
      That contrast is the argument for the capability-set design.
- [ ] GAP3.6d is present and **clearly labelled historical**. Nothing in the corpus may describe the
      union-type defect as live.
- [ ] GAP3.6e demonstrates all three states of `is_enforced()` × `is_pass()`, with load shed and
      timeout distinguishable.
- [ ] GAP4.3 confirms determinism with a real repeat count, **re-measured with admission in the
      path**.
- [ ] GAP4.10 reports admission preflight at 100% under documented configuration — and reports the
      native-configuration column honestly rather than suppressing it.
- [ ] GAP2 has 20+ candidates with honest confidence ratings, and the eight P0 items are among them
      at HIGH confidence (they have *stated* rationale, which most of this codebase does not).
- [ ] **Answer the founder questions before running D2.** They become the "why it's shaped this way"
      content that no amount of code reading can recover. Note that §17 Q1–Q12 are already answered —
      your new questions should be about what P0 and P1 deliberately deferred (see the P1 completion
      report's deferrals list and §16's D-ADM entry), not about those.
- [ ] If any drift was found against `ARCHITECTURE_CURRENT.md` **beyond what its current-state
      header block and §16 reconciliation table already record**,
      correct that document first — the whole suite cites it.
