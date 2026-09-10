# P1.5 Slice E — Contract Complexity / Admission Experiment

**Status: CLOSED — no hard complexity admission boundary justified.**
**Production behaviour change: none.**

---

## 1. The question

> Can CONGINE derive a deterministic **static** property of an admitted contract
> that predicts semantic evaluation risk strongly enough to justify a production
> admission decision?

Slice E is an experiment, not a feature. It is also **not** needed to make timeout
behaviour safe — Slice C already did that. An expensive admitted semantic contract
now returns `degraded_reason=semantic_timeout`, `evaluation_stage=semantic`,
`is_enforced() == False`, which is a truthful governed result. A static admission
rule would therefore have to justify itself on its own terms: refusing a contract
that CONGINE *can* enforce, before it ever runs, purely because of structural cost
risk.

It does not. The answer is **no**, and this document records why.

### What Slice E is not asking

Slice B refuses contracts for **capability truth** — an unsupported dialect
clause, an annotation-only keyword, an unsupported format, an external `$ref`, a
pattern RE2 cannot compile. Those refusals stand and are untouched. Slice E asks
the different question of whether a **valid, supported, enforceable** contract
should be refused for cost. Five refusal controls are carried in the corpus purely
to keep the two axes visibly separate, and they are excluded from every predictor
statistic.

---

## 2. Method

| | |
|---|---|
| Corpus | `tools/p1_5_evidence/complexity_corpus.py`, version **1**, hash **`c80030f7da8c4e8c…`** |
| Features | `tools/p1_5_evidence/features.py`, schema version **1**, 22 features |
| Measurement | `tools/p1_5_evidence/complexity.py`, methodology version **1** |
| Statistics | `tools/p1_5_evidence/analysis.py`, standard library only |
| Raw artifact | `tools/p1_5_evidence/baseline/slice_e_complexity.json` (520 KB) |
| Corpus cases | 91 — **86 predictors**, 5 refusal controls |
| Measurement contexts | **85** (one alias collapsed; see §2.3) |
| Payload cases | **207** |
| Fresh processes | **5** official workers, each a cold interpreter |
| Timed operations | ~52 000 per worker |
| Platform | Python 3.14.6 · Windows-11-10.0.26200 · jsonschema 4.26.0 |

### 2.1 Corpus design

Parameterised families, each a pure function of its parameters — deterministic,
reproducible, content-hashed, order-stable. No random schemas.

| Family | Independent variable |
|---|---|
| `width` | properties ∈ {1, 5, 10, 25, 50, 100, 200} |
| `depth` | nesting depth ∈ {1…6} at fixed width |
| `anyof` / `oneof` / `allof` | branch breadth ∈ {2, 5, 10, 25} |
| `combo-depth` | combinators nested inside combinators, depth ∈ {1, 2, 3} |
| `enum` | cardinality ∈ {10, 50, 200, 1000}, plus 10×50 and 25×200 |
| `array` | `items` (10/100 elements), `contains` + `minContains`/`maxContains`, `prefixItems` |
| `regex` | RE2-safe pattern count ∈ {1, 5, 25, 100} × pattern length ∈ {10, 42, 202} chars |
| `refs` / `ref-depth` | 1–100 local refs, repeated vs distinct targets, chain depth 1–5 |
| `format` | every format name the wired checker can genuinely assert, format checking **on** |
| `dialect` | 3 representative shapes × all 5 supported drafts |
| `pair-*` | three deliberately matched falsification pairs (§5.3) |

Pattern length is grown by repeating a character class, never by nesting
quantifiers: Slice B closed catastrophic backtracking by making RE2 the semantic
engine, and re-introducing it here would measure a defect that no longer exists.

**Format coverage is partial and recorded.** `email`, `ipv4`, `ipv6` and `uuid`
were generated; `date-time` and `uri` were **skipped** because no checker for them
is installed in this environment. That is not a silently dropped predictor
fixture — it is a capability this evaluator does not have, so no admissible
fixture exists to generate. The skip and its reason are in the artifact under
`format_family_skipped`.

