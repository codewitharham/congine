# CONGINE PHASE 0 — AUDIT & HEALTH REPORT

Date: 2026-07-20 | Baseline reconciled: 2026-06-14 | Auditor: Claude Code (principal-engineer audit)

> **Evidence discipline.** Every `file:line` below was opened and read. Every command in §2 was
> run in this environment and its exit status captured. Claims are marked **(observed)** when I ran
> or read the thing directly, or **(inferred)** when I reasoned from observed facts without direct
> execution (e.g. CI behaviour I cannot trigger here). Where the baseline and the code disagree, the
> code wins and the drift is called out.

---

## 0. Executive Summary

Phase 0 — the deterministic hot-path validation guard — is **substantially complete, genuinely
well-tested, and architecturally clean.** The full suite is **266 passed / 1 skipped / 0 failed at
91% branch coverage** (observed), the six-layer hexagonal architecture has **no import-direction
violations** (observed), and **all seven hot-path guarantees hold and are test-backed** (with two
platform/scope asterisks noted in §6). The determinism moat is intact: there is **no LLM, network
call, or nondeterministic dependency anywhere in the validation hot path** (observed).

The blocking work is correctness/polish, not new capability. The single most important defect is the
**multi-tenant container eviction** (`for_tenant()` calls `close()` on a container a caller may still
hold, and does so while holding a global lock) — the one place the SDK can crash a live tenant. Two
other items create *false confidence*: the **silently-ignored schema keywords** (`minLength` etc.)
and the **Python-version contradiction** that makes the advertised 3.10 floor un-installable.

A material finding of this audit is **baseline drift**: roughly a month was assumed to have passed
since 2026-06-14, but version control shows **no `src/` changes after the baseline** — the last code
commit is `cf4118f` (2026-06-16, diagrams/docs only), and the bug-fix commits predate the baseline.
Consequently several baseline claims are now stale: **4 of 6 "untested container" gaps are actually
covered** (via `tests/adversarial/test_remediations.py`), and **baseline debt #4 (bytes-vs-chars) is
mischaracterised** — empirically the guard *over-counts* multibyte input (conservative), it does not
undercount, so it is not the vulnerability described.

**Findings by severity:** CRITICAL 0 · HIGH 1 · MEDIUM 6 · LOW 11 · INFO 4.

**Top 3 to fix before MCP:**
1. **[HIGH]** Multi-tenant `for_tenant()` eviction closes a possibly-live container (and blocks under a global lock). `dependency_injection.py:107-118`.
2. **[MEDIUM]** Silent non-enforcement of `minLength`/`maxLength`/`format` — manufactures false safety. `domain/validator.py:333-367`.
3. **[MEDIUM]** `requires-python` contradiction — the advertised 3.10 floor cannot install (observed), CI's 3.10 matrix is broken. `pyproject.toml:6,18,69` + `.github/workflows/ci.yml:65`.

---

## 1. Health Scorecard

| Dimension | State | Evidence / one-line justification |
| --- | --- | --- |
| Build / install | 🟡 YELLOW | Installs, imports, resolves `__version__=0.1.0` on 3.11–3.14 (observed); but the advertised 3.10 floor **fails to install** (`requires-python>=3.11`, observed) — version metadata is self-contradictory. |
| Tests | 🟢 GREEN | 266 passed, 1 skipped (Windows symlink), 0 failed on Python 3.14.5 (observed). |
| Coverage | 🟢 GREEN | 91% branch overall; hot-path modules 95–100% (breaker 100%, cache/executor 95%). Gaps: `timer.py` 0% (dead), eviction branch `dependency_injection.py:110-114` uncovered. |
| Lint (`ruff check`) | 🟢 GREEN | "All checks passed" on `libs/congine-sdk` (observed). |
| Format (`ruff format --check`) | 🟡 YELLOW | 74/75 files formatted; **`examples/LangChain/agent.py` would reformat** — and this is a CI **hard gate** (`ci.yml:138`). (observed) |
| Types (mypy) | 🟡 YELLOW | **4 errors** (observed) despite a commit claiming "100% strict type safety"; mypy is **not a declared dep** and runs `|| true` in CI (`ci.yml:207`) — non-gating. Errors are runtime-safe but real. |
| Security static (bandit) | 🟢 GREEN | 0 High, 1 Medium (false positive: `0.0.0.0` in a loopback allowlist), 4 Low (asserts); not wired into repo tooling (gap). (observed) |
| Deps (pip-audit) | 🟡 YELLOW | Dependency-light **core is clean**; 3 CVEs in the **optional** `[langchain]` extra (`langchain-core`, `langsmith`). (observed) |
| Architecture | 🟢 GREEN | Import-direction scan finds **no inner→outer concrete imports**; composition root is sole wiring site; ports are `@runtime_checkable`. (observed) |
| Concurrency | 🟡 YELLOW | Executor/cache/breaker lock discipline is correct; the risk is eviction `close()` on a live container under a held global lock (see H-1). |
| Configuration | 🟢 GREEN | Every easily-missed knob is threaded to a concrete (observed); lone dead-configurable is `region` (parsed, never read). |
| Docs vs reality | 🟡 YELLOW | Baseline over-states coverage gaps, mischaracterises debt #4, and CLAUDE.md/classifiers claim 3.10; stale `TelemetryEvent` docstring. |

