# V2 — THE CONGINE FORMAL DOCUMENT SUITE

What the nine documents are, what each must contain, how they differ from the earlier repo-docs batch,
and the order to build them. Read this before running `PROMPT_D1`.

> **Revised 2026-08-17 against commit `6345a1e`.** This batch was drafted against `a561992`. Two
> commits have landed since — `49a2f93` (closed all twelve `ARCHITECTURE_CURRENT.md` §17 open
> questions) and `6345a1e` (the eight-item **P0 Trust-Critical Hardening** pass). The reconciliation
> record is `ARCHITECTURE_CURRENT.md`'s **current-state header block** plus its **§16
> reconciliation table**, and every prompt in this batch now points at those.
>
> **The one change that rewrites this document's centre of gravity.** The v1 batch elevated the
> **union-type defect (D18)** to "the single most safety-critical artifact in the suite":
> `{"type": ["string","null"]}` caused silent permanent degradation of every validation against that
> contract. **That defect is fixed.** Unions are now a first-class, enforced spelling.
>
> It has been replaced — not deleted — by something broader and more interesting to document: the
> **contract admission boundary** (`ARCHITECTURE_CURRENT.md` §13.8). CONGINE now refuses, at load,
> any contract whose meaning it cannot determine, and refuses any clause no active evaluator will
> execute. The safety-critical story is no longer *"here is a trap the product cannot see"* but
> *"here is the boundary that makes the trap unreachable, and here is exactly what it still does not
> cover."* That is a better story and a harder one to write honestly, which is why the coverage
> matrix in §4 now has a row for it.
>
> **Do not describe D18 as a live defect in any suite document.** Where it appears, it is history —
> and useful history, because it motivates the boundary that replaced it.
>
> ---
>
> **Reconciled again 2026-08-22, at P1 closure (`b482bc4`).** This document's structure, the F01–F09
> roles, the coverage-matrix philosophy and the authoring order are **unchanged** — P1 was a
> structural hardening pass, not a change to what the suite must say. Three coverage additions and
> one sequencing correction follow, and the architecture spine that the whole suite is built from is
> now the **post-P1** `ARCHITECTURE_CURRENT.md`.
>
> - **Architecture coverage** must now include: the **explicit layer dependency matrix** (not a
>   numeric ordering — `L4 → L2` and `L4 → L3` are forbidden); the **L0 canonical cross-layer value
>   contracts** and the compatibility re-export that keeps L2 identity; **`TYPE_CHECKING` imports
>   enforced under the same matrix** with zero exemptions; the L1 **`ISyncRunner`** port; and the
>   **mechanical architecture gate** that verifies the rule itself.
> - **Contract Language coverage** must keep four things distinct: the **native rule vocabulary**,
>   the **semantic evaluator capability**, **contract admission**, and **explicit non-enforcement
>   truth** (`is_pass()` vs `is_enforced()`). "Everything else is silently ignored" is not the
>   current universal story and must not be written as one — a contract the wired evaluators cannot
>   enforce is *refused*, with the `schema_storage.put()` bypass as the one documented exception.
> - **Evidence coverage** must include the **reproducible P0 harnesses** (`tools/p0_evidence/`,
>   reconstructed after P0 closed — state that provenance) and the **P1 structural verification**:
>   five blocking gates, 613/1, 90 architecture tests, strict production mypy.
> - **Roadmap coverage** starts from **P0 CLOSED / P1 CLOSED / P1.5 NEXT**, then P2, P3, then
>   Phase A onwards. Earlier drafts stepped from "Phase 0" straight to Phase A; that is superseded.
>
> **Do not hardcode debt counts.** Take each item's status from §16's reconciliation table. And
> "P1 CLOSED" is not "enterprise-release ready" — the deferrals are listed in the P1 completion
> report.

---

## 1. TWO TIERS, NOT ONE

Your earlier batch and this one produce different things. Confusing them wastes effort.

