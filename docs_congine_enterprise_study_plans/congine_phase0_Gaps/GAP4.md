# GAP4 — Empirical measurements

**Generated:** 2026-08-16 · **Commit:** `49a2f93` (working tree clean)
**Machine:** Windows 11 Pro 10.0.22631, x86-64 · **Interpreter:** CPython 3.14.5 (`.venv`)
**Package:** `congine-sdk 0.1.0`, editable · **Runner:** `uv 0.11.19`

Every number below was measured on this machine, with the exact command recorded. Nothing is
estimated. Where a measurement could not be taken it is recorded as **NOT MEASURED** with the reason.

> **Caveat that applies to every latency figure.** These are single-machine, single-run numbers on a
> developer laptop under Windows, not a controlled benchmark. Treat the *shape* of each distribution
> and the *ratios between scenarios* as the finding; treat absolute microseconds as indicative. The
> conclusions drawn below (O(1) cache, sub-millisecond rule engine, load shed rather than queue,
> bounded boot) rest on ratios and orders of magnitude, all of which have wide margins.

---

## 4.1 Test suite

**Command:**
```bash
uv run --package congine-sdk --extra langchain --extra stats --extra dev \
  pytest libs/congine-sdk/tests -q --durations=15 \
  --cov=congine_core --cov-report=term-missing --cov-report=json:coverage.json
```

**Result: `350 passed, 1 skipped in 23.14s`** · exit code 0.

### Breakdown by category

Each category was run separately (`pytest libs/congine-sdk/tests/<dir> -q`).

| Category | Files | `def test_` | Collected result | Duration |
|---|---|---|---|---|
| `tests/unit/` | 21 | 210 | **264 passed** | 1.54 s |
| `tests/adversarial/` | 8 | 42 | **41 passed, 1 skipped** | 4.04 s |
| `tests/integration/` | 1 | 11 | **11 passed** | 11.64 s |
| root-level (`tests/*.py`) | 5 | 34 | **34 passed** | 3.92 s |
| **Total** | **35** | **297** | **350 passed, 1 skipped** | **23.14 s** |

Collected counts exceed `def test_` counts because of parametrisation (297 definitions → 351
collected). There is no dedicated concurrency directory; concurrency is exercised inside
`tests/adversarial/test_bounded_executor.py` and `tests/unit/test_container_tenant_lru.py`.

### The one skipped test

```
SKIPPED [1] libs\congine-sdk\tests\adversarial\test_remediations.py:193:
           symlinks not permitted on this platform/user
```
`test_symlinked_snapshot_is_refused` — it needs symlink creation, which requires Developer Mode or
elevation on Windows. **This is the test backing guarantee G4's symlink-refusal layer
(`§14.4`), and it does not run on this platform.** On a POSIX CI runner it executes.

### ⚠ Drift against `arch_progress.md` / `ARCHITECTURE_CURRENT.md`

| Source | Claim | Measured | Verdict |
|---|---|---|---|
| `ARCHITECTURE_CURRENT.md` head, `§2.2` | 293 passed, 1 skipped; 34 test files | **350 passed, 1 skipped; 35 files** | **DRIFT** — +57 tests, +1 file |
| `docs/architecture/OPEN_QUESTIONS.md` | "350 passed, 1 skipped (was 293/1)" | **350 passed, 1 skipped** | **CONFIRMED exactly** |

The architecture document predates commit `49a2f93`, which added 57 tests alongside the Q1–Q12
work. `OPEN_QUESTIONS.md` is the accurate source. The +57 arrive in
`test_readme_config_table.py` (new), `test_schema_vocabulary.py` (+), `test_sync_usecase.py` (+),
`test_config_wiring.py` (+), `test_container_tenant_lru.py` (+).

---

## 4.2 Coverage

**Command:** as above, `--cov=congine_core --cov-report=term-missing`.
`branch = true` is set in `pyproject.toml:81`, but the JSON report emitted only statement totals
(`num_branches` absent), so **branch coverage is NOT MEASURED: the coverage.py JSON report did not
include branch totals in this run.** Statement coverage below.