---

## 2. Executable Health Check Results

Environment: Windows 11, `uv 0.11.19`, default `python 3.12.12`; `uv` resolves the workspace to
**Python 3.14.5** (highest satisfying `requires-python>=3.11`).

| # | Command (from workspace root) | Exit | Result |
| --- | --- | --- | --- |
| 1 | `uv sync --package congine-sdk --extra dev --extra langchain --extra stats` | 0 | Resolved 82 / checked 46 packages; install succeeds. |
| 2 | `uv run --package congine-sdk python -c "import congine_core; …"` | 0 | Python 3.14.5; `__version__ = 0.1.0`. |
| 3 | `… pytest libs/congine-sdk/tests --cov=congine_core --cov-report=term-missing` | 0 | **266 passed, 1 skipped**; **TOTAL 91%** branch coverage. |
| 4 | `uv run … ruff format --check libs/congine-sdk` | 1 | 1 file would reformat: `examples/LangChain/agent.py`. |
| 5 | `uv run … ruff check libs/congine-sdk` | 0 | All checks passed. |
| 6 | `uv run --with mypy … mypy libs/congine-sdk/src/congine_core` | 1 | **4 errors** in 2 files (see F-14). |
| 7 | `uv run --with bandit … bandit -r libs/congine-sdk/src` | 1 | 0 High / 1 Medium / 4 Low (all benign — see F-16). |
| 8 | `uv run --with pip-audit … pip-audit` | 1 | 3 CVEs, all in optional `[langchain]` transitive deps (see F-20). |
| 9 | `uv pip install --python 3.11 … ./libs/congine-sdk` | 0 | Install **succeeds** on the real `requires-python` floor. |
| 10 | `uv pip install --python 3.10 … ./libs/congine-sdk` | 1 | **Fails**: "`congine-sdk==0.1.0 depends on Python>=3.11 … cannot be used`". |

**Test count vs baseline.** Baseline claims ~259 functions / 32 files. Observed: **exactly 259 `def test_`
functions across 32 files** (`grep` count), collected as **267 test items** (266 run + 1 skipped) due
to parametrization. Numbers match the baseline precisely — corroborating that the tree is frozen.

**Coverage by hot-path-critical module (observed, branch):**

| Module | Cover | Notable missing |
| --- | --- | --- |
| `adapters/dependency_injection.py` | 96% | **110-114 (tenant eviction/`close()`)**, 300-301 (drift ImportError) |
| `infrastructure/circuit_breaker.py` | 100% | — |
| `infrastructure/bounded_executor.py` | 95% | 170-172 (submit-after-shutdown) |
| `infrastructure/lfu_cache.py` | 95% | 186-189 (`_evict_lfu` stale-min reconcile) |
| `usecases/validate_contract_usecase.py` | 86% | size-guard / degrade branches |
| `usecases/sync_contracts_usecase.py` | 94% | breaker helper branches |
| `infrastructure/http_contract_repository.py` | 81% | snapshot error paths |
| `infrastructure/file_contract_repository.py` | 74% | yaml/error paths (lowest) |
| `infrastructure/timer.py` | **0%** | **entire module — deprecated & now unexercised** |