| | **Tier R — Repo documentation** | **Tier F — Formal document suite** |
|---|---|---|
| Lives in | The repository (`docs/`, `README.md`) | Published artifacts (PDF / DOCX) |
| Reader | A developer using or extending the SDK | An engineer, investor, partner or auditor being *introduced* to the system |
| Success test | "Can I find the answer fast?" | "Do I now understand this thing completely?" |
| Updated | Per task, continuously | Per phase / release |
| Produced by | The earlier batch (`PROMPT_2/3_DOC_*`) | **This batch** |
| Examples | README, CONTRACTS, RULE-VOCAB, CONFIG-REF | Concept Brief, SRS, ARD, POC Report |

**Tier F is what you asked for**: "the face of the product… extreme level of depth… shown as proof to
anyone being introduced to this idea either for the first time or the thousandth."

Tier R still matters and is not cancelled. But Tier F is the priority now, and the docs *website*
(Task 2) draws from Tier R content while Tier F stands alone as the formal record.

---

## 2. THE NINE DOCUMENTS

| ID | Document | The question it answers | Depth | Primary source |
|---|---|---|---|---|
| **F01** | Concept & Rationale Brief | What is Congine, why does it exist, why now? | Conceptual | Complete Reference Part I–II; §1 |
| **F02** | Domain Compendium | The five key ideas, each to the bottom | **Deepest** | §13, §15; Complete Reference Part III |
| **F03** | Architecture & Design Document (ARD) | How is it built, and why that way? | Deep technical | `ARCHITECTURE_CURRENT.md` §3–§11 |
| **F04** | Software Requirements Specification (SRS) | What must it do, provably? | Formal | §12, §13, §14 + existing SRS |
| **F05** | Proof of Concept & Evidence Report | What is proven, with what evidence? | Empirical | §2, §14, §16, test suite |
| **F06** | Use Case & Edge Case Compendium | Every actor, flow, boundary and failure | Exhaustive | §8, §9, §13 |
| **F07** | Security & Threat Model | What can go wrong, and what stops it? | Deep technical | §14, §13.5 |
| **F08** | Roadmap & Execution Plan | What is next, in what forced order, why? | Strategic | §15; Complete Reference Part IV |
| **F09** | Decision Record Archive | Why is it shaped this way? | Historical | Appendix B, §16, §17 |

### Why nine, and why these

You asked for "POC, ARD etc." and for coverage of "history tracking, token optimization, contracts
definition, MCP server". Mapping your requirements onto the suite:

- **POC** → F05. **ARD** → F03. **SRS** → F04 (you have a draft; it gets rebuilt against verified reality).
- **history tracking / token optimization / contracts / MCP / DSL** → **F02, which is the centrepiece.**
  These five ideas do not belong scattered across an architecture document. They are the product's
  intellectual content and they deserve one document that takes each to the bottom.
- **"idea brief to why solving it"** → F01.
- **"use cases, edge cases"** → F06.
- **"all methodologies"** → distributed: enforcement methodology in F02, engineering methodology in F03,
  verification methodology in F05, security methodology in F07.

---

## 3. F02 — THE DOMAIN COMPENDIUM (the document that carries your requirement)

This is the one that must leave "no marks or gaps." Its structure, since it is the least obvious:

| Part | Subject | Must cover |
|---|---|---|
| **A** | **Contracts** — the standard | What a contract is; the exact eight keywords the engine reads; **every keyword not enforced by default**; **the contract admission boundary** — the seven `ContractAdmissionCode` values, what `strict` vs `warn` can and cannot do, and what happens to a refused contract; rule ordering and why; the dual vocabulary; authoring methodology; versioning; the graduated posture ladder |
| **B** | **The verdict** — judgment | The six rules in evaluation order; determinism as a property and what would destroy it; breach structure; **`is_pass()` vs `is_enforced()` — the three-state model**; enforcement policies; why no model sits on the verdict path |
| **C** | **Token optimization** | LLM statelessness as root cause; the retry-loop economics; the four levers ranked honestly; why deterministic detection is the largest lever and caching the smallest; correction hints; delta protocol; measurement methodology |
| **D** | **History & institutional memory** | Human vs machine context loss; the three stores (event log, architectural graph, pattern index); payload hashing and privacy-by-design; selective recall; the erasure-vs-immutability tension and its resolution |
| **E** | **Multi-agent normalization** | Why agents diverge; **why training is rejected** and what replaces it; contract-as-equalizer; per-agent adapters as anti-corruption layer; capability profiles as statistics not models |
| **F** | **MCP — the integration surface** | What MCP is; why the tool-call model rather than a proxy; the advisory limitation and the enforcement ladder that compensates; the tool surface; where it attaches (§15.1); **stated as not yet built** |
| **G** | **Business Policy DSL & Policy IR** | The compilation pipeline (authoring → DSL → IR → deterministic evaluator); **the design-time vs runtime separation** — models may assist authoring, never render verdicts; relation to policy-as-code precedent; the ladder to Executable Organizational Policy |
| **H** | **How the domains interlock** | The layered dependency; why the build order is forced; what breaks if inverted |

