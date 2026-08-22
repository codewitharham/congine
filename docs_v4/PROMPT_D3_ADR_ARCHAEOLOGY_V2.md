# PROMPT D3 — ADR ARCHAEOLOGY V2 (replaces PROMPT_C)

## How to use

**Where:** Claude Code. Run any time after D1; ideally after F03 so the vocabulary is settled.
**Attach:** your answers to the D1 founder questions.
Reads from repo: `docs/_suite/gap/GAP2_DECISIONS.md`, `ARCHITECTURE_CURRENT.md`.
**Produces:** `docs/adr/NNNN-*.md` + `docs/adr/README.md`, and `docs/_suite/F09_DECISION_ARCHIVE.md`.

**Two stages with you in the middle. This is not optional.** Claude Code can recover *what* was
decided; it frequently cannot recover *why*. A fabricated rationale in a permanent record is worse
than an honest gap, because ADRs are consulted precisely when someone is about to reverse a decision.

**What changed from v1:** the candidate-mining work is largely done — `GAP2` produced it and
`ARCHITECTURE_CURRENT.md` Appendix B indexes every audit ID. Stage 1 is therefore consolidation and
triage rather than excavation, and §16 (the debt register, with its reconciliation table) and §17
(open questions, six of nine now answered) are new inputs.

> **Revised 2026-08-17 against `6345a1e`.** This prompt is the one that *benefits* most from the two
> commits that have landed since it was drafted, for a reason worth stating up front: **the archive
> is no longer purely archaeological.** `49a2f93` answered all twelve §17 open questions, and
> `6345a1e` landed eight hardening findings with a written completion report. That means a large
> block of decisions has **stated, contemporaneous rationale** — HIGH confidence, quotable — rather
> than rationale you must infer from structure. Those should be the easiest and best ADRs in the log.
>
> It also means the log has its first genuine **supersession**: §17 Q1 (`region`) was answered one
> way in `49a2f93` and reversed in `6345a1e`. That is exactly what ADR `Status: Superseded by NNNN`
> exists for, and getting it right is worth more than any three ordinary entries — because it is the
> only place in the corpus that demonstrates the practice actually working.

---

# STAGE 1 — PROPOSE

```text
=== BEGIN PROMPT D3, STAGE 1 ===
```

# ROLE

You are consolidating the decision record for Congine. Many architecturally significant decisions were
made over months; none were formally recorded. Candidate material already exists — your job is to
triage it, fill what it misses, and present it for the founder's review. **You are not writing ADRs in
this stage.**

# WHY THIS MATTERS

The founder works with AI coding agents. An agent with no access to rationale will confidently reverse
a hard-won decision and silently reintroduce the bug it fixed. This log is the countermeasure, and it
only works if it is honest.

# INPUTS

1. **`docs/_suite/gap/GAP2_DECISIONS.md`** — the primary candidate set (expect 20–35 entries)
2. **`ARCHITECTURE_CURRENT.md` Appendix B** — the complete audit-ID index. **Note the two distinct
   `P0-` series** (B.1): `P0-1`/`P0-2` are the original priority items; `P0-01`…`P0-08` are the
   Trust-Critical Hardening findings. Do not merge them into one numbering.
3. **`ARCHITECTURE_CURRENT.md` §16** — the debt register, with a **reconciliation table** at the top
   giving each item's verified current status (resolved / open / superseded / deferred). Use that
   table rather than a headline count. Both halves are ADR material,
   and they are different kinds: an *open* debt may encode a decision to accept a trade-off; a
   *closed* one records the decision that closed it, and often a rejected alternative. Distinguish
   "accepted trade-off" from "unfixed bug" — only the former is a decision.
3a. **`docs/_suite/hardening/P0_COMPLETION_REPORT.md`** and
   **`docs/_suite/hardening/P1_COMPLETION_REPORT.md`** (the latter including its *Final P1 Closure*
   section) — stated rationale for the P0 and P1 decisions, which is rare in this codebase and
   should be treated as HIGH-confidence evidence.
3b. **`git log` through the P1 CLOSED commit `b482bc4`** — commit messages for P0 and P1 carry
   rationale that exists nowhere else.
4. **`ARCHITECTURE_CURRENT.md` §17** — nine questions, of which **six are now answered** (Q3, Q5 and
   Q9 remain open). Each answer is a decision, and each was made deliberately with the question
   written down first, which is the
   cleanest provenance any decision in this codebase has.