**What changed since 2026-06-14 (version control, observed).** Nothing in `src/`. HEAD is `cf4118f`
(2026-06-16, diagram `.svg`s + docs). The baseline docs `01–05` were committed in `bb890b8`
(2026-06-15). The bug-oriented commits — `72af5f6` "resolved PII regex + multiTenant cache leaks",
`6e1b60e`, `051ceae` "SDK deadLocks + hardcoded removes" — are dated **2026-06-10…06-12, i.e. before
the baseline**. So the baseline was written *after* those fixes and its residual bug list still
describes current code. `git log --since="2026-06-17"` is empty (observed).

**Tooling gaps (health findings, not silent skips):** no type-checker in `[dev]` deps and mypy is
non-gating; no bandit / pip-audit / safety pinned as gating; CI's `security` job uses `safety` +
`npm audit` with `|| echo` (non-gating, `ci.yml:329-335`).

---

## 3. Architectural Integrity

**Import-direction scan (observed).** `grep` for `from congine_core.(infrastructure|adapters)` under
`ports/`, `domain/`, `usecases/` → **no matches**. Inner layers never import an outer concrete.

- **L0** (`config`, `exceptions`, `security_limits`, `pii_sanitize`) import only stdlib / each other.
- **L1** `ports/*` are `@runtime_checkable Protocol`s; cross-layer value objects (`TelemetryEvent`,
  `BreachDetail`) are referenced **`TYPE_CHECKING`-only** (verified in `ports/event_bus.py:16-17`), so
  importing a port never drags L2 at runtime.
- **L2** `domain/validator.py` holds the in-domain `IValidator` seam (`:293-301`) — the one sanctioned
  protocol outside `ports/`, exactly as documented.
- **L3/L4** depend on L0–L2 + external libs only; **L4 never imports L5**.
- **L5** `adapters/dependency_injection.py` is the **sole** concrete-wiring site (`__init__`,
  `:132-259`). `guard.py` and `langchain_handler.py` attach at the edge.

**Composition root & singletons.** `get_default()` is a double-checked lazy singleton and **raises in
`multi_tenant` mode** (`:60-65`, observed). `for_tenant()` is a bounded (128) insertion-ordered LRU
(`:72-118`). `reset_default()` tears down default + tenant registry (`:120-130`).

**One architectural blemish (see F-15):** the `IEventBus` **port** declares only `publish`
(`ports/event_bus.py:24`), but the composition root calls `queue_depth()`, `dropped_total`, and
`stop()` on the bus (`dependency_injection.py:335,350`). The extra surface is duck-typed, so a
third-party bus that satisfies the published Protocol would break `health()`/`close()`.

---

## 4. Prior-Baseline Reconciliation

Status legend: **VP** = Verified Present · **VF** = Verified Fixed/Absent · **PA** = Partially
Addressed · **UNV** = Unverified.

### Known bugs & debt (`01_SYSTEM_STATE.md` table)

| # | Item | Status | Evidence (file:line) | Note |
| --- | --- | --- | --- | --- |
| 1 | Example enum mismatch (`manual_review` ∉ enum) | **VP** | `examples/LangChain/agent.py:75,91` vs `contracts/return_processing.json:7` | Confirmed; offline Scenario 1 raises under `mode="raise"`. Also `bootstrap()`s at import & hard-imports langchain (extra fragility). → F-8 |
| 2 | Multi-tenant eviction `close()`s a live container | **VP** | `dependency_injection.py:107-118` | Confirmed; branch **untested** (cov 110-114 missing). Worse than documented: `close()` runs **under `_tenant_lock`** and can block on drain. → **H-1** |
| 3 | `requires-python` contradiction | **VP** | `pyproject.toml:6` vs `:18,:69`; `ci.yml:65` | **Observed:** install fails on 3.10, succeeds on 3.11. CI 3.10 matrix broken. → F-3 |
| 4 | Size guards count chars not bytes | **VP (mischaracterised)** | `validate_contract_usecase.py:127,145` | Mechanism confirmed, **but empirically it *over*-counts multibyte** (ensure_ascii=True → ASCII output; 1000 CJK = 6012 "bytes" vs 3012 true). **Not** an undercount/bypass. → F-9 |
| 5 | Stale `TelemetryEvent` "mutable" docstring | **VP** | `domain/models.py:5` (class is `frozen=True`, `:74`) | Module docstring stale; class docstring (`:78`) already correct. → F-10 |
| 6 | `pii_sanitize` uses stdlib `re` | **VP** | `pii_sanitize.py:9,14` | Confirmed. Pattern uses a **backreference** `\1` → RE2 *cannot* compile it; not a trivial swap. Input bounded. → F-11 |
| 7 | CompositeValidator runs semantic on non-dict | **VP** | `domain/validator.py:451-453` | Confirmed latent; harmless (merged result already fails). → F-12 |
| 8 | Dual schema vocabulary implicit | **VP** | `domain/validator.py:333-367` | Confirmed. Live in-repo example: `return_processing.json:9` `minLength:10` silently unenforced by default. → **F-2** |
| 9 | `ValidationTimer` deprecated dead code | **VP (worse)** | `infrastructure/timer.py` | Unwired **and now 0% coverage** — `test_timer.py` was repointed to `BoundedValidationExecutor`, so nothing exercises it. → F-13 |

