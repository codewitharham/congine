# Phase 0 Final Readiness & Gap Analysis Report
### Congine SDK (AMCE Architecture) — Adversarial Principal-Architect Review

**Scope:** `libs/congine-sdk/` → `src/congine_core/` (29 source modules, 21 test modules)
**Method:** Line-by-line directory scan + static parse + runtime test execution.
**Test state at audit:** `197 passed, 2 skipped` on the installed interpreter (**CPython 3.14.2 only**).
**Reviewer stance:** Adversarial. Findings are stated bluntly with file:line evidence and concurrency/portability arguments.

---

## 1. EXECUTIVE SUMMARY & STANDALONE VERDICT

The codebase is **genuinely well-engineered at the micro level** — clean hexagonal layering, constructor DI with zero globals (except one deliberate, locked singleton), an O(1) LFU cache, atomic snapshotting, length-capped ReDoS guards, and a real bounded/load-shedding executor. Whoever wrote this understood the failure modes. The audit-comment trail (`H1`, `H2`, `C2`, `M3`…) shows the seams were *named*. The problem is that several of them are **named but not actually closed**, and the packaging is **fundamentally un-shippable** as an open-source artifact today.

### Blunt scorecard (1 = broken, 5 = bulletproof)

| Dimension | Score | One-line justification |
|---|---|---|
| **Production Architecture** | **3 / 5** | Textbook hexagonal layering, but pinned to a Python floor no production shop runs, plus dead/legacy code paths still exported. |
| **Concurrency / Async Safety** | **2 / 5** | Sync hot path is correctly bounded & timed. **The async path bypasses the bounded executor AND the timeout entirely** — the headline guarantee is false for `async` callers. |
| **Security / Multi-tenant Isolation** | **3 / 5** | Snapshot scoping (hash of base_url|project|tenant), symlink/owner refusal and atomic writes are real and good. But there is **no inter-process file lock**, **no circuit breaker**, and HTTPS is only a warning. |
| **Developer Experience (DX)** | **2 / 5** | One-line README, **no LICENSE**, test/lint tools shipped as *runtime* deps, `>=3.14` floor, BYOM/local-first story entirely absent. |
| **Test Robustness** | **3 / 5** | 197 green tests + a dedicated adversarial suite is above average for Phase 0, but everything is validated on a **single, bleeding-edge interpreter**; no version matrix, and the async-bypass defect has **no covering test**. |

### Final Verdict: **NO — not ready to open-source to Google / Meta / Apple today.**

Three independent show-stoppers, any one of which fails a first-pass review by a senior engineer at those companies:

1. **It will not import on their machines.** `requires-python = ">=3.14"` (pyproject.toml:4) plus two **PEP 758 unparenthesized `except A, B:` clauses** (valid *only* on CPython 3.14+). On Python 3.9–3.13 — i.e. essentially all of production industry — `http_contract_repository.py` and `langchain_handler.py` raise `SyntaxError` at import. The package is dead-on-arrival outside this one dev box.
2. **The flagship async guarantee is unmet.** The async guard does not flow through `BoundedValidationExecutor.run_with_timeout`; it submits straight to the raw pool's unbounded queue and then runs validation *inline* with the timeout disabled (§3 H1/H2). The README's "bounded queue + load shedding + no event-loop stalls" claim is only half true.
3. **It is not a distributable open-source project.** No `LICENSE`, no `CONTRIBUTING`, no `SECURITY.md`, a stub `README.md`, `pytest`/`ruff`/`pytest-cov` as install-time dependencies, and a declared-but-unused `pydantic`. Legal/secops at a FAANG will reject on the missing license alone.

This is **~1 focused sprint** away from a credible launch, not a rewrite. The core is sound.

---

## 2. COMPONENT INVENTORY & VERIFICATION (L0 → L5 HEXAGONAL SCHEME)