5. **`ARCHITECTURE_CURRENT.md` §15** — decisions about what *not* to build yet are decisions
6. **`docs/_suite/hardening/P0_COMPLETION_REPORT.md`** — the eight P0 items, the intentional breaking changes, the two architectural bugs
   caught in flight, and what was deliberately not fixed. All are decision records in narrative
   form. Pair it with the P1 completion report's *Final P1 Closure* section for the P1 equivalents,
   and with `ARCHITECTURE_CURRENT.md`'s current-state header block and §16 reconciliation table for current status.
7. **`docs/_suite/hardening/P0_COMPLETION_REPORT.md`** — the primary-source document for eight
   decisions, in *before / now / evidence* form. Quote it; this is stated rationale.
8. The codebase and git history — to fill gaps GAP2 left

# METHOD

**Step 1 — Consolidate.** Start from GAP2. Add anything found in §16, §17, §15 or git history it missed.

**Step 2 — Triage by significance.** ADR-worthy means it affects **structure, non-functional
characteristics, dependencies, interfaces, or construction technique**. Classify each `SIGNIFICANT` /
`BORDERLINE` / `NOT SIGNIFICANT` with one line of reasoning. **Be willing to reject** — a log padded
with trivia is a log nobody reads. Target 18–28 accepted.

**Step 3 — Rate rationale confidence honestly.** HIGH (stated in code/comment/commit — quote it) /
MEDIUM (strongly implied) / LOW (inferred from structure) / UNKNOWN (no evidence). **Below HIGH, pose a
specific question to the founder. Do not fill the gap yourself.**

> **Expect a bimodal distribution, and do not flatten it.** Decisions from `49a2f93` and `6345a1e`
> mostly rate **HIGH**: the question was written down in §17 before it was answered, or the rationale
> is stated in a module docstring, or the P0 completion report records it in *before / now* form.
> Older decisions — the six-layer hexagon, `re2` as a core dependency, LFU-with-TTL, the frozen value
> objects — mostly rate LOW or UNKNOWN, because they predate any recording practice.
>
> That contrast is itself worth a line in F09's "decisions whose rationale could not be recovered"
> section: the codebase began recording its reasoning at a specific point, and everything before it
> is archaeology. Resist the temptation to promote an old decision to HIGH because a *recent*
> document explains it — a later rationalisation is not the original reason, and conflating the two
> is precisely how a fabricated rationale enters a permanent record.

**Step 4 — Include the negative decisions.** Decisions *not* to build something are among the most
valuable ADRs, because they are the ones most likely to be silently reversed. From §15 and the roadmap:
not building a distributed cache yet; not putting a model on the verdict path; not training per-agent
models; not using vector search in Phase 1; keeping the dependency surface small.

**Step 5 — Identify supersessions.** A decision that was made, then *reversed*, needs two ADRs and a
`Status` link, not one merged entry. There is at least one certain case:

> **`region` (§17 Q1).** `49a2f93` decided *"`region` selects a default control-plane URL"* —
> answering the recorded question directly. `6345a1e` (P0-08) **reversed it**: the hostnames were
> unverified placeholders, so the mapping could send an API key to an endpoint nobody had confirmed.
> The replacement decision is narrower — region is metadata, only `CONGINE_BASE_URL` selects a
> control plane, and region-without-base-URL is an error rather than a silent loopback fallback.
>
> Write **both**. The first gets `Status: Superseded by NNNN`. Its Context is still valuable, because
> the forces that motivated it (a validated, documented, GDPR-connoted field that did nothing) were
> real. The second's Consequences must record the general rule it established: **a governance SDK
> must never infer a credential destination.**
>
> This is also the clearest case in the corpus of a decision that was *correct as asked* and still
> wrong — the real question was not "what could `region` do" but "what is this component allowed to
> infer". Say so in the second ADR's Context. It is the kind of thing an agent reading the log later
> most needs to see.

Check whether any other candidate has the same shape before assuming this is the only one.

**Step 6 — Order and number.** ADR-0001 is the conventional meta-ADR establishing the practice. Then
foundational decisions, then chronological where determinable.

# OUTPUT

Write `docs/adr/_CANDIDATES.md`:

```
## Proposed ADR-NNNN: <title, form "Use X for Y" or "Do X rather than Y">
- Significance: SIGNIFICANT | BORDERLINE | NOT SIGNIFICANT — <one line>
- What was decided: <factually>
- Evidence: <file:line; quotes; commits; ARCHITECTURE_CURRENT §n; GAP2 ref>
- Context (recoverable): <the forces that appear to have driven it>
- Rationale confidence: HIGH | MEDIUM | LOW | UNKNOWN
- Consequences in code: <including negative ones>
- Rejected alternatives visible: <if any>
- ❓ QUESTION FOR FOUNDER: <required unless HIGH>
- Relates to: <other candidate numbers>
```

# SEED LIST — verify each, add everything else

Foundational: six-layer hexagon with inward-only dependencies · determinism as a hard constraint,
no model on the verdict path · `re2` as a required core dependency · structural `Protocol` ports rather
than ABCs · frozen value objects · single composition root.

Hot path: bounded executor with load shedding · permit release in a done-callback · nested validation
inline rather than pooled · sync and async sharing one semaphore · telemetry published before fail-mode
enforcement.

Resilience: circuit breaker plus disk snapshot · portalocker single-flight boot with jitter · snapshot
integrity via atomic write, advisory lock, symlink and owner refusal · per-scope snapshot path hashing ·
prime-in-place rather than clear-then-refill.

Semantics: dual schema vocabulary (fast rules by default, full JSON Schema opt-in) · `IValidator` in L2
rather than L1 · three fail modes with DEGRADE default · guard mode as an independent raise site ·
LFU with TTL as the cache policy.

Tenancy: `get_default()` disabled in multi-tenant mode · bounded tenant registry · **P0-1 deferred
teardown via weakref** · finalizer armed at construction rather than at eviction, making every
container self-cleaning (`49a2f93`, §17 Q5).

Semantics, continued: **union `type` support rather than loud rejection** (`49a2f93`, Q2 — this is
what closed D18; record both options the question offered and why the first won) · `null_forbidden`
retained as a permanent CONGINE extension with a portability advisory rather than removed (Q3).

Ports: **`IStoppable` / `IObservable` extracted into `ports/lifecycle.py`** so a port declares its
full lifecycle surface (`49a2f93`, Q8, closing D14) · **health read through declared surfaces rather
than concrete attributes** (P0-01) — and note the second-order decision: the same principle was
applied to the *new* admission counters in the same pass, specifically so the fix did not ship
alongside its own successor.

Contract admission (`6345a1e`, P0-03/P0-04) — expect four or five ADRs here, not one:
- **A contract CONGINE cannot interpret is a publication error, not a runtime condition** — the
  governing decision. Rejected alternative: make `RuleEngine` strict at runtime, declined because it
  puts authoring diagnosis on a millisecond-budgeted hot path.
- **Admission lives in L2 and is pure** — takes a mode and an explicit capability set, reads no
  configuration. Rejected alternative: an L3 use case.
- **Enforceability is judged against a capability set, not an "is semantic validation on?" flag** —
  because "semantic validator enabled ⇒ every non-native keyword is enforced" is already false
  (`format` needs a second flag).
- **`WARN` relaxes compatibility, never correctness** — a permissive mode that could admit an
  unenforceable contract would rebuild the failure the boundary removes.
- **Never preserve malformed grammar because old code happened not to crash on it** — the rule that
  justified refusing bare-string `required` (iterated character-by-character) and bare-string `enum`
  (matched by substring).

Result semantics (`6345a1e`): **`is_enforced()` added rather than changing `is_pass()`** (P0-05) ·
**`LoadShedError` subclasses `TimeoutError` but not `CongineBaseException`** (P0-06 — two separate
inheritance decisions, each load-bearing, and each worth stating) · **`LoadShedError` placed in L0
rather than beside the executor that raises it**, because L3 must catch it and L3→L4 is forbidden ·
**machine-facing enums are `enum.StrEnum` while the pre-existing policy enums are left as
`(str, Enum)`** — the second half is as much a decision as the first, and its rationale (changing
them would alter output elsewhere) is the kind that gets silently reversed.

Configuration (`6345a1e` closeout): **`__post_init__` is the single normalization *and* validation
boundary** · **`validate()` is called, never reimplemented — one owner for the invariants** ·
**uniform `strip().lower()` on both construction paths**, which only widens acceptance ·
**`from_env` keeps its per-field `try/except` so errors name the environment variable** · **fail
loudly on malformed booleans, unknown enum values and empty directory paths** (P0-07), on the
principle that *a typo must never quietly change deployment topology*.

