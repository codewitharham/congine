# Congine SDK (AMCE / Phase 0) — Independent Zero-Knowledge Engineering & Security Audit

**Auditor stance:** Adversarial Principal Systems Architect + Vulnerability Engineer.
**Mandate:** Fresh, line-by-line re-read of _every_ file. No reliance on prior reports.
**Verification basis:** All 29 `src` modules + 21 test modules + `pyproject.toml` + `project.json` + `*.egg-info` read this pass. Static parse on the resident interpreter (**CPython 3.14.2**), `python -m pytest` executed.
**Raw test result (this pass):** `201 passed, 2 skipped` — **but see Diagnostic D-1: the suite only _collects_ on Python 3.14.**

---

## 1. STANDALONE PRODUCTION VERDICT

| Vector                            | Score (1–5) | Verdict                                                                                                                                       |
| --------------------------------- | ----------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| Micro-architecture / layering     | **3.5**     | Clean hexagon; one real port omission (validation runner has no L1 seam) + a misleading concrete type hint.                                   |
| Concurrency & async safety        | **4.0**     | Sync + async now share one bounded, load-shedding, timed pool. Re-entrancy handled. No in-process deadlock/race found.                        |
| Portability / syntax floor        | **2.0**     | Declares `>=3.10` but a **test module uses Python-3.14-only syntax**, so the suite cannot even collect on 3.10–3.13. Claim is unproven/false. |
| Security / multi-tenant isolation | **3.5**     | Strong snapshot scoping + symlink/owner + cross-process lock. Weakened by warn-only HTTPS and no log-redaction contract.                      |
| Packaging & hygiene               | **2.0**     | Runtime deps cleaned, but the nx `test` target is broken, the committed `*.egg-info` is stale, and there is **no LICENSE**.                   |
| Test robustness                   | **3.5**     | 201 tests + adversarial suites (ReDoS, executor, remediations). Single-interpreter only; the floor is untested.                               |

### One-sentence justification

**Not safe to ship to enterprise or open-source today:** the codebase advertises a Python 3.10 floor it provably does not satisfy (a 3.14-only `except` tuple in `tests/adversarial/test_remediations.py:189`), ships with no LICENSE, a broken CI/test invocation, and no network circuit breaker — all blocking despite a genuinely solid validation core.

---

## 2. CORE ARCHITECTURAL FLOW ANATOMY

### 2.1 The real validation lifecycle (traced to bare metal)

**Entry — decoration (`adapters/guard.py`).** `@congine_guard(contract_id, version, container=None, mode, extractor)` validates `mode∈{envelope,output,raise}` at decoration (`guard.py:55`), then returns a sync or async wrapper chosen by `inspect.iscoroutinefunction` (`guard.py:99`). Container is resolved **lazily at call time** via `_resolve()` → `ServiceContainer.get_default()` (`guard.py:55-57`) — no per-decoration container, no import-time threads.

**Sync path (`guard.sync_wrapper` → `ValidateContractUseCase.execute`, `usecases/validate_contract_usecase.py:65`):**

```
fn() → execute(payload, cid, ver)
  ├─ _resolve_schema: schema_storage.get(cid)            [miss → CongineContractNotFoundError]   :150
  ├─ timer.run_with_timeout(do_validate, timeout_ms)                                              :73
  │     └─ BoundedValidationExecutor._acquire_and_submit  (bounded_executor.py:143)
  │           ├─ _sem.acquire(blocking=False)  → False ⇒ rejected_total++ ; raise TimeoutError    :153
  │           └─ thread_pool.submit(func) ; future.result(timeout)                                 :97
  ├─ Timeout/Exception ⇒ _degraded_on_timeout / _degraded_on_error (status=fail, degraded=True)   :77 / :116
  ├─ _finalize: event_bus.publish(TelemetryEvent)  [BEFORE fail-mode]                              :199
  └─ fail-mode: STRICT→raise CongineValidationError / DEGRADE→warn / SILENT→swallow                :150
```