### Documented coverage gaps (`01_SYSTEM_STATE.md`)

| Item | Status | Evidence |
| --- | --- | --- |
| No dedicated `test_container.py` | **VP** | No such file; container behaviours covered via `test_remediations.py`, `test_tenant_isolation.py`, `test_config_wiring.py`. |
| `for_tenant()` eviction at `_MAX_TENANTS` | **VP** | No test references `_MAX_TENANTS`/129-tenant eviction; cov `110-114` missing. **The one real remaining gap.** |
| `reset_default()` teardown | **VF** | `test_remediations.py:71` `test_reset_default_clears`. |
| `health()` aggregation shape | **VF** | `test_remediations.py:107`; `test_config_wiring.py:114,143`. |
| `evaluate_drift()` `__drift__` event | **VF** | `test_remediations.py:82` `test_evaluate_drift_publishes_telemetry_on_drift`. |
| `bootstrap()` in-event-loop guard | **VF** | `test_remediations.py:123` `test_bootstrap_inside_running_loop_raises`. |

> **Baseline drift:** 4 of 6 documented gaps are **already closed**. The baseline understated existing
> coverage — reconcile the next roadmap against reality, not the 2026-06-14 snapshot.

### Documented "partial" areas

| Area | Status | Note |
| --- | --- | --- |
| Multi-tenant eviction lifecycle | **VP (partial)** | Real; the top correctness bug (H-1). |
| Drift = manual/opt-in library call | **VP (by design)** | `record_drift_sample`/`evaluate_drift` exist; no auto-wiring. Correct for Phase 0. |
| Telemetry hard-coded path, no contract test | **VP (by design)** | `queue_event_bus.py:34` `_TELEMETRY_PATH="/api/v1/telemetry"`; no control plane exists yet. → INFO |

---

## 5. Findings (severity-ranked)

### [HIGH] H-1 — `for_tenant()` eviction closes a possibly-live container, under a global lock
- **Location:** `adapters/dependency_injection.py:107-118` (eviction) + `:346-351` (`close()`).
- **Evidence (observed):** at capacity, eviction runs `oldest_container = pop(oldest_key)` then
  `oldest_container.close()` **inside `with cls._tenant_lock`**. `close()` calls
  `validation_executor.shutdown(wait=False)`, `schema_storage.stop()`, `event_bus.stop(drain=True)`.
  The registry is keyed by **`for_tenant()` lookups, not validation activity** (`:82-88`), and nothing
  refcounts live holders.
- **Impact:** In `multi_tenant` mode with >128 distinct tenants, the LRU tenant is torn down even if a
  request still holds its container. That caller's next validation hits a shut-down pool
  (`RuntimeError: cannot schedule new futures after shutdown`), a stopped sweeper, and a drained bus —
  a hard failure, not graceful degradation. Additionally, `event_bus.stop(drain=True)` can block for
  seconds against a dead control plane (breaker-bounded to ~5 batches × HTTP timeout), and it holds
  the process-wide `_tenant_lock` the whole time, **stalling every other tenant's `for_tenant()`**.