Negative decisions: no distributed cache yet · no vector search in Phase 1 · no per-agent model
training · dependency-light core with optional extras · no LLM in correction-hint generation ·
**no model anywhere in contract admission, the conformance verdict, or enforcement-action
selection** · **version-aware fail-closed deliberately deferred** rather than approximated (blocked
on `ISchemaStorage.put` carrying no version) · **partial-enforcement metadata deferred** rather than
shipped as an unsafe escape hatch · **the P0-2 keyword scan was not moved behind `ISchemaStorage`**
(Q4) — an AST test enforces it instead, which is a decision with a known cost (D-ADM stays open).

**P1 structural decisions (`b482bc4`) — candidates for verification, not automatic ADR creation.**
Each of these is a real decision with a stated rationale in the P1 completion report, but the
founder must confirm significance and framing before any becomes an ADR:

- **an explicit layer dependency matrix instead of numeric layer ordering** — including the finding
  that the previous `target_layer <= source_layer` rule was green while seven forbidden edges were
  live, and the choice to *falsify* the new gate rather than trust a passing run;
- **`TYPE_CHECKING` imports enforced as architectural dependencies**, with the deliberate refusal to
  grant any exemption or allowlist entry;
- **canonical cross-layer value contracts relocated from L2 to the L0 kernel**, with the L0
  admission principle written down so L0 does not become a dumping ground;
- **a compatibility re-export (`domain/models.py`) that deliberately retains L2 identity** for the
  gate — chosen over both a hard break and a gate exemption;
- **a narrow `ISyncRunner` port instead of an `L4 → L3` concrete dependency** — chosen over
  allowlisting the edge;
- **runtime `runtime_checkable` Protocol validation at composition seams**, with the explicit
  scoping that it proves structural compatibility, not behavioural conformance;
- **transactional composition root** — rollback of partially acquired resources rather than
  documenting the leak;
- **terminal lifecycle semantics** — `CongineLifecycleError` on use-after-close, deliberately *not*
  a degraded `ValidationResult`;
- **blocking strict mypy on production source only**, rather than either non-blocking or whole-tree;
- **RE2 as the sanitizer engine**;
- **evidence harnesses committed as reproducible trust artifacts**, reconstructed after P0 closed —
  including the honest decision *not* to claim the new determinism hash matches P0's.

**Attribute each decision to when it was made.** Distinguish: made during original design · made
during P0 · made during P1 · rationale reconstructed retroactively. **Do not fabricate the
motivation for a P1 choice merely because the diff makes the change obvious** — where the report
does not state a reason, `RATIONALE NOT RECORDED` remains the correct answer.

# GUARDRAILS

- Write no ADRs in this stage.
- Never invent rationale. `UNKNOWN` plus a question is correct.
- Do not pad. Mark trivia NOT SIGNIFICANT.
- Do not modify source code.

# FINAL REPORT

- Candidate count by significance.
- The consolidated **❓ QUESTIONS FOR FOUNDER**, numbered so they can be answered by number.
- **Candidates where the code shows a decision but no rationale evidence exists at all** — the
  highest-risk gaps, most likely to be silently reversed.
- Proposed numbering order.

```text
=== END STAGE 1 ===
```

---

# ⏸ THE HUMAN STEP — YOURS, AND NOT SKIPPABLE

For each candidate: confirm or override the significance rating; answer every ❓; and **be honest where
you do not remember.** "Rationale not recorded at the time" is a useful ADR. A confident invention is a
landmine that will be trusted for years.

Also add, by hand, any decision that left **no trace in the code** — something you chose *not* to
build, a direction abandoned, a constraint accepted. Archaeology never finds these, and they are often
the most valuable entries in the log.

---

# STAGE 2 — WRITE

```text
=== BEGIN PROMPT D3, STAGE 2 ===
```

# ROLE

Write the approved ADRs from `docs/adr/_CANDIDATES.md` as annotated by the founder.

# FORMAT (Nygard, exactly)

`docs/adr/NNNN-kebab-case-title.md`, zero-padded to four digits:

```markdown
# NNNN. <Short decision title>

Date: <YYYY-MM-DD — when the decision was made if known, else the recording date, noted as such>
Status: Accepted

## Context
<The forces, constraints and situation that required a decision. NEUTRAL and factual — no solution, no
advocacy. This is the section a future reader relies on most, because it tells them whether the forces
still apply.>

## Decision
<Active voice: "We will …". One clear choice.>

## Consequences
<The resulting state, BOTH positive and negative. What becomes easier. What becomes harder. What new
constraints follow. Rejected alternatives and why they lost.>
```

