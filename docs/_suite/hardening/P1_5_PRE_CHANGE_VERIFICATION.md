# P1.5 Semantic Validation Safety — Pre-Change Verification

**Stage 0 only. No production code was modified to produce this document.**

---

## 1. Baseline discovery (measured from Git, not assumed)

| | |
|---|---|
| Starting branch | `POST_P1_CONTEXT_RECONCILIATION` |
| Starting HEAD | `e59fece5fe58cab0e121824cdfe44ddadaff1057` |
| P1 engineering baseline | `b482bc4b2c88273e2a29a0f418a53f7ba3ab0614` |
| Documentation/context baseline | `e59fece` — *"docs: reconcile context sources with P1 closed architecture"* |
| Worktree state | **clean** (`git status --short` empty) |
| `b482bc4` is an ancestor of HEAD | **YES** |

Observed history matches the expected chain:

```
b482bc4  P1 CLOSED engineering baseline
   ↓
7fd9f0d  founder-owned Markdown deletion (3 SDK audit files)
   ↓
e59fece  POST-P1 CONTEXT-SOURCE RECONCILIATION  ← current HEAD
```

**Production-code delta since `b482bc4`: NONE.** All 13 changed paths are `.md`:
`docs/architecture/ARCHITECTURE_CURRENT.md`, nine `docs_v4/*.md`, and the three
`libs/congine-sdk/SDK_AUDIT_*.md` deletions. Filtering `git diff --name-only b482bc4 HEAD`
for non-`.md` returns nothing — **no `.py`, `.json`, `.toml`, `.lock`, `.yml` change**. The P1
engineering baseline is intact and P1.5 may begin.

### Environment

| | |
|---|---|
| Python | 3.14.6 |
| OS | Windows 11 (`MINGW64_NT-10.0-26200`) |
| CPU | Intel64 Family 6 Model 140 Stepping 1 |
| uv · Node · npm | 0.12.5 · v24.18.0 · 11.16.0 |
| jsonschema | **4.26.0** |
| google-re2 · httpx · portalocker | 1.1.20251105 · 0.28.1 · 3.2.0 |
| mypy · ruff · pytest | 2.3.1 · 0.15.15 · 9.0.3 |

---

## 2. Current blocking gate results

Nx targets present: `architecture`, `examples`, `lint`, `test`, `typecheck`.
All run with `--skipNxCache`.

| Gate | Command | Result |
|---|---|---|
| Lint | `npm exec nx -- run congine-sdk:lint --skipNxCache` | **Pass** — 99 files formatted, all Ruff checks passed |
| Typecheck | `npm exec nx -- run congine-sdk:typecheck --skipNxCache` | **Pass** — strict mypy, 0 issues, 40 source files |
| Architecture | `npm exec nx -- run congine-sdk:architecture --skipNxCache` | **Pass** — 40 source files, 90 architecture tests |
| Examples | `npm exec nx -- run congine-sdk:examples --skipNxCache` | **Pass** — offline guarded fallback validated |
| Test | `npm exec nx -- run congine-sdk:test --skipNxCache` | **613 passed, 1 skipped** |

Architecture allowlist entries: **0**. `TYPE_CHECKING` exemptions: **0**.

## 3. P0 trust evidence

`uv run --package congine-sdk --extra dev python -m tools.p0_evidence` → exit 0, **5/5 hold**.

| Category | Result |
|---|---|
| Determinism, N=5000 | **1 distinct canonical verdict** |
| Admission preflight | **3/3 = 100 %** |
| False-safety corpus | **4/4 refused, 0 false PASS** |
| Load shedding | **2000/2000 → `LoadShedError`**; deadline overrun stays a plain `TimeoutError` |
| Configuration parity | **5/5** enum fields canonical under both doors |

**Determinism hash is byte-identical to the recorded post-P1 baseline:**

```
715725383efa751299422a3dbe990c34c4c47d657e73ca90a03088ddf7f36dfa
```

Methodology and inputs unchanged, so this must remain identical through P1.5 closure.

---

## 4. Current semantic-validation architecture

### 4.1 Evaluator selection path

`ServiceContainer.__init__` constructs `JsonSchemaSemanticValidator` **unconditionally**, then
selects the validator strategy on `config.semantic_validation_enabled`:

```
LocalValidator()                        ← always built (L2, native rules)
JsonSchemaSemanticValidator(...)        ← always built (L4)
   max_breaches      = config.semantic_max_breaches      (default 100)
   format_checking   = config.semantic_format_checking   (default False)
   jsonschema_draft  = config.jsonschema_draft           (default draft202012)
        ↓
if config.semantic_validation_enabled:  validator = CompositeValidator(rule, semantic)
else:                                   validator = LocalValidator alone
```

The `JsonSchemaSemanticValidator` **instance** is therefore built once per container and reused.
That is not where the cost lives — see §4.3.

### 4.2 Execution order and duplication

`CompositeValidator.validate()` (L2, `domain/validator.py`) runs **sequentially**, native first:

```
start = perf_counter()
rule_result = rule_validator.validate(payload, schema)      # native, 6 rules
breaches   += semantic_validator.validate(payload, schema)  # full JSON Schema
duration_ms = elapsed
status = "pass" if not breaches else "fail"
degraded = rule_result.degraded          ← propagates only from the RULE validator
```

**Both run. Every time. There is no short-circuit.** Work is genuinely duplicated: `type`, `enum`,
`pattern`, `required` and range constraints are evaluated by the native engine *and again* by the
JSON Schema evaluator, which re-checks the whole schema.

Note also that `degraded` is taken from the rule validator only — the semantic validator has **no
channel to report degradation at all**. It returns `List[BreachDetail]` or raises.

### 4.3 Where the cost actually is — the central Stage-0 finding

`JsonSchemaSemanticValidator.validate()` performs, **on every call**:

1. `_check_schema_patterns(schema)` — walks `properties` for over-long patterns;
2. **`self._validator_cls.check_schema(schema)`** — validates the schema against the meta-schema;
3. **`self._validator_cls(schema, format_checker=...)`** — constructs a *new* validator instance;
4. `validator.iter_errors(payload)` — the actual evaluation.

Steps 2–3 are *schema preparation*. They do not depend on the payload, yet they repeat per
validation. Measurement (§6) shows they are **86–100 % of total semantic cost**.

### 4.4 Budget and timeout ownership

There is exactly **one** budget. `ValidateContractUseCase.execute()`:

```
started = perf_counter()
result  = self.timer.run_with_timeout(do_validate, self.timeout_ms)   # timeout_ms = validation_timeout_ms
except LoadShedError  → _degraded_on_capacity  → DegradedReason.LOAD_SHED
except TimeoutError   → _degraded_on_timeout   → DegradedReason.TIMEOUT
```

`self.timeout_ms` derives from `validation_timeout_ms`, **default `DEFAULT_VALIDATION_TIMEOUT_MS = 100`**.

`BoundedValidationExecutor.run_with_timeout()` acquires its permit **non-blocking** (shedding on
saturation), then waits `future.result(timeout=timeout_ms/1000)`. Therefore the single 100 ms budget
covers **all** of:

| Consumer | In the 100 ms? |
|---|---|
| Queue wait while workers are busy | **YES** — the future may sit queued after a permit is taken |
| Native `RuleEngine` evaluation | YES |
| Semantic schema preparation (`check_schema` + construction) | **YES** |
| Semantic evaluation (`iter_errors`) | YES |
| Orchestration overhead | YES |

There is **no semantic sub-budget and no separate semantic timeout field**. Config exposes only
`validation_timeout_ms`, `semantic_validation_enabled`, `semantic_max_breaches`,
`semantic_format_checking`, `jsonschema_draft`.

### 4.5 Degradation / result behaviour on timeout

A semantic overrun and a native overrun produce **the identical observable result**:

```
ValidationResult(status="fail", breaches=(), degraded=True, degraded_reason="timeout")
```

Load shed is correctly distinct (`DegradedReason.LOAD_SHED`, raised before execution). But
**semantic deadline exhaustion is indistinguishable from native deadline exhaustion** in the result,
in telemetry, and in logs. An operator cannot tell "your contract is too expensive for the semantic
evaluator" from "the machine was slow".

### 4.6 Admission capability model

`admit_contract(schema, mode, enforced_keywords)` judges against a capability set composed in
`SyncContractsUseCase.__init__`:

```
enforced = set(NATIVE_ENFORCED_KEYWORDS)                    # 10 keywords
if semantic_validation_enabled:
    enforced |= SEMANTIC_ENFORCED_KEYWORDS                  # 33 keywords
    if semantic_format_checking: enforced.add("format")
```