- **Confidence:** observed (code + coverage gap). Failure-injection not run (Execution Mode off).
- **Fix direction:** don't `close()` on eviction while a reference may be live — adopt refcount or
  idle-time eviction; at minimum move `close()` **outside** the lock and defer teardown. Add the
  missing `test_container_tenant_lru.py`.
- **Effort:** M | **Guarantee touched:** 6 (multi-tenant isolation).

### [MEDIUM] F-2 — Silent non-enforcement of `minLength`/`maxLength`/`format` (false safety)
- **Location:** `domain/validator.py:333-367` (`_extract_params`).
- **Evidence (observed):** the rule engine vocabulary is `required`, `type`, `enum`,
  `min|max|minimum|maximum`, `pattern`, `null_forbidden`. There is **no branch** for `minLength`,
  `maxLength`, or `format`. Under default config (`semantic_validation_enabled=False`) those keywords
  are silently ignored. The shipped `return_processing.json:9` (`summary.minLength:10`) is unenforced
  by default.
- **Impact:** an author writes a contract that *looks* enforced and isn't — a validation firewall that
  silently passes. Highest-leverage correctness item for real users.
- **Confidence:** observed. **Fix direction:** at prime/sync time, WARN once per contract naming each
  unenforced keyword while semantic validation is off (recommended over silently enforcing new
  semantics). **Effort:** M | **Guarantee touched:** none directly (correctness/UX).

### [MEDIUM] F-3 — `requires-python` contradiction breaks the advertised 3.10 floor and CI
- **Location:** `pyproject.toml:6` (`>=3.11`) vs `:18` (classifier 3.10), `:69` (`ruff target-version=py310`); `.github/workflows/ci.yml:26,65` (matrix incl. 3.10); `libs/congine-sdk/.claude/CLAUDE.md`.
- **Evidence (observed):** `uv pip install --python 3.10 ./libs/congine-sdk` → exit 1,
  "`depends on Python>=3.11 … cannot be used`"; `--python 3.11` → exit 0.
- **Impact:** anyone on 3.10 (advertised as supported) cannot install. CI's `python-test`/`python-lint`
  3.10 jobs run `uv sync` under 3.10 and must fail there; because `ci-status` gates on those jobs, the
  pipeline is (inferred) red on 3.10 or silently degraded.
- **Confidence:** install behaviour observed; CI-red is inferred (cannot run CI here).
- **Fix direction:** pick **3.11** as the single floor; drop the 3.10 classifier, set `ruff
  target-version=py311`, drop 3.10 from the CI matrix, align CLAUDE.md. **Effort:** S.

### [MEDIUM] F-4 — Semantic-validation path has weaker ReDoS protection than the rule engine
- **Location:** `infrastructure/jsonschema_validator.py:148-168` (`_check_schema_patterns`).
- **Evidence (observed):** the pattern-length guard only inspects **top-level** `schema["properties"][f]["pattern"]`.
  Nested patterns (`items`, `$defs`, `patternProperties`, nested `properties`) are not checked; payload
  **value** length is not capped for the `pattern` keyword; and `jsonschema` matches with **stdlib `re`**
  (`import re`, `:10`), not RE2. The rule engine, by contrast, caps value length (50 000) and uses RE2.
- **Impact:** with `semantic_validation_enabled=True`, a catastrophic regex in a (trusted-authored)
  schema plus an attacker-controlled payload value can cause super-linear backtracking. Bounded by the
  1 MB payload/schema size guards, off by default — but enabling semantic validation *reduces* ReDoS
  protection, contrary to intuition.
- **Confidence:** observed (code). Not exploited here. **Fix direction:** recurse the pattern-length
  check over the whole schema and cap value length before `iter_errors`, or document the residual.
  **Effort:** M | **Guarantee touched:** 5 (ReDoS).

### [MEDIUM] F-5 — `close()` teardown can block on telemetry drain (amplifies H-1)
- **Location:** `infrastructure/queue_event_bus.py:127-141` (`stop`), `182-193` (`_flush_remaining`), `:234-281` (`_ship`).
- **Evidence (observed):** `stop(drain=True)` sets the stop-event then flushes; each queued batch does
  one POST bounded by `control_plane_http_timeout_seconds` (default 10 s). The breaker short-circuits
  after ~5 failures, so worst case ≈ 5 × 10 s before drops become instant. Interruptible backoff
  correctly avoids retry×backoff stalls.
