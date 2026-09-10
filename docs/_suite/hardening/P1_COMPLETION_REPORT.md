# P1 Structural Hardening — CLOSED

Implementation date: 2026-08-21  
Closure date: 2026-08-22  
P0 source commit: `1258a982b7dca2caac38de07256a8339575edbf6` (branch `P0_CLOSED_PHASE0`)  
P1 closure branch: `P1_CLOSED_PHASE1`

> **On the closure SHA.** Task §27 asked for the final P1 commit SHA in this
> file. That is self-referential — a commit cannot contain its own hash — so by
> founder amendment the closure SHA is recorded in the terminal closure evidence
> and the closure summary instead. This file records the P0 source commit and
> the closure branch, both of which are stable.

**Read [Final P1 Closure](#final-p1-closure) for the authoritative closure
state.** Everything above it describes the implementation as it stood on
2026-08-21, before the closeout audit; it is retained as the implementation
record. Where the two disagree, the closure section governs — in particular, the
architecture gate described below was found to be enforcing a weaker rule than
claimed, and was corrected during closure.

## Status

The remaining P1 structural-hardening implementation is complete. All locally
available Nx gates pass in the locked Python 3.14.6 environment. CI now applies
the same lint, test, strict typecheck, architecture, and offline-example gates
to Python 3.11, 3.12, and 3.13.

The exact 3.11–3.13 matrix was not executed locally: this host only provides
Python 3.14.6, and two attempts to provision uv-managed 3.11–3.13 interpreters
stalled before installing an interpreter. No CI run was created because this
work was required to remain uncommitted. Matrix execution is therefore an
external verification follow-up, not a claimed local result.

The authoritative P0 baseline remains **478 passed, 1 skipped**. Historical
436/1 and 350/1 snapshots are pre-closeout evidence, not the P1 baseline.

## Delivered changes

### Blocking structural gates

- Added mypy and `types-jsonschema` to the SDK `dev` extra through uv and
  updated the workspace lockfile.
- Added strict mypy configuration for production source only
  (`src/congine_core`) with Python 3.11 as the language floor.
- Added the blocking Nx `typecheck` target and removed the CI `|| true` escape
  hatch.
- Added a standard-library AST architecture checker and Nx `architecture`
  target. It enforces same-layer/inward runtime imports across L0–L5, exempts
  only the root public export aggregator as a source, ignores genuine
  `TYPE_CHECKING` edges, rejects imports through the root aggregator, and checks
  literal `__import__`/`importlib.import_module` edges. Tests cover aliases,
  shadows, nested function/class scopes, and collision attempts.

### Runtime composition contracts

- `ValidateContractUseCase` now validates schema storage, validator, event bus,
  logger, and validation runner roles during construction.
- `SyncContractsUseCase` now validates schema storage, repository, logger, and
  an optional supplied circuit breaker.
- `CompositeValidator` now validates rule and semantic validator roles.
- Invalid implementations raise `CongineConfigurationError` naming both the
  rejected role and expected Protocol. Test fakes now implement their complete
  declared Protocols.

### Transactional lifecycle

- Container construction now delays worker starts until the graph is complete
  and rolls back every acquired owner if any construction/start/finalizer step
  fails.
- Normal shutdown unregisters `atexit` callbacks owned by the validation
  executor, LFU cache, queue event bus, and background sync worker.
- Container close is terminal, idempotent, thread-safe, and bounded. Concurrent
  close callers observe completion without duplicating teardown.
- Shutdown rejects new producer work before stopping consumers. The event-bus
  worker/finisher owns final drain and HTTP-client closure, serialized against
  shipping, so caller-side close cannot race a live ship operation.
- Queue publication remains non-raising by port contract; publication after
  shutdown is rejected by dropping and counting the event.
- Fault-injection tests cover failures after each acquisition and after live
  workers/hooks start, and prove later clean construction still succeeds.

### Safety and cleanup

- Added `CongineLifecycleError(CongineBaseException)` and exported it from the
  public package root.
- Added `ServiceContainer.closed` and `ensure_open()`. Container entry points,
  guards, and LangChain callbacks fail fast once close begins. Default and
  tenant registries replace closed cached containers.
- Replaced sanitizer backreference matching with the RE2-only expression
  `(?:\".*?\"|'.*?'|\b\d{4,}\b)` while preserving masking output.
- Added representative regression, deterministic 10,000-case equivalence,
  large adversarial, and end-to-end telemetry sanitizer tests. Independent
  review also found no divergence across 200,000 mixed inputs.
- Deleted the unused `ValidationTimer` implementation, its dedicated tests,
  and remaining references.
- Removed the unreachable sync keyword-warning state while preserving the
  public admission scanner and fail-closed `admit_contract` writer guard.

### LangChain and example hardening

- Callback buffers, per-run results, and `last_result` now share lock-backed
  state boundaries.
- Every `CongineBaseException` propagates, including strict-validation,
  missing-contract, and lifecycle failures.
- Unexpected host callback failures—including malformed callback values and a
  failing host logger—are logged best-effort and contained with `None`.
- The provider-free example fallback now emits the contract-valid `escalate`
  decision.
- Added a cross-platform smoke runner that fixes the local contract path,
  enables semantic validation, disables telemetry/background services, clears
  the Google API key, runs the real guard, and closes its container.
- Added the non-cached Nx `examples` target and run it on every supported Python
  CI matrix leg. The example now directly declares Pydantic and no longer
  declares the unused DeepAgents package.

### Documentation

- Updated the SDK README for terminal lifecycle, the exported lifecycle error,
  LangChain exception behavior, and the verified offline command.
- Reconciled the LangChain example README with the functions and output the
  shipped example actually provides.
- Added only a supersession notice to the stale current-architecture document;
  its full rewrite remains P3 work.
- Historical Phase 0 dossier and GAP evidence files were not edited.

## Public interface and behavior changes

| Surface | P1 behavior |
| --- | --- |
| `CongineLifecycleError` | New exported SDK-root exception derived from `CongineBaseException` |
| `ServiceContainer.closed` | Read-only terminal-state inspection |
| `ServiceContainer.ensure_open()` | Raises `CongineLifecycleError` after shutdown begins |
| `ServiceContainer.close()` | Terminal, idempotent, thread-safe, bounded teardown |
| Use-case/composite construction | Rejects non-conforming runtime port implementations immediately |
| LangChain callbacks | Propagate SDK-domain failures; contain unexpected non-SDK failures |
| Queue event bus after stop | Rejects new events by drop/count without violating the non-raising port |

No schema, `ValidationResult`, admission, contract-identity, or wire format was
changed.

## Verification evidence

| Gate | Result |
| --- | --- |
| `npm exec nx -- show project congine-sdk --json` | One project; `lint`, `test`, `typecheck`, `architecture`, and `examples` resolve |
| `npm exec nx -- run congine-sdk:lint --skipNxCache` | Pass; Ruff format and checks clean |
| `npm exec nx -- run congine-sdk:typecheck --skipNxCache` | Pass; 38 production source files, zero issues |
| `npm exec nx -- run congine-sdk:architecture --skipNxCache` | Pass; 38 source files scanned and 17 checker tests passed |
| `npm exec nx -- run congine-sdk:examples --skipNxCache` | Pass; offline guarded fallback validated |
| `npm exec nx -- run congine-sdk:test --skipNxCache` | **540 passed, 1 skipped** (541 collected) on Python 3.14.6 |
| P1 lifecycle focus | 10 passed, including active-worker/hook rollback |
| LangChain focus | 21 passed |
| CI/project parsing | GitHub workflow YAML and Nx project JSON valid |
| `git diff --check` | Pass |

The full Nx suite includes the existing P0 result-semantics, admission,
configuration-parity, deterministic-validation, and load-shedding regressions.
The total changed because four obsolete timer tests were removed and new P1
tests were added; invariant coverage and exit status are authoritative.

## Explicit deferrals

P1 does not claim completion of:

- P1.5 three-axis result semantics;
- schema-storage admission enforcement or an `AdmittedContract` boundary;
- version-aware storage/contract identity;
- semantic-validation budgets;
- supply-chain remediation/gates (the pre-change npm install reported seven
  high-severity findings);
- expanded platform execution beyond the configured Python 3.11–3.13 CI
  matrix;
- P3 full documentation and architecture reconciliation.

Retained references to internal components after their owning container closes
remain unsupported.

## Worktree integrity

- HEAD did not move; no commit was created.
- Nothing was staged.
- The three pre-existing user-owned SDK audit deletions remain deleted and were
  neither restored nor edited.
- All P1 implementation and evidence files remain uncommitted for review.

## P1 IMPLEMENTATION COMPLETE

Local gates are closed. Python 3.11–3.13 execution remains pending on the
configured CI matrix: managed-interpreter provisioning stalled on this host,
and no CI run can exercise uncommitted work.

---

# Final P1 Closure

**Closure date:** 2026-08-22  
**Pre-closeout HEAD:** `1258a982b7dca2caac38de07256a8339575edbf6`  
**Final branch:** `P1_CLOSED_PHASE1`  
**Environment:** Python 3.14.6 · uv 0.12.5 · Node v24.18.0 · npm 11.16.0 · Windows 11

## The defect this closeout found

The pre-closeout report claimed the architecture gate enforced "same-layer/inward
runtime imports". It did — and that was the problem. The checker approved any
edge where `target_layer <= source_layer`, which is **not** CONGINE's dependency
model. Because `2 < 4` and `3 < 4`, `L4 → L2` and `L4 → L3` were silently
permitted, and internal `TYPE_CHECKING` imports were skipped entirely.

The gate reported zero violations, so the green result proved nothing. Seven
forbidden edges were live in the tree, two of them runtime imports:

| Edge | Site | Kind |
| --- | --- | --- |
| L4→L2 | `infrastructure/jsonschema_validator.py` — `BreachDetail` | runtime |
| L4→L2 | `infrastructure/ks_drift.py` — `DriftResult` | runtime |
| L4→L2 | `infrastructure/queue_event_bus.py` — `TelemetryEvent` | TYPE_CHECKING |
| L4→L2 | `infrastructure/noop_event_bus.py` — `TelemetryEvent` | TYPE_CHECKING |
| L1→L2 | `ports/event_bus.py` — `TelemetryEvent` | TYPE_CHECKING |
| L1→L2 | `ports/semantic_validator.py` — `BreachDetail` | TYPE_CHECKING |
| L4→L3 | `infrastructure/background_sync.py` — `SyncContractsUseCase` | TYPE_CHECKING |

Two self-tests encoded the wrong rule directly: one asserted that an L4 module
importing both `usecases.sync` and `domain.models` was clean, and another
asserted `TYPE_CHECKING` outward imports were allowed.

## How it was resolved — structurally, with no allowlist

Six of the seven edges shared one root cause: the canonical value contracts were
misfiled as L2 judgment logic. They were reclassified rather than exempted.

### P1 architectural clarification — L0 owns value contracts

`domain/models.py` → **`congine_core/models.py` (L0 kernel)**. The module is
pure frozen dataclasses and a `StrEnum` with zero internal imports, so it already
satisfied L0; only its filing was wrong. `BreachDetail`, `ValidationResult`,
`TelemetryEvent`, `DriftResult` and `DegradedReason` are the vocabulary every
layer exchanges, which is why ports and infrastructure legitimately needed them.

The layer split is now explicit and recorded — **not deferred to P3**:

- **L0 owns pure canonical cross-layer value contracts** — `config`,
  `exceptions`, `security_limits`, `pii_sanitize`, `models`.
- **L2 continues to own deterministic judgment and rules** — `RuleEngine`, the
  validators, contract admission, schema vocabulary.

`congine_core/domain/models.py` is retained as a **compatibility re-export**. It
does not weaken the gate: the checker resolves that path by directory, so it
keeps its **L2** identity and an L1/L4 module importing through it still fails.
`tests/architecture/test_layer_dependencies.py::test_infrastructure_cannot_reach_domain_through_the_compatibility_shim`
pins exactly that.

The seventh edge was resolved with a narrow port: `ports/sync_runner.py` declares
`ISyncRunner` (one method, `sync_once() -> int`), and `BackgroundSyncWorker` is
typed against it, making the edge `L4 → L1`. `SyncContractsUseCase` satisfies it
structurally and was not modified.

### Public behaviour

Documented and root-level public symbols and their semantics are **unchanged**.
`congine_core.__all__` and `congine_core.domain.__all__` are unchanged by the
reclassification, and `from congine_core import BreachDetail`,
`from congine_core.domain import BreachDetail`, `from congine_core.domain.models
import BreachDetail` and `from congine_core.models import BreachDetail` all
resolve to the same class object.

Recorded honestly: the **canonical module path changed** from
`congine_core.domain.models` to `congine_core.models` — `BreachDetail.__module__`
now reads `congine_core.models`. Code that asserts on `__module__`, or that
pickles these types across a version boundary, would observe the change. The old
import path itself continues to work.

The only public-surface addition is `ISyncRunner` on `congine_core.ports`.
(`CongineLifecycleError` was added by the P1 implementation, above.)

## Architecture dependency matrix — now enforced explicitly

| Layer | May import |
| --- | --- |
| L0 Kernel | L0 |
| L1 Ports | L0, L1 |
| L2 Domain | L0, L1, L2 |
| L3 Use Cases | L0, L1, L2, L3 |
| L4 Infrastructure | L0, L1, L4 |
| L5 Adapters / Composition | L0, L1, L2, L3, L4, L5 |

`_ALLOWED_DEPENDENCIES` in `tools/check_architecture.py` states this as a matrix;
the numeric comparison is gone. The public-aggregator pseudo-layer appears in no
row, so an internal module importing `from congine_core import ...` is rejected
from every layer — §7's rule now holds structurally rather than by a special case.

Verified rejections and permissions, each with a self-test:

| Edge | Verdict | | Edge | Verdict |
| --- | --- | --- | --- | --- |
| L0→L2 | REJECTED | | L3→L4 | REJECTED |
| L0→L4 | REJECTED | | L4→L0 | ALLOWED |
| L1→L2 | REJECTED | | L4→L1 | ALLOWED |
| L2→L1 | ALLOWED | | **L4→L2** | **REJECTED** |
| L2→L4 | REJECTED | | **L4→L3** | **REJECTED** |
| L3→L2 | ALLOWED | | L5→L4 | ALLOWED |

All 36 source/target combinations are asserted, in both runtime and
`TYPE_CHECKING` form (72 cases), alongside the retained tests for import
aliases, nested functions, nested classes, literal `__import__`, literal
`importlib.import_module`, package-root aggregator misuse, and shadow/collision
attempts. The checker suite grew from **17 to 90 tests**.

**The gate was falsified, not merely observed passing.** Re-injecting the three
representative removed edges into a scratch copy produced exactly three
violations — `L4→L3` runtime, `L4→L2` through the compatibility shim, and
`L1→L2` under `TYPE_CHECKING` — all of which the previous rule accepted silently.

## TYPE_CHECKING policy — explicit, no bypass

Internal CONGINE imports under `if TYPE_CHECKING` are **architectural
dependencies and are enforced against the identical matrix**. A module that needs
the concrete type of an outer implementation knows about that implementation
whether or not the import survives to runtime.

The guard is still resolved, for two reasons: the `else` arm of an
`if TYPE_CHECKING` is ordinary runtime code and must not be mis-tagged, and the
diagnostic reports which edges were erased. `LayerViolation.type_checking` is
**diagnostic only and never an exemption**.

**There are zero allowlist entries and zero TYPE_CHECKING exemptions.** Every
edge that would have required one was removed structurally. §24's "no blanket
undocumented architecture bypass" therefore holds by construction rather than by
documentation.

## Final gate results

All run with `--skipNxCache`.

| Gate | Result |
| --- | --- |
| `nx show project congine-sdk --json` | One project; `architecture`, `examples`, `lint`, `test`, `typecheck` resolve |
| `nx run congine-sdk:lint` | **Pass** — 99 files formatted, all Ruff checks passed |
| `nx run congine-sdk:typecheck` | **Pass** — strict mypy, zero issues in 40 production source files |
| `nx run congine-sdk:architecture` | **Pass** — 40 source files, **90 checker tests** |
| `nx run congine-sdk:examples` | **Pass** — offline guarded fallback validated |
| `nx run congine-sdk:test` | **613 passed, 1 skipped** |
| `git diff --check` | **Pass** |

**Authoritative test count: 613 passed, 1 skipped** (was 540/1 pre-closeout;
+73 from the parametrised matrix coverage). The single skip is unchanged:
`test_symlinked_snapshot_is_refused`, symlinks not permitted on this platform.
No test was weakened, disabled or relaxed to reach this state.

CI contains **no** `mypy ... || true`. mypy config is `strict = true`,
`python_version = "3.11"`, `files = ["src/congine_core"]`, with no
`ignore_errors` and no broad production exclusions.

## Verified P1 subsystems

Verification-first: each was re-run and preserved, not rewritten.

| Area | Evidence |
| --- | --- |
| Runtime port checks | 33 passed — `CongineConfigurationError` names rejected role and expected Protocol |
| Transactional composition / rollback | Fault-injection suite green; no leaked worker, client or hook |
| Terminal lifecycle | `close()` terminal, idempotent, thread-safe, bounded; use-after-close raises `CongineLifecycleError`; atexit hooks unregistered |
| Closed-container registry | Default and tenant registries replace rather than return closed containers; one effective replacement under concurrency |
| Telemetry shutdown | 52 passed across the shutdown scenarios; implementation **preserved**, not rewritten |
| RE2 sanitizer | Repository-owned deterministic tests pass; `pii_sanitize.py` imports `re2` only — no stdlib `re` on the sanitizer path |
| `ValidationTimer` | Absent from `src/`, `tests/` and `examples/`; timeout invariant covered by the bounded executor |
| Admission surfaces | `find_unenforced_keywords`, `admit_contract`, admission tests and the production writer guard all intact |
| LangChain | 21 focused tests — CONGINE exceptions propagate, foreign failures contained, concurrent-callback state clean |
| Offline example | Real Nx target, real public guard, contract-valid `escalate` fallback, container closed |

## P0 trust baseline — re-run

The P0 harnesses were **never committed as scripts**, and the P0 determinism hash
survives in `P0_COMPLETION_REPORT.md` only truncated (`3ab5ce02…`). They have
been reconstructed and **committed** as `libs/congine-sdk/tools/p0_evidence/`, so
P1.5 and P2 re-run identical methodology instead of reconstructing it again:

```
uv run --package congine-sdk python -m tools.p0_evidence
```

**Result: 5/5 constitutional properties hold (exit 0).**

| Evidence | Result |
| --- | --- |
| Determinism, N=5000 | **1 distinct canonical verdict**; `is_enforced=True`, 3 breaches |
| Admission preflight | **3/3 = 100%** admitted, STRICT mode |
| False-safety corpus | **4/4 REFUSED, 0 false PASS** |
| Load shedding | **2000/2000 → `LoadShedError`**; deadline overrun → plain `TimeoutError`, not a `LoadShedError` |
| Configuration parity | **5/5** enum fields canonical under both doors; all default fields agree |

Load-shed rejection latency, recorded as evidence only and deliberately not
tuned: p50 1.60 µs, p90 1.70 µs, p99 5.20 µs.

### Two honest caveats

**The determinism hash is a new baseline, not a match.** The canonical
serialisation P0 used was never recorded, so the hash below comes from a form
defined here (status, degraded state, `is_enforced`, `is_pass`, and ordered
breaches; `duration_ms` excluded as wall clock, not judgment). It is therefore
**not comparable** to P0's truncated `3ab5ce02…`, and no prefix match should be
claimed. What was verified is the invariant that actually matters — one canonical
verdict across N=5000 — which holds. Future phases compare against:

```
715725383efa751299422a3dbe990c34c4c47d657e73ca90a03088ddf7f36dfa
```

**The admission preflight configuration was corrected during closure, not the
admission rule.** A first run reported 1/3, refusing two contracts on
`minLength`/`maxLength` as `unsupported_keyword`. That was a harness error: those
are semantic keywords, and the shipped example sets
`CONGINE_SEMANTIC_VALIDATION=true` — provider-free (no LLM credentials) and
semantic validation are independent switches, since the semantic evaluator is a
local JSON Schema evaluator. Judging the contracts under the configuration they
actually ship with yields 3/3. **Admission was not relaxed**; the harness now
reads the setting out of `smoke.py` and raises rather than guessing if it
disappears, so it cannot silently drift from what ships.

The false-safety corpus gained a fourth case covering the subtler trap: with
semantic validation **on** but format checking **off**, a `format` clause is
still unenforced and must still be refused. It is.

## Unchanged deferrals

P1 closed means P1's responsibilities are complete. It does **not** mean CONGINE
is enterprise-release complete. These remain open and are not claimed fixed:

- the raw `schema_storage.put()` admission bypass — universal admission behind
  `ISchemaStorage`, and an `AdmittedContract`/`CompiledContract` storage
  boundary, remain **DEFERRED**;
- version-aware storage / contract identity;
- partial-enforcement and richer three-axis result semantics;
- semantic-validation budget work;
- supply-chain remediation, SBOM and security release gates (the pre-change npm
  install reported seven high-severity findings);
- cross-version release evidence;
- full architecture and documentation reconciliation (P3). `ARCHITECTURE_CURRENT.md`
  keeps its supersession warning until then.

Retained references to internal components after their owning container closes
remain unsupported.

At P1 close, contract admission stands as: **DONE** — public scanner, public
admission API, production sync admission, CI guard against new unadmitted
production writers. **DEFERRED** — universal admission behind `ISchemaStorage`,
the raw `put()` bypass, the `AdmittedContract`/`CompiledContract` boundary, and
version-aware storage identity.

## P2 verification boundary

Python 3.11–3.13 execution is **P2 scope and does not block P1 closure**. This
host provides only Python 3.14.6 and uv-managed interpreter provisioning stalled.
P1's obligation is correct CI configuration and correct blocking local gates,
both of which are met; P2 supplies the authoritative cross-version and release
evidence.

**No cross-version determinism is claimed.** The determinism result above is
single-environment evidence.

## Phase status

- **P1 — CLOSED**
- **P1.5 — NOT STARTED**
- **P2 — NOT STARTED**
- **P3 — NOT STARTED**
- **Phase A — NOT STARTED**
- **Phase B — NOT STARTED**
- **Phase C — NOT STARTED**

## Next Authorized Phase

**P1.5 — Semantic Validation Safety**, scoped to the hardening package only:

- **P1.5-01** honest semantic-validation warnings
- **P1.5-02** separate native/semantic budget policy
- **P1.5-03** complexity/admission prototype
- **P1.5-04** compiled-validator caching investigation

P1.5 **must start from the P1 CLOSED commit** on `P1_CLOSED_PHASE1` — not from
P0 HEAD, and not from a dirty worktree.

P2 follows P1.5: release verification, Python matrix, Linux CI, determinism
golden corpus, branch coverage, supply-chain gates, SBOM, release benchmarks.