**Overall: 92% — 1 805 of 1 967 statements covered, 162 missing, 95 excluded.**

### Per-module

| Module | Stmts | Miss | Cover | Missing lines |
|---|---|---|---|---|
| `infrastructure/timer.py` | 21 | 21 | **0%** | 18-81 |
| `infrastructure/file_contract_repository.py` | 73 | 19 | **74%** | 88-89, 102-112, 138, 142-146, 161-164 |
| `infrastructure/http_contract_repository.py` | 125 | 24 | **81%** | 48-50, 122, 129, 133, 152-153, 186-187, 195-198, 222-223, 236-238, 250-256 |
| `adapters/langchain_handler.py` | 85 | 15 | **82%** | 34, 43-51, 78, 107, 119, 131, 137, 140-141, 145-147 |
| `usecases/validate_contract_usecase.py` | 111 | 16 | **86%** | 63, 74, 78, 95, 100, 112-119, 128-129, 146-147, 149 |
| `congine_core/__init__.py` | 15 | 2 | 87% | 80-81 |
| `infrastructure/queue_event_bus.py` | 136 | 18 | **87%** | 120, 140-141, 157, 169-170, 179-180, 222-231, 254, 266, 279, 281 |
| `pii_sanitize.py` | 8 | 1 | 88% | 24 |
| `usecases/sync_contracts_usecase.py` | 151 | 12 | 92% | 162, 217-220, 223-226, 293, 301-302, 313-314 |
| `config.py` | 158 | 8 | 95% | 74, 198-199, 215, 356, 362, 409-410 |
| `domain/validator.py` | 167 | 8 | **95%** | 87, 109-111, 175, 228, 313, 433 |
| `infrastructure/bounded_executor.py` | 75 | 4 | **95%** | 138, 170-172 |
| `infrastructure/lfu_cache.py` | 119 | 6 | 95% | 151-152, 186-189 |
| `infrastructure/jsonschema_validator.py` | 62 | 2 | 97% | 152, 156 |
| `adapters/dependency_injection.py` | 200 | 4 | **98%** | 167, 401, 420-421 |
| `infrastructure/background_sync.py` | 42 | 1 | 98% | 91 |
| `infrastructure/ks_drift.py` | 62 | 1 | 98% | 155 |
| `domain/models.py`, `domain/schema_vocabulary.py`, `exceptions.py`, `infrastructure/circuit_breaker.py`, `infrastructure/logger.py`, `infrastructure/noop_event_bus.py`, `security_limits.py`, `adapters/guard.py`, all 9 `ports/*`, all 4 aggregate `__init__.py` | — | 0 | **100%** | — |

### What is uncovered, and whether it matters

**Hot-path modules are well covered.** `domain/validator.py` 95%, `bounded_executor.py` 95%,
`lfu_cache.py` 95%, `dependency_injection.py` 98%, `adapters/guard.py` **100%**,
`domain/models.py` **100%**, `domain/schema_vocabulary.py` **100%**, and every port 100%.

Specific gaps worth naming:

- **`timer.py` at 0%.** The `--cov` run reports zero because the deprecated module is imported but
  its body never executes under coverage in the full-suite configuration, even though
  `tests/unit/test_timer.py` (4 tests) exists and passes. Either way it is dead code the container
  never constructs (`§16.3`).
- **`validate_contract_usecase.py:112-119`** — the *async* degradation branches
  (`_degraded_on_timeout`, `_degraded_on_error` reached from `execute_async`). The sync twins are
  covered; the async ones are not. Given that H1/H2 exist precisely to make the async path
  equivalent, this is the most consequential coverage gap in the file.
- **`validate_contract_usecase.py:128-129, 146-147`** — the `except (TypeError, ValueError): size = 0`
  fallbacks in both size guards. **This is debt D6's fail-open path and it is untested.**
- **`http_contract_repository.py:250-256`** — `_owned_by_current_user`'s POSIX body. Unreachable on
  Windows; covered on a POSIX runner.