Admission answers **"will some wired evaluator execute this clause?"** — a *capability* question.
It does **not** ask **"can that evaluator execute it within the operational envelope?"** — a *cost*
question. That gap is precisely the P1.5 thesis.

### 4.7 Telemetry / logging

Semantic outcomes surface only as breaches (`rule="SEMANTIC_SCHEMA"`, and `"SEMANTIC_TRUNCATED"`
when `max_breaches` is hit). There is **no semantic-cost signal** anywhere: no startup log, no
health field, no telemetry attribute, no configuration-time warning.

### 4.8 Semantic feature triggers

`CONGINE_SEMANTIC_VALIDATION=true` is the only switch that engages the evaluator;
`semantic_format_checking` additionally enables format assertions. Both default to `False`.

---

## 5. Architectural placement (unchanged, must stay)

| Component | Layer |
|---|---|
| `models.py` canonical value contracts | L0 |
| `ISemanticValidator`, `IValidationRunner` | L1 |
| `LocalValidator`, `CompositeValidator`, `RuleEngine`, `contract_admission`, `schema_vocabulary` | L2 |
| `ValidateContractUseCase`, `SyncContractsUseCase` | L3 |
| `JsonSchemaSemanticValidator`, `BoundedValidationExecutor` | L4 |
| `ServiceContainer` | L5 |

Matrix, zero allowlists and zero `TYPE_CHECKING` exemptions all hold at HEAD.

---

## 6. Measured performance baseline

Scratchpad harness (a committed harness under `tools/p1_5_evidence/` is Slice A work).
Median of 200 iterations for small/medium, 40 for large; 3 warmup iterations; cold cache;
`format_checking=False`; draft 2020-12. Milliseconds.

| Case | native p50 | semantic **full** p50 | semantic **prep** p50 | semantic **eval-only** p50 | prep share | semantic p95 | semantic max |
|---|---|---|---|---|---|---|---|
| native-small (3 props) | 0.014 | 2.227 | 3.079 | 0.036 | ~100 % | 5.83 | 16.20 |
| native-medium (25) | 0.048 | 22.988 | 23.829 | 0.252 | ~100 % | 47.57 | 144.60 |
| native-large (120) | 0.279 | 107.477 | 102.447 | 1.362 | 95 % | 119.49 | 133.78 |
| semantic-small (3 + minLength/maxLength) | 0.051 | 4.113 | 4.142 | 0.070 | 100 % | 7.37 | 8.53 |
| semantic-medium (25 + pattern) | 0.599 | 29.083 | 27.460 | 0.558 | 94 % | 37.84 | 46.13 |
| semantic-large (120 + pattern) | 2.843 | **159.345** | 136.494 | 3.500 | 86 % | **306.11** | 336.55 |

*Sub-millisecond rows carry visible measurement noise — `native-small` shows prep p50 slightly above
full p50, which is noise at that scale, not a real inversion. The large-case ratios are robust.*

### Four conclusions the numbers force

1. **Semantic cost is preparation cost.** 86–100 % of every semantic validation is `check_schema` +
   validator construction — payload-independent work repeated on each call. Pure evaluation is
   0.04–3.5 ms.
2. **The default budget is already exceeded.** `semantic-large` p50 **159 ms** and p95 **306 ms**
   against `validation_timeout_ms` **100 ms**. A large semantic contract does not occasionally
   time out — it times out **routinely**, and reports `degraded_reason="timeout"`.
3. **The multiplier is 100×–3000×.** `native-medium` is 0.048 ms natively and 22.988 ms under the
   semantic evaluator — ~480×. Nothing in configuration, docs or runtime tells a user this.
4. **A cache would remove almost all of it.** Reusing a prepared validator drops `semantic-large`
   from ~159 ms to ~3.5 ms (~45×) and `semantic-medium` from ~29 ms to ~0.56 ms (~52×) — *if*
   sharing can be proven safe. That proof is Slice D work and is **not** assumed here.

---

## 7. Current known semantic-safety gap (the P1.5 problem statement)

CONGINE can **admit** a contract it understands but **cannot evaluate** inside its operational
envelope, and when that happens the failure is reported in a way an operator cannot act on:

1. Admission asks a *capability* question, never a *cost* question (§4.6).
2. One 100 ms budget covers queue wait, native, semantic preparation and semantic evaluation (§4.4).
3. Semantic preparation alone routinely exceeds that budget (§6).
4. The resulting degradation is `degraded_reason="timeout"` — identical to a native overrun (§4.5).
5. Nothing warns the user at configuration time (§4.7).

G14 is **not currently violated** — a semantic timeout is honestly reported as degraded and
`is_enforced()` is `False`, so "not evaluated" never looks conforming. The defect is weaker but real:
the *reason* is untruthful by omission, and the condition is far more likely than anyone is told.

---

## 8. Proposed P1.5 slices

| Slice | Scope | Expected outcome |
|---|---|---|
| **A** | Commit reproducible benchmark harness at `tools/p1_5_evidence/`; formalise §6; decide the minimal truthful cost-communication surface | Evidence tooling + cost truth |
| **B** | Separate native and semantic budget policy; config fields with G13 parity; minimal result/telemetry truthfulness so semantic exhaustion is distinguishable | Budget architecture |
| **C** | Complexity/admission prototype — test candidate predictors against measured cost. **A negative result is an acceptable outcome** | Evidence-backed, or documented negative |
| **D** | Compiled-validator caching — measure, then **prove or reject** thread-safe sharing before implementing anything | Bounded cache, or documented rejection |
| **E** | Integrated adversarial verification | Falsification evidence |
| **F** | Completion report + surgical `ARCHITECTURE_CURRENT.md` reconciliation | Closure |

### Files expected to change (by layer)

| Layer | Likely files |
|---|---|
| L0 | `config.py` (new budget fields), possibly `models.py` (new `DegradedReason` member) |
| L1 | `ports/semantic_validator.py` **only if** a capability/budget seam proves necessary |
| L2 | `domain/validator.py` (`CompositeValidator` budget split), possibly a complexity module if Slice C justifies one |
| L3 | `usecases/validate_contract_usecase.py` (budget orchestration) |
| L4 | `infrastructure/jsonschema_validator.py` (preparation/caching), `bounded_executor.py` **only if** unavoidable |
| L5 | `adapters/dependency_injection.py` (wiring) |
| Tests | semantic, budget, config parity, architecture, adversarial |
| Tools | `tools/p1_5_evidence/` (new) |

---

## 9. Explicit deferrals (must not leak into P1.5)

**P2:** Python 3.11–3.13 matrix · Linux release CI · branch coverage · pip-audit · SBOM ·
cross-platform determinism corpus · formal release performance budgets.
**P3:** D1/D2/D3 · F01–F09 · ADR archive · full documentation-suite reconciliation.
**Product:** CLI · MCP · durable event store · Control Plane backend · correction hints ·
architecture graph · agent adapters · adaptive routing · Policy IR · Business Policy DSL.
**Separately deferred:** universal `schema_storage.put()` admission ·
`AdmittedContract`/`CompiledContract` boundary · version-aware storage identity ·
full three-axis result-model redesign.

Local numbers in §6 are **single-machine, single-platform** measurements. They are P1.5 safety
evidence, **not** release SLAs — P2 owns those.

---

## 10. Founder decisions required

1. **Default budget values.** New semantic budget defaults must not silently change whether existing
   deployments start timing out. Recommendation: keep `semantic_validation_enabled=False` default
   untouched, and set the semantic budget so today's *enabled* behaviour is not made stricter.
2. **A new `DegradedReason` member** (e.g. `SEMANTIC_TIMEOUT`) is the minimal way to distinguish
   semantic exhaustion. It is an additive change to a public, wire-visible enum — confirm this counts
   as acceptable rather than the deferred three-axis redesign.
3. **Slice C outcome authority.** Confirm that "no reliable deterministic predictor found → do not
   implement hard admission rejection" is an acceptable closure state.
4. **Slice D outcome authority.** Caching is conditional on proving thread safety. If `jsonschema`
   validator instances cannot be shown safe to share, confirm that caching immutable preparation
   artifacts only — or not caching at all — is acceptable.

No decision is requested that code or evidence can answer.

---

## 11. Stop conditions

Work halts and reports rather than proceeding if: the determinism hash changes under unchanged
methodology · any P0 evidence category regresses · an architecture allowlist or `TYPE_CHECKING`
exemption would be needed · truthful reporting requires the deferred three-axis redesign · thread
safety of a shared validator cannot be established · a complexity threshold would need to be chosen
without stable evidence · native latency regresses materially.
