# P1.5 Slice F — Safe Semantic Preparation Cache

**Status: IMPLEMENTED.** Both gates passed.
**Public API, config, health and telemetry: unchanged.**

---

## 1. The question

> Can CONGINE safely eliminate repeated semantic schema-preparation work **without**
> changing semantic decisions and **without** sharing mutable `jsonschema` validator
> instances?

Yes. `check_schema` is deterministic for fixed schema content under a fixed validator
class, and it was being repaid on every validation of an unchanged contract.

Slice E's "21× median / 4035× max" came from reusing a live prepared validator. That
was **evidence, not a design**: it proved repeated preparation is expensive, not that
sharing validator objects is safe. Path **B** was measured as a reference bound and
**never implemented**. The shipping decision was **C versus A**.

### Why the safe design is not a compromise

The pre-planning probe found the constraint everyone would expect to be expensive is
essentially free:

| Fixture | `check_schema` | fresh validator construction |
|---|---:|---:|
| `width-200` | **104.68 ms** | 0.021 ms |
| `depth-6` | **79.70 ms** | 0.014 ms |
| `refs-repeat-100` | **51.83 ms** | 0.011 ms |
| `width-10` | **8.15 ms** | 0.020 ms |

Constructing a fresh validator every time — the requirement that rules out sharing —
costs 0.01–0.02 ms. Practically all of preparation is `check_schema`, which is
exactly what the safe cache removes. The safe design gives up almost nothing.

---

## 2. What ships

```
snapshot, digest = prepare_identity(schema)     # one walk: owned copy + JSON audit

_check_schema_patterns(snapshot)                # SAME position as before, every call
    -> early return on breach, unchanged

if digest is None or not cache.is_prepared(key):
    validator_class.check_schema(snapshot)      # skipped ONLY on a confirmed marker
    cache.mark_prepared(key)                    # only after genuine success

validator = validator_class(snapshot, format_checker=..., registry=...)   # ALWAYS fresh
iter_errors(payload)                            # unchanged
```

**The cache changes exactly one operation.** On a confirmed `CHECK_SCHEMA_VALID`
marker, `check_schema` is skipped. Nothing else moves: the RE2 pattern guard keeps
its position ahead of `check_schema` and runs on every call, the no-retrieval
registry stays part of fresh validator construction, format behaviour stays in
construction and evaluation, `iter_errors` stays evaluation.

> **COLD** = previous evaluator semantics + owned-snapshot/identity work + marker insertion
> **WARM** = the cold ordering, minus **only** `check_schema`

**Contract admission does not move.** It stays at its activation/sync boundary in
L2/L3. Nothing is duplicated into L4, and no `L4→L2/L3` dependency was introduced.
The invariant: *cache state may skip `check_schema` only; it never replaces admission
and never replaces evaluator policy.*

### Identity

| Dimension | Role |
|---|---|
| canonical schema content digest (SHA-256) | **required** — the schema is what `check_schema` judges |
| the concrete validator **class object** | **required** — `check_schema` validates against that class's `META_SCHEMA` |
| format-checking policy | **defensive** — cannot affect `check_schema`; included so differently configured evaluators never share markers |
| `CHECK_SCHEMA_CACHE_VERSION` | **required** — bumped if the marker's meaning ever changes |

The class **object** is used rather than its name: `jsonschema.validators.extend`
produces an unrelated class that keeps the same `__name__`, so a name-keyed cache
could let a marker earned against the stock metaschema authorise the RE2-extended
class, or the reverse. Never keyed by `contract_id`, version string, `id()` or
`hash()`. The digest is internal cache identity only and is never exposed as storage
or version identity.

### Ownership, contents, bound

Owned by the `JsonSchemaSemanticValidator` instance — no process global, no
cross-container singleton, no background thread, no executor, no change to
`ServiceContainer.close()`. It is collected with its evaluator.

Contents: an immutable `CHECK_SCHEMA_VALID` marker and its key. No validator
instances, iterators, results, breach lists, schema bodies, canonical blobs,
registries or contract ids.