Parts F and G are new relative to your v1 documents and are the reason this batch exists.

---

## 4. THE COVERAGE MATRIX (the "no gaps" guarantee)

`PROMPT_D2` enforces this table. Every concept below must appear in at least one document at **Deep**
level, and cross-references must resolve.

| Concept | F01 | F02 | F03 | F04 | F05 | F06 | F07 | F08 | F09 |
|---|---|---|---|---|---|---|---|---|---|
| Functional vs organizational correctness | **Deep** | Ref | — | Ref | — | Ref | — | — | — |
| Determinism as the governing invariant | **Deep** | **Deep** | **Deep** | Ref | **Deep** | — | Ref | Ref | Ref |
| Contracts & schema vocabulary | Ref | **Deep** | Ref | **Deep** | Ref | **Deep** | Ref | — | Ref |
| The six rules & evaluation order | — | **Deep** | Ref | **Deep** | Ref | **Deep** | — | — | Ref |
| **Contract admission & enforceability** | Ref | **Deep** | **Deep** | **Deep** | **Deep** | **Deep** | **Deep** | Ref | Ref |
| **Enforcement vs conformance (`is_enforced()`)** | Ref | **Deep** | Ref | **Deep** | **Deep** | **Deep** | **Deep** | — | — |
| Union-type degradation (D18) — **historical, FIXED** | — | Ref | Ref | — | Ref | Ref | — | — | Ref |
| **Native vs semantic vocabulary vs admission** (keep distinct) | Ref | **Deep** | **Deep** | **Deep** | Ref | **Deep** | Ref | — | Ref |
| Token optimization | Ref | **Deep** | — | Ref | Ref | Ref | — | Ref | — |
| History / institutional memory | Ref | **Deep** | Ref | Ref | — | Ref | Ref | Ref | — |
| Multi-agent normalization | Ref | **Deep** | Ref | Ref | — | Ref | — | Ref | — |
| MCP integration surface | Ref | **Deep** | **Deep** | Ref | — | **Deep** | Ref | **Deep** | — |
| Business Policy DSL / Policy IR | Ref | **Deep** | Ref | — | — | — | Ref | **Deep** | — |
| Six-layer hexagon & **explicit dependency matrix** | Ref | — | **Deep** | Ref | Ref | — | Ref | Ref | **Deep** |
| **L0 canonical value contracts & compatibility re-export** | — | Ref | **Deep** | Ref | Ref | — | — | — | **Deep** |
| **`TYPE_CHECKING` enforcement & the mechanical architecture gate** | — | — | **Deep** | Ref | **Deep** | — | Ref | Ref | **Deep** |
| **Transactional composition & terminal lifecycle** | — | — | **Deep** | Ref | **Deep** | **Deep** | Ref | — | **Deep** |
| **Reproducible P0 evidence harnesses** | Ref | — | Ref | — | **Deep** | — | Ref | Ref | Ref |
| Ports & adapters catalogue | — | — | **Deep** | **Deep** | — | — | Ref | Ref | Ref |
| Composition root & wiring | — | — | **Deep** | Ref | Ref | — | Ref | — | Ref |
| Lifecycle & bootstrap | — | — | **Deep** | Ref | Ref | **Deep** | — | — | Ref |
| Control flows | — | Ref | **Deep** | Ref | Ref | **Deep** | Ref | — | — |
| Failure paths (22 modes) | — | — | Ref | Ref | Ref | **Deep** | **Deep** | — | — |
| Concurrency & state | — | — | **Deep** | Ref | Ref | Ref | Ref | — | Ref |
| Configuration surface (48 fields) | — | — | Ref | **Deep** | Ref | — | Ref | — | — |
| **Configuration-path parity (one validation owner)** | — | — | **Deep** | **Deep** | Ref | Ref | Ref | — | Ref |
| Invariants & guarantees (13) | — | Ref | **Deep** | **Deep** | **Deep** | Ref | **Deep** | — | Ref |
| Security & trust boundaries | — | Ref | Ref | **Deep** | Ref | Ref | **Deep** | — | Ref |
| Extension seams | — | Ref | **Deep** | — | — | — | — | **Deep** | Ref |
| Debt register (22 items; 15 closed, 7 open) | — | Ref | Ref | Ref | **Deep** | Ref | Ref | **Deep** | Ref |
| Enforcement ladder & deployment | Ref | **Deep** | Ref | Ref | — | **Deep** | Ref | Ref | — |

