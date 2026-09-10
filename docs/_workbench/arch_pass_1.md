## 2. Drift report — what changed since 2026-06-14

### 2.1 The module-count discrepancy, resolved

The two prior documents disagree. Both were measuring the same tree; they were counting different things.

| Source | Claim | Verdict |
|---|---|---|
| `docs/context/01_SYSTEM_STATE.md:7` | "33 source modules across 6 tiers" | **WRONG** — no counting rule over the tree at that commit yields 33 |
| `docs/system-analysis/01_FILE_INVENTORY.md:5` | "36 Python source modules" | **CONFIRMED exactly** |

Verification (`git ls-tree -r --name-only 051ceae -- libs/congine-sdk/src/congine_core`, the last
commit before the 2026-06-14 doc date):

| Counting rule | Count at 2026-06-14 baseline | Count today |
|---|---|---|
| All `.py` files under the package root | **36** | **37** |
| Excluding all six `__init__.py` | 30 | 31 |
| Excluding only the package-root `__init__.py` | 35 | 36 |

`01_FILE_INVENTORY.md`'s 36 is the "all `.py` files" figure and is exact. `01_SYSTEM_STATE.md`'s 33
matches none of these rules. The only reconstruction that produces 33 is *36 minus the three
`__init__.py` files that are pure re-export shims* (`domain/__init__.py`, `ports/__init__.py`,
`usecases/__init__.py`), keeping the three that carry logic (the package root's `__version__`
resolution, `adapters/__init__.py`'s lazy `__getattr__`, `infrastructure/__init__.py`'s deliberate
`ValidationTimer` exclusion). **UNVERIFIED: whether that was the author's actual intent** — it is a
reconstruction, not a documented rule.

Corroborating evidence that `01_SYSTEM_STATE.md` was otherwise carefully measured: its companion
claim in the same line — "259 test functions across 32 test files" — reproduces **exactly** at commit
`051ceae` (32 files matching `test_*.py`, 259 `def test_` definitions). The counting method was
sound; the module figure specifically is the outlier.

**Authoritative current count: 37 Python files under `libs/congine-sdk/src/congine_core/`, of which
31 are implementation modules and 6 are package `__init__.py` files.** This document uses
"37 files / 31 modules" throughout.

### 2.2 What moved since 2026-06-14

Version control (`git log --since=2026-06-01`) shows exactly two commits touching the SDK after the
audit date, plus an uncommitted working tree:

| Change | Where | Status |
|---|---|---|
| Tenant-eviction rewrite (P0-1): `weakref.finalize` deferred teardown, `_evicted_total`, idempotent `close()`, `reset_default()` outside locks | `adapters/dependency_injection.py` (+135 lines) | committed `a561992` |
| New direct test for tenant LRU eviction | `tests/unit/test_container_tenant_lru.py` (7 tests) | committed `a561992` |
| Unenforced-keyword vocabulary module (P0-2) | `domain/schema_vocabulary.py` (144 lines, **new file**) | **uncommitted** |
| Load-time unenforced-keyword WARNING + de-dup | `usecases/sync_contracts_usecase.py` (+63 lines) | **uncommitted** |
| `semantic_validation_enabled` threaded into `SyncContractsUseCase` | `adapters/dependency_injection.py:320` (+1 line) | **uncommitted** |
| Tests for the above | `tests/unit/test_schema_vocabulary.py` (12), `tests/unit/test_sync_usecase.py` (+6), `tests/unit/test_config_wiring.py` (+2) | **uncommitted** |
| `requires-python` raised to `>=3.11`; classifiers extended to 3.14 | `pyproject.toml` | committed |
| LangChain example added (`examples/LangChain/`) | example tree | committed |

Nothing else in `src/` changed. Test suite today: **293 passed, 1 skipped** (34 `test_*.py` files,
286 `def test_` definitions; the collected count is higher because of parametrisation).

### 2.3 Claim-by-claim verdict on the prior documents

Legend: **CONFIRMED** (still exactly true) · **CHANGED** (was true, has since moved) ·
**WRONG** (was not true when written) · **GONE** (no longer exists).

