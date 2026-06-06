# AMCE · Congine SDK — Phase 0 Comprehensive Analysis & Roadmap
**Document Type:** Engineering & Product Analysis — Internal Strategy Guide
**Scope:** Phase 0 (`congine_core`) completion, architectural integrity, production readiness, and monetization path
**Sources:** Phase 0 Engineering Blueprint (66pp), Independent Adversarial Audit (`phase0-congine-newAudit.md`), AMCE System Design HLD+LLD (Phase 1 MVP)
**Status:** Pre-publication — working toward production-ready / monetization-stage milestone

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Phase 0 Actual Completion State](#2-phase-0-actual-completion-state)
3. [Audit Findings — Severity-Ranked Digest](#3-audit-findings--severity-ranked-digest)
4. [Architectural Integrity Analysis](#4-architectural-integrity-analysis)
5. [Security & Multi-Tenant Hardening Analysis](#5-security--multi-tenant-hardening-analysis)
6. [Reliability & Resilience Gaps](#6-reliability--resilience-gaps)
7. [Observability & Operational Visibility Gaps](#7-observability--operational-visibility-gaps)
8. [Portability, Packaging & OSS Hygiene](#8-portability-packaging--oss-hygiene)
9. [HLD-to-SDK Alignment Gap (AMCE HLD vs Congine SDK)](#9-hld-to-sdk-alignment-gap-amce-hld-vs-congine-sdk)
10. [Scalability Analysis](#10-scalability-analysis)
11. [Monetization Readiness Assessment](#11-monetization-readiness-assessment)
12. [Prioritized Action Plan](#12-prioritized-action-plan)
13. [What "Phase 0 Done" Actually Means](#13-what-phase-0-done-actually-means)

---

## 1. Executive Summary

The Congine SDK's Phase 0 validation core (`congine_core`) is **architecturally strong** — the hexagonal layering is clean, the O(1) LFU cache is correctly implemented, the bounded executor is genuinely load-shedding and now symmetric across sync and async paths, and snapshot writes are atomically advisory-locked. The core validation logic is production-quality code.

However, **Phase 0 is not complete** in the engineering sense — there are four categories of gaps that collectively prevent it from reaching production, open-source release, or monetization:

**Category A — Hard Blockers (must fix before any external use):**
- A broken Python version floor claim (`>=3.10` declared, 3.14-only syntax present in tests — the suite cannot even collect on any supported Python)
- No LICENSE file (legally blocks both open-source release and commercial distribution)
- No circuit breaker around the control plane (application boot can stall up to 10 seconds per attempt against a hung registry)
- Broken CI/test invocation in the monorepo tooling (`nx test` target missing `--extra dev`)

**Category B — Architectural Debt (must fix before API surface ossifies):**
- Missing `IValidationRunner` L1 port — the entire timeout/executor layer has no hexagonal seam, violating the architecture's own layering contract
- `ValidationTimer` dead but still exported — misleads consumers into wiring the unbounded, non-load-shedding implementation
- `repositories/` directory should be renamed `ports/` before the public API is published
- L3 `ValidateContractUseCase` names an L4 concrete (`"ValidationTimer"`) in its type hint instead of the L1 port

**Category C — Production Hardening (must fix before enterprise/paying use):**
- HTTPS enforcement defaults to `False` for non-local control planes — credential-bearing SDK ships secrets over HTTP by default
- N-worker thundering herd: every Gunicorn/Uvicorn worker independently fetches the full contract set on boot
- 15ms default timeout is too tight once `CompositeValidator` + `jsonschema` semantic validation is active
- Silent telemetry drops with no counter — loss is invisible
- Drift detection crashes without a guard if `[stats]` extra is absent

**Category D — Product/Monetization Gaps:**
- No README, no real quickstart, no config reference
- No `FileContractRepository` (local-first/GitOps story is unbuilt — this is a core positioning promise)
- BYOM healing loop is unbuilt (the primary enterprise differentiator)
- `re2` described as available but not declared as an installable extra

The bottom line: **none of these gaps require a rewrite**. Every fix lands inside the existing hexagonal seams. The estimated total remediation effort is 8–12 engineering days before Phase 0 can be declared complete and the project can move to Phase 1 or monetization exploration.

---

## 2. Phase 0 Actual Completion State

### 2.1 What Is Genuinely Shipped and Working

The following components are verified-sound by both the Blueprint and the adversarial audit, with evidence at the source level:

| Component | File(s) | Verified State |
|---|---|---|
| O(1) LFU cache with TTL + daemon sweeper | `infrastructure/lfu_cache.py` | Correct — Ketan-Shah buckets, single RLock, lazy + sweep expiry, no race found |
| BoundedValidationExecutor (sync + async) | `infrastructure/bounded_executor.py` | Correct — shared `_acquire_and_submit`, same semaphore and deadline for both paths, re-entrancy inline-run guard |
| ValidateContractUseCase | `usecases/validate_contract_usecase.py` | Correct — schema resolve, timed execution, telemetry-before-raise ordering verified |
| RuleEngine (6 static rules) | `domain/validator.py` | Correct — length-capped regex, fail-closed on bad pattern, skips non-string for REGEX_PATTERN |
| LFUCache concurrency | `lfu_cache.py` | Correct — no double-release, no permit leak |
| Snapshot advisory lock | `http_contract_repository.py:162` | Correct — portalocker LOCK_EX \| LOCK_NB + atomic os.replace + symlink/owner check |
| Telemetry-before-raise ordering | `validate_contract_usecase.py:199,:150` | Correct — telemetry event published before STRICT escalation |
| ReDoS resistance | `validator.py:243–285` | Correct — fail-closed length caps + LRU-compiled patterns |
| Container lifecycle (no import-time threads) | `dependency_injection.py:45–61` | Correct — lazy double-checked singleton |
| Failure taxonomy (degrade vs raise vs silent) | `config.py`, `validate_contract_usecase.py` | Correct — three modes mapped correctly |

### 2.2 What Is Incomplete or Broken

| Gap | Severity | Effort |
|---|---|---|
| Python 3.14-only `except` syntax in `test_remediations.py:189` | **BLOCKER** | 5 min |
| No LICENSE file | **BLOCKER** | 1 hr |
| No circuit breaker (H4 open from Phase 0 audit) | **BLOCKER** | 1 day |
| Broken `nx test` target (missing `--extra dev`) | **BLOCKER** | 15 min |
| Missing `IValidationRunner` L1 port (D-4) | High | 0.5 day |
| `ValidationTimer` dead but exported | High | 30 min |
| `repositories/` → `ports/` rename | High | 0.5 day |
| HTTPS default `False` for non-local planes (D-6) | High | 30 min |
| N-worker thundering herd on boot (D-7) | High | 0.5 day |
| 15ms timeout too tight for semantic validation (D-8) | Medium | 30 min |
| Silent telemetry drops, no `dropped_total` counter (D-10) | Medium | 0.5 day |
| Numpy-gated drift crashes without guard (D-10) | Medium | 1 hr |
| `re2` claim in `ARCHITECTURE.md` but not in `pyproject.toml` | Medium | 30 min |
| Stale `*.egg-info` in VCS (D-9) | Low | 15 min |
| No real README / quickstart / config table | Medium | 1 day |
| `FileContractRepository` unbuilt | Medium (product) | 1 day |
| BYOM healing loop unbuilt | Medium (product) | 2–3 days |
| No CI version matrix (3.10–3.14) | High | 0.5 day |
| `__version__` duplicated in `__init__.py` and `pyproject.toml` | Low | 15 min |

---

## 3. Audit Findings — Severity-Ranked Digest

### 3.1 P0 — Critical Blockers

#### D-1: Python 3.14-Only Syntax Breaks the Declared Floor
**File:** `tests/adversarial/test_remediations.py:189`
**Evidence:**
```python
# BROKEN — comma-separated exception syntax is Python 3.14+
except OSError, NotImplementedError, AttributeError:
```
**Impact:** The test suite cannot even collect on CPython 3.10, 3.11, 3.12, or 3.13 — the four Python versions the package explicitly supports. The `requires-python = ">=3.10"` claim in `pyproject.toml` is therefore technically false. Any enterprise buyer or open-source contributor running the standard Python version will hit an immediate import failure in the test layer. The audit result of "201 passed" is only valid on CPython 3.14.2.
**Fix:** `except (OSError, NotImplementedError, AttributeError):` — one character change, five minutes of work.

#### D-2: Broken CI/Test Invocation
**File:** `project.json:20` (nx `test` target)
**Evidence:** The nx test target does not pass `--extra dev` (or equivalent) when invoking `uv run pytest`. The dev dependency group containing `pytest`, `ruff`, and `mypy` is not auto-installed by `uv run` without explicit opt-in.
**Impact:** Any clean-room CI runner will fail to collect tests. The test suite effectively does not run in CI as configured.
**Fix:** Add `--extra dev` flag to the nx test target, or migrate the toolchain to `[dependency-groups]` (PEP 735), which `uv` auto-installs.

#### D-5: No Circuit Breaker on Control-Plane Boundary (H4 from Phase 0 Blueprint)
**File:** `dependency_injection.py:185`, `http_contract_repository.py:89`
**Evidence:** `ServiceContainer.bootstrap()` calls `sync_once()` synchronously and inline. `sync_once` drives `asyncio.run(fetch_active_contracts())` with a **10-second** client timeout. There is no CLOSED/OPEN/HALF-OPEN state machine anywhere in the codebase (verified by grep).
**Impact — three failure modes:**
1. A cold or hung control-plane **stalls application boot for up to 10 seconds per attempt**. Under a 3-retry configuration this is a 30-second startup penalty, which breaks liveness probes and Kubernetes readiness gates.
2. A flapping background plane burns the full timeout on every sync pass, producing a steady ~7.5s of backoff per failing telemetry batch — a continuous background drain.
3. A persistent outage creates no "fast fail" path — each worker retries independently, consuming threads.
**Fix:** Implement a simple `CircuitBreaker` class (L4 infrastructure, wraps both `HttpContractRepository.fetch_active_contracts` and `QueueEventBus._ship`). Add a `breaker_state` key to `health()`. Modify `bootstrap()` to consult the breaker and skip the blocking fetch if OPEN, falling through to snapshot immediately.

#### No LICENSE File
**Impact:** Without a LICENSE file, the codebase is legally "all rights reserved" by default in most jurisdictions. This blocks:
- Any open-source contribution or usage
- Any commercial distribution or resale
- Any investor or acquirer due diligence
**Fix:** Add `LICENSE` (Apache-2.0 is the standard for enterprise-friendly Python SDKs; MIT is simpler but provides less patent protection). Also add `SECURITY.md` with a responsible disclosure policy before publishing.

### 3.2 P1 — Architectural Debt

#### D-4: Missing IValidationRunner L1 Port
**Evidence:** `validate_contract_usecase.py:27,39` declares `timer: "ValidationTimer"` as its type hint. The container actually injects `BoundedValidationExecutor` (not `ValidationTimer`). There is no `IValidationRunner` protocol in `repositories/` (or anywhere in L1). The `run_with_timeout_async` method is accessed via `getattr` shim at L3 (line `:104`).
**Architectural impact:** This is the most significant architectural violation in Phase 0. Every other cross-layer collaborator has a proper L1 `typing.Protocol` seam:
- `ISchemaStorage` → `LFUCache`
- `IContractRepository` → `HttpContractRepository`
- `IEventBus` → `QueueEventBus`
- `ILogger` → `StructuredLogger`
- `ISemanticValidator` → `JsonSchemaSemanticValidator`

But the **validation runner** — the component that enforces the system's hardest performance guarantee — has no seam. L3 is implicitly coupled to an L4 concrete. This defeats testability (you cannot inject a mock timer without monkey-patching), and it means any future swap of the executor (e.g., a process-pool variant, a thread-local variant for testing) requires modifying L3 code.
**Fix:**
```python
# repositories/validation_runner.py (new L1 port)
from typing import Protocol, runtime_checkable, Callable, Any, Awaitable

@runtime_checkable
class IValidationRunner(Protocol):
    def run_with_timeout(self, fn: Callable[[], Any], timeout_ms: int) -> Any: ...
    async def run_with_timeout_async(self, fn: Callable[[], Any], timeout_ms: int) -> Any: ...
```
Then type `ValidateContractUseCase.timer` as `IValidationRunner` and remove the `getattr` shim.

#### D-3/D-11: `ValidationTimer` Dead but Still Exported
**Evidence:** `infrastructure/timer.py::ValidationTimer` is never instantiated anywhere in `src/`. The container wires `BoundedValidationExecutor` as the timer. Yet `ValidationTimer` is still exported in:
- `infrastructure/__init__.py:16,23`
- `congine_core/__init__.py` (package root)

**Impact:** A consumer who reads the documentation or package exports and wires `ValidationTimer` directly gets an **unbounded, non-load-shedding** timer. The load-shedding guarantee is silently defeated. This is a silent correctness trap for any integrator.
**Fix:** Remove from all public `__init__.py` exports. If the class is kept for legacy reference, move it to `_legacy/` with a deprecation notice pointing to `BoundedValidationExecutor`.

#### D-11: `repositories/` Directory Name Misrepresents the Layer
**Evidence:** The `repositories/` directory (L1) holds not only repository ports (`IContractRepository`, `ISchemaStorage`) but also non-repository ports: `ILogger` (`repositories/logger.py`) and `IEventBus` (`repositories/event_bus.py`). The Blueprint itself acknowledges this: "The directory is named repositories/ but holds non-repository ports too. A future rename to ports/ is tracked in §7."
**Impact:** Once the public API is published with `from congine_core.repositories import ILogger`, any rename becomes a breaking change. The window to fix this cleanly is now, before publication.
**Fix:** Rename `repositories/` → `ports/`, update all internal imports, update `ARCHITECTURE.md`. The Blueprint already calls these "L1 protocol seams" — the directory name should match.

### 3.3 P2 — Production Hardening

#### D-6: HTTPS Default is Insecure for Non-Local Planes
**Evidence:** `config.py:107` — `require_https: bool = False`. `dependency_injection.py:86-93` emits a warning for cleartext but proceeds.
**Impact:** The SDK carries an API key and telemetry payloads. With `require_https=False` as the default, any deployment that does not explicitly set `CONGINE_REQUIRE_HTTPS=true` ships credentials over plaintext HTTP. The secure default should be inverted.
**Fix:** Change `require_https: bool = True` in `CongineConfig`. Add an explicit opt-out mechanism (`CONGINE_ALLOW_CLEARTEXT=true`) for development/internal use, with a loud startup warning.

#### D-7: N-Worker Thundering Herd at Boot
**Evidence:** Each Gunicorn/Uvicorn worker spawns its own `ServiceContainer`, which independently calls `bootstrap()` → `sync_once()` → `fetch_active_contracts()`. Under N=8 workers, that is 8 simultaneous full-contract-set fetches against the registry at every deploy.
**Impact:** At scale (N=16–32 workers, large contract sets), this creates a synchronized registry burst that can saturate the control plane's connection pool exactly when it matters most — during a deployment. The `portalocker` advisory lock makes concurrent snapshot writes safe but does not coordinate the upstream fetch.
**Fix:** Implement single-flight boot coordination:
1. First worker to boot acquires the portalocker write lock, fetches, and writes the snapshot.
2. Subsequent workers that fail to acquire the lock immediately skip to `load_snapshot()` (which the first worker just wrote).
3. Add a jitter of `random.uniform(0, 0.5)` seconds before each worker's fetch attempt to desynchronize.

#### D-8: 15ms Default Timeout is Too Tight for Semantic Validation
**Evidence:** `config.py:85` — `validation_timeout_ms: int = 15`. The test fixtures contradict this: `conftest.py:151` uses 50ms, `test_end_to_end.py:32` uses 200ms.
**Impact:** `LocalValidator` (rule engine only) executes in microseconds. `CompositeValidator` + `jsonschema.iter_errors()` over a large schema (e.g., a 50-field LLM output schema) can realistically take 20–80ms. With a 15ms ceiling and `FailMode.STRICT`, legitimate payloads are degraded as timeouts. This will produce false-positive breach alerts in production.
**Fix:** Change the default to `validation_timeout_ms: int = 100`. Update the Blueprint's latency table accordingly. The "sub-200ms" host-perceived SLA is unaffected — 100ms validation budget with O(1) cache lookup + telemetry still lands well within the host budget.

---

## 4. Architectural Integrity Analysis

### 4.1 Layer Dependency Matrix — Current State vs Intended

The Blueprint defines a strict 6-tier hexagonal monolith. Below is the current actual dependency state:

| Layer | Should Import | Actually Imports | Violations |
|---|---|---|---|
| L0 Kernel | nothing | nothing | ✅ Clean |
| L1 Ports | L0 only (L2 via TYPE_CHECKING) | L0 | ✅ Clean |
| L2 Domain | L0, own IValidator | L0, own IValidator | ✅ Clean |
| L3 Use Cases | L1 + L0 | L1 + L0 + `"ValidationTimer"` string hint | ⚠️ String literal names L4 concrete |
| L4 Infra | L1 + L2 + L0 | L1 + L2 + L0 | ✅ Clean |
| L5 Adapters | everything | everything | ✅ Clean |

The single real violation is the L3 type hint that names an L4 concrete by string. At runtime this is harmless (the container injects correctly), but it represents a documentation/type-system lie and will confuse anyone reading the use-case layer in isolation. Fixing D-4 (adding `IValidationRunner`) resolves this entirely.

### 4.2 Missing Port — IValidationRunner

This is the most architecturally significant gap. The complete port signature should be:

```python
# ports/validation_runner.py

from typing import Protocol, runtime_checkable, Callable, Any
from typing import Awaitable

@runtime_checkable
class IValidationRunner(Protocol):
    """
    L1 port for bounded, timed execution of validation callables.
    Implementations are expected to enforce:
      - Capacity bounding (load-shedding on saturation)
      - Hard deadline enforcement (timeout_ms ceiling)
      - Re-entrancy safety (no nested-pool deadlock)
    """
    @property
    def capacity(self) -> int:
        """Total outstanding-work ceiling (workers + pending)."""
        ...

    def run_with_timeout(
        self,
        fn: Callable[[], Any],
        timeout_ms: int
    ) -> Any:
        """Synchronous timed execution. Raises TimeoutError on deadline breach."""
        ...

    async def run_with_timeout_async(
        self,
        fn: Callable[[], Any],
        timeout_ms: int
    ) -> Any:
        """Async timed execution. Raises TimeoutError on deadline breach."""
        ...

    def health(self) -> dict:
        """Returns in_flight, rejected_total, capacity."""
        ...
```

With this port in place:
- `ValidateContractUseCase.__init__` types `timer: IValidationRunner` (real, not string)
- The `getattr(self.timer, "run_with_timeout_async", None)` shim at line `:104` is eliminated
- A test double (`class FakeRunner(IValidationRunner)`) can be injected without any infrastructure
- Future executor variants (ProcessPoolExecutor, thread-local inline) can be added by implementing this port at L4

### 4.3 Composition Root Wiring Order — One Risk

The Blueprint documents the L5 wiring order correctly (L4 first, L2 next, L3 last). The only risk here is that `ServiceContainer._default_instance` is a class variable guarded by a `threading.Lock` (double-checked locking). This works correctly for CPython's GIL semantics, but the pattern relies on the GIL for the second read of `_default_instance`. With Python's announced direction toward sub-interpreters and free-threading (3.13+), this lock should be reinforced. Recommendation: use a `threading.local()` or an explicit module-level lock that is acquired for the full double-check block, not just the write.

### 4.4 Dead Export Risk — Public API Surface

The current `congine_core/__init__.py` exports `ValidationTimer`. Any consumer that reads the package exports and wires this class gets an unbounded timer with no load-shedding and no deadline. This is a **silent correctness trap**. The correct exported timer collaborator is `BoundedValidationExecutor`. Before the package version is bumped past `0.1.0`, this must be removed from the public surface.

The complete recommended public API surface for Phase 0:

```
congine_core:
  bootstrap / bootstrap_async         (via ServiceContainer)
  congine_guard                        (decorator)
  ServiceContainer                     (composition root)
  CongineConfig / from_env             (config)
  ValidationResult / BreachDetail      (domain models)
  CongineBaseException + subtypes      (exception hierarchy)
  CongineCallbackHandler               (LangChain adapter)
  
  # Ports (for custom implementations):
  ISchemaStorage, IContractRepository, IEventBus,
  ILogger, ISemanticValidator, IValidationRunner  ← add this
  
  # NOT exported:
  ValidationTimer, LFUCache internals, BoundedValidationExecutor internals
```

---

## 5. Security & Multi-Tenant Hardening Analysis

### 5.1 What Is Correctly Implemented

The adversarial audit confirms these security controls are correctly implemented:

**Snapshot poisoning resistance:** `HttpContractRepository.save_snapshot` (`http_contract_repository.py:120–176`) implements:
1. Per-tenant scope hash — snapshot path includes `scope=sha256(tenant_id+project_id)[:8]`
2. Symlink refusal — if the snapshot path is a symlink, the write is rejected
3. Owner check — snapshot directory must be owned by the current process UID
4. Advisory lock — `portalocker LOCK_EX | LOCK_NB` prevents concurrent cross-process writes
5. Atomic replace — `os.replace()` on a same-directory tempfile ensures the live snapshot is never partially written

**ReDoS resistance:** `domain/validator.py:243–285` implements:
1. Pattern length cap (>1000 chars → breach, not evaluation)
2. Value length cap (>50,000 chars → skip regex entirely)
3. LRU-cached `re.compile()` — patterns are not re-compiled on every call
4. `re.error` caught and converted to a breach (not a crash)

**Multi-tenant isolation at the snapshot layer** is strong. The weakness is at the HTTPS layer.

### 5.2 HTTPS Default Inversion — Priority Fix

The current behavior for a production deployment that sets `CONGINE_BASE_URL=https://api.congine.io` but forgets `CONGINE_REQUIRE_HTTPS=true`:

```
WARN congine base_url is not HTTPS; API key and telemetry are
     sent in cleartext base_url=https://api.congine.io  ← confusingly shown as https
```

Wait — the warning fires when `base_url` is NOT HTTPS. If it is HTTPS, there is no enforcement of the scheme. The actual risk is when `base_url=http://...` — the key and telemetry travel over HTTP. With `require_https=False` as the default, this is a permitted state.

**Recommended change:**
```python
# config.py
require_https: bool = True  # was: False

# Add explicit cleartext opt-out
allow_cleartext_for_local_dev: bool = False  # env: CONGINE_ALLOW_CLEARTEXT
```

The `is_local_base_url()` check already exists — it can be used to exempt loopback addresses from the HTTPS requirement without needing the explicit opt-out flag.

### 5.3 Log Redaction Gap

The `StructuredLogger` (`infrastructure/logger.py`) emits structured JSON logs with `**kwargs` passed as arbitrary contextual data. There is no log-redaction contract — no field blocklist, no PII scrubber, no log-safe wrapper.

In practice, validation breach details include field values from the LLM payload (e.g., `message: "score 1.4 above maximum 1"`). In a multi-tenant deployment, these log lines go to a shared logging pipeline. If a payload contains PII, it can surface in logs.

**Recommended additions:**
1. A configurable `log_safe_fields` allowlist in `CongineConfig` (default: `contract_id`, `status`, `duration_ms`, `rule`, `field` — but not `message` or `value`)
2. A `redact(value, field_name) -> str` utility in `StructuredLogger` that checks against the allowlist

### 5.4 API Key Transport in Telemetry

The telemetry drain worker (`queue_event_bus.py`) sends the API key as an HTTP header on every batch POST. This is correct behavior, but it means the API key appears in HTTP access logs on both the SDK side and the registry side. Recommendation: consider adding a telemetry-specific signing token that is separate from the control-plane API key, so a telemetry endpoint compromise does not yield control-plane write access.

---

## 6. Reliability & Resilience Gaps

### 6.1 Circuit Breaker Design (H4 — The Highest-Priority Unbuilt Feature)

The circuit breaker is the single most important reliability feature for production enterprise use. Here is the recommended design that fits the existing L4 infrastructure layer without any domain changes:

```
┌─────────────────────────────────────────────────────┐
│               CircuitBreaker (L4)                   │
│  Implements: wraps HttpContractRepository +          │
│              QueueEventBus._ship                     │
│                                                      │
│  State machine:                                      │
│  CLOSED ──(k consecutive failures)──► OPEN           │
│  OPEN   ──(cooldown_seconds elapsed)──► HALF_OPEN    │
│  HALF_OPEN ──(probe success)──────────► CLOSED       │
│  HALF_OPEN ──(probe fails)────────────► OPEN         │
│                                                      │
│  Config (CongineConfig):                             │
│    breaker_failure_threshold: int = 5               │
│    breaker_cooldown_seconds: int = 30               │
│                                                      │
│  bootstrap() consults breaker:                       │
│    OPEN → skip blocking fetch, load snapshot         │
│    CLOSED/HALF_OPEN → attempt fetch                  │
│                                                      │
│  health() addition:                                  │
│    "breaker_state": "CLOSED" | "OPEN" | "HALF_OPEN" │
└─────────────────────────────────────────────────────┘
```

**Critical implementation note:** The breaker state must be **process-local** (in-memory). A distributed/Redis-backed breaker is Phase 2+. For Phase 0, a per-process in-memory breaker already provides the boot-stall protection and background-sync fast-fail that are the two most urgent use cases.

**File placement:** `infrastructure/circuit_breaker.py` — a pure L4 class, implementing no new L1 port (the breaker wraps existing adapters, it is not a dependency-inverted seam).

### 6.2 Thundering Herd — Single-Flight Boot Coordination

The fix for the N-worker boot burst uses an existing mechanism (portalocker) in a new way:

```
Worker boot sequence (proposed):

1. Each worker attempts portalocker.lock(snapshot_lock_file, LOCK_EX | LOCK_NB)
   ├─ Lock acquired (first worker):
   │   → fetch_active_contracts() from registry
   │   → save_snapshot() under the same lock
   │   → release lock
   │   → prime own cache from just-saved snapshot
   │
   └─ Lock not acquired (N-1 workers):
       → sleep(random.uniform(0.05, 0.3))  # jitter
       → load_snapshot()                    # use what first worker wrote
       → prime own cache from snapshot

2. All workers are now cache-warm with zero registry burst after the first
```

This requires a ~30-line change to `SyncContractsUseCase.sync_once` and `ServiceContainer.bootstrap`.

### 6.3 Background Sync Resilience

The `BackgroundSyncWorker` (`infrastructure/background_sync.py`) correctly swallows errors and uses `threading.Event.wait` for interruptible sleep. However, there are two gaps:

1. **No jitter on the sync interval** — all workers in a multi-process deployment will attempt the background sync at the same interval offset from their boot time. If they all boot together (deployment), their background syncs will also cluster together. Add `±10%` random jitter to `sync_interval_seconds`.

2. **`CongineSyncError` does not distinguish "registry gone" from "schema changed"** — a silent schema migration on the registry side that breaks the snapshot envelope validation will cause the background sync to fall back to the old snapshot indefinitely, with no alert distinguishing "control plane is down" from "schema format changed". Add a sub-type `CongineSchemaFormatError` for this case.

### 6.4 `asyncio.wait_for` Zombie Thread Warning

`bounded_executor.py:134` awaits `asyncio.wait_for(asyncio.wrap_future(future), timeout)`. When the timeout fires, `wait_for` cancels the future wrapper, but the underlying `ThreadPoolExecutor` thread is **not** interrupted — it continues running. If that thread later raises an exception, Python may emit an "exception was never retrieved" warning on the event loop.

This is architecturally unavoidable with `ThreadPoolExecutor` (threads cannot be interrupted). The correct mitigation is to add a `future.cancel()` call in the timeout handler and suppress the `CancelledError` in the thread-side callback — this at least removes the spurious log noise under timeout storms.

---

## 7. Observability & Operational Visibility Gaps

### 7.1 Silent Telemetry Drop

**Current behavior:** When the `QueueEventBus` queue reaches its 10,000-event limit, `put_nowait()` raises `queue.Full`, which is caught and suppressed. The `health()` dict exposes `telemetry_queue_depth` but has no `dropped_total` counter.

**Impact:** Under sustained load, you can lose thousands of telemetry events with zero observable signal. An operator watching `health()` sees `queue_depth: 10000` (which is a warning signal, but not a loss signal) — they have no way to know how many events were dropped or for how long.

**Fix:**
```python
# queue_event_bus.py
class QueueEventBus:
    def __init__(self, ...):
        ...
        self._dropped_total: int = 0
        self._dropped_lock = threading.Lock()

    def publish(self, event) -> None:
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            with self._dropped_lock:
                self._dropped_total += 1
            self._logger.warn("telemetry_dropped", total=self._dropped_total)

    def queue_depth(self) -> int:
        return self._queue.qsize()

    def dropped_total(self) -> int:
        with self._dropped_lock:
            return self._dropped_total
```

Add `telemetry_dropped_total` to `ServiceContainer.health()`.

### 7.2 Drift Detection Crash Without Guard

`ServiceContainer.evaluate_drift` (`dependency_injection.py:212`) calls `KSDriftEngine.detect` directly. `KSDriftEngine.detect` calls `_require_numpy()`, which raises `ImportError` if the `[stats]` extra is not installed.

**Impact:** A host application that calls `container.evaluate_drift(...)` without installing `congine_core[stats]` gets an unguarded `ImportError` — a crash that is not covered by `CongineBaseException` and therefore bypasses the SDK's blast-radius containment.

**Fix:**
```python
# dependency_injection.py
def evaluate_drift(self, reference, sample) -> DriftResult:
    if self._drift_engine is None:
        raise CongineConfigurationError(
            "Drift detection requires the [stats] extra: "
            "pip install congine_core[stats]"
        )
    return self._drift_engine.detect(reference, sample)
```

Additionally, document this requirement prominently in the README's feature matrix.

### 7.3 Health Dashboard Completeness

The current `health()` dict (`dependency_injection.py:247`) exposes six keys. Recommended additions for production observability:

| New Key | Source | Purpose |
|---|---|---|
| `telemetry_dropped_total` | `event_bus.dropped_total()` | Sustained-loss signal |
| `breaker_state` | `circuit_breaker.state` | Fast-fail signal |
| `snapshot_age_seconds` | `time.time() - snapshot_mtime` | Schema freshness signal |
| `config_validation_timeout_ms` | `config.validation_timeout_ms` | Runtime config verification |

---

## 8. Portability, Packaging & OSS Hygiene

### 8.1 Python Version Floor — The Critical Lie

The package declares `requires-python = ">=3.10"` in `pyproject.toml`. This claim is false due to `tests/adversarial/test_remediations.py:189` using `except OSError, NotImplementedError, AttributeError:` (Python 3.14-only comma-syntax).

Beyond the syntax fix, the floor claim requires active proof:

**Required CI matrix:**
```yaml
# .github/workflows/ci.yml
strategy:
  matrix:
    python-version: ["3.10", "3.11", "3.12", "3.13", "3.14"]
    os: [ubuntu-latest, macos-latest]
```

Without this matrix, the floor is marketing, not engineering. Every Python version from 3.10–3.14 must pass the full test suite before the package is published.

### 8.2 re2 Claim in ARCHITECTURE.md

`ARCHITECTURE.md:48` states the SDK uses "the re2 linear-time engine when installed." There is no `re2` or `google-re2` in any dependency group in `pyproject.toml`. The adversarial ReDoS test (`test_redos.py:46`) is `skipif` — it effectively never runs in CI.

**Options (pick one):**
1. **Add the extra:** `[project.optional-dependencies] redos = ["google-re2>=1.0"]` and wire the conditional import in `validator.py`
2. **Remove the claim:** Strike the `re2` mention from `ARCHITECTURE.md` and document that protection is length-cap-only

Option 1 is the stronger engineering choice and closes the ReDoS audit finding properly. The length caps are a necessary fallback regardless.

### 8.3 Complete OSS Hygiene Checklist

For either open-source release or commercial distribution, the following files must exist:

```
congine_core/
├── LICENSE              ← Apache-2.0 or MIT — BLOCKING
├── README.md            ← Install, quickstart, config table, layer diagram — BLOCKING
├── SECURITY.md          ← Responsible disclosure policy — Required for enterprise
├── CHANGELOG.md         ← Version history — Required for semver discipline
├── CONTRIBUTING.md      ← Contribution guide — Required for OSS
├── .github/
│   ├── workflows/ci.yml ← Full matrix + lint + type-check — BLOCKING
│   └── CODEOWNERS       ← Review accountability
└── pyproject.toml
    ├── [project.urls]   ← Homepage, repository, documentation
    └── [project.classifiers] ← PyPI metadata
```

### 8.4 Stale Egg-Info in VCS

`src/congine_sdk.egg-info/requires.txt` still lists the pre-Sprint-1 dependency set including `pydantic>=2.13.4` and dev tools as runtime dependencies. A wheel built without regenerating this file would re-introduce removed dependencies.

**Fix:**
1. Add `*.egg-info/` to `.gitignore`
2. Delete `src/congine_sdk.egg-info/` from the repository
3. Add a CI step that verifies the wheel's `METADATA` dependencies match `pyproject.toml`

### 8.5 Version Single-Sourcing

`__version__ = "0.1.0"` appears in both `congine_core/__init__.py` and `pyproject.toml:3`. When the version is bumped, they can diverge. Fix:

```python
# congine_core/__init__.py
try:
    from importlib.metadata import version
    __version__ = version("congine_core")
except Exception:
    __version__ = "0.0.0+unknown"
```

---

## 9. HLD-to-SDK Alignment Gap (AMCE HLD vs Congine SDK)

This section addresses an important strategic alignment issue: the AMCE HLD+LLD document describes a system that uses **different naming conventions, a different architecture pattern, and a different API surface** than the Congine SDK Blueprint. This creates ambiguity about which document represents the actual system.

### 9.1 Naming Convention Divergence

| Concept | Congine SDK Blueprint | AMCE HLD+LLD |
|---|---|---|
| Decorator | `@congine_guard` | `@amce_guard` |
| Main class | `ServiceContainer` | `AmceClient` |
| Config class | `CongineConfig` | `AmceConfig` |
| Fail modes | `DEGRADE / STRICT / SILENT` | `fail_open / fail_closed` (binary) |
| Default fail mode | `DEGRADE` | `fail_closed` |
| Package name | `congine_core` | `amce` |
| Executor | `BoundedValidationExecutor` | `ThreadPoolExecutor(max_workers=4)` (unbounded) |
| Error base | `CongineBaseException` | `ContractBreachException` |

**The core SDK (Blueprint) is the authoritative source.** The HLD document appears to describe an earlier design iteration or a simplified conceptual model for stakeholder communication — not the actual shipped code.

### 9.2 Architectural Pattern Divergence

The AMCE HLD shows a simpler, non-hexagonal architecture:
- `AmceClient` directly owns both `_validator` and `_worker` — no Use Case layer
- Guard directly accesses `client._pool.submit(client._validator.validate, ...)` — bypasses L3 orchestration
- No ports/adapters pattern — concrete dependencies wired directly
- `ThreadPoolExecutor(max_workers=4)` with no semaphore-based load shedding

The Congine Blueprint's hexagonal architecture (L0–L5 with proper ports) is significantly more sophisticated and production-appropriate. The HLD's simplified version would not support the multi-mode failure taxonomy, the LFU cache's O(1) eviction, or the bounded semaphore load-shedding that the Blueprint implements.

**Recommendation:** The AMCE HLD should be updated to reflect the actual Congine architecture, or treated as a "simplified integration guide" aimed at consumers rather than an implementation blueprint. The two documents should not coexist as equally-authoritative references — this will cause confusion for any engineer joining the project.

### 9.3 NestJS Backend — Phase Boundary Clarity

The AMCE HLD includes a full NestJS + PostgreSQL backend design (Contract Registry, Telemetry Ingestion). The Congine Blueprint places this firmly in Phase 1+. This is correct — the Python SDK (Phase 0) can operate against any HTTP endpoint that satisfies the contract bundle and telemetry interfaces, including a simple mock or a locally-run registry.

**However**, the Phase 1 backend design in the HLD does not define a formal API contract (OpenAPI spec). Before starting Phase 1 backend work, an OpenAPI specification for:
- `GET /contracts/active` → `ContractBundleDto`
- `POST /telemetry/ingest/batch` → `202 Accepted`

...must be written and versioned alongside the SDK. The SDK's `HttpContractRepository` is the only consumer of these endpoints and its expected response shapes must be authoritative.

### 9.4 Database Schema Notes (AMCE HLD §2.1)

The PostgreSQL schema in the HLD is well-designed for Phase 1. A few observations for when this phase begins:

1. **GIN indexes on `schema_definition` and `validation_rules` JSONB** — correct for schema-content queries, but GIN index writes are expensive. Monitor write throughput carefully on high-telemetry deployments.
2. **`telemetry_logs` has no partition key** — the HLD notes "Table partitioning (manual, Phase 2)" but the `created_at DESC` index will degrade as the table grows. Add `PARTITION BY RANGE (created_at)` with monthly partitions from day one. It is much harder to add partitioning to a large existing table.
3. **`raw_payload_hash VARCHAR(64)` in telemetry** — storing even a hash of the LLM payload may have privacy implications. Ensure this is documented in the SECURITY policy and opt-out is possible via config.
4. **`drift_score FLOAT` in telemetry** — the HLD stores a single drift score, but the KSD drift engine (`ks_drift.py`) produces `DriftResult(statistic, p_value, drift_detected, n_reference, n_sample)`. The schema should store the full result as JSONB, not just one float.

---

## 10. Scalability Analysis

### 10.1 Current Scaling Model

The Congine SDK is an **in-process engine**. It scales horizontally with the host process — one `ServiceContainer` per process, one `LFUCache` per process, one `BoundedValidationExecutor` pool per process. This is the correct architecture for a latency-critical hot-path SDK.

The fundamental scaling model is:

```
Throughput = (max_workers * 1000) / avg_validation_ms

At defaults (10 workers, ~0.5ms avg rule-engine validation):
  Peak throughput ≈ 20,000 validations/second per process

With semantic validation (10 workers, ~30ms avg jsonschema validation):
  Peak throughput ≈ 333 validations/second per process
  (load shedding kicks in at capacity=20 outstanding)
```

### 10.2 Scaling Bottlenecks

**Bottleneck 1: Schema Cache Size vs Working Set**
The default cache capacity is 500 schemas (`CONGINE_CACHE_CAPACITY=500`). For most deployments, this is more than sufficient. For an enterprise customer with 1000+ active contracts, LFU eviction will kick in and schema lookups will occasionally miss the cache, causing synchronous re-fetches. The cache capacity should be configurable per deployment, and the `cache_entries` health metric should be monitored against `capacity` proactively.

**Bottleneck 2: Snapshot File Contention**
Under N=32 workers on a single host, the `portalocker LOCK_NB` (non-blocking) lock on `save_snapshot` means 31 workers skip the write and proceed. This is correct behavior. However, if the snapshot file is on NFS or a slow network-attached filesystem, even `load_snapshot()` can take 100ms+. Ensure `snapshot_dir` is always on a local disk.

**Bottleneck 3: Telemetry Queue Depth Under Spike Load**
At 20,000 validations/second peak, the telemetry queue fills 10,000 slots in 0.5 seconds. The drain worker batches at ≤100 events per POST. At a 5ms POST latency (local network), drain throughput is ≤20,000 events/second — borderline. Under sustained peak load, the queue will fill and events will be dropped. Recommendation: either raise `telemetry_queue_size` to 50,000 or increase the batch size to 500.

**Bottleneck 4: BoundedValidationExecutor and GIL**
The validation pool uses `ThreadPoolExecutor`. For pure-Python rule evaluation, GIL contention at high thread counts limits actual parallelism. Beyond ~8 workers on a GIL-bound workload, adding more workers produces diminishing returns. The `max_workers=10` default is appropriate. For CPU-intensive semantic validation (jsonschema), consider a `ProcessPoolExecutor` variant as a Phase 2 option (new L4 adapter, no domain change required).

### 10.3 Horizontal Scaling Readiness

| Concern | Current State | Phase 1 Need |
|---|---|---|
| Multi-process boot burst | ⚠️ Thundering herd | Single-flight coordination (D-7) |
| Shared schema cache | ✅ Per-process LFU (correct) | Optional Redis adapter (Phase 2) |
| Cross-process telemetry dedup | N/A (each process sends independently) | Server-side dedup on contract_version+timestamp |
| Distributed circuit breaker | ❌ Not applicable for in-process | In-memory per-process is correct for Phase 1 |
| Container/K8s compatibility | ⚠️ Liveness probe stall risk | Fixed by circuit breaker + non-blocking bootstrap |

---

## 11. Monetization Readiness Assessment

### 11.1 The Three Paths to Value

**Path A: Open-Source Release (community-first)**
Release `congine_core` as Apache-2.0 or MIT. Build community adoption. Monetize via a managed control plane (SaaS Contract Registry + Dashboard).

*Blockers today:* No LICENSE, broken Python floor, no README, no CI. These are all fixable in 2–3 days of work. Everything else (circuit breaker, IValidationRunner, etc.) is engineering excellence but not a launch blocker for OSS.

*Timeline to OSS-ready:* **1 week** of focused work on P0 blockers + README + CI matrix.

**Path B: Commercial SDK (direct sale to enterprises)**
License the SDK commercially (source or binary). Sell to enterprises that need LLM output governance.

*Blockers today:* No LICENSE (legally can't sell without one), no circuit breaker (enterprises will not deploy a component that can stall their application boot), HTTPS default is wrong, no README/documentation.

*Timeline to commercial-ready:* **3–4 weeks** — all P0 + P1 items, plus documentation, plus BYOM (the key enterprise differentiator).

**Path C: Sell the Company/Project**
Sell the IP, codebase, or company to a larger AI tooling vendor.

*Blockers today:* Same as Path B, plus: the HLD-to-SDK naming divergence needs reconciliation (a buyer will ask "which document is the real architecture?"), and the AMCE project name vs Congine SDK naming needs to be settled.

*Timeline to acqui-hire/acquisition ready:* **4–6 weeks** — above, plus Phase 1 backend sketch implemented as a working demo.

### 11.2 The Key Differentiators (What Makes This Sellable)

Three features make this SDK genuinely differentiated from naive "validate LLM output" libraries:

1. **O(1) LFU cache with bounded concurrency** — not a nice-to-have; this is what makes sub-15ms validation physically possible. Most comparable libraries use dict-based caches with no eviction and no concurrency control.

2. **Hexagonal architecture with dependency inversion** — the ports/adapters pattern means a buyer can replace any component (cache, transport, event bus) without touching business logic. This is a serious engineering choice that signals long-term maintainability.

3. **BYOM healing loop** (when built) — the `validate → fail → heal via own model → re-validate` loop is the highest-value enterprise feature. It transforms the SDK from a "rejection gate" into a "correction engine." This is the feature that justifies a premium price point.

### 11.3 What Must Be Built Before Monetization

The minimum viable "sellable" state, ordered by dependency:

```
Week 1 (P0 Blockers — must ship first):
  ├─ Fix D-1 (except syntax)                    [5 min]
  ├─ Fix D-2 (nx test target)                   [15 min]
  ├─ Add LICENSE (Apache-2.0)                   [1 hr]
  ├─ Add circuit breaker                        [1 day]
  └─ Add CI version matrix                      [0.5 day]

Week 2 (Architectural cleanup — before API freeze):
  ├─ Add IValidationRunner L1 port              [0.5 day]
  ├─ Remove ValidationTimer export             [30 min]
  ├─ Rename repositories/ → ports/             [0.5 day]
  ├─ Fix HTTPS default                         [30 min]
  └─ Fix thundering herd (single-flight boot)  [0.5 day]

Week 3 (Production hardening):
  ├─ Raise default timeout to 100ms            [30 min]
  ├─ Add dropped_total counter                 [0.5 day]
  ├─ Guard drift call                          [1 hr]
  ├─ Add re2 extra OR remove claim             [30 min]
  ├─ Remove stale egg-info                     [15 min]
  └─ Single-source __version__                 [15 min]

Week 4 (Documentation & Product):
  ├─ Write real README                         [1 day]
  ├─ Write SECURITY.md                         [0.5 day]
  ├─ Write CHANGELOG.md                        [0.5 day]
  └─ Build FileContractRepository              [1 day]

Week 5-6 (Differentiator feature):
  └─ Build BYOM healing loop                   [2-3 days]
      ├─ IModelClient L1 port
      ├─ OllamaClient / OpenAI-compatible L4 adapter
      └─ HealContractUseCase L3
```

---

## 12. Prioritized Action Plan

### Tier 1: Hard Blockers — Fix Before Any External Use

These must be resolved before any external reviewer, investor, or customer sees the codebase:

| # | Action | File | Effort | Impact |
|---|---|---|---|---|
| 1 | Fix `except (OSError, NotImplementedError, AttributeError):` syntax | `tests/adversarial/test_remediations.py:189` | 5 min | Unbreaks Python 3.10–3.13 |
| 2 | Add `--extra dev` to nx test target | `project.json:20` | 15 min | Unbreaks CI |
| 3 | Add `LICENSE` file (Apache-2.0) | root | 1 hr | Unblocks all distribution |
| 4 | Implement `CircuitBreaker` (L4) and integrate into `bootstrap()` and background sync | `infrastructure/circuit_breaker.py`, `dependency_injection.py` | 1 day | Fixes 10s boot stall |
| 5 | Add CI matrix (Python 3.10–3.14) + ruff + mypy gates | `.github/workflows/ci.yml` | 0.5 day | Proves the floor claim |

### Tier 2: Architectural Debt — Fix Before API Freeze

These must be resolved before the package version is published to PyPI or any documentation is written:

| # | Action | File | Effort | Impact |
|---|---|---|---|---|
| 6 | Add `IValidationRunner` L1 port | `ports/validation_runner.py` (new) | 0.5 day | Completes the hexagon |
| 7 | Update `ValidateContractUseCase` to use `IValidationRunner` | `usecases/validate_contract_usecase.py` | 0.5 day | Removes L3→L4 concrete coupling |
| 8 | Remove `ValidationTimer` from all exports | `infrastructure/__init__.py`, `congine_core/__init__.py` | 30 min | Removes silent correctness trap |
| 9 | Rename `repositories/` → `ports/` | all imports | 0.5 day | Name matches meaning before API ossifies |
| 10 | Change HTTPS default to `True` | `config.py:107` | 30 min | Secure default |
| 11 | Implement single-flight boot coordination | `usecases/sync_contracts_usecase.py` | 0.5 day | Fixes thundering herd |

### Tier 3: Production Hardening — Fix Before Enterprise Deployment

| # | Action | File | Effort | Impact |
|---|---|---|---|---|
| 12 | Raise default `validation_timeout_ms` to 100 | `config.py:85` | 30 min | Stops false-positive timeouts |
| 13 | Add `dropped_total` counter to `QueueEventBus` + `health()` | `infrastructure/queue_event_bus.py`, `dependency_injection.py` | 0.5 day | Telemetry loss visibility |
| 14 | Guard `evaluate_drift` with `CongineConfigurationError` | `dependency_injection.py:212` | 1 hr | Prevents unguarded ImportError |
| 15 | Add `re2` extra to `pyproject.toml` OR remove claim from `ARCHITECTURE.md` | `pyproject.toml` / `ARCHITECTURE.md` | 30 min | Honest capability claim |
| 16 | Remove stale `*.egg-info` from VCS | `.gitignore`, repo | 15 min | Clean packaging |
| 17 | Single-source `__version__` via `importlib.metadata` | `congine_core/__init__.py` | 15 min | No version divergence |
| 18 | Add log redaction framework to `StructuredLogger` | `infrastructure/logger.py` | 1 day | PII safety in multi-tenant logs |

### Tier 4: Phase 0 Feature Completion

| # | Action | File | Effort | Impact |
|---|---|---|---|---|
| 19 | Write `README.md` with install, quickstart, config table, architecture diagram | `README.md` | 1 day | Required for all distribution paths |
| 20 | Write `SECURITY.md` | `SECURITY.md` | 0.5 day | Enterprise trust signal |
| 21 | Implement `FileContractRepository(IContractRepository)` | `infrastructure/file_contract_repository.py` | 1 day | Local-first/GitOps story |
| 22 | Reconcile AMCE HLD naming with Congine Blueprint | HLD document | 0.5 day | Single authoritative architecture |

### Tier 5: Phase 1 Preview Features (Post-Phase-0)

| # | Action | File | Effort | Impact |
|---|---|---|---|---|
| 23 | Implement `IModelClient` L1 port | `ports/model_client.py` | 0.5 day | BYOM seam |
| 24 | Implement `OllamaClient` / `OpenAICompatibleClient` L4 adapters | `infrastructure/` | 1 day | BYOM transport |
| 25 | Implement `HealContractUseCase` L3 | `usecases/heal_contract_usecase.py` | 1–2 days | BYOM healing loop (the differentiator) |
| 26 | Write OpenAPI spec for Contract Registry API | `api/openapi.yaml` | 0.5 day | Phase 1 backend alignment |
| 27 | Implement breaker state persistence (fast cold-boot fail-fast) | `infrastructure/circuit_breaker.py` | 0.5 day | Boot time under persistent outage |

---

## 13. What "Phase 0 Done" Actually Means

Phase 0 "done" does not mean feature-complete — it means **production-safe and independently deployable**. The following checklist defines the exit criteria:

### 13.1 Hard Exit Criteria (All Must Pass)

- [ ] `python -m pytest` passes on CPython 3.10, 3.11, 3.12, 3.13, 3.14 (full matrix in CI)
- [ ] `ruff check src/ tests/` passes with zero warnings
- [ ] `mypy src/` passes with zero errors
- [ ] `LICENSE` file present (Apache-2.0 or MIT)
- [ ] `README.md` present with install instructions, quickstart, config table
- [ ] `SECURITY.md` present with disclosure policy
- [ ] `CircuitBreaker` implemented and integrated — `bootstrap()` completes in <500ms even against a hung control plane
- [ ] `IValidationRunner` L1 port implemented — `ValidateContractUseCase` has no L4 concrete references
- [ ] `ValidationTimer` removed from all public exports
- [ ] `repositories/` renamed to `ports/`
- [ ] Default `require_https=True` for non-local planes
- [ ] `dropped_total` exposed in `health()`
- [ ] `evaluate_drift` guarded against missing `[stats]` extra
- [ ] `*.egg-info` removed from VCS

### 13.2 Soft Criteria (Strongly Recommended Before Publish)

- [ ] Single-flight boot coordination implemented (thundering herd fixed)
- [ ] Default `validation_timeout_ms` raised to 100
- [ ] `re2` declared as optional extra (or claim removed)
- [ ] `__version__` single-sourced via `importlib.metadata`
- [ ] `FileContractRepository` implemented (local-first story)
- [ ] AMCE HLD document reconciled with Congine Blueprint naming

### 13.3 What This Enables

When all hard criteria pass:
- **Open-source launch** is unblocked — the package can be published to PyPI under a real license with a real CI badge and a real Python floor claim
- **Enterprise pilots** are unblocked — a paying customer can deploy without risk of boot stalls, credential leaks, or false-positive validation timeouts
- **Investor/acquirer demos** are unblocked — the architecture is clean, documented, and self-evidently production-quality
- **Phase 1 backend work** can begin in parallel — the SDK's L1 ports are frozen and the NestJS backend just needs to satisfy the contract bundle and telemetry API shapes

The core insight from this analysis is that **Phase 0 is structurally sound but operationally incomplete**. The validation logic, concurrency model, caching strategy, and hexagonal architecture are all genuinely strong — they are worth preserving exactly as they are. The remaining work is not about changing what the engine does; it is about making it provably safe to run, honest about its capabilities, and clean enough that any engineer (or customer) can pick it up and trust it.

---

*Analysis generated from: Congine SDK Phase 0 Engineering Blueprint (66pp), Independent Adversarial Audit (phase0-congine-newAudit.md, 179 lines, CPython 3.14.2, 201 passed / 2 skipped), AMCE System Design HLD+LLD. All file and line references are traceable to the source documents.*
