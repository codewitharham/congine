# P1.5 Semantic Validation Safety — CLOSED

Engineering closure record. Every figure below was recomputed from repository state
or from the committed evidence artifacts during the closure audit; none was copied
forward from an earlier report.

---

## Status

| | |
|---|---|
| Phase | **P1.5 — Semantic validation safety and preparation hardening** |
| Verdict | **CLOSED** |
| P1 engineering baseline | `b482bc4b2c88273e2a29a0f418a53f7ba3ab0614` |
| P1.5 context baseline | `e59fece5fe58cab0e121824cdfe44ddadaff1057` |
| Engineering HEAD | `84641869035fb64ee63db90f43fa955562e87e71` |
| Production delta during closure | **none** — this pass is documentation only |

### Commit chain

Verified linear over `e59fece..HEAD`: exactly eight commits, no others.

| # | SHA | Slice |
|---|---|---|
| 1 | `eaa7b518203d80a1bf919a2260659a2ca8d0eefe` | A0 — capability falsification |
| 2 | `2e0dd78a7e9c321ac8a2475248c3520cd69b7d22` | A — reproducible evidence harness |
| 3 | `928ae6f85f9ab8beea8d4c47a78b6dee4fe30faf` | A0.1 / A.1 — dialect matrix, corrections |
| 4 | `ad54283e289903e96ad44cbc69a21cc61bd70296` | B — evaluator and admission truth defects |
| 5 | `217c649f29bef1250441853c7f1ff6439f83e95e` | PRE-C — dialect check, deadline-fidelity witness |
| 6 | `2ef5cadf28232d2b0d4a90076a55d1fe99381e51` | C + minimal D — staged budgets, stage-truthful results |
| 7 | `acb677a9616b939d002208b1ed2ef2857f24800a` | E — complexity/admission experiment |
| 8 | `84641869035fb64ee63db90f43fa955562e87e71` | F — safe preparation cache |

---

## What each slice established

### A0 — capability falsification

Measured what the wired evaluator genuinely enforces, rather than what documentation
believed. Admission had been composing its capability set from a **static keyword
list** whenever semantic validation was enabled, ignoring the configured dialect.
Against the five supported validators that over-claimed **11 keywords on draft4, 6 on
draft6, 5 on draft7 and 1 on 2019-09** — each a G12 violation, admission advertising
enforcement it could not deliver.

A separate harness error was found and reported during this slice: a socket-level
probe concluded "no retrieval" while `urlopen` had in fact been called ten times. The
claim was only settled by a live loopback server proving a real fetch. Recorded here
because the corrected method — hermetic retriever spy plus opt-in live server — is
what the retained witnesses use.

### A0.1 / A.1 — hardening the evidence

Completed the dialect falsification across all five drafts, replaced the harness's
tolerated-untruth allowlist with end-to-end policy truth, added the hermetic
retrieval gate, and corrected benchmark terminology (`prep_to_total_ratio_pct`, with
its arithmetic documented, after the earlier name implied a fractional decomposition
it was not).

### B — semantic safety

- **Regex.** Semantic pattern evaluation rebound to RE2 via `_re2_validator_class`,
  preserving `search` semantics, so schema-supplied patterns cannot reach the
  backtracking engine on the semantic path.
- **References.** An explicit no-retrieval `referencing.Registry` refuses every
  external `$ref`; verified local JSON-pointer references remain enforced.
- **Capability.** `SemanticCapability` (L0) is now **derived from the concrete wired
  evaluator at composition time** and passed inward to admission, replacing the
  static list. Includes value-aware `boolean_exclusive_bounds`, because draft 4
  asserts exclusive bounds as booleans modifying `minimum`/`maximum` while draft 6+
  uses standalone numbers — a keyword-level capability cannot express that, and
  treating them alike would refuse genuinely enforceable draft-4 contracts.
- **Admission.** Reference resolution and cycles, nested patterns, formats, and
  exclusive bounds are all checked against real capability.

### PRE-C — correction and deadline evidence

Targeted draft-4 composed-semantics check, and a deadline-fidelity witness with a
cooperative control, establishing that stage budgets are meaningful before they were
built on.

### C + minimal D — runtime budget and result truth

- **Two deadlines, not one.** `_StageBudget` tracks an absolute aggregate deadline
  *and* a per-stage deadline. An aggregate alone cannot enforce a stage cap: with a
  100 ms aggregate and a 20 ms native cap, a runner returning at 30 ms has blown its
  cap while the aggregate still has 70 ms. Millisecond conversion **floors**; a
  sub-millisecond remainder counts as exhausted.