- **Impact:** container shutdown / eviction can pause seconds against a dead plane. Benign in isolation
  but **compounds H-1** because eviction runs `close()` under `_tenant_lock`.
- **Confidence:** observed. **Fix direction:** cap drain attempts on eviction/`close()` (reuse the
  `max_attempts=1` exit-flush path); never drain under a shared lock. **Effort:** S.

### [MEDIUM] F-6 — CI `format-check` hard gate currently fails on the example
- **Location:** `.github/workflows/ci.yml:137-138`; `examples/LangChain/agent.py`.
- **Evidence (observed):** `ruff 0.15.15` (the pinned version) `format --check libs/congine-sdk` exits
  1 on `agent.py`; the `format-check` job runs the identical command and is in the hard `ci-status`
  gate (`:405-414`).
- **Impact:** `main`/PR CI is (inferred) red on formatting, or the example was never run through CI.
- **Confidence:** local format failure observed; CI-red inferred. **Fix direction:** `ruff format` the
  example (folds into F-8). **Effort:** S.

### [MEDIUM] F-7 — Dependency vulnerabilities in the optional `[langchain]` extra
- **Location:** `pyproject.toml:44`; transitive `langchain-core 0.3.86`, `langsmith 0.8.8`.
- **Evidence (observed):** `pip-audit` → `PYSEC-2026-2193`, `PYSEC-2026-2562` (langchain-core),
  `GHSA-f4xh-w4cj-qxq8` (langsmith). The dependency-light **core is clean**.
- **Impact:** consumers installing `[langchain]` pull known-vulnerable transitive deps; the demo env
  is affected. **Fix direction:** bump the `langchain-core` floor to a patched line or document the
  exposure; keep it opt-in. **Effort:** S.

### [MEDIUM] F-8 — LangChain example fails offline & is fragile (baseline debt #1, expanded)
- **Location:** `examples/LangChain/agent.py:75,91` (+ import-time `bootstrap()` `:62`, hard langchain import `:19`).
- **Evidence (observed):** offline fallback returns `action="manual_review"`, absent from the contract
  enum `["approve_return","reject_return","escalate"]` (`return_processing.json:7`); under `mode="raise"`
  the "clean" Scenario 1 raises when `GOOGLE_API_KEY` is unset. The module also `bootstrap()`s at
  import and imports `CongineCallbackHandler` unconditionally (needs `[langchain]`).
- **Impact:** the "first impression" demo crashes for a newcomer running it offline. **Fix direction:**
  return `escalate` (and fix the Pydantic `description`), format the file, consider lazy bootstrap.
  **Effort:** S | **Guarantee touched:** none.

### [LOW] F-9 — Byte-named size budget measured in characters (baseline debt #4, reclassified)
- **Location:** `usecases/validate_contract_usecase.py:127,145`.
- **Evidence (observed, empirical):** `len(json.dumps(payload, default=str))` with the default
  `ensure_ascii=True` produces ASCII, so the measure equals its own byte length **and over-counts
  multibyte** (1000 CJK → 6012 vs 3012 true UTF-8 wire bytes; 500 emoji → 6009 vs 2009). It **never
  undercounts**, so it is a conservative bound, not a bypass.
- **Impact:** cosmetic/semantic only — a large multibyte payload may be rejected slightly early. The
  baseline's "undercount" premise is wrong, and the roadmap's proposed fix
  (`len(json.dumps(payload).encode("utf-8"))`) is a **no-op** on ASCII output.
- **Confidence:** observed (ran it). **Fix direction:** if byte-accuracy is desired, measure
  `len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))` and rename the intent; otherwise
  document that the bound is on escaped-JSON length. **Effort:** S.

### [LOW] F-10 — Stale module docstring calls `TelemetryEvent` "mutable"
- **Location:** `domain/models.py:5` (class is `frozen=True`, `:74`; class docstring `:78` is correct). **Fix:** delete the stale clause. **Effort:** S.

### [LOW] F-11 — `pii_sanitize` uses stdlib `re` (baseline debt #6)
- **Location:** `pii_sanitize.py:9,14`. Pattern `(['\"])(.*?)\1|(\b\d{4,}\b)` uses a **backreference**
  (`\1`) that RE2 does not support, so a straight re2 swap is impossible. Input (breach messages) is
  bounded; worst case is O(n²), not exponential. **Fix direction:** rewrite without the backreference
  (e.g. two anchored alternations) then move to re2, or accept and document. **Effort:** S.