- **`queue_event_bus.py:222-231`** — the breaker-OPEN batch-drop branch.
- **`file_contract_repository.py:102-112`** — the YAML branch, which only executes when `PyYAML`
  is importable.

**NOT MEASURED: coverage on a POSIX runner.** Several gaps above are platform-conditional and would
close on Linux. Only Windows was available.

---

## 4.3 Determinism, demonstrated

**Command:** `python scratchpad/gap4/m43_determinism.py` — N = **5 000** iterations of one
(payload, contract) pair through the full `ValidateContractUseCase.execute` path, each verdict
canonicalised to sorted-key JSON and SHA-256'd.

The contract deliberately exercises five of the six rules including a union type and a regex:

```python
SCHEMA = {"type":"object","required":["label","score","email"],"null_forbidden":["label"],
          "properties":{"label":{"type":["string","null"],"enum":["ok","bad"]},
                        "score":{"type":"number","min":0,"max":1},
                        "email":{"type":"string","pattern":"^[a-z]+@[a-z]+\\.[a-z]+$"}}}
PAYLOAD = {"label":"nope","score":1.5,"email":"BAD","extra":123}
```

**Result — verbatim:**

```
python           : 3.14.5 Windows
N                : 5000
distinct verdicts: 1
  sha256=aef0d7e85c9c559225f3b6257ab99e5f...  count=5000
verdict          : {"breaches":[["ENUM_VALUES","label","Value for 'label' is not an allowed enum value"],["RANGE_CHECK","score","Value for 'score' is above maximum 1"],["REGEX_PATTERN","email","Value for 'email' does not match pattern"]],"degraded":false,"degraded_reason":null,"status":"fail"}
DETERMINISTIC    : True
```

**5 000 / 5 000 byte-identical.** One distinct verdict hash. Breach **order** is stable too — it
follows rule-declaration order (`ENUM_VALUES` → `RANGE_CHECK` → `REGEX_PATTERN`), not payload key
order, and `extra: 123` produced no breach (no `additionalProperties` enforcement, as documented).

**What is deliberately excluded from the verdict.** `duration_ms` is wall-clock and varies
(measured `0.0921` vs `0.0582` ms on consecutive identical calls). It is carried on
`ValidationResult` and copied into telemetry, but it is not part of the judgment. **Any downstream
consumer that hashes a whole `ValidationResult` will get a non-deterministic digest** — the
determinism claim holds for `(status, degraded, degraded_reason, breaches)`, which is the correct
scope, but it is a distinction the suite should state.

**Scope limits — what this does NOT prove.** Determinism across Python versions, across platforms,
across `re2` versions, or across processes with different `PYTHONHASHSEED`. All 5 000 runs were in
one process on one interpreter. **NOT MEASURED: cross-version and cross-platform determinism** — it
would need a CI matrix run, and the CI file does not currently assert verdict equality across the
matrix.

---

## 4.4 Validation latency

**Command:** `python scratchpad/gap4/m44a.py` — 1 000 timed iterations per scenario after 100 warm-up
iterations, measuring the full `execute()` path (size guards + cache get + executor + rules +
telemetry publish to `NoOpEventBus` + enforcement).

### Rule-only (`LocalValidator`, the default configuration) — milliseconds

| Scenario | p50 | p90 | p99 | p99.9 | max | mean |
|---|---|---|---|---|---|---|
| tiny (3 props / 3 fields) | 0.051 | 0.119 | 0.243 | 0.388 | 0.409 | 0.070 |
| small (10 / 10) | 0.073 | 0.173 | 0.318 | 0.449 | 0.503 | 0.096 |
| medium (50 / 50) | 0.111 | 0.253 | 0.472 | 0.650 | 0.774 | 0.151 |
| large (200 / 200) | 0.423 | 0.676 | 1.187 | 1.991 | 2.471 | 0.463 |
| xlarge (500 / 500) | 0.956 | 1.317 | 1.899 | 2.732 | 3.052 | 1.009 |
| **regex (50 props with `pattern`)** | 0.488 | 0.908 | **2.772** | **6.099** | **29.384** | 0.634 |
| wide payload (10 props / 500 fields) | 0.177 | 0.324 | 0.772 | 1.989 | 3.187 | 0.210 |