**Bound: 256 entries, internal constant, no config field.** Eviction costs a repeated
`check_schema` and never a different verdict, so an operator knob would add permanent
public surface (dataclass, `from_env`, container wiring, README table) for something
with no safety consequence.

**Measured footprint: 69 075 bytes for 256 entries (≈270 B/entry).** Measured with
`sys.getsizeof` over a filled cache rather than derived from key lengths — object and
container overhead dominates at this size. The first attempt at this figure charged
every entry the full size of the shared validator class and came out **5× too high**
at 1337 B/entry; the reported number counts the container, each key tuple and the
digest string it owns, with the class and the marker counted once as the shared
objects they are. Exact bytes remain interpreter- and platform-dependent, which is a
reason to report the figure honestly, not a reason to add configuration.

**Positive cache only.** A malformed schema is never negative-cached, keeping
exception identity and stale error text out of the cache entirely.

**The lock is metadata-only.** It guards lookup, recency, insertion, eviction and the
counters — never `check_schema`, snapshotting, canonicalisation, construction or
evaluation. Held across a cold 100 ms `check_schema`, it would make one expensive
schema block every unrelated validation in the process, converting a latency
optimization into a throughput regression. The accepted consequence is that two
threads racing on the same cold schema may both run `check_schema`; that wastes work
once and costs nothing in correctness. No single-flight machinery was added.

### The audit, and what is deliberately not cacheable

Cache-safe content is exactly plain JSON: `None`, `bool`, `int`, a **finite** `float`,
`str`, inside built-in `dict` (string keys) and `list`. Refused: `NaN`/`±Inf`,
non-string keys, custom `Mapping`/`list` subclasses, and container cycles.

`bool` is tested **before** `int` because `isinstance(True, int)` is `True` in Python;
the obvious ordering would re-own `True` as `1` and digest content the caller never
supplied.

A refusal is an **optimization boundary, never a validation verdict** — the schema
takes the existing uncached path with unchanged semantics. Two behaviours were
verified against the pre-Slice-F code and are preserved exactly rather than
"improved": an external `$ref` still raises `_WrappedReferencingError` on the
low-level path, and a self-referential schema still raises `RecursionError`. Inability
to cache must not become a new way for a contract to fail.

---

## 3. Evidence

### Method

| | |
|---|---|
| Corpora | Slice A (`fixtures.CORPUS`) **∪** Slice E — **neither modified** |
| Union contexts | **95** — 10 Slice-A only, 84 Slice-E only, **1 shared**, 2 aliases deduplicated |
| Slice-A admission re-check | **11/11 still admitted** under current capability truth; **0** historical refused references |
| Fresh processes | **5** per phase, each with a deterministic case rotation |
| Payload rule | declared **before** timing: lexicographically first payload class per context |
| Iteration tiers | declared in advance: small(<2 KB) 40, medium(<20 KB) 20, large 8 |
| Quantiles | nearest-rank, frozen floors (p95 `n`≥20, p99 `n`≥100) |
| Artifacts | `baseline/slice_f_preparation_cache.json`, `baseline/slice_f_production_path.json` |

**Global deduplication.** "Unique context" means unique across Slice A ∪ Slice E, not
inside each. `semantic-medium` (Slice A) and `width-25` (Slice E) are byte-identical
under the same draft and format policy; both provenances are retained but they
contribute **one** observation, so a shape present in both histories cannot be counted
twice into the cache's apparent benefit.

**Cache state was verified, never inferred.** Every timed observation declared its
expected state and recorded the observed one; cold was re-established before *each*
iteration so a cold series could not warm itself up. **0 mismatches** across both
phases (5 runs × 95 contexts × 2 states).

### Phase 1 — feasibility (candidate model)

| | min | median | max |
|---|---:|---:|---:|
| warm-hit saving | **20.9%** | **91.0%** | **98.1%** |
| cold-miss overhead | −16.5% | 4.0% | 56.5% |
| identity overhead | 0.008 ms | 0.031 ms | 3.165 ms |