### [LOW] F-12 — CompositeValidator invokes the semantic validator on non-dict payloads
- **Location:** `domain/validator.py:451-453`. `LocalValidator` short-circuits a non-dict to a fail,
  but `CompositeValidator` still calls `semantic_validator.validate(payload, schema)`. Harmless today
  (merged result already fails; jsonschema returns a breach, not an exception). **Fix:** early-return
  if `rule_result` failed on a non-dict. **Effort:** S.

### [LOW] F-13 — `ValidationTimer` is dead code with 0% coverage (baseline debt #9)
- **Location:** `infrastructure/timer.py` (0% coverage, observed). Unwired by the container; `test_timer.py`
  now exercises `BoundedValidationExecutor`, not the timer. **Fix direction:** delete `timer.py` (and
  remove the `DeprecationWarning` shim) or explicitly quarantine with a coverage pragma + a note.
  **Effort:** S | **Guarantee touched:** none.

### [LOW] F-14 — mypy reports 4 errors and is non-gating
- **Location (observed):** `jsonschema_validator.py:108` (`type` has no `check_schema`);
  `dependency_injection.py:172` (`Optional[str]` → `str`), `:335` (`IEventBus` has no `queue_depth`),
  `:350` (`IEventBus` has no `stop`). All runtime-safe. **Fix direction:** add `mypy` to `[dev]`, make
  it gating, and resolve (F-15 fixes two). **Effort:** S–M.

### [LOW] F-15 — `IEventBus` port omits the lifecycle/observability surface the container needs
- **Location:** `ports/event_bus.py:24` (only `publish`) vs `dependency_injection.py:335,350`
  (`queue_depth`/`dropped_total`/`stop`). A conformant third-party bus would break `health()`/`close()`.
  **Fix direction:** declare the full surface on the Protocol (or split a `ILifecycle`/`IObservableBus`).
  **Effort:** S.

### [LOW] F-16 — bandit findings are all benign (documented to avoid re-triage)
- **B104** `config.py:31` — `"0.0.0.0"` flagged as "bind all interfaces"; it is a **loopback-exemption
  list entry**, not a socket bind — false positive. (Minor design note: `is_local_base_url()` treats
  `http://0.0.0.0` as local/HTTPS-exempt.) **B101** `sync_contracts_usecase.py:159-160` — asserts are
  redundant guards already enforced at `:120`; safe even under `python -O`. **Fix direction:** add a
  bandit config with these as documented allowances if bandit is adopted. **Effort:** S.

### [LOW] F-17 — `region` is a dead-configurable
- **Location:** `config.py` (field `:73`, parsed `:155,181`); **no `.region` read anywhere in `src/`**
  (observed grep). Parsed but never threaded to behaviour. **Fix:** consume it (region→base_url map) or
  document it as informational. **Effort:** S.

### [LOW] F-18 — Snapshot load has a residual TOCTOU window
- **Location:** `http_contract_repository.py:151-157`. `os.path.islink` / owner checks are done by path,
  then `open(path)` re-resolves the path — a swap between check and open is possible. Mitigated by the
  per-user `0700` app-owned snapshot dir (`:184-187`), so real exploitability is low. **Fix direction:**
  `open` first (O_NOFOLLOW on POSIX) then `fstat` the fd. **Effort:** M | **Guarantee touched:** 4.

### [LOW] F-19 — HTTP response cap is enforced after the body is fully read
- **Location:** `http_contract_repository.py:121-125`. `len(response.content) > max_bytes` checks *after*
  httpx has buffered the whole body, so `max_http_response_bytes` rejects but does not prevent a memory
  spike from a hostile/compromised control plane. **Fix direction:** stream with a byte limit. **Effort:** M.

### [INFO] F-20 — Design/observational notes
- `_DEFAULT_SAFE_FIELDS` (`logger.py:27-29`) is **defined but never referenced** — dead constant (the
  active allowlist comes from `config.effective_log_safe_fields()`). Harmless; delete for clarity.