### 2.2 The corpus is admission-gated

Slice E measures the cost of **supported, admitted** contracts, not of arbitrary
JSON Schema documents. Before any timing is taken, every fixture is run through
CONGINE's real admission path — `admit_contract` with the capability derived from
the actual configured evaluator, and the keyword set composed exactly as
`SyncContractsUseCase` composes it — under its own draft and format policy.

- Every predictor fixture **must be admitted**. A refused predictor is a corpus
  failure that stops the experiment; it is never quietly dropped, because
  dropping it would bias the corpus toward whatever admission happens to like.
- Every refusal control **must be refused**.
- Every predictor schema must be **below the schema-size preflight**, so no
  measured cost belongs to a contract the ordinary safety preflight would reject.

Result: **86/86 predictors admitted, 5/5 controls refused, 0 oversize.** Per-fixture
admission witnesses — digest, draft, format policy, capability identity, decision —
are stored in the artifact.

A practical consequence shaped the corpus: dialect-sensitive constructs are
generated **per-draft**. Exclusive bounds are spelled as draft-4 boolean modifiers
on draft 4 and as standalone numbers from draft 6 onward, because one spelling
everywhere would produce a contract that is *legitimately* refused on the other
dialects — a corpus bug wearing the costume of evidence.

### 2.3 Measurement context, not schema digest

Preparation is payload-independent but **not** context-independent: the same bytes
under draft 7 and under 2020-12 build different validator classes and run a
different `check_schema`. The unit of observation is therefore

```
measurement_context_id = H(schema_digest · draft · format_policy · capability_identity)
```

with exactly **one** preparation record per context per worker. Two entries that
collapse to the same identity are aliases of one experiment and contribute one
observation; two entries sharing bytes across dialects are genuinely different
experiments and contribute two. One alias was found and recorded
(`refs-repeat-10` ≡ `dialect-refs-draft202012`), which is why 86 predictors
produce 85 contexts.

### 2.4 What was measured

| Quantity | Definition |
|---|---|
| `preparation` | `check_schema` + validator construction — once per context |
| `evaluation` | `iter_errors` on an already-prepared validator — per payload class |
| `semantic_evaluator_total` | preparation + evaluation + semantic-validator-local orchestration |

**`semantic_evaluator_total` is deliberately not a "governed semantic-stage
total".** It does not run through the L3 scheduling and deadline path. It
**excludes** contract resolution, the payload/schema size preflight, native
validation, executor queue residence, and L3 aggregate-deadline orchestration, and
it is **not equatable with the `validation_timeout_ms` budget**.

### 2.5 Quantile policy, fixed before measurement

Nearest-rank, no interpolation, under a floor fixed in advance so a quantile can
never be quietly upgraded because it flattered a hypothesis:

| Statistic | Required `n` |
|---|---|
| p50, max | ≥ 1 |
| p95 | ≥ 20 |
| p99 | ≥ 100 |

Below the floor the value is `null` with a `not_reported_reason`. Iteration counts
come from structural size alone and were never adjusted after seeing results:

| Tier | Canonical bytes | Iterations | Warmup | Contexts |
|---|---|---|---|---|
| small | < 2 000 | 120 | 5 | 71 |
| medium | < 20 000 | 40 | 5 | 12 |
| large | ≥ 20 000 | 12 | 3 | 2 |

Slice A/B's `benchmark.Timing` cannot express an omitted quantile, so it was left
untouched as frozen prior evidence and Slice E uses its own `ComplexityTiming`.

### 2.6 Pilot and rotation

One pilot process ran first, solely to estimate runtime and catch fixture-generation
or methodology bugs. It estimated ~2 min/worker; no tier changed, so the methodology
version did not move. **Pilot timings enter nothing** — the record refuses to
analyse a run not marked `evidence: true`.

The five official workers each execute the corpus in a **different deterministic
rotation** (worker *k* rotates by *k*/5), recorded per run. Five workers sharing one
sequence would let a cross-case warming effect masquerade as a property of the
schemas.