- **95/95 contexts benefit.** Identity overhead never erases the saving.
- **Break-even is 1–2 calls everywhere**: 33 contexts have a cold path no slower than
  current at all; the remaining 62 recover their overhead on the second call.
- **0 semantic equivalence failures**, **0 cache-state failures**.

Expensive Slice-A fixtures, which are the ones that matter most:

| Fixture | A current | C warm | saved |
|---|---:|---:|---:|
| `semantic-nested-d6` | 468.13 ms | 10.37 ms | 97.8% |
| `semantic-large` | 62.70 ms | 5.58 ms | 91.1% |
| `semantic-nested-d4` | 50.35 ms | 1.08 ms | 97.9% |
| `native-large` | 46.38 ms | 0.96 ms | 97.9% |
| `semantic-combinator-20` | 41.70 ms | 1.22 ms | 97.1% |

Slice-A family: median saving **96.5%**, minimum **87.8%**, worst cold overhead 15.3%.

#### Two things the headline numbers hide, reported plainly

**The cold-overhead metric is noisy, and not because of the cache.** The worst case,
`allof-25`, shows +6.57 ms cold overhead — but its identity work is **0.045 ms**
against a 9.98 ms `check_schema`. Both A and C-cold run `check_schema`, so what that
figure mostly measures is run-to-run variance in an operation common to both paths.
The *structural* cold cost is the identity work, which is 0.008–3.165 ms and always a
small fraction of the total.

**The repeatability criterion had to be stated more carefully.** The gate was first
encoded as "warm saving positive in **every** run", which flagged two contexts:
`array-items-100` and `dialect-refs-draft4`. Both are evaluation-dominated
(`check_schema` is only 16% and 21% of their total), both had **one** negative run in
five, and both retain a clearly positive median (23.6% and 20.9%). `array-items-100`'s
single −0.74 ms excursion is 60× its entire 0.012 ms identity overhead, so the cache
cannot be its cause.

Read as the median across fresh processes — the aggregation used everywhere else in
this evidence — **zero contexts regress**. Both numbers are reported in the artifact.
This distinction was drawn *after* seeing the results and is flagged as such; the
conclusion does not depend on it, because every context's median saving is positive
under either reading.

### Phase 2 — production path

Re-measured through the actual `JsonSchemaSemanticValidator.validate()`, since the
Phase-1 model is not what ships. Eviction is a **real LRU eviction** (capacity-1
evaluator, second schema pushes the first out), not a test-only reset.

| | min | median | max |
|---|---:|---:|---:|
| warm vs cold | **22.0%** | **91.3%** | **98.2%** |

| Safety property | Result |
|---|---|
| cold == warm == post-eviction breaches | **True**, all 95 contexts × 5 runs |
| cache-state verification failures | **0** |
| semantic equivalence failures | **0** |
| contexts where a real LRU eviction was not observed | **0** |

Production agrees with the model to within a point (91.3% vs 91.0% median), which is
the check that matters: the shipped code behaves as the evidence predicted.

### Deadline fidelity, re-run after implementation

Cooperative control returned at 102.63 ms against a 100 ms budget (1.03×).
`semantic-nested-d6`: caller **131.2 ms**, worker **372.5 ms**, tail 241.5 ms.

**Verdict unchanged** — the governed caller observes deadline exhaustion without
waiting for the semantic work to finish. A cold miss still pays `check_schema` inside
the semantic stage and can still produce a truthful `SEMANTIC_TIMEOUT / SEMANTIC`; a
warm hit simply lets more validations finish inside budget. No cache work was moved
outside the governed stage.

---

## 4. Safety

All 68 tests in `tests/unit/test_p1_5_preparation_cache.py` are deterministic with no
timing assertions.