- **Post-stage check.** A normal result is discarded if *either* deadline expired
  while it ran, so a late PASS never becomes an enforced PASS.
- **Result truth.** `DegradedReason.SEMANTIC_TIMEOUT` and `EvaluationStage` make a
  semantic overrun distinguishable from a native one. `LoadShedError` is caught
  **before** `TimeoutError` at every stage, since it subclasses it (P0-06).
- **Double-execution trap closed.** The container had been passing a
  `CompositeValidator`; it now passes the native validator plus the semantic
  validator separately, and the use case refuses composite+semantic at construction.
- Config validated in `__post_init__` — not `validate()`, which early-returns for
  local base URLs and would have skipped the new fields.

### E — complexity / admission experiment

**Conclusion: `NO HARD COMPLEXITY ADMISSION JUSTIFIED`.** Frozen. See §"Frozen
conclusions" below.

### F — safe preparation cache

**Conclusion: `SAFE PREPARATION CACHE ESTABLISHED`.** Frozen. See §"Frozen
conclusions" below.

---

## Frozen conclusions

### Slice E — `NO HARD COMPLEXITY ADMISSION JUSTIFIED`

Reproduced during this audit from the committed artifact: **0 of 85** admitted
contexts exceed the 100 ms local default aggregate-budget sensitivity reference, so
the population is `separable: false` and there is nothing for a cost boundary to
divide.

Static-cost observations must **never** become a complexity admission score, a
`NEAR_LIMIT` state, a schema-cost rejection rule, a public complexity API, a
configuration threshold, or a health threshold.

The conceptual split is permanent:

> **supported / unsupported → deterministic admission truth**
> **slow / fast → runtime budgeting and optimization**

Machine-dependent cost remains **operational evidence, not contract truth**.

Supporting findings retained: schema size predicts *preparation* (`nodes` +0.889) and
rank order is reproducible across cold processes (0.945–0.980), but byte-identical
schemas differ **6.01×** in cost across dialects, one schema's payload classes differ
up to **10×**, the best predictor ranks the costliest contract 19th, and every
candidate threshold requires retuning per held-out family.

### Slice F — `SAFE PREPARATION CACHE ESTABLISHED`

Production cache semantics, frozen:

- **`CHECK_SCHEMA_VALID` only.** A hit skips `validator_class.check_schema(snapshot)`
  **and nothing else**.
- **Every semantic evaluation still constructs a fresh `jsonschema` validator
  instance.** No validator is stored, shared or reused.
- **Identity** = canonical schema content digest (SHA-256) · concrete validator
  **class object** · format-policy isolation · `CHECK_SCHEMA_CACHE_VERSION`. The
  class object rather than its name, because `jsonschema.validators.extend` produces
  an unrelated class with the same `__name__`.
- **Cache**: evaluator-local · bounded to 256 entries · positive-only · metadata-only
  contents · metadata-only lock · no background thread · no executor.
- **Never retained**: validator instances, schemas, results, breach lists,
  registries, contract IDs.
- **No admission move. No `L4→L2/L3` dependency. No config, health, telemetry or
  public API change** *(Slice F specifically; see the P1.5-wide surface delta below,
  which did change in Slice C).*

Measured footprint recomputed during this audit: **69 075 bytes for 256 entries
(269.8 B/entry)**.

---

## Slice-F methodology chronology — preserved, not merged

The two evidence phases are recorded separately and deliberately. They do not carry
equal weight.

### Phase 1 — post-observation interpretation change

Phase 1's initial definition of "repeatable" required **positive warm saving in all
five fresh processes**. Two evaluation-dominated contexts — `array-items-100` and
`dialect-refs-draft4` — each had **one** negative run out of five. **Only after
observing that** was the interpretation changed to the median aggregation already used
throughout the evidence suite.

**That revised Phase-1 interpretation is therefore post-observation, and is not
represented as predeclared confirmatory evidence.**

Both readings remain in the artifact. Under the median reading, zero contexts regress;
recomputed during this audit: warm saving **min 20.9% / median 91.0% / max 98.1%**,
95/95 contexts benefiting, 0 cache-state failures, 0 equivalence failures. The
supporting observation — that `array-items-100`'s −0.74 ms excursion is roughly 60×
its entire 0.012 ms identity overhead, so the cache cannot be its cause — is retained
as an argument, not as a substitute for the disclosure.

### Phase 2 — confirmatory production evidence