---

## 3. What predicted preparation

Spearman rank correlation, measurement-context weighted, median across five fresh
processes. Pearson was computed and is in the artifact, but is secondary and
insufficient: it is dominated by absolute magnitudes, and absolute magnitudes here
are a property of this workstation.

| Feature | prep | total (worst payload) | eval (worst payload) |
|---|---:|---:|---:|
| `nodes` | **+0.889** | +0.854 | +0.851 |
| `bytes` | +0.769 | **+0.865** | +0.831 |
| `properties` | +0.727 | +0.727 | +0.847 |
| `semantic_keywords` | +0.537 | +0.492 | +0.529 |
| `regexes` | +0.501 | +0.480 | +0.712 |
| `regex_chars` | +0.463 | +0.443 | +0.683 |
| `max_regex_chars` | +0.254 | +0.246 | +0.575 |
| `max_depth` | +0.148 | +0.191 | −0.115 |
| `combinator_product` | +0.116 | +0.036 | −0.255 |
| `max_combinator_breadth` | +0.102 | +0.020 | −0.263 |
| `combinators` | +0.101 | +0.018 | −0.279 |
| `enum_max_cardinality` | −0.093 | +0.114 | −0.109 |
| `refs` | +0.050 | +0.078 | +0.307 |
| `ref_graph_depth` | +0.018 | +0.033 | +0.245 |
| `prefix_items` | −0.004 | −0.022 | −0.062 |

**Size predicts preparation, and nothing else does.** `nodes`, `bytes` and
`properties` are the only features with a strong relationship; every structural
feature that was *supposed* to be interesting — combinator breadth, combinator
product, nesting depth, reference count, reference-graph depth, enum cardinality —
is near zero, and several are **negatively** correlated with evaluation cost. A
schema is expensive to prepare roughly in proportion to how much of it there is,
which is close to saying preparation is dominated by walking the document.

Within-family monotonicity is correspondingly clean — 30 of 31 adjacent steps are
strictly increasing, the single exception being `enum` preparation, whose cost
barely moves with cardinality at all:

| Family | prep | total |
|---|---|---|
| `width`, `depth`, `anyof`, `oneof`, `allof`, `combo-depth`, `ref-depth` | strict | strict |
| `enum` | 2/3, non-strict | strict |

So the honest positive finding is: **preparation is well explained by schema size,
and that ordering is reproducible.** The rest of this document is about why that is
not enough to refuse a contract.

---

## 4. Cross-process rank stability

Each of the five cold interpreters used its own rotation, so run identity and case
ordering are deliberately confounded — agreement means neither a cold start nor an
ordering effect changed the ranking.

| Ranking | min pairwise Spearman | median |
|---|---:|---:|
| preparation | 0.959 | 0.976 |
| `semantic_evaluator_total`, worst payload | 0.945 | 0.980 |

**No evidence instability.** Rank order survives a fresh process and a different
execution order. This is reported as a genuine positive: the measurements are
reproducible, and the negative conclusion below is therefore not an artefact of
noisy data.

Absolute preparation times are a different story: the same context's preparation
p50 varies by a **median factor of 2.19** between cold processes on this one
machine. Ranks are stable; milliseconds are not. That gap is the heart of §7.

---

## 5. Why no boundary is justified

### 5.1 Nothing in the admitted corpus is expensive

`semantic_evaluator_total` across all 85 contexts ranges **0.144 ms – 89.70 ms**.

Against the default `validation_timeout_ms = 100` — a **local default
aggregate-budget sensitivity reference**, never a normative semantic-stage
boundary — **0 of 85 contexts** are above the line.

A cost-admission rule needs two populations to separate. There is only one. Every
non-trivial threshold against the real default is therefore **pure false
positive**: it refuses contracts that fit. The analysis records this as
`separable: false, reason: no_contexts_above_reference` rather than reporting a
"best rule", because a best rule computed on a degenerate split would be an
artefact of the threshold sweep, not a finding.