| Layer | Directory | Modules actually built | Verdict |
|---|---|---|---|
| **L0 Shared** | `(root)` | `config.py` (frozen dataclass + `from_env` + policy validation), `exceptions.py` (6 canonical + 4 aliases) | ✅ Complete, dependency-free as designed. |
| **L1 Protocols** | `repositories/` | `ISchemaStorage`, `IContractRepository`, `IEventBus`, `ILogger`, `ISemanticValidator` — all `@runtime_checkable Protocol`, all import-light (`TYPE_CHECKING` for L2 refs) | ✅ Clean ports. ⚠️ Directory **named `repositories/` but holds non-repository ports** (`ILogger`, `IEventBus`). Misnomer vs. ARCHITECTURE.md's "L1 protocols". |
| **L2 Domain** | `domain/` | `models.py` (BreachDetail, ValidationResult, DriftResult, TelemetryEvent), `validator.py` (RuleEngine ×6 rules, `IValidator`, LocalValidator, CompositeValidator) | ✅ Pure, no I/O. `IValidator` co-located with impl — the **sanctioned** exception per ARCHITECTURE.md §2. Rule placement correct. |
| **L3 Usecases** | `usecases/` | `validate_contract_usecase.py`, `sync_contracts_usecase.py` | ✅ Stateless orchestration, L1-only deps, `ValidationTimer` typed under `TYPE_CHECKING`. |
| **L4 Infra** | `infrastructure/` | `lfu_cache`, `http_contract_repository`, `queue_event_bus`, `logger`, `timer`, `bounded_executor`, `background_sync`, `ks_drift`, `jsonschema_validator` | ✅ Rich. ⚠️ **`timer.py` (`ValidationTimer`) is now dead code** — the container wires `BoundedValidationExecutor` as the timer (`dependency_injection.py:96,130`); `ValidationTimer` is never instantiated yet is still re-exported from `congine_core/__init__.py:40,87`. |
| **L5 Adapters** | `adapters/` | `dependency_injection.py` (ServiceContainer composition root), `guard.py` (`@congine_guard`), `langchain_handler.py` (optional) | ✅ Composition root is global-free except the intentional double-checked-locked `get_default()` singleton. |

**Protocol-placement rule (ARCHITECTURE.md M6):** *Followed.* Every cross-boundary port lives in L1; the only in-domain interface is `IValidator`, which is the explicitly sanctioned exception. No inner layer imports an outer concrete (verified: L2/L3 import only from L1/L0; L4 concretes referenced only in L5 `dependency_injection.py`).

**Structural discrepancies found:**
- **Naming:** `repositories/` ≠ "protocols". Either rename to `ports/`/`protocols/` or document the widened meaning. ARCHITECTURE.md itself calls it "L1 repositories/ typing.Protocol seams", so at minimum align the prose.
- **Dead export:** `ValidationTimer` (L4) — remove or re-route, otherwise consumers will build it and silently get an *unbounded, non-load-shedding* timer (the exact thing `BoundedValidationExecutor` was written to replace).
- **README/ARCHITECTURE drift:** ARCHITECTURE.md:48 claims re2 is used "when installed" — it is **not even an optional extra** in pyproject.toml (only `langchain` and `stats`), so the linear-time engine can never be `pip`-resolved by a consumer.

---

## 3. CRITICAL & HIGH SEVERITY SEAMS DETECTED (AUDIT TARGETS)

### C1 (Resource Leaks) — **RESOLVED. ✅**
`@congine_guard` does **not** build a container per decoration. `guard.py:58-59` resolves lazily at *call* time:
```python
def _resolve() -> ServiceContainer:
    return container if container is not None else ServiceContainer.get_default()
```
and `get_default()` (`dependency_injection.py:45-61`) is a double-checked-locked process-wide singleton. Decoration is side-effect-free; import of the module spawns **zero** threads, atexit handlers, or caches. One shared cache / telemetry worker / validation pool backs every default guard. **This seam is genuinely closed.** Minor note: the singleton is never auto-`close()`d (only `reset_default()` / GC); acceptable for a process-lifetime object, but document it.

### C2 (Data Isolation & Integrity) — **PARTIALLY RESOLVED. ⚠️**
**Scoping: correct.** `_scope_key()` (`http_contract_repository.py:44-49`) hashes exactly `base_url|project_id|tenant_id` → 16-hex filename component, under a **per-user, app-owned** dir (`%LOCALAPPDATA%` / `$XDG_CACHE_HOME`), never world-shared `/tmp`. Load refuses symlinks and non-owner files (`:110-114`), validates the envelope (`:165-173`), and writes are crash-atomic (`mkstemp` same-dir + `os.replace`, `:141-145`). This defeats the predictable-`/tmp/congine_snapshot.json` poisoning class. **Good work.**

**Locking: MISSING. This is the C2 gap.** There is **no `fcntl` / `portalocker` / advisory lock anywhere** (grep confirms zero hits). Under Gunicorn/Uvicorn with N worker processes:
- Each worker has its **own** `ServiceContainer` → own in-memory cache → each independently hits the control plane on boot. That is an **N× thundering-herd** on the registry at every deploy/restart, with no coordination.
- All N workers write the *same* scoped snapshot path concurrently. On POSIX `os.replace` is atomic so you get last-writer-wins with no torn file — *tolerable*. On **Windows, `os.replace` raises `PermissionError`/`OSError` if any other worker has the destination open** for read at that instant; `save_snapshot` (`:122-149`) only guards the temp-file cleanup, so the raise propagates into `SyncContractsUseCase._apply` → caught only as `OSError` at `sync_contracts_usecase.py:97` (so it logs and survives) — but the snapshot silently fails to persist under contention, degrading the offline guarantee precisely when load is highest.
- **Verdict:** No corruption on POSIX, but **no inter-process coordination**, herd amplification, and a Windows write-failure window. A real launch needs an advisory lock (`portalocker`) around `save_snapshot`, and ideally a shared on-disk cache or a single-flight boot.