#### From `docs/context/01_SYSTEM_STATE.md`

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | "33 source modules across 6 tiers" | **WRONG** | §2.1 |
| 2 | "259 test functions across 32 test files" | **CHANGED** | Exact at baseline; now 34 files / 286 definitions / 294 collected |
| 3 | `ServiceContainer` has no dedicated test file | **CHANGED** | `tests/unit/test_container_tenant_lru.py` now exists (7 tests) |
| 4 | `for_tenant()` LRU eviction "not directly asserted" | **CHANGED** | `test_container_tenant_lru.py:51,76,94,130,138,157,191` |
| 5 | `bootstrap()` in-event-loop guard untested | **WRONG** | `tests/adversarial/test_remediations.py:123` `test_bootstrap_inside_running_loop_raises` existed at baseline |
| 6 | `health()` aggregation untested | **WRONG** | `tests/adversarial/test_remediations.py:107` `test_health_snapshot_shape` |
| 7 | `evaluate_drift()` `__drift__` event untested | **WRONG** | `tests/adversarial/test_remediations.py:82,95` |
| 8 | `reset_default()` teardown untested | **WRONG** | `tests/adversarial/test_remediations.py:71` |
| 9 | `ValidationTimer` deprecated and not wired | **CONFIRMED** | `infrastructure/timer.py:39`; absent from `infrastructure/__init__.py:27-39` |
| 10 | Debt #1 — LangChain example enum mismatch | **VERIFIED PRESENT** | `examples/LangChain/agent.py:75,90` say `manual_review`; `contracts/return_processing.json:7` enum is `["approve_return","reject_return","escalate"]` |
| 11 | Debt #2 — eviction `close()`s a live container | **VERIFIED FIXED** | `dependency_injection.py:157-163` removes the entry and arms `weakref.finalize`; no `close()` under the lock |
| 12 | Debt #3 — `requires-python` contradicts 3.10 floor | **VERIFIED PRESENT** | `pyproject.toml:6` `>=3.11` vs `:18` classifier 3.10 vs `:69` `target-version = "py310"` |
| 13 | Debt #4 — size guards count characters, undercounting multibyte UTF-8 | **WRONG (direction inverted)** | `json.dumps(..., default=str)` uses `ensure_ascii=True`, so its output is pure ASCII and `len(str) == len(str.encode("utf-8"))` exactly. Measured: `{"k": "é"×10}` → guard sees 69, compact UTF-8 is 29. The guard **over**-counts by up to ~6× and is therefore conservative, not permissive. The debt is real (the number is not the payload's wire size) but it is fail-safe, not fail-open |
| 14 | Debt #5 — stale `TelemetryEvent` "mutable" docstring | **VERIFIED PRESENT** | `domain/models.py:5` says mutable; `:74` is `@dataclass(frozen=True)` |
| 15 | Debt #6 — `pii_sanitize` uses stdlib `re` | **VERIFIED PRESENT** | `pii_sanitize.py:9,14` |
| 16 | Debt #7 — `CompositeValidator` runs semantic validator on non-dict payloads | **VERIFIED PRESENT** | `domain/validator.py:451-453` — no short-circuit between the two calls |
| 17 | Debt #8 — silent schema-keyword vocabulary | **PARTIALLY ADDRESSED** | Enforcement unchanged (`domain/validator.py:333-367`), but a load-time WARNING now fires (`sync_contracts_usecase.py:273-306`, `domain/schema_vocabulary.py`). Detection landed; enforcement did not |
| 18 | Debt #9 — `ValidationTimer` dead code retained | **VERIFIED PRESENT** | `infrastructure/timer.py` still present, still tested by `tests/unit/test_timer.py` (4 tests) |
| 19 | "no literal TODO/FIXME remain in src/" | **CONFIRMED** | `grep -rn "TODO\|FIXME" src/` → no matches |
| 20 | All seven hot-path guarantees hold | **CONFIRMED with amendments** | See §14 — all seven hold; two acquire new caveats |

#### From `docs/system-analysis/00_SYSTEM_MAP.md`

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 21 | Strict 6-tier hexagon, dependencies inward only | **CONFIRMED** | §4 — re-verified by AST analysis |
| 22 | `IValidator` is the one sanctioned in-domain protocol | **CONFIRMED** | `domain/validator.py:293-301` |
| 23 | `ServiceContainer` is the sole construction site | **CONFIRMED** | §4.4 |
| 24 | Hot path: guard → use case → cache → executor → rules → telemetry → enforce | **CONFIRMED** | §8.1 |
| 25 | `ServiceContainer.__init__` at `dependency_injection.py:132` | **CHANGED** | now `:202` (P0-1 rewrite shifted line numbers) |
| 26 | `_resolve_schema` at `:161`, `_finalize` at `:205`, `_check_payload_size` at `:125` | **CONFIRMED** | unchanged |
| 27 | `bootstrap()` loop-guard at `dependency_injection.py:270` | **CHANGED** | now `:346-354` |
| 28 | `for_tenant` registry at `:72-118`, cap 128 | **CHANGED (lines)** / **CONFIRMED (cap)** | now `:102-176`; `_MAX_TENANTS = 128` at `:76` |
| 29 | `close()` at `:346-351` tears down in order sync → cache → bus → pool | **CHANGED (lines)** / **CONFIRMED (order)** | now `:439-457` |
| 30 | Appendix lifecycle: "breaker OPEN → `load_snapshot_only()` (fast-fail)" | **WRONG** | `bootstrap()` never calls `load_snapshot_only()`. The OPEN-breaker fallback is inline in `sync_contracts_usecase.py:201-205` (`_fetch_sync` → `load_snapshot()`). `load_snapshot_only()` (`:113-121`) is reached **only** by the single-flight *loser* branch (`:153`, `:172`) |
| 31 | "`config.py` … one frozen dataclass with ~45 fields" | **CHANGED** | exactly **46** fields today |
| 32 | Linkage map (`00_SYSTEM_MAP.md:370-400`) | **CHANGED** | `usecases/sync_contracts_usecase` now also imports `domain/schema_vocabulary` at runtime — the row is stale. See Appendix A for the current map |
| 33 | "no server, no database, no CLI" | **CONFIRMED** | §15 |