To have anything at all to analyse, the remaining sections use a **hypothetical
sensitivity scenario at 25 ms** (11/85 contexts above). No run configured it, it is
not a proposed default, and it exists only to let a structural rule be shown to
disagree with reality.

### 5.2 The best predictor misranks the most expensive contract

`nodes` is the strongest feature at +0.889. It is also decisively wrong about the
single most expensive contract in the corpus:

| Contract | `nodes` | rank by `nodes` | measured cost | rank by cost |
|---|---:|---:|---:|---:|
| `enum-25x200` | 27 | 19th | **89.70 ms** | **1st** |
| `width-200` | 202 | 1st | 72.60 ms | 2nd |
| `enum-1000` | 3 | 75th | 13.99 ms | 15th |

Twenty-five properties each carrying a 200-member enum is 27 nodes and the most
expensive thing measured. Best in-sample rules against the 25 ms scenario all miss
it:

- `nodes > 51` → FP 0, **FN 1** — misses `enum-25x200`
- `properties > 35.5` → **FP 1** (`refs-repeat-40`, 14.58 ms), **FN 1** (`enum-25x200`)
- `regexes > 28.5` → FP 0, **FN 2** (`enum-25x200`; `refs-repeat-100`, 33.59 ms)

Substantial examples exist on both sides.

### 5.3 Matched pairs break the predictors by construction

Each pair holds a candidate feature roughly constant and changes the structure
underneath it.

| Pair | prep | total | ratio |
|---|---:|---:|---:|
| `pair-properties-flat-12` (12 props, depth 1) | 6.23 ms | 4.78 ms | — |
| `pair-properties-nested-12` (12 props, depth 4) | 10.13 ms | **18.65 ms** | **3.9×** |
| `pair-structure-flat` (16 props, direct constraints) | 10.16 ms | 6.45 ms | — |
| `pair-structure-combinator` (same constraints via `allOf`) | 14.07 ms | **15.50 ms** | **2.4×** |
| `pair-refgraph-wide` (20 refs → 1 target) | 5.76 ms | 6.56 ms | — |
| `pair-refgraph-deep` (20 refs → 5-deep chain) | 6.74 ms | 8.51 ms | 1.3× |

Equal property counts differ 3.9× in cost. Semantically equivalent constraints
differ 2.4× depending only on whether they are spelled through `allOf`.

### 5.4 Identical feature vectors, different cost

The most direct falsification available: if the entire 22-feature vector cannot
tell two contracts apart while measurement can, no rule over those features can
separate them either. **Eight such groups exist.** The worst are dialect groups —
byte-identical schemas whose cost depends on which draft is configured, something
no static property of the document can see:

| Group | spread | detail |
|---|---:|---|
| `refs-repeat-10` ≡ `dialect-refs-*` | **6.01×** | draft6 1.01 ms · draft7 1.02 ms · draft4 1.59 ms · 2020-12 3.59 ms · **2019-09 6.08 ms** |
| `dialect-bounds-*` | 4.62× | draft7 0.14 ms · draft6 0.15 ms · 2019-09 0.63 ms · 2020-12 0.67 ms |
| `dialect-core-*` | 2.60× | draft7 1.78 ms · draft6 1.75 ms · draft4 3.11 ms · 2020-12 4.53 ms · 2019-09 4.54 ms |
| `anyof-N` ≡ `oneof-N` | 1.02–1.10× | same shape, different keyword |

A boundary defined on schema structure would classify all five dialect variants
identically while their real cost differs sixfold.

### 5.5 Payload dependence

Same schema, different payload, cost varies **1.0× – 10.0×** (median 1.08×). The
tail is where it matters, and it is systematic rather than incidental: for every
`enum` family member the **worst payload class is `invalid`**, because a conforming
value short-circuits and a non-member is only rejected after the whole enum has
been scanned.