**Async path (`guard.async_wrapper` → `execute_async`, `validate_contract_usecase.py:75`):**

```
await fn() → await execute_async(payload, cid, ver)
  ├─ _resolve_schema (same)
  ├─ run_async = getattr(self.timer, "run_with_timeout_async", None)                               :104
  │     └─ await BoundedValidationExecutor.run_with_timeout_async(do_validate, timeout_ms)   (bounded_executor.py:103)
  │           ├─ same _acquire_and_submit / same BoundedSemaphore permit
  │           └─ await asyncio.wait_for(asyncio.wrap_future(future), timeout)                       :134
  ├─ degraded helpers (same) ; _finalize (same telemetry + fail-mode)
```

The async and sync paths now converge on `_acquire_and_submit` (`bounded_executor.py:143`) and `_finalize` (`validate_contract_usecase.py:185`) — **identical capacity bound, timeout, telemetry, and fail-mode**. This is correct and is the system's strongest property.

**Schema supply (control path, off the hot path):** `SyncContractsUseCase.sync_once[_async]` → `HttpContractRepository.fetch_active_contracts` (HTTP GET, 10 s, tenant headers) → on `CongineSyncError` falls back to `load_snapshot` (symlink-refused/owner-checked/envelope-validated, `http_contract_repository.py:120-132`) → `_prime_cache` does per-key `LFUCache.put` (in-place, coherent for concurrent `get`) → `save_snapshot` under a `portalocker` advisory lock (`http_contract_repository.py:162`).

**Cache (`infrastructure/lfu_cache.py`):** O(1) LFU (Ketan-Shah buckets) under one `RLock`; lazy TTL expiry on read + a daemon sweeper; `_min_freq` reconciled lazily in `_evict_lfu` (`lfu_cache.py:177`). Thread-safe.

**Telemetry (`infrastructure/queue_event_bus.py`):** `publish` = non-blocking `put_nowait`, dropped on a full 10k queue (`queue_event_bus.py:96`); daemon batches ≤100 and POSTs with exponential backoff over a reused client; `atexit` flush bounded to 1 attempt (`:155`).

### 2.2 Theory-vs-implementation mismatches