**Deep** = the authoritative treatment lives here. **Ref** = mentioned with a cross-reference.
A concept with no **Deep** anywhere is a gap and blocks completion.

---

## 5. WHAT CHANGED FROM V1, AND WHY

| Change | Reason |
|---|---|
| **`PROMPT_A_CODEBASE_RECALL` retired** | `ARCHITECTURE_CURRENT.md` already contains ~80% of EX1–EX8. Re-running it duplicates weeks of work. |
| **Replaced by `PROMPT_D1` — four passes, not eight** | Only four things are genuinely missing: per-file narrative material, decision rationale, integration examples, and empirical measurements. |
| **New tier: formal suite (F01–F09)** | You asked for POC/ARD-class documents; the v1 batch produced repo docs. Different artifact, different reader. |
| **F02 Domain Compendium is new** | MCP, Business Policy DSL and Policy IR did not exist in the v1 scope. They are now central and need a home with real depth. |
| **Coverage matrix added** | Your explicit requirement was "no gaps." A matrix makes that testable rather than aspirational. |
| **Union-type defect elevated to safety-critical** | Discovered by Pass 12. It causes silent non-enforcement — the exact failure the product exists to prevent. **Superseded 2026-08-17 — see the row below.** |
| **Current-vs-planned boundary enforced per document** | `ARCHITECTURE_CURRENT.md` §15 proves eight capabilities absent. Documents that imply otherwise destroy credibility with the exact audience they target. |
| **`ARCHITECTURE_CURRENT.md` becomes the technical spine** | Every technical claim in F03–F07 cites a section of it. Documents stop being independently derived and start being consistent by construction. |

### Amended 2026-08-17, against `6345a1e`