Collected **after** that interpretation was fixed, through the actual
`JsonSchemaSemanticValidator.validate()` path, over the globally deduplicated
population. Reproduced during this audit:

| | |
|---|---|
| Contexts | **95** |
| Fresh processes | 5 |
| Expected/observed cache-state mismatches | **0** |
| Production warm-vs-cold | **min 22.0% · median 91.3% · max 98.2%** |
| cold == warm == post-eviction breaches | **True** |
| Contexts where a real LRU eviction was not observed | 0 |

**Phase 2 is the confirmatory production evidence supporting the shipped
optimization.**

---

## The P1.5 guarantee

### P1.5 does **not** claim

- deterministic wall-clock completion;
- hard cancellation of running Python worker execution;
- portable 100 ms semantic performance;
- cross-platform performance equivalence.

### P1.5 **does** establish

- unsupported or uninterpretable semantic contracts are not activated as enforced
  policy;
- **the admitted semantic capabilities/keywords in CONGINE's supported subset have
  measured enforcement witnesses across the supported dialects** — this is the
  epistemic claim A0/A0.1/B established, and it is not a claim that every possible
  schema composition was exhaustively proven;
- unsafe stdlib-regex semantic patterns cannot enter the supported semantic path;
- external reference retrieval is prevented for the supported path;
- format / content / reference capability truth is admission-aware;
- governed semantic validation has aggregate and stage **logical deadline** truth;
- a result completing after its applicable logical deadline cannot be returned as an
  enforced normal result;
- load shedding remains distinct from semantic timeout;
- repeated successful `check_schema` preparation may be reused through immutable
  exact-content/context proof;
- each payload evaluation still uses a fresh validator instance.

### Late-worker limitation — documented, not resolved

Work may continue after the governed caller has timed out. Slice F adds exactly one
permitted internal side effect: after `check_schema` genuinely succeeds, a late worker
may insert `CHECK_SCHEMA_VALID`. This is safe only because that marker carries
**preparation truth for a schema and context and no payload or final-result truth**.

**Final-result ownership remains with the governed caller path (L3).** No late PASS,
result, or telemetry publication is permitted; a late worker cannot mutate a returned
`ValidationResult`, persist a verdict, mutate caller-owned input, or share its live
validator.

---

## Invariant reconciliation — G1–G16

Classification preserved: **G1–G11** mechanical/runtime · **G12–G14**
epistemic/trust · **G15–G16** structural/lifecycle. **Net: sixteen invariants, all
holding.** No new invariant number was created; nothing in P1.5 warranted one.

**No P1.5 change weakened any earlier invariant.** Refinements:

| Invariant | P1.5 effect |
|---|---|
| **G5** — no ReDoS | **Strengthened.** Semantic regex evaluation rebound to RE2, so schema-supplied patterns cannot reach the backtracking engine on the semantic path. |
| **G12** — policy activation truth | **Strengthened.** Admission is capability-aware: `SemanticCapability` derived from the concrete wired evaluator replaces the static keyword list, closing the draft4/6/7/2019-09 over-claims. **The D-ADM `schema_storage.put()` bypass remains unresolved and deferred** — still the one path by which an unenforceable contract can become active. |
| **G13** — configuration truth | **Preserved.** The two new stage-budget fields validate in `__post_init__`, so direct construction and `from_env()` converge on the same canonical state. |
| **G14** — enforcement truth | **Strengthened.** `DegradedReason.SEMANTIC_TIMEOUT` and `EvaluationStage` make a semantic overrun distinguishable from a native one; a post-deadline result cannot be returned as enforced. |
| **G15** — layer matrix | **Preserved.** Allowlist **0**, TYPE_CHECKING exemptions **0**, now 42 source files. |
| **G16** — composition / lifecycle | **Preserved.** The preparation cache belongs to the evaluator, has no background thread, no executor, and requires no `close()` change; it is collected with its evaluator. |

---

## Surface and dependency delta across P1.5

Measured `e59fece..8464186`.

| | |
|---|---|
| Production source files changed | **15** |
| Lines | **+1679 / −53** |

**Public API** — `EvaluationStage` added to `congine_core.__all__` (Slice C). This is
the only public-surface addition in P1.5; Slice F added none.

**Configuration** — two fields: `native_validation_timeout_ms`,
`semantic_validation_timeout_ms` (both default `None`), with env readers
`CONGINE_NATIVE_TIMEOUT_MS` and `CONGINE_SEMANTIC_TIMEOUT_MS`. README config table
updated (+3/−1) as the 4-touch rule requires.