### H1 (Thread-Pool Exhaustion) — **RESOLVED on sync, OPEN on async. ❌ (for async)**
Sync path is correct: `ValidateContractUseCase.execute` → `BoundedValidationExecutor.run_with_timeout` acquires a `BoundedSemaphore(max_workers+max_pending)` **non-blocking** and sheds load (`bounded_executor.py:94-97`) instead of unbounded-queueing. Permit held until the future *genuinely* completes (`:107`), so zombies correctly drain capacity. Mathematically: outstanding work ≤ `capacity`; the `(N+1)`-th concurrent submission raises `TimeoutError` immediately. ✅

**But the async guard never enters this path.** `guard.py:93-101`:
```python
loop = asyncio.get_running_loop()
validation_result = await loop.run_in_executor(
    ctx.validation_executor.thread_pool,          # ← raw pool, NOT run_with_timeout
    lambda: ctx.validate_contract_usecase.execute(...),
)
```
`run_in_executor` calls `ThreadPoolExecutor.submit`, whose work queue is an **unbounded `SimpleQueue`**. The `BoundedSemaphore` is **never acquired** on the async path. Then, inside `execute`, the call to `self.timer.run_with_timeout(...)` runs **on a pool worker thread**, so the re-entrancy guard fires (`bounded_executor.py:91-92`):
```python
if self._on_worker_thread():
    return func()          # ← runs INLINE: no semaphore, no timeout
```
**Consequences for async callers (the LLM-serving common case):**
- **No load shedding.** 10k concurrent `await guarded()` calls enqueue 10k lambdas; only `max_workers` run at once, the rest pile up unbounded in the pool queue → memory growth + latency blow-out. The sub-200 ms hot-path guarantee is **violated under exactly the burst it was meant to survive.**
- **No timeout.** `validation_timeout_ms` (default **15 ms**) is silently ignored for async. A pathological/slow schema (or a `re` backtrack the length-cap didn't catch) runs to completion, occupying a worker indefinitely.
- **No covering test.** The adversarial `test_bounded_executor.py` exercises the sync semaphore, not the async guard's bypass.

This is the single most important defect: the architecture's headline property is asymmetric between sync and async.

### H2 (Event-Loop Starvation) — **RESOLVED (the narrow claim). ✅ / ⚠️**
The async guard *does* offload off the loop (`run_in_executor`), so synchronous validation never blocks the asyncio event loop — the literal H2 ("does it call sync code on the loop?") is fixed. ⚠️ The caveat is H1 above: it offloads to an **unbounded, untimed** pool. So you trade "loop stall" for "unbounded executor backlog + no deadline". Loop stays responsive; throughput and latency still collapse under load.

### H3 (ReDoS & Input Security) — **RESOLVED (with a caveat). ✅**
`validator.py:31-51, 243-266` is a textbook defence:
- Pattern length capped at `_MAX_PATTERN_LENGTH = 1000`; value length capped at `_MAX_REGEX_VALUE_LENGTH = 50_000` — both **fail-closed** (emit a breach, skip the match).
- Compiled patterns cached via `functools.lru_cache(maxsize=512)`.
- Anchored `fullmatch`; `re.error` caught and surfaced as a breach, never raised.
- Optional linear-time `re2` backend when importable.
**Caveat:** `re2` is **not declared** as an extra in pyproject.toml, so in practice every consumer runs the stdlib `re` backtracking engine. The length caps make catastrophic backtracking *bounded* (1000-char pattern × 50k value is a finite, if not cheap, worst case), so this is acceptable — but the ARCHITECTURE.md promise of a linear-time engine is unreachable without adding `re2`/`google-re2` to `[project.optional-dependencies]`. Also note the **15 ms default timeout does not protect the async path** (H1), so on async the only remaining ReDoS guard is the length cap.

### H4 (Network Boundaries & Circuit Breakers) — **NOT IMPLEMENTED. ❌**
There is **no circuit breaker** anywhere — no `CLOSED/OPEN/HALF-OPEN` state machine, no failure-rate window, no half-open probe. grep for breaker state is empty. What exists instead:
- `HttpContractRepository.fetch_active_contracts` — a flat `httpx` GET with a 10 s timeout (`:89`), and on any failure the caller degrades to `load_snapshot()`.
- `QueueEventBus._ship` — exponential backoff (base 0.5 s, cap 8 s, 4 attempts; `:210-240`), then drop.

**Why this is a real risk, with the mitigating nuance:** when the registry is down, **every** background sync pass eats the full 10 s connect/read timeout before degrading. Because syncs run on the *single* `BackgroundSyncWorker` daemon thread (not the validation pool), a dead registry does **not** starve the validation thread pool — so the catastrophic "registry-down → hot-path starvation" scenario is largely avoided *by accident of threading topology*, not by design. **However:** `bootstrap()` runs `sync_once()` **synchronously and inline** (`dependency_injection.py:185`), so a cold/hung registry blocks application boot for up to 10 s per attempt with no breaker to fast-fail. And telemetry `_ship` can spend `~0.5+1+2+4 ≈ 7.5 s` of backoff per failing batch on the bus thread, throttling drain throughput when the plane flaps. **A genuine breaker (open after k consecutive failures, half-open probe every t seconds) is required** before this is "bulletproof".

---

## 4. LOCAL-FIRST & BYOM EXTENSION READINESS

**Blunt assessment: the local-first / BYOM story is essentially unbuilt.** The SDK is architected as a *thin client of a remote control plane*, not as a local-first engine. Evidence:

- **No local/file contract source.** The only `IContractRepository` implementation is `HttpContractRepository`. There is **no `FileContractRepository`** that reads a local `./contracts/*.json|*.yaml` directory. A GitOps workflow ("commit contracts to the repo, the SDK reads them") is impossible without writing a new L4 adapter. The seam *exists* (the `IContractRepository` protocol is clean and the use case is source-agnostic), so this is an additive, low-risk feature — but it is **not present**.
- **Config assumes a network plane.** `CongineConfig` is all `base_url`/`api_key`/`project_id`/`tenant_id`. There is no `contracts_dir` / `mode=local` switch. `is_local_base_url()` only relaxes *credential validation* for loopback; it does not enable a file-driven mode. A consumer who wants pure offline operation must still point at a `localhost` plane.
- **No Healing / patching layer at all.** There is **zero** code for a "Local Healing Layer", remediation, or model-driven patching. `tests/adversarial/test_remediations.py` exists but tests validation-failure handling, not any healing pipeline. BYOK/BYOM (Ollama, custom low-cost keys) has **no abstraction, no `IHealer`/`IModelClient` protocol, no config surface**. This is a Phase-1 greenfield, not a Phase-0 gap to patch.
- **What IS ready (the good news):** The hexagonal seams make both features clean to add. A `FileContractRepository(IContractRepository)` drops straight into `SyncContractsUseCase` with no domain change. A healing layer would be a new L3 use case + an L1 `IModelClient` port + L4 `OllamaClient`/`OpenAICompatibleClient` adapters, wired in `ServiceContainer`. The `CompositeValidator` pattern is exactly the right precedent for composing a "validate → heal → re-validate" loop. **Estimated effort: each is a few hundred lines, well-isolated.**

**Readiness grade for the BYOM/local-first pitch: 2/5 — the foundation supports it, but none of it is written, and the public README/positioning promises ("Local SDK Plane", "BYOK/BYOM") are not yet backed by code.**

---

## 5. COMPLETE GAP ANALYSIS & ROADMAP FOR THE NEXT SPRINT

### 5a. Missing files / methods / blocks (explicit)

**Portability / packaging (blockers):**
- `pyproject.toml:4` — `requires-python = ">=3.14"` must drop to a realistic floor (`>=3.9` or `>=3.10`).
- `http_contract_repository.py:118` — `except FileNotFoundError, json.JSONDecodeError, OSError:` → must be **parenthesized** `except (FileNotFoundError, json.JSONDecodeError, OSError):`.
- `langchain_handler.py:144` — `except IndexError, TypeError:` → `except (IndexError, TypeError):`.
- `pyproject.toml:5-13` — move `pytest`, `pytest-asyncio`, `pytest-cov`, `ruff` into `[project.optional-dependencies].dev`; **remove unused `pydantic`** (grep confirms it is imported nowhere in `src/`).
- Add `re2`/`google-re2` to a `[project.optional-dependencies].redos` (or drop the ARCHITECTURE.md claim).

**OSS hygiene (blockers for FAANG adoption):**
- `LICENSE` — **absent.** (Apache-2.0 or MIT.) Legal will hard-block without it.
- `README.md` — currently **one line**; needs install, quickstart, `@congine_guard` example, config table, architecture diagram.
- `CONTRIBUTING.md`, `SECURITY.md` (vuln disclosure policy), `CODE_OF_CONDUCT.md`, `CHANGELOG.md` — all absent.
- CI matrix config (test across 3.9–3.13/3.14, lint, type-check) — none present in the SDK dir.

**Correctness / concurrency:**
- `guard.py` async path — route through a **bounded, timed** offload. Add `BoundedValidationExecutor.run_with_timeout_async()` (acquire semaphore → `submit` → `asyncio.wrap_future` with `asyncio.wait_for(timeout)`), so async callers get the same shedding + deadline as sync. **Add a covering adversarial test.**
- `http_contract_repository.save_snapshot` — wrap the `os.replace` in a `portalocker` advisory lock; add single-flight boot to kill the N-worker herd.
- `dependency_injection.py` — add a real **CircuitBreaker** (`CLOSED/OPEN/HALF-OPEN`) around `fetch_active_contracts` and telemetry `_ship`; make `bootstrap()` non-blocking or breaker-guarded so a dead plane can't hang boot for 10 s.
- Remove dead `infrastructure/timer.py::ValidationTimer` (or stop exporting it) so no consumer wires the unbounded variant.

**Local-first / BYOM (Phase-1 scope, but stub the seams now):**
- `infrastructure/file_contract_repository.py` — `FileContractRepository(IContractRepository)` reading `config.contracts_dir`.
- `config.py` — add `contracts_dir: Optional[str]` and a `mode: "remote"|"local"` switch.
- New L1 port `repositories/model_client.py::IModelClient` + L4 `OllamaClient` / `OpenAICompatibleClient` + L3 `HealContractUseCase` (validate → heal-with-BYOM → re-validate).

### 5b. Prioritized pre-`git init` checklist

| # | Priority | Task | Type | Effort |
|---|---|---|---|---|
| 1 | **P0 — blocker** | Parenthesize the 2 `except A, B:` clauses (`http_contract_repository.py:118`, `langchain_handler.py:144`) | Fix | 5 min |
| 2 | **P0 — blocker** | Lower `requires-python` to `>=3.10`; verify import on 3.10–3.13 | Fix | 30 min |
| 3 | **P0 — blocker** | Split runtime vs dev deps; drop unused `pydantic`; un-pin aggressive minimums | Fix | 30 min |
| 4 | **P0 — blocker** | Add `LICENSE` (Apache-2.0/MIT) | Add | 10 min |
| 5 | **P0 — blocker** | Fix the async-guard bypass: bounded + timed offload + covering test | Fix | 0.5–1 day |
| 6 | **P1 — high** | Write a real `README.md` (install, quickstart, config table, layering) | Add | 0.5 day |
| 7 | **P1 — high** | Implement `CircuitBreaker` on the control-plane boundary; make `bootstrap()` non-blocking | Feature | 1 day |
| 8 | **P1 — high** | `portalocker` advisory lock + single-flight on snapshot write (multi-worker safety) | Fix | 0.5 day |
| 9 | **P1 — high** | CI matrix (3.10–3.14) + ruff + mypy/pyright gate | Infra | 0.5 day |
| 10 | **P2 — med** | Remove dead `ValidationTimer` export; rename `repositories/` → `ports/` (or document) | Cleanup | 0.5 day |
| 11 | **P2 — med** | `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `CHANGELOG.md` | Add | 0.5 day |
| 12 | **P2 — med** | Declare `re2` extra (or remove the linear-time claim from ARCHITECTURE.md) | Fix | 15 min |
| 13 | **P3 — Phase 1** | `FileContractRepository` + `config.contracts_dir` (local-first / GitOps) | Feature | 1 day |
| 14 | **P3 — Phase 1** | `IModelClient` port + Ollama/OpenAI-compatible adapters + `HealContractUseCase` (BYOM healing) | Feature | 2–3 days |

**Bottom line:** items 1–5 (≈1.5 days) move the project from "won't import / won't license" to "installs and runs honestly." Items 6–9 (≈3 days) make the concurrency and network claims true. Items 13–14 are the actual BYOM/local-first product and belong to Phase 1. **Do not run `git init` on the public repo until items 1–4 are done — they are reputational, not just technical.**

---
*Report generated by adversarial line-by-line scan. Every CRITICAL/HIGH finding is backed by a file:line citation above and is independently reproducible (`python -m compileall` on 3.13 will fail items 1; `grep -rn "except .*, .*:" src/` reproduces the syntax sites; `python -m pytest` reproduces the 197-pass baseline on 3.14).*