| Context | spread | early-valid | late-valid | invalid |
|---|---:|---:|---:|---:|
| `enum-1000` | **10.0×** | 1.42 ms | 1.40 ms | **13.99 ms** |
| `enum-25x200` | 8.47× | 10.59 ms | 15.08 ms | **89.70 ms** |
| `enum-200` | 4.56× | 0.78 ms | 1.18 ms | 3.53 ms |
| `array-items-100` | 1.84× | 4.29 ms (early-invalid) | — | 7.86 ms (late-invalid) |

The most expensive observation in the whole experiment is a schema-plus-payload
combination, and admission never sees the payload. A static rule tuned on the
median payload under-predicts the tail by an order of magnitude; tuned on the tail,
it refuses contracts that are cheap for every input they will actually receive.

### 5.6 Out-of-sample: thresholds do not survive a new family

Choosing a threshold on the whole corpus and scoring it on the whole corpus proves
nothing. The real question is whether a rule derived **without ever seeing** a
structural family still classifies that family correctly. Leave-one-family-out,
**no retuning** on the held-out family:

| Feature | held-out FP | held-out FN | distinct thresholds across folds | stable? |
|---|---:|---:|---:|---|
| `nodes` | 0 | 2 | 3 | **NO** |
| `properties` | 0 | 2 | 3 | **NO** |
| `regexes` | 0 | 3 | 2 | **NO** |

Every candidate needed a **different threshold** depending on which family it was
derived from. By the standard set for this slice, a threshold that requires
retuning when a new structural family appears is not a stable production boundary —
and JSON Schema will keep supplying new structural families.

### 5.7 The classification itself is machine-speed dependent

Synthetic scaling is a **falsification probe only**. It may show a locally derived
threshold is fragile; it can never establish cross-machine invariance,
cross-platform performance or release portability. P2 owns that evidence.

Scaling every measurement by plausible machine-speed factors moves not just the
thresholds but the *population being classified*:

| Reference | unscaled | ×0.5 | ×1.5 |
|---|---:|---:|---:|
| 100 ms (local default aggregate-budget reference) | 0 | 0 | **2** |
| 25 ms (hypothetical sensitivity scenario) | 11 | 2 | 12 |

A machine one-third slower turns a corpus with **nothing** above the default
reference into one with two contracts above it. And the thresholds themselves move:
`nodes > 51` moves under ×0.5, `properties > 35.5` moves under **both** scales,
`regexes > 28.5` moves under ×0.5.

This probe **disqualifies** these candidates. No candidate is qualified by it.

---

## 6. Conclusion

**NO RELIABLE DETERMINISTIC STATIC COST-ADMISSION BOUNDARY FOUND.**

| Requirement for a production boundary | Outcome |
|---|---|
| Corresponds to an unsupported construct or reliably explosive regime | **No** — the whole admitted corpus fits inside the default reference |
| Payload sensitivity | **Fails** — up to 10× on one schema; the worst case is schema+payload, which admission never sees |
| Fresh-process rank stability | **Passes** (0.945–0.980) — the one criterion met |
| Structural counterexamples | **Fails** — 8 identical-feature groups up to 6.01×; matched pairs 2.4× and 3.9× |
| Family holdout | **Fails** — every candidate needs a different threshold per held-out family |
| False positive / false negative | **Fails** — substantial examples on both sides; best predictor ranks the costliest contract 19th |
| Machine-speed sensitivity | **Fails** — thresholds and the classified population both move under ×0.5/×1.5 |

Summarised: **which predictors explained preparation** — `nodes` (+0.889), `bytes`
(+0.769), `properties` (+0.727), i.e. document size. **Which failed** — every
structural feature intended to capture semantic difficulty: combinator breadth,
combinator product, combinator depth, nesting depth, reference count, reference
reuse, reference-graph depth, enum cardinality, `prefixItems`, array constraints;
several correlate *negatively* with evaluation cost. **Where payload dependence
broke predictiveness** — the `enum` families, where `invalid` payloads cost up to
10× a conforming one and produce the corpus maximum. **Where structurally identical
schemas cost differently** — the dialect groups, 6.01× on byte-identical documents.
**Whether combinations helped** — not pursued: a scalar score over features that
individually misrank the most expensive contract, and whose thresholds do not
survive a held-out family, cannot be rescued by weighting them together, and
building one would have been the threshold theater this slice prohibits. **Why local
timing cannot define a portable threshold** — §5.7: on this single machine, a 1.5×
speed change moves the expensive population from 0 to 2 contracts and moves every
candidate threshold.