**Reading it.**

- The default budget is **100 ms** (`config.py:108`). Rule-only validation uses **0.05 %–1 %** of it
  at p50. There is enormous headroom.
- Latency scales with **schema property count**, not payload size — the "wide payload" row (500
  payload fields against a 10-property schema) is 0.177 ms p50, five times cheaper than the
  500-property schema, because the rules iterate `properties`, not the payload.
- **The regex row is the tail risk.** Its p99.9 is 6.1 ms and its max 29.4 ms — 60× its own p50.
  That is `re2` compilation on a cold `lru_cache` plus the outliers of matching 50 patterns.
  Post-warm-up this is GC and scheduler noise; it is still the widest tail in the system and the
  reason `_compiled_pattern`'s 512-entry cache exists.

### Semantic validation ON (`CompositeValidator` = rules + full JSON Schema)

**Command:** `python scratchpad/gap4/m44b.py` — 200 iterations, 20 warm-up, identical schemas.

| Scenario | p50 | p90 | p99 | max | mean | vs rule-only mean |
|---|---|---|---|---|---|---|
| 3 props / 3 fields | 1.465 | 2.142 | 2.851 | 2.988 | 1.563 | **20×** |
| 10 / 10 | 3.460 | 5.178 | 6.524 | 6.752 | 3.777 | **42×** |
| 50 / 50 | 15.219 | 19.815 | 28.161 | 35.825 | 16.062 | **81×** |
| 200 / 200 | **60.579** | **74.175** | **83.690** | **100.494** | 63.150 | **99×** |

(Rule-only control at the same iteration count: 0.078 / 0.091 / 0.198 / 0.640 ms mean.)

### ⚠ FINDING — the documented remedy breaches the default budget

The 200-property row peaks at **100.494 ms against a 100 ms default timeout.** I measured whether
validations actually degrade.

**Command:** `python scratchpad/gap4/m44c.py` — 200 executions per size, counting `degraded` results.

```
default validation_timeout_ms = 100
  n props   degraded/200  reasons
----------------------------------------------------
      200             11  ['timeout']
      400            200  ['timeout']
      800            200  ['timeout']
```

**At 200 properties, 5.5 % of validations degrade. At 400 and above, 100 % degrade.**

This matters more than the numbers suggest, and it should be stated plainly in F05 and F02:

`CONGINE_SEMANTIC_VALIDATION=true` is the **documented remedy** for the silent-non-enforcement
foot-gun (`§13.7` item 1; the P0-2 warning's own remediation hint is
`"set CONGINE_SEMANTIC_VALIDATION=true to enforce full JSON Schema"`). But a degraded result is
`status="fail"`, `degraded=True`, `breaches=()`, and under the default `degrade` fail mode that is
a WARNING and the output flows through (`§9.6`). So on a large contract, **switching on the remedy
replaces one silent non-enforcement with another** — and the second one is arguably worse, because
the first at least evaluated the six rules.

The two failure modes are distinguishable (`degraded=True` vs a clean pass), but only by a caller
who inspects `degraded` — and every documentation sample reads `is_pass()`.

**❓ QUESTION FOR FOUNDER:** Should `validation_timeout_ms` scale with, or be validated against,
`semantic_validation_enabled` and contract size? As shipped, the default 100 ms budget and the
default remedy are incompatible for contracts beyond roughly 200 properties, and nothing warns at
load or at configuration time.

---

## 4.5 Load-shedding behaviour

**Command:** `python scratchpad/gap4/m45_shed.py` — `BoundedValidationExecutor(max_workers=4,
max_pending=2)` → capacity 6. Six threads occupy all six permits with a blocking callable, then
2 000 further calls are made **with a 5 000 ms timeout budget** — so if the executor *queued*, each
call would block for seconds.

**Result — verbatim:**