- `_TELEMETRY_PATH` (`queue_event_bus.py:34`) is hard-coded — acceptable for Phase 0 (no control plane),
  but there is no config knob or contract test. Revisit before the plane exists.
- Tier-2 aliases `ValidationTimeoutException`/`TenantIsolationViolationException` both **alias
  `CongineValidationError`** (`exceptions.py:64-65`) — a host cannot distinguish a timeout by type. By
  design (nothing raises them); fine for Phase 0.
- Circuit-breaker probe can leak `_probe_in_flight=True` if a non-`CongineSyncError` escapes the fetch
  (leaving HALF_OPEN stuck) — the repository contract only raises `CongineSyncError`, so latent only.

---

## 6. Guarantee Verification

| # | Guarantee | Verdict | Evidence / test backing |
| --- | --- | --- | --- |
| 1 | Bounded latency / load shedding | **HOLDS** | `bounded_executor.py:59-64,161-180` — `BoundedSemaphore(workers+pending)`, non-blocking acquire→shed, permit released only on future completion (zombies keep capacity); sync+async share `_acquire_and_submit`. Tests: `test_bounded_executor.py` (10). |
| 2 | No control-plane stall on boot | **HOLDS** | `sync_contracts_usecase.py:182-195` + `circuit_breaker.py`. Test `test_remediations.py:201` asserts `<500ms` with a 10 s slow fetch + OPEN breaker. Strong. |
| 3 | No thundering herd | **HOLDS** | `sync_contracts_usecase.py:105-135,156-181` — jitter + non-blocking `portalocker` boot lock. Tests: `test_single_flight_boot.py` (3). |
| 4 | Snapshot integrity | **HOLDS*** | `http_contract_repository.py:142-207` — atomic temp+`os.replace`, advisory lock, symlink/owner refusal, envelope validation. *Residual TOCTOU (F-18); the symlink test `test_remediations.py:183` is **skipped on Windows** — POSIX-only verified here. |
| 5 | No ReDoS | **HOLDS*** | `domain/validator.py:248-290` (RE2 + length caps). Tests: `test_redos.py` (5). *Semantic path is weaker (F-4) when enabled. |
| 6 | Multi-tenant isolation | **AT RISK** | `get_default()` disabled in multi-tenant (`dependency_injection.py:60-65`), scoped snapshots (`http_contract_repository.py:53-58`) — both verified & tested (`test_tenant_isolation.py`). **But eviction can close a live container (H-1) and that path is untested.** |
| 7 | PII-safe telemetry | **HOLDS** | Breach messages sanitized at source (`validate_contract_usecase.py:220`); logger unconditional blocklist + non-local allowlist (`logger.py:31-40,75-87`; `config.py:297-318`). Tests: `test_pii_sanitization.py` (3). |

**Determinism moat:** the validation hot path (`guard → execute → validator.validate`) is pure
in-process code (RE2 + optional jsonschema); **no LLM, no network, no nondeterminism** (observed). The
only network/randomness lives in boot/sync/telemetry, off the hot path. **INTACT.**

---

## 7. Unverified / Open Questions

1. **CI actual state on Python 3.10** — mechanically the 3.10 matrix jobs cannot `uv sync`
   (`requires-python>=3.11`), so `ci-status` should be red; I cannot run GitHub Actions here to confirm
   whether `main` is currently passing, skipped, or the matrix is being ignored. *(inferred)*
2. **Snapshot symlink/owner defence on Windows** — the only test is POSIX-gated (`test_remediations.py:183`
   skipped here). The Windows path (`_owned_by_current_user` returns `True` unconditionally, `:248-249`)
   is unverified by test. Needs a Windows-appropriate assertion.
3. **F-6 / F-8 CI-red vs ruff drift** — the `agent.py` format failure is deterministic on ruff 0.15.15
   locally; whether CI last ran with an identical formatter build (so the example was ever green) is
   unverified.
4. **Eviction failure-mode** — H-1 is established by code + coverage, but I did not run a 129-tenant
   use-after-`close()` reproduction (Execution Mode is off). The roadmap's acceptance test should prove it.
5. **`for_tenant()` with an explicit `config=`** does not set `deployment_mode=MULTI_TENANT` (only the
   auto branch does, `:96`) — intended or oversight? Minor; flagged for a human decision.