1. **`ARCHITECTURE.md:48` claims a linear-time `re2` engine "when installed."** `re2` is **not** a declared extra in `pyproject.toml` (only `langchain`, `stats`, `dev`). In every realistic install the `re.compile` backtracking engine is used (`domain/validator.py:46-51`); the catastrophic-backtracking test is `skipif` and effectively never runs (`tests/adversarial/test_redos.py:46`). The guarantee is length-cap-only, not engine-immune.
2. **`ValidationTimer` is the documented timer collaborator but is dead.** `validate_contract_usecase.py:27,39` type-hints `timer: "ValidationTimer"`, yet the container injects a **different** concrete — `BoundedValidationExecutor` (`dependency_injection.py:96,130`). `ValidationTimer` (`infrastructure/timer.py`) is never instantiated in `src` and is the _unbounded_ implementation the architecture set out to replace — yet it is still exported (`infrastructure/__init__.py:16,23`; `congine_core/__init__.py`).
3. **No port for the validation runner.** Every other cross-layer collaborator has an L1 Protocol; the timeout/pool runner does not. L3 depends directly on an L4 concrete name (mismatch #2). See Diagnostic D-4.

---

## 3. DEEP DIAGNOSTIC BREAKDOWN (FILE & LINE EVIDENCE)

### 🔴 D-1 — Python-3.14-only syntax in the test suite breaks the declared 3.10 floor

**`tests/adversarial/test_remediations.py:189`**

```python
except OSError, NotImplementedError, AttributeError:
```

This is an **unparenthesized exception tuple (PEP 758, CPython 3.14+ only)**. On Python 3.10–3.13 this is a hard **`SyntaxError`** at import → pytest aborts collection of the module → `nx test` fails the run. `pyproject.toml:4` declares `requires-python = ">=3.10"`, so the project **does not run on its own stated floor.** (The earlier Sprint-1 sweep fixed the two `src/` occurrences but did not grep `tests/` — this one survived.)
**Fix:** `except (OSError, NotImplementedError, AttributeError):`.

### 🔴 D-2 — `nx test` target cannot resolve `pytest` (dependency-group mismatch)

**`project.json:20`**

```
uv run --package congine-sdk --extra langchain --extra stats pytest libs/congine-sdk/tests
```

`pytest`/`pytest-asyncio`/`pytest-cov`/`ruff` now live in `[project.optional-dependencies].dev` (`pyproject.toml:19-24`). The nx command requests `--extra langchain --extra stats` but **not** `--extra dev`, so on a clean `uv` sync the test runner itself is absent → `nx test` breaks. (It "passes" locally only because the ambient venv already has pytest 9.0.3.)
**Fix:** add `--extra dev`, **or** (preferred for uv) move the toolchain into a native `[dependency-groups] dev = [...]` block, which `uv run` installs by default, and drop `[project.optional-dependencies].dev`.

### 🔴 D-3 — No LICENSE / no real README (open-source + enterprise blocker)

`ls` shows **no** `LICENSE`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md`. `README.md` is a single line. Legal review at any enterprise blocks ingestion of unlicensed code; a one-line README makes the SDK unusable by a newcomer.

### 🟠 D-4 — L3→L4 coupling: the validation runner has no L1 port and a wrong type hint

**`usecases/validate_contract_usecase.py:26-27,39`**

```python
if TYPE_CHECKING:
    from congine_core.infrastructure.timer import ValidationTimer   # L4 concrete
...
    timer: "ValidationTimer",
```

The use case (L3) names an L4 concrete in its contract, and the **actually injected object is a third type** (`BoundedValidationExecutor`). `execute_async` even has to `getattr(self.timer, "run_with_timeout_async", None)` (`:104`) to discover the method, because no interface guarantees it. **Define `IValidationRunner(Protocol)` in `repositories/` with `run_with_timeout` + `run_with_timeout_async`; type L3 against it.** This is the one genuine Ports-&-Adapters violation in the codebase.

### 🟠 D-5 — No circuit breaker on the network boundary; boot blocks on a dead registry

There is **no CLOSED/OPEN/HALF-OPEN breaker** anywhere (verified by grep). `ServiceContainer.bootstrap` runs `sync_once()` **synchronously and inline** (`dependency_injection.py:185`), and `sync_once` drives `asyncio.run(fetch_active_contracts())` with a **10 s** client timeout (`http_contract_repository.py:89`). A cold/hung control plane therefore **stalls application boot up to 10 s per attempt** with no fast-fail; a flapping plane burns the full timeout on every background pass and ~7.5 s of backoff per failing telemetry batch (`queue_event_bus.py:210-240`).

### 🟠 D-6 — Cleartext control plane is a warning, not a block

**`config.py:187` / `dependency_injection.py:86-93`.** For a non-local `base_url`, HTTPS is enforced **only** when `require_https=True` (default `False`, `config.py:107`). Otherwise the API key + telemetry ship over HTTP with a log line. For a credential-bearing SDK the secure default should be inverted: **default `require_https=True` for non-local planes**, opt-out explicitly.

### 🟠 D-7 — Per-process cache ⇒ boot-time thundering herd

Each worker process builds its own `ServiceContainer` → own in-memory `LFUCache`. Under Gunicorn/Uvicorn with N workers, every worker independently fetches the full contract set on boot — an **N× synchronized burst** on the registry at each deploy. The Sprint-1 `portalocker` lock makes concurrent snapshot _writes_ safe but does **not** coordinate the fetch. Add single-flight boot (first worker fetches+writes snapshot under the lock; the rest load the fresh snapshot) or jittered boot.

### 🟡 D-8 — 15 ms default validation timeout is too tight for semantic validation

**`config.py:85,145`** `validation_timeout_ms=15`. Rule-engine validation is microseconds, but `CompositeValidator` + `jsonschema` `iter_errors` over a large schema/payload can exceed 15 ms, yielding spurious `degraded`/timeout results — and under `FailMode.STRICT` a timeout becomes a **hard raise to the caller** (`validate_contract_usecase.py:150` → `_handle_failure`). Raise the default to ~50–100 ms (the test fixtures already use 50/200 ms — `conftest.py:151`, `test_end_to_end.py:32`).

### 🟡 D-9 — Stale build metadata committed

**`src/congine_sdk.egg-info/requires.txt`** still lists `pydantic>=2.13.4`, `pytest>=9.0.3`, `ruff>=0.15.15` as **runtime** requires — the pre-Sprint-1 dependency set. `*.egg-info` is a generated artifact and should be `.gitignore`d; a wheel/sdist built without regenerating it would re-introduce the bloated/removed deps. Remove from VCS.

### 🟡 D-10 — Observability & feature-gating gaps

- **Silent telemetry loss:** queue-full drops (`queue_event_bus.py:96`) increment no counter; `health()` (`dependency_injection.py:247`) exposes `telemetry_queue_depth` but no `dropped_total`. Under sustained load you lose events blind.
- **Drift is numpy-gated but the call raises:** `KSDriftEngine.detect` (`ks_drift.py:111`) `_require_numpy()`-raises `ImportError` if `[stats]` absent, and `ServiceContainer.evaluate_drift` (`dependency_injection.py:212`) calls it directly — a host that calls drift without the extra crashes. Guard or document.
- **Async timeout log-noise (low confidence):** `asyncio.wait_for` cancelling `wrap_future(future)` (`bounded_executor.py:134`) while the underlying thread keeps running can surface "exception was never retrieved" noise if the zombie later raises; benign but worth a watch under timeout storms.

### 🟡 D-11 — Naming / API-surface debt before publish

- `repositories/` (L1) holds non-repository ports `ILogger`, `IEventBus` (`repositories/logger.py`, `repositories/event_bus.py`) — the package name misrepresents the layer. Rename to `ports/` before the API ossifies.
- `__version__ = "0.1.0"` is duplicated in `congine_core/__init__.py` and `pyproject.toml:3` — single-source it.
- Dead `ValidationTimer` exported (D-4); remove from public surface.

### ✅ Verified-sound (no action)

- **C1 container leak:** lazy double-checked singleton; import is side-effect-free (`dependency_injection.py:45-61`).
- **Cache concurrency:** single `RLock`, O(1), lazy + sweeper TTL; no race found (`lfu_cache.py`).
- **Executor:** bounded semaphore, permit held until genuine completion, re-entrancy inline-run, RuntimeError-on-shutdown handled (`bounded_executor.py:143-167`). No deadlock/double-release.
- **Snapshot poisoning:** symlink refusal + owner check + envelope validation + atomic replace + advisory lock (`http_contract_repository.py:120-176`).
- **ReDoS:** fail-closed pattern/value length caps + LRU-cached compile (`validator.py:243-285`).
- **Telemetry-before-raise ordering:** event published before STRICT escalation (`validate_contract_usecase.py:199` then `:150`) — verified by `test_strict_mode_raises_end_to_end`.

---

## 4. DEPENDENCY & HYGIENE SCRUTINY

**Runtime deps (`pyproject.toml:5-8`):** `httpx>=0.28`, `jsonschema>=4.23`, `portalocker>=2.8` — lean and correct for the feature set. `pydantic` correctly removed (it was never imported).

**Findings:**

- **`requires-python = ">=3.10"` is aspirational, not real** — contradicted by D-1. Either fix D-1 and add a CI matrix proving 3.10, or raise the floor honestly.
- **Dev toolchain placement is fragile** — `[project.optional-dependencies].dev` is not auto-installed by `uv run`; the nx target doesn't request it (D-2). Prefer `[dependency-groups]`.
- **`re2` claim undeclared** — either add `redos = ["google-re2"]` extra or strike the claim in `ARCHITECTURE.md:48`.
- **Stale `*.egg-info` in VCS** (D-9) — gitignore + remove.
- **`stats`/`langchain` extras** are clean and lazily imported (`ks_drift.py:31`, `langchain_handler.py:25`) — good.
- **Pinned floors** (`pytest>=8.0`, `httpx>=0.28`, etc.) are reasonable; no upper-bound caps except langchain (`<0.4`) which is appropriate for a 0.x optional dep.

---

## 5. PHASE 1 ACTION PLAN

### P0 — Critical Blockers (crashes, portability, license, network holes)

1. **Fix D-1:** parenthesize `except (OSError, NotImplementedError, AttributeError):` (`test_remediations.py:189`). _(5 min)_
2. **Fix D-2:** add `--extra dev` to `project.json:20` **or** migrate the toolchain to `[dependency-groups]`. _(15 min)_
3. **Add `LICENSE`** (Apache-2.0/MIT) + a real `README` (install, quickstart, config table, layering diagram). _(0.5 d)_
4. **Add a CI version matrix (3.10–3.14)** + ruff + a type-check gate — without it, P0-1 will silently regress and the floor stays unproven. _(0.5 d)_
5. **Circuit breaker (D-5):** CLOSED/OPEN/HALF-OPEN around `fetch_active_contracts` + telemetry ship; make `bootstrap()` non-blocking or breaker-guarded so a dead plane can't stall boot. _(1 d)_

### P1 — Architectural Cleanups (debt, interface refinement)

6. **D-4:** introduce `IValidationRunner` (L1) with `run_with_timeout` + `run_with_timeout_async`; type `ValidateContractUseCase` against it; drop the `getattr` shim. _(0.5 d)_
7. **D-3/secure-default:** default `require_https=True` for non-local planes (D-6). _(30 min)_
8. **D-7:** single-flight / jittered boot to remove the N-worker registry herd. _(0.5 d)_
9. **D-8:** raise default `validation_timeout_ms` to ~50–100 ms (or make it semantic-aware). _(30 min)_
10. **Hygiene:** remove dead `ValidationTimer` export; rename `repositories/`→`ports/`; single-source `__version__`; gitignore + drop `*.egg-info` (D-9, D-11). _(0.5 d)_
11. **Observability:** add `dropped_total` to the bus + `health()`; guard/doc the numpy-gated drift path (D-10). _(0.5 d)_

### P2 — Feature Extensions (local-first, failover, BYOM)

12. **`FileContractRepository(IContractRepository)`** reading a local `./contracts/` dir + `config.contracts_dir` / `mode=local` — enables GitOps/local-first with zero domain change (the port already exists). _(1 d)_
13. **BYOM blueprint:** `IModelClient` (L1) + `OllamaClient` / `OpenAI-compatible` adapters (L4) + `HealContractUseCase` (L3) implementing validate→heal→re-validate, composed like `CompositeValidator`. _(2–3 d)_
14. **Resilience polish:** declare a `redos = ["google-re2"]` extra and wire it (makes the linear-time claim true); persisted breaker state for fast cold-boot fail-fast. _(0.5 d)_

---

### Auditor's note on independence

This was a fresh re-read; findings are evidence-cited and reproducible. Full disclosure: items D-2 (nx dev-extra) and the surviving D-1 (tests/ comma-except) are **regressions/omissions from the prior Sprint-1 dependency move and `src`-only grep** — surfaced here precisely because this pass treated the tree as unknown and grepped `src/` **and** `tests/`. The validation core is strong; the blockers are portability, packaging, licensing, and the missing network breaker — none requiring a rewrite.

_Reproduce: `grep -rn "except [A-Za-z]A-Za-z0-9_.]\_, " src/ tests/`→ 1 hit (test_remediations.py:189);`grep -n extra project.json`→ no`dev`; `grep -rin breaker src/`→ none;`grep -rn "ValidationTimer(" src/`→ none;`ls | grep -i license`→ none;`python -m pytest` → 201 passed on 3.14.\*