```
max_workers=4 max_pending=2 -> capacity=6
in_flight after saturating = 6 / capacity 6

rejections: {'validation capacity exhausted (load shed)': 2000}
rejection latency over N=2000 (microseconds):
  p50=1.70  p90=2.10  p99=13.00  max=146.90  mean=2.22
  -> requested timeout was 5000 ms; observed max 0.147 ms
  SHEDS RATHER THAN QUEUES: True
rejected_total = 2000   in_flight = 6
health() = {'in_flight': 6, 'rejected_total': 2000, 'capacity': 6}

--- release the zombies; capacity must return ---
after release: in_flight=0  rejected_total=2000
post-recovery call -> 'served'
```

**What this establishes.**

1. **It sheds, it does not queue.** 2 000 / 2 000 rejected with the message
   `"validation capacity exhausted (load shed)"` — raised from `bounded_executor.py:164`, *before
   any work is submitted*. Rejection latency p50 **1.70 µs**, max **147 µs**, against a 5 000 ms
   budget. That is a factor of ~34 000 between the budget and the worst observed rejection.
2. **Permit-until-completion is real.** `in_flight` stayed pinned at 6 for the entire rejection
   run — the blocked zombies never released their permits, which is the design's most subtle
   property (`§10.3`) and is here observed rather than reasoned about.
3. **Capacity returns cleanly.** After releasing the blocked callables, `in_flight` returned to
   **0** and the next call was served. No permit leak across 2 000 rejections and 6 completions.
4. **`rejected_total` is the only attribution signal.** It reached exactly 2 000. As `§16` D19
   notes, an individual caller cannot tell load shed from a genuine overrun — both surface as
   `degraded_reason="timeout"`. This counter is process-wide.

**Harness note.** The first run of this measurement was invalid — my script referenced `_safe`
before defining it, so the saturating threads all died with `NameError` and every call was accepted
(`in_flight = 0`, 2 000 × `ACCEPTED`). That was a defect in my harness, not in the product; it was
fixed and re-run. Recorded because the first output would otherwise look like a shedding failure.

---

## 4.6 Cache behaviour — the O(1) claim

**Command:** `python scratchpad/gap4/m46_cache.py` — 20 000 random `get`s per size after 2 000
warm-up, on a cache filled to capacity.

### `get` latency vs cache size (microseconds)

| Capacity | Entries | p50 | p90 | p99 | mean | ratio to first |
|---|---|---|---|---|---|---|
| 10 | 10 | 1.000 | 1.200 | 2.300 | 1.069 | 1.00× |
| 100 | 100 | 0.900 | 1.500 | 3.400 | 1.129 | 1.06× |
| 1 000 | 1 000 | 0.800 | 1.000 | 2.600 | 0.921 | 0.86× |
| 10 000 | 10 000 | 0.900 | 1.600 | 4.700 | 1.181 | **1.10×** |
| 100 000 | 100 000 | 2.700 | 4.200 | 12.101 | 3.893 | 3.64× |

### `put` at capacity — forces `_evict_lfu` on every insert (microseconds)

| Capacity | p50 | p90 | p99 | mean | ratio to first |
|---|---|---|---|---|---|
| 10 | 1.200 | 1.600 | 2.600 | 1.398 | 1.00× |
| 100 | 1.200 | 1.500 | 3.700 | 1.409 | 1.01× |
| 1 000 | 1.200 | 1.400 | 2.500 | 1.345 | 0.96× |
| 10 000 | 1.200 | 1.900 | 7.001 | 1.570 | 1.12× |
| 100 000 | 1.600 | 2.600 | 12.704 | 2.002 | 1.43× |

**The O(1) claim holds.** A **1 000× increase** in cache size (10 → 10 000) changes `get` mean
latency by **1.10×** and `put`-with-eviction by **1.12×**. Under O(n) the same increase would cost
~1 000×. The rise at 100 000 entries (3.64× / 1.43×) tracks memory-locality and CPU-cache pressure,
not algorithmic complexity — a 10 000× size increase producing 3.6× is decisively not linear.

### The deliberate O(n) operation, for contrast

`sweep_expired()` is a full scan **by design** (`lfu_cache.py:224-238`) and lives off the hot path:

| Entries | Sweep | Ratio |
|---|---|---|
| 1 000 | 0.115 ms | 1.0× |
| 10 000 | 1.125 ms | 9.8× |
| 100 000 | 15.306 ms | 133.2× |

Cleanly linear (slightly super-linear at 100 k from memory pressure). This is the M4 trade made
visible: `_evict_key` refuses to recompute `_min_freq` so that expiry stays O(1) on the hot path,
and the cost is paid here, on the sweeper daemon, every `cache_sweep_interval_seconds`.

**Operational note.** At default `cache_capacity=500` the sweep is far below 0.115 ms. But a
deployment raising capacity to 100 000 would have its `congine_cache_sweeper` thread hold
`LFUCache._lock` for ~15 ms every 30 s — and `get` on the hot path contends for that same `RLock`.
Not a defect at any plausible contract count; worth knowing before the capacity knob is raised.

**Confirmed:** `capacity=0` disables caching entirely — `put` is a no-op, `size()` stays 0, `get`
returns `None` (`lfu_cache.py:110-111`). Combined with G10 this makes *every* validation raise
`CongineContractNotFoundError`.

---

## 4.7 Boot with a dead control plane

**Command:** `python scratchpad/gap4/m47_boot.py`. Base URL `https://203.0.113.1:8443` —
TEST-NET-3 (RFC 5737), guaranteed unroutable, so a real transport timeout is paid.
`CONGINE_CONTROL_PLANE_HTTP_TIMEOUT=2.0` (shortened from the 10 s default to keep the run tractable),
breaker threshold 5, cooldown 30 s.

**Result — verbatim:**

```
base_url=https://203.0.113.1:8443  http_timeout=2.0s  breaker_threshold=5  cooldown=30.0s

 boot #   elapsed s  loaded   breaker after   note
----------------------------------------------------------------------
      1       2.690       0          CLOSED   paid HTTP timeout
      2       2.024       0          CLOSED   paid HTTP timeout
      3       2.027       0          CLOSED   paid HTTP timeout
      4       2.027       0          CLOSED   paid HTTP timeout
      5       2.025       0            OPEN   paid HTTP timeout
      6       0.000       0            OPEN   FAST-FAIL (no network)
      7       0.000       0            OPEN   FAST-FAIL (no network)
      8       0.000       0            OPEN   FAST-FAIL (no network)

total for 8 boots: 10.792s
bootstrap() NEVER RAISED on a dead control plane: True

--- full bootstrap() end-to-end, breaker already OPEN ---
bootstrap() -> loaded=0  elapsed=0.3145s  breaker=OPEN
```

**Guarantee G2 confirmed exactly as `§14.2` and `§8.3` describe.**

- Attempts 1–5 each pay one HTTP timeout (2.02–2.69 s; the first includes TLS/DNS setup).
- The fifth failure trips the breaker to **OPEN** — matching `breaker_failure_threshold=5`.
- Attempts 6–8 cost **0.000 s**. The network is skipped entirely: `_fetch_sync` sees
  `_breaker_allows()` false and returns `load_snapshot()` inline (`sync_contracts_usecase.py:201-205`).
  This is `§8.3` Case A, and it confirms `§8.3`'s correction to the prior docs — the OPEN path is
  the inline `load_snapshot()`, not `load_snapshot_only()`.
- **`bootstrap()` never raised.** Bounded initialisation holds.
- With the default 10 s timeout the same sequence costs ~50 s before the breaker opens, then 0 s
  thereafter. That is the number an operator sizing a Kubernetes readiness probe needs, and it is
  exactly the failure `circuit_breaker.py:5-8` says the class exists to prevent.

**The `bootstrap()` row is worth reading carefully.** It took **0.3145 s** with the breaker already
OPEN and no network call at all. That time is the **single-flight jitter** —
`random.uniform(0.0, 0.5)` at `sync_contracts_usecase.py:142`, paid before the boot lock is
attempted. So even a fully offline boot pays up to 500 ms of deliberate delay. Correct (it
desynchronises a deployment burst) and worth documenting for anyone measuring cold-start.