# RULES

1. **ADR-0001 first** — the meta-ADR establishing the practice. Context: decisions were made without a
   record, and AI-assisted development makes silent reversal a live risk. Decision: Nygard-format ADRs
   in `docs/adr/`, append-only. Consequences: rationale survives; a small per-decision cost; never
   edited except the `Status` line.
2. **Context must be neutral** — the situation, not the solution.
3. **Consequences must include the downside.** An ADR listing only benefits is marketing.
4. **Mark retroactive records honestly** — after the Status line:
   `> Recorded retroactively on <date>. Reconstructed from code evidence and the author's recollection.`
   Where the founder said rationale was not recorded, say so in Context rather than inventing.
5. **Include rejected alternatives** wherever known — frequently the most valuable content.
6. **Cite evidence** — `file:line`, audit ID, commit, or `ARCHITECTURE_CURRENT §n`.
7. **One to two pages each.** Running long usually means it is two decisions — split it.
8. **Cross-link** related ADRs.
9. **Never edit an accepted ADR's substance.** Supersede with a new one and update the old `Status`.
    The `region` pair (Stage 1, Step 5) is the worked example: `Status: Superseded by NNNN` on the
    first, and a Context on the second that explains what the reversal learned rather than merely
    what it changed.
10. **Write only what the founder approved.**

# ALSO PRODUCE

- **`docs/adr/README.md`** — the index: numbered list with titles and statuses, a paragraph on what
  ADRs are and when to write one, the template, and the append-only rule.
- **`docs/_suite/F09_DECISION_ARCHIVE.md`** — the suite document: an introduction explaining the
  practice, the decisions grouped thematically (foundational / hot path / resilience / semantics /
  tenancy / negative decisions), each summarised in a paragraph with a link to its ADR, plus a section
  on **decisions whose rationale could not be recovered** — an honest record of what was lost.
- **Add ADR cross-references to `ARCHITECTURE_CURRENT.md`.** Note that §12 is the *configuration
  surface*, not design decisions — that numbering came from an earlier draft. The sections that
  actually want ADR links are the **current-state header block** and **§16** (reconciliation),
  **§13** (contract admission),
  **§14.8–§14.10** (the invariants — especially the epistemic/trust set **G12–G14** and the
  structural set **G15–G16**), **§16.2** (the debt status table) and
  **§17** (the question-resolution table). Link, do not restate.
- **Delete `docs/adr/_CANDIDATES.md`** — it was scaffolding.

# GUARDRAILS

- Do not invent rationale. Where the founder said "not recorded," record that.
- Do not write ADRs for rejected candidates.
- Do not editorialise about the quality of past decisions. Record them.
- Do not modify source code.

# FINAL REPORT

- Every ADR created, with number and title.
- The full text of any ADR where you made a judgment call phrasing the rationale, so the founder can
  verify you represented their reasoning correctly.
- Decisions noticed while writing that are not yet recorded and probably should be.

```text
=== END STAGE 2 ===
```

---

## After it runs — your checklist

- [ ] ADR-0001 exists and establishes the practice.
- [ ] Every Context is neutral; every Consequences names a downside.
- [ ] Retroactive entries are marked as such — and the `49a2f93`/`6345a1e` entries are **not**
      marked retroactive, because their rationale was recorded at the time. Marking a
      contemporaneous decision as reconstructed understates the evidence you actually have.
- [ ] **The `region` supersession pair exists**, with `Status: Superseded by NNNN` on the first.
      This is the only demonstration in the log that the practice works; without it the archive is a
      list rather than a record.
- [ ] The P0 placement decisions are recorded with their reasons: `LoadShedError` in L0,
      `ContractAdmissionMode` in L0, `admit_contract` in L2. Each looks arbitrary in the code and is
      not, and each is the kind an agent will "tidy" back into the wrong layer.
- [ ] The negative decisions (what you chose not to build) are present — these are the ones an agent
      will otherwise reverse.
- [ ] No ADR contains a rationale you did not actually have.
- [ ] `CLAUDE.md` points at `docs/adr/` with an instruction to consult before architectural changes.
      **This is what makes the log operational rather than decorative.**