**Health** — four additive static keys: `validation_aggregate_budget_ms`,
`validation_native_stage_cap_ms`, `validation_semantic_stage_cap_ms`,
`semantic_validation_enabled`.

**Dependencies** — one addition: `referencing>=0.28.4`, promoted from transitive to
declared because `Registry(retrieve=...)` — the supported API for refusing external
reference resolution — is not re-exported by `jsonschema`. `uv.lock` +2 lines. No
other dependency added or removed.

**Architecture** — no allowlist entry, no TYPE_CHECKING exemption, no new layer edge.
The preparation cache is L4→L4.

---

## Verification from HEAD `8464186`

| Gate | Result |
|---|---|
| lint | **pass** — 117 files formatted, all checks passed |
| strict mypy | **pass** — no issues in **42** source files |
| architecture | **pass** — 42 source files scanned; **90** architecture tests; allowlist **0**; TYPE_CHECKING exemptions **0** |
| examples | **pass** |
| full tests | **823 passed, 1 skipped** |
| semantic-safety | **green** — admission refuses everything the evaluator cannot enforce, and admits everything it can |
| capability drift | **NONE** (model matches all 5 drafts) |
| P0 evidence | **5/5 properties hold** |
| P0 determinism hash | `715725383efa751299422a3dbe990c34c4c47d657e73ca90a03088ddf7f36dfa` — **unchanged** |
| `git diff --check` | clean |

### Test-count progression

Only points that were actually recorded are listed; the four earliest P1.5 commits
were not measured at the time and are not reconstructed here.

| Milestone | Total |
|---|---|
| P0 baseline | 478 passed, 1 skipped |
| P1 closed | 540 passed, 1 skipped |
| Slice C + D | 702 passed, 1 skipped |
| Slice E | 755 passed, 1 skipped |
| Slice F / final | **823 passed, 1 skipped** |

### Evidence-integrity audit

No exploratory re-timing was performed. Committed artifacts were verified only.

| Check | Result |
|---|---|
| Slice-E corpus hash reproduces committed value | **match** (`c80030f7da8c4e8c…`) |
| Slice-A/B historical fixture digests unchanged | **11/11 match** in `pre_change_benchmark.json`; `post_slice_b_capability.json` carries no `fixture_manifest` section, so nothing to compare there |
| Slice-E `reanalyse()` reproduces committed conclusion | **yes** — 0/85 contexts above the 100 ms reference, `separable: false` |
| Slice-F artifacts parse | **yes** — `phase1_candidate_model`, `phase2_production_path` |
| Slice-F Phase-1 `reanalyse()` from stored raw observations | **yes** — gate PASS, 95/95 benefiting, 0 state failures, 0 equivalence failures |
| Slice-F Phase-2 confirmatory numbers | **yes** — 95 contexts, 5 runs, 0 mismatches, 22.0 / 91.3 / 98.2 % |
| Union population resolves | **95** unique contexts, 1 shared A∪E, 2 aliases deduplicated |
| Slice-A current-admission truth | **11/11 admitted**, 0 refused historical references |

---

## Deferred — explicitly **not** solved by P1.5

### P2 — verification / release gates (NOT STARTED)

Real supported-Python and cross-platform performance evidence · Linux release CI
matrix · golden determinism corpus · branch coverage target · reproducible
performance-regression evidence · `pip-audit` / supply-chain review · SBOM · security
lint · release / package smoke evidence.

Every timing figure produced by P1.5 is observational, single-platform, and explicitly
**not** a release SLA. P2 owns performance gates.

### P3 — formal documentation and ADR reconciliation (NOT STARTED)

D1 · D2 · D3 · F01–F09 · ADR stabilization. W1/W2 remain downstream of P3.

### Open architectural and product debt

- **D-ADM** — raw `ISchemaStorage.put()` bypasses contract admission outside the
  designated writer. Unresolved. Still the one path by which an unenforceable or
  malformed contract can become active.
- **Version-aware storage identity** — deferred. The Slice-F content digest is
  internal cache identity only and is deliberately not exposed as storage or version
  identity.
- **Richer result semantics** — the evaluation / conformance / coverage / action
  three-axis result model remains deferred.
- **Partial breaches on a degraded path** — when a native breach is followed by a
  semantic timeout, the degraded result is returned and the partial native breaches
  are dropped. The current model cannot express "known breach, partially enforced".

None of the above is marked solved by P1.5.

---

## P1.5 CLOSED