**Consequence, confirmed:** with the cache empty, the next validation raised
`CongineContractNotFoundError: Schema anything not found` — G10, fail-closed, in every mode.

---

## 4.8 Static analysis

| Tool | Configured? | Command | Result |
|---|---|---|---|
| **ruff format** | Yes (`pyproject.toml:64-73`, `target-version = "py311"`) | `uv run --package congine-sdk ruff format --check libs/congine-sdk` | **PASS — 80 files already formatted** |
| **ruff check** | Yes | `uv run --package congine-sdk ruff check libs/congine-sdk` | **PASS — All checks passed!** (ruff 0.15.15) |
| **mypy** | **Partially — and non-blocking** | `.github/workflows/ci.yml:211`: `uv run --package congine-sdk mypy libs/congine-sdk \|\| true` | **NOT MEASURED: mypy is not installed** (absent from the `[dev]` extra and from the lockfile) **and its CI invocation is suffixed `\|\| true`, so it can never fail the build.** No `[tool.mypy]` section exists in either `pyproject.toml`. |
| **bandit** | **No** | — | **NOT MEASURED: bandit is not configured anywhere** — no config, no dependency, no CI step. |
| **pip-audit** | **No** | — | **NOT MEASURED: pip-audit is not configured anywhere** — no config, no dependency, no CI step. |

### Findings

1. **Ruff is clean on both format and lint.** Only the default rule set is enabled; no `select`
   list is configured, so security-adjacent rulesets (`S` / flake8-bandit, `ASYNC`, `B`) are **not**
   active. Extending `select` would be the cheapest way to get bandit-class coverage without a new
   tool.
2. **The type-checking gap is the notable one.** Commit `e5c2054` is titled *"chore: achieve 100%
   strict type safety and verify adversarial runtime contracts"*, and the source is annotated
   throughout with `# type: ignore[...]` comments implying a checker once ran. Today it is neither
   installed nor enforced. For a codebase whose seams are `typing.Protocol` — where structural
   conformance is *only* checkable statically — this is a material gap: §3.8 of GAP3 shows a
   Protocol-conformant implementation still crashing at runtime, which is precisely the class of
   defect a type checker plus a stricter port declaration would catch.
3. **No dependency-vulnerability scanning.** Four runtime dependencies (`google-re2`, `httpx`,
   `jsonschema`, `portalocker`), one of which is a native extension. `SECURITY.md` exists but no
   automated audit runs.

**❓ QUESTION FOR FOUNDER:** Should mypy be restored as a blocking CI gate (added to `[dev]`, given
a `[tool.mypy]` section, and the `|| true` removed)? The `# type: ignore` annotations throughout
`src/` are currently unverified claims.

---

## 4.9 Scale facts — authoritative

Established once here; cited throughout the suite. Every figure was counted programmatically.