| Property | How it is held |
|---|---|
| **No validator sharing** | key parts asserted to be `str`/`type`/`bool`/`int`; the class is referenced for identity, never an instance |
| **Nothing mutable cached** | no schema body, no result, no breach list; mutating one result cannot empty another |
| **Mutation cannot poison** | mutation after population misses; the *new* constraint is the one enforced; nested dict and nested list mutation both miss; validation never mutates the caller's schema |
| **Identity follows content** | equal-but-distinct objects hit; key order irrelevant; content and nested change miss; draft, format policy and cache version isolate |
| **Marker narrowness** | the RE2 pattern guard fires on every call, warm included; a pattern rejection never populates the cache; invalid schemas are not negative-cached |
| **Cycles and exotic input** | self-referential dict, self-referential list, nested cycle, `NaN`/`±Inf`, non-string keys, custom `dict` subclass — all uncached, existing behaviour preserved exactly; a repeated sub-object is *not* mistaken for a cycle |
| **Concurrency** | concurrent cold misses agree and produce one entry; concurrent hits agree; 8 distinct schemas concurrently keep their own verdicts; eviction pressure at capacity 2 preserves all 16 verdicts; a test asserts correctness does not depend on holding the lock across preparation |
| **Late worker** | a worker finishing after its caller's timeout may insert a marker; a later request that hits it produces a result equal to a cold evaluation; the evaluator has no telemetry, no storage and no `ValidationResult` to publish |
| **Budget** | cold-path semantic timeout still truthful; a warm path is still refused by the post-stage check when late; a hit does not reset the deadline |
| **Compatibility** | `CompositeValidator`, the governed use case, all five drafts, format checking on and off, local refs; public `__all__` unchanged |

### The one documented exception to the Slice-C late-worker model

Slice C established that a timed-out semantic worker keeps running with **no**
externally visible side effect. Slice F adds exactly one internal side effect: after
`check_schema` genuinely succeeds, that worker may insert `CHECK_SCHEMA_VALID` even
though its caller already timed out.

This is safe only because the marker carries **preparation truth for a schema and
context, and no payload or final-result truth whatsoever**. It is a performance-only
exception. Final-result ownership remains in L3; a late worker cannot publish a
contradictory PASS, emit final-result telemetry, mutate a returned `ValidationResult`,
persist a verdict, mutate caller input, or share its live validator.

---

## 5. Production delta

| File | Change |
|---|---|
| `infrastructure/schema_preparation_cache.py` | **new** (L4) — audit, owned snapshot, canonical identity, bounded LRU of `CHECK_SCHEMA_VALID` |
| `infrastructure/jsonschema_validator.py` | `validate()` routes preparation through the cache; the single `check_schema` call site |

Unchanged: contract admission · Slice-C budget semantics (`validation_timeout_ms`,
stage caps, absolute deadlines, post-stage checks, `SEMANTIC_TIMEOUT`,
`EvaluationStage`, load-shed distinction) · result semantics · reference, regex and
format policy · `CompositeValidator` and the low-level API · `CongineConfig` · health
keys · telemetry · public `__all__`.

Internal `stats()` counters (hits/misses/evictions) exist for tests and evidence only
and are deliberately not surfaced through health or telemetry.

---

## 6. Reproducing this

```bash
uv run --package congine-sdk python -m tools.p1_5_evidence prepcache --scale
uv run --package congine-sdk python -m tools.p1_5_evidence prepcache --pilot        # not evidence
uv run --package congine-sdk python -m tools.p1_5_evidence prepcache --json         # Phase 1, ~12 min
uv run --package congine-sdk python -m tools.p1_5_evidence prepcache --production --json  # Phase 2, ~4 min
uv run --package congine-sdk python -m tools.p1_5_evidence deadline
```

Both artifacts retain the methodology version, payload-selection rule, iteration
schedule, quantile floors, per-fixture admission classification, provenance and
aliases, and — for each run — its identity, rotation offset, case order, per-context
component and path timings, and the expected/observed cache state of every
observation. `preparation_cache.reanalyse()` recomputes every conclusion from the raw
observations without trusting this document.

Statistics that cannot be computed are recorded as `null` with a reason
(`no_warm_saving_to_recover`, `cold_path_not_slower_than_current`) rather than as a
misleading number.

**Observational only. Not a release SLA; P2 owns performance gates.**