| Change | Reason |
|---|---|
| **D18 demoted from safety-critical to historical** | It is **fixed**. Unions are enforced (`49a2f93`), and a union containing an unrecognised member is refused at admission (P0-04). A suite that still warns about it as live would be wrong in the one place it most needs to be right. |
| **"Contract admission & enforceability" added as the new Deep row** | It replaces D18 as the safety-critical spine, and it is *seven* documents' concern rather than four, because it touches semantics (F02), architecture (F03), requirements (F04), evidence (F05), edge cases (F06) and security (F07) simultaneously. |
| **"Enforcement vs conformance" added as a Deep row** | `is_enforced()` (P0-05) makes a distinction that previously existed only in prose: *was the policy actually evaluated?* is now separately answerable from *did the output conform?* Any document that describes the verdict without this is describing the pre-P0 system. |
| **"Configuration-path parity" added as a Deep row** | The P0 closeout found that a directly constructed `CongineConfig` skipped validation entirely and that all five enum fields accepted raw strings — so `fail_mode="strict"` **degraded instead of raising**. One boundary (`__post_init__`) now owns normalization and validation. This is a stated guarantee (G13), not an implementation detail. |
| **Invariant count 11 → 13 (P0) → 16 (P1)** | P0 added **G12** (an uninterpretable contract never becomes active policy), **G13** (configuration is construction-path independent) and **G14** (no silent non-enforcement). P1 added **G15** (the layer matrix is mechanically enforced) and **G16** (transactional composition + terminal close). Three kinds, and F03/F05/F07 must keep them distinct: **G1–G11 mechanical/runtime** (nothing stalls, deadlocks or leaks); **G12–G14 epistemic/trust** — they constrain what CONGINE may **claim**; **G15–G16 structural** — how the system is built and torn down. *(An earlier §14 reconciliation failed to preserve G13 and misnumbered the other post-G11 invariants; the numbering above is canonical.)* |
| **Config surface 46 → 48 fields** | `max_contract_file_bytes` (`49a2f93`), `contract_admission` (`6345a1e`). |
| **Debt register: most items closed, all three HIGH among them** | F05 and F08 must report the current state, not the `a561992` state — and **must read §16's reconciliation table rather than any list quoted here**. *(This row's original enumeration is now out of date: P1 additionally closed **D4** (the `QueueEventBus` stop race), **D10** (constructor-failure resource leak), **D14** (ports under-declaring lifecycle) and the docstring half of **D5**. The one that still matters is the residual admission bypass — **D17, renamed D-ADM** — which P1 explicitly deferred.)* |

---

## 6. BUILD ORDER

```
PROMPT_D1  →  docs/_suite/gap/GAP1..GAP4.md          (one run, resumable)
                        │
        ┌───────────────┴────────────────┐
        ▼                                ▼
PROMPT_D2 (per document)          PROMPT_D3 (ADR archaeology, 2 stages)
   F03 → F04 → F02 → F06 → F07 → F05 → F08 → F01              → F09
```

**Why this authoring order** (it is not the numeric order):

1. **F03 (ARD) first** — it is the closest to `ARCHITECTURE_CURRENT.md` and establishes the shared
   vocabulary every later document reuses.
2. **F04 (SRS)** — requirements are stated against the architecture that F03 just fixed.
3. **F02 (Compendium)** — the deepest document; write it once the technical substrate is settled.
4. **F06 (Use/Edge cases)** — enumerated against known control flows and failure paths.
5. **F07 (Security)** — builds on boundaries from F03 and failures from F06.
6. **F05 (POC/Evidence)** — evidence is assembled against claims the earlier documents made.
7. **F08 (Roadmap)** — forward view, informed by the seams and debts now fully documented.
8. **F01 (Concept Brief)** — **written last.** It is the summary; you cannot summarise well until the
   detail is settled. This is the same reason a README is finalised last.
9. **F09 (ADRs)** — independent; run `PROMPT_D3` any time after D1.

---

## 7. FORMAT AND HOUSE STYLE

- **Authored as Markdown**, one file per document, under `docs/_suite/`. Rendered to PDF at the end by
  a single assembly script. Same rationale as before: resumable, diffable, one style applied by one
  script rather than drifting by hand.
- **Every technical claim cites** either `ARCHITECTURE_CURRENT.md §n` or `file.py:line`.
- **Dual voice** — technical precision plus a load-bearing metaphor where it aids intuition. The
  metaphor must explain a mechanism; if it can be deleted without loss, delete it.
- **Status labelling is mandatory.** Every capability is marked `IMPLEMENTED`, `PARTIAL`, or
  `PLANNED — Phase X`. No exceptions.
- **Document control block** on every document: ID, version, date, source commit, owner, status,
  and the sections of `ARCHITECTURE_CURRENT.md` it derives from. **The source commit is
  `6345a1e0e3a18d652f3dcfae566fb0606322a30f`** unless the tree has moved again — check `git log -1`
  rather than copying this value forward.
- **A fixed defect is described in the past tense, and only where it explains something.** D18 is the
  worked example: it belongs in F02 (why the admission boundary exists), F05 (what was found and
  closed) and F09 (the decision to support unions rather than reject them), and nowhere else. It must
  never appear in a warning, a checklist, or a "things to watch for" list. **The general rule: this
  suite documents the system as it is, and uses history only to explain why it is that way.**