| Fact | Value | How counted |
|---|---|---|
| **Source files** (`.py` under `src/congine_core/`) | **38** | `find src/congine_core -name "*.py" \| wc -l` |
| — implementation modules | **32** | 38 minus 6 package `__init__.py` |
| — package `__init__.py` | **6** | root, `ports`, `domain`, `usecases`, `infrastructure`, `adapters` |
| **Source lines** (physical, incl. blanks/comments) | **5 473** | `find … -exec cat {} + \| wc -l` |
| **Source lines** (non-blank, non-comment) | **4 402** | as above, filtered |
| **Statements** (coverage.py) | **1 967** | `--cov` totals |
| **Modules per layer** | L0 **5** · L1 **9** · L2 **4** · L3 **3** · L4 **13** · L5 **4** | per-directory `find` |
| **Ports** (`ports/*.py`, excl. `__init__`) | **8** | `ls src/congine_core/ports/*.py` |
| **Protocols declared** | **10** | 7 functional + 2 lifecycle (L1) + `IValidator` (in-domain, L2) |
| **Public API symbols** (`__all__`) | **46** | `len(congine_core.__all__)` |
| **`CongineConfig` fields** | **47** | `len(dataclasses.fields(CongineConfig))` |
| **Test files** | **35** | `find tests -name "test_*.py"` |
| — unit / adversarial / integration / root | 21 / 8 / 1 / 5 | per-directory |
| **`def test_` definitions** | **297** | `grep -rh "def test_"` |
| — unit / adversarial / integration / root | 210 / 42 / 11 / 34 | per-directory |
| **Tests collected & run** | **351** (350 passed, 1 skipped) | pytest |
| **Statement coverage** | **92 %** (1 805 / 1 967) | coverage.py |
| **Audit IDs annotated in `src/`** | **43 distinct**, ~120 occurrences | `grep -oE` over `src/` |
| **Runtime dependencies** | **4** | `google-re2`, `httpx`, `jsonschema`, `portalocker` |
| **Optional extras** | **4** | `langchain`, `stats`, `redos` (no-op alias), `dev` |
| **Concrete implementations wired by the container** | **16** constructions, 1 file | `§4.4` |
| **Rule identifiers produced** | **9** | 6 rules + `INPUT_BOUNDS`, `SEMANTIC_SCHEMA`, `SEMANTIC_TRUNCATED` |
| **Schema keywords enforced by default** | **8** (3 top-level + 5 per-property, 7 spellings) | `schema_vocabulary.py:38-47` |
| **Documented failure modes** | **50** | `§9` rows 1–50 |
| **Invariants / guarantees** | **11** (G1–G11) | `§14` |
| **Debt register items** | **22** (D1–D22) + 9 prior | `§16` — *see GAP1 §DRIFT: 9 are now closed* |

### ⚠ Scale facts that contradict `ARCHITECTURE_CURRENT.md`

| Fact | Document says | Measured | 
|---|---|---|
| Source files | 37 | **38** |
| Implementation modules | 31 | **32** |
| Source lines | 5 075 | **5 473** |
| `ports/` modules | 7 | **8** |
| `CongineConfig` fields | 46 | **47** |
| Tests | 293 passed / 1 skipped, 34 files | **350 passed / 1 skipped, 35 files** |

These are cited throughout the existing document set. **Every downstream document must use the
right-hand column.**

---

## Measurements taken — index

| § | Measurement | Status |
|---|---|---|
| 4.1 | Test suite, full + per category | ✅ measured — 350 passed / 1 skipped / 23.14 s |
| 4.2 | Statement coverage, overall + per module | ✅ measured — 92 % |
| 4.2 | Branch coverage | ⚠ **NOT MEASURED** — JSON report omitted branch totals |
| 4.2 | Coverage on POSIX | ⚠ **NOT MEASURED** — Windows only available |
| 4.3 | Determinism, N = 5 000 | ✅ measured — 1 distinct verdict |
| 4.3 | Cross-version / cross-platform determinism | ⚠ **NOT MEASURED** — needs a CI matrix |
| 4.4 | Latency, rule-only, 7 scenarios | ✅ measured — full distribution |
| 4.4 | Latency, semantic-on, 4 scenarios | ✅ measured — **budget breach found** |
| 4.4 | Timeout-degradation rate under semantic validation | ✅ measured — 5.5 % @200 props, 100 % @400+ |
| 4.5 | Load-shedding rejection latency | ✅ measured — 1.70 µs p50 |
| 4.6 | Cache O(1), get and put, 5 sizes | ✅ measured — 1.10× over 1 000× growth |
| 4.6 | `sweep_expired` O(n), 3 sizes | ✅ measured — linear, as designed |
| 4.7 | Boot vs dead control plane | ✅ measured — 5 timeouts then 0.000 s |
| 4.8 | ruff format + check | ✅ measured — both PASS |
| 4.8 | mypy | ⚠ **NOT MEASURED** — not installed; CI invocation is `\|\| true` |
| 4.8 | bandit | ⚠ **NOT MEASURED** — not configured |
| 4.8 | pip-audit | ⚠ **NOT MEASURED** — not configured |
| 4.9 | Scale facts | ✅ measured — 6 contradict the architecture document |