Slice C already handles the case this boundary was meant to pre-empt: an expensive
contract that overruns produces a truthful non-enforced `semantic_timeout` naming
the semantic stage. Refusing such contracts in advance, on evidence this weak,
would reject valid enforceable policy for no gain in safety.

### Production changes made

**None.** No L0 complexity type, no L2 classifier, no `SyncContractsUseCase`
admission change, no threshold, no `NEAR_LIMIT` state, no config field, no health
key, no public API. `validation_timeout_ms`, `native_validation_timeout_ms`,
`semantic_validation_timeout_ms`, the aggregate and stage absolute deadlines, the
post-stage checks, `SEMANTIC_TIMEOUT`, `EvaluationStage` and the load-shed
distinction are all untouched.

The feature extractor and corpus remain in `tools/p1_5_evidence/` as evidence
tooling. Nothing in `src/congine_core` imports them, and a negative result means
nothing here moves inward.

---

## 7. Observations for Slice F

Recorded only. **Nothing was implemented, no cache was built, no validator instance
is shared, and semantic evaluator construction is unchanged.**

1. **Is preparation mainly a deterministic function of the schema?**
   Its *ordering* is: rank stability 0.959–0.976 across cold processes, and size
   features explain it at +0.889. Its *absolute cost* is not portable — the same
   context's preparation varies by a median factor of 2.19 between processes on one
   machine.
2. **Does repeated validation of the same schema repay preparation every call?**
   Yes. `JsonSchemaSemanticValidator.validate()` calls `check_schema` and constructs
   a validator on **every** call, so an unchanged schema pays full preparation per
   validation.
3. **Is preparation dominant enough for caching to remain worth investigating?**
   Yes, and strongly. Preparation is a median **90%** of `semantic_evaluator_total`
   (range 21–158%; preparation and total are sampled independently, so the ratio can
   exceed 100% under normal variance — it supports "preparation dominates", never a
   literal share of a whole). Reusing an already-prepared validator is a median
   **21×** faster than the current path, up to **4035×** on the largest fixtures.

This is the useful outcome of Slice E: the cost is real and it is concentrated in
work that is repeated unnecessarily, which is an argument for **caching**, not for
**refusal**. Whether that cache is safe to build is Slice F's question, not this
one.

---

## 8. Reproducing this

```bash
uv run --package congine-sdk python -m tools.p1_5_evidence complexity --scale   # size, no measurement
uv run --package congine-sdk python -m tools.p1_5_evidence complexity --pilot   # runtime estimate, not evidence
uv run --package congine-sdk python -m tools.p1_5_evidence complexity --json    # 5 fresh workers (~23 min)
```

`baseline/slice_e_complexity.json` retains the methodology version, corpus version
and hash, per-fixture admission witnesses, feature definitions, platform metadata,
the iteration schedule and quantile floors, and — for each of the five runs — its
identity, rotation offset, case order, per-measurement-context preparation
statistics, and per schema+payload evaluation and `semantic_evaluator_total`
statistics. Derived analysis is stored separately in the same record, so every
conclusion above can be recomputed from the raw observations via
`complexity.reanalyse()` without trusting this document.

Statistics that could not be computed are recorded as `null` with a reason
(`constant_feature`, `constant_cost`, `insufficient_observations`,
`no_contexts_above_reference`) — never as a misleading `0.0`, and never as an
uncontrolled `NaN`. Insufficient evidence is a valid result.

**Observational only. Not a release SLA; P2 owns performance gates.**