#### From `docs/system-analysis/01_FILE_INVENTORY.md`

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 34 | 36 modules; package root `libs/congine-sdk/src/congine_core/` | **CONFIRMED (baseline)** / **CHANGED (now 37)** | §2.1 |
| 35 | Per-module responsibilities and internal-import lists | **CONFIRMED except two rows** | `domain/` gains `schema_vocabulary.py`; `usecases/sync_contracts_usecase.py` gains a runtime `domain.schema_vocabulary` import and a `semantic_validation_enabled` constructor parameter |
| 36 | `main.py` is a stub, "not part of the SDK" | **CONFIRMED** | `libs/congine-sdk/main.py`, 95 bytes, outside `src/` |
| 37 | conftest fakes satisfy ports structurally | **CONFIRMED** | `tests/conftest.py:17-119` — no protocol import, no subclassing |

#### From `docs_v2/01_CORE_ENGINE_ARCHITECTURE.md`

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 38 | MCP server exists | **DOES NOT EXIST** | no `mcp/` package; `IMCPTransport` absent — §15.1 |
| 39 | `SqliteEventBus` exists | **DOES NOT EXIST** | §15.2 |
| 40 | `TelemetryEvent` carries `project_id`/`agent_id`/`file_paths`/`git_commit_sha`/`session_id` | **DOES NOT EXIST** | `domain/models.py:91-96` — six fields only |
| 41 | `correction_hint` on `BreachDetail` | **DOES NOT EXIST** | `domain/models.py:25-27` — three fields |
| 42 | `HistoryQueryUseCase` | **DOES NOT EXIST** | `usecases/` holds exactly two modules |
| 43 | `IAgentAdapter` + per-agent adapters | **DOES NOT EXIST** | §15.7 |
| 44 | `domain/arch_graph.py`, `validate_arch_usecase.py` | **DOES NOT EXIST** | §15.6 |
| 45 | "Rule engine only understands `required`, `type`, `enum`, `min`/`max`/`minimum`/`maximum`, `pattern`, `null_forbidden`" | **CONFIRMED, and it is now the authoritative list** | `domain/schema_vocabulary.py:23-32` mirrors it; guarded against drift by `tests/unit/test_schema_vocabulary.py:119` |

Everything in rows 38–44 belongs to §15 (extension seams) and nowhere else in this document.

### 2.4 Did P0-1 and P0-2 land?

**P0-1 (safe tenant container eviction): YES — landed and committed.**

The old code called `close()` on the evicted container while holding `_tenant_lock`. Both halves of
that defect are gone:

- `dependency_injection.py:157-163` — at capacity, eviction pops the registry entry, bumps
  `_evicted_total`, and calls `_arm_deferred_teardown()`, which only registers a
  `weakref.finalize` (`:422-437`). No component is stopped at eviction time.
- `_teardown_components` (`:40-62`) is a module-level function taking the four sub-components by
  value, never `self`, so the finalizer cannot keep the container alive. It uses `drain=False` so a
  dead control plane cannot stall the finalizer, and wraps each stop in
  `contextlib.suppress(Exception)`.
- The warning log and the return happen **outside** the lock (`:168-176`).
- `close()` is now idempotent behind `_close_lock` (`:445-448`) and detaches an armed finalizer
  (`:454-457`) so teardown runs exactly once.
- `reset_default()` (`:178-195`) collects containers under the locks but calls `close()` after
  releasing both.

Backed by seven tests, of which the decisive ones are
`test_eviction_does_not_disable_live_container` (asserts `result.degraded is False` on a still-held
evicted container — i.e. the pool is genuinely alive, not merely constructed) and
`test_for_tenant_eviction_returns_promptly` (a victim whose `stop()` sleeps 3 s must not delay the
triggering `for_tenant()` call beyond 1 s).

**P0-2 (unenforced schema keyword warning): YES — landed, but uncommitted, and detection-only.**

- `domain/schema_vocabulary.py` (new, pure, no I/O) exposes `find_unenforced_keywords(schema)` with
  **allowlist** semantics: anything not in the enforced set and not in a metadata allowlist is
  reported, so keywords nobody thought to blocklist are still caught as JSON Schema evolves.
- `sync_contracts_usecase.py:273-306` calls it once per contract at cache-prime time, emits one
  WARNING naming the unenforced `field.keyword` paths plus a remediation hint, de-duplicates on
  `(contract_id, SHA-256 schema fingerprint)` so background re-syncs do not repeat it, bounds the
  de-dup set at 4096 entries, and swallows every exception so a diagnostic can never break priming.
- It is skipped entirely when `semantic_validation_enabled` is true (`:283-284`), which the
  container now threads in (`dependency_injection.py:320`).

**What P0-2 does *not* do:** it does not change enforcement. A contract using `minLength` still
validates as passing under default configuration. The trap is now *observable*, not *closed*. Two
gaps remain, both in §13: the warning fires only on the **cache-prime path**, so a schema injected
directly via `schema_storage.put()` is never scanned; and the scan is deliberately non-recursive, so
a nested subtree is reported once at its parent field rather than enumerated.
