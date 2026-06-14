# 03 — Spec Reconciliation (build vs. spec vs. prior findings)

> Reconciles the **code as read** against every spec/doc in the repo and every prior audit finding. Generated
> 2026-06-14. For each prior finding I state its **current status by reading the code** (RESOLVED / PARTIALLY FIXED
> / STILL PRESENT), not by trusting the audit.

Documents reconciled: `README.md`, `ARCHITECTURE.md`, `SECURITY.md`, `CHANGELOG.md`, `.claude/CLAUDE.md`,
`pyproject.toml`, the three audits (`SDK_AUDIT_Cursor.md`, `SDK_AUDIT_Antigravity_Gemini3.1_pro.md`,
`SDK_AUDIT_Antigravity_Gemini3.5_Flash.md`), and the prior analysis set in `docs/context/`.

---

## Part A — Build-vs-spec divergences (doc says X, code does Y)

### A1. `requires-python = ">=3.11"` contradicts the stated 3.10 floor — **DIVERGENCE (still present)**
- **Docs say 3.10:** `pyproject.toml` classifiers list `Programming Language :: Python :: 3.10`; `[tool.ruff]
  target-version = "py310"`; `.claude/CLAUDE.md` says "ruff `target-version = py310` is pinned to the supported
  floor; do not introduce 3.11+ syntax"; the CHANGELOG advertises a "CI matrix for Python 3.10–3.14".
- **Code says 3.11:** `pyproject.toml:6` → `requires-python = ">=3.11"`.
- **Consequence & recommendation:** package metadata forbids 3.10 installs while everything else claims 3.10
  support. `pyproject.toml` is currently `M` (modified) in git status, so this may be mid-edit. **Pick one floor.**
  If 3.10 is intended (the dominant signal), set `requires-python = ">=3.10"`. This is the #1 build-correctness item
  and it's small.

### A2. `ARCHITECTURE.md` still names the pre-rename `repositories/` directory — **STALE DOC**
- **Code:** the L1 directory is `ports/` (the rename `repositories/ → ports/` is recorded in `CHANGELOG.md` as
  audit D-11, and all imports use `congine_core.ports`).
- **Doc:** `ARCHITECTURE.md` still says "L1 `repositories/`" in its layer diagram (line 11) and "Every protocol …
  lives in `repositories/` (L1)" in the protocol-placement rule (line 21). `README.md` and `.claude/CLAUDE.md`
  correctly say `ports/`.
- **Recommendation:** update `ARCHITECTURE.md` to `ports/` for consistency. Pure doc fix.

### A3. `ARCHITECTURE.md` says "5-layer" while the system is 6-tier (L0–L5) — **MINOR WORDING DRIFT**
- `ARCHITECTURE.md` header: "strict 5-layer Clean/Hexagonal design," then lists L0 through L5 (six levels).
  `README.md` and `.claude/CLAUDE.md` consistently say "6-tier." Harmonize the count (L0 is a real tier).

### A4. README config-reference table is incomplete vs. `from_env()` — **DOC GAP**
- `.claude/CLAUDE.md` designates the README config table as "the canonical, user-facing config doc" and mandates
  it be updated whenever a field is added (the 4-touch rule). Reading `CongineConfig.from_env()`, several
  environment-mapped fields are **absent from the README table**, e.g. `CONGINE_LOCAL_CONTRACTS_DIR`,
  `CONGINE_CONTRACT_SOURCE`/`CONGINE_CONTRACTS_DIR`, `CONGINE_TELEMETRY_ENABLED` and the five `CONGINE_TELEMETRY_*`
  knobs, `CONGINE_CONTROL_PLANE_HTTP_TIMEOUT`, `CONGINE_SNAPSHOT_LOCK_TIMEOUT`, `CONGINE_JSONSCHEMA_DRAFT`,
  `CONGINE_SEMANTIC_MAX_BREACHES`, `CONGINE_DRIFT_SAMPLE_LIMIT`, `CONGINE_MAX_SCHEMA_BYTES`,
  `CONGINE_MAX_CONTRACT_FILES`, `CONGINE_MAX_STREAM_BUFFER_CHARS`, `CONGINE_MAX_HTTP_RESPONSE_BYTES`,
  `CONGINE_LOG_REDACTION`, `CONGINE_CACHE_SWEEP_INTERVAL_SECONDS`. These are all wired and tested
  (`tests/unit/test_config_wiring.py`) — the gap is documentation only. **Recommendation:** complete the table; it
  is the user-facing surface and "easy to leave stale" (its own warning).

### A5. `CHANGELOG.md` skips FIX-12 — **TRACEABILITY GAP (cosmetic)**
- The "Phase 0 Lockdown" list jumps FIX-11 → FIX-13. Either FIX-12 was folded into another item or the number was
  retired. Not a code issue; note it so the audit-ID trail (which the code comments rely on) stays complete.

### A6. Stale `TelemetryEvent` docstring — **STALE DOC (in source)**
- `domain/models.py:5-6` module docstring says "the outbound `TelemetryEvent` is mutable to allow post-init
  defaulting," but the class is `@dataclass(frozen=True)` (line 74) and uses `object.__setattr__` precisely
  because it is frozen. Comment contradicts code. One-line fix.

### A7. SDK self-described as v0.1.0 while shipping all "Unreleased" fixes — **VERSION/CHANGELOG LAG (benign)**
- `pyproject.toml` `version = "0.1.0"`; `CHANGELOG.md` keeps every FIX-01..FIX-14 under **[Unreleased]** with a
  separate `[0.1.0]` "pre-remediation" baseline. `__version__` is single-sourced from installed metadata, so the
  runtime version will read `0.1.0`. This is internally consistent (the remediated build is still pre-tag) — just
  be aware that "0.1.0" now denotes the *remediated* code, not the pre-remediation baseline the CHANGELOG labels
  `[0.1.0]`. Recommendation: cut a `0.1.1`/`0.2.0` tag and move the Unreleased block under it before publishing.

---

## Part B — Prior audit findings: current status (verified against code)

### B.1 — `SDK_AUDIT_Cursor.md` §1.5 (Technical Debt & Risks)

| # | Finding | Status (read from code) | Evidence |
|---|---------|--------------------------|----------|
| 1 | Timeout ≠ cancellation; zombies hold permits | **STILL PRESENT (by design, correct)** | `bounded_executor.py:174` releases permit only via done-callback — intentional honest accounting (see `02_FAILURE_PATHS.md` B4) |
| 2 | Default fail mode is permissive (`DEGRADE`) | **STILL PRESENT (by design)** | `config.py:77` default `FailMode.DEGRADE`; documented in README failure-mode table |
| 3 | Telemetry loss is silent | **PARTIALLY FIXED** | drops now counted (`queue_event_bus.py:_dropped_total`) and surfaced as `telemetry_dropped_total` in `health()`. Durability still absent |
| 4 | Process-local isolation only | **STILL PRESENT (by design, Phase 0)** | cache/breaker/queue/registry all in-process |
| 5 | `TenantIsolationViolationException` placeholder never raised | **STILL PRESENT** | `exceptions.py:65` alias = `CongineValidationError`; nothing raises it as a distinct type |
| 6 | No contract version resolution | **STILL PRESENT** | cache key = `contract_id` only; `version` in telemetry only (see B13 in failure paths) |
| 7 | Semantic validation off by default | **STILL PRESENT (by design)** | `config.py:89` `semantic_validation_enabled=False` |
| 8 | `asyncio.run` in sync sync path | **STILL PRESENT (mitigated)** | `sync_contracts_usecase.py:189` uses `asyncio.run`; `bootstrap()` guards against being called inside a running loop (`dependency_injection.py:270`), and the background worker runs in its own thread (no running loop). Risk only if a host calls `sync_once()` directly from within an event loop |
| — | `pyproject` 3.11 vs ruff py310 | **STILL PRESENT** | see A1 |
| — | `CongineCallbackHandler` swallows non-Congine errors → `None` | **STILL PRESENT (by design)** | `langchain_handler.py:105-119` logs + returns `None`; deliberate (a callback must not crash the LLM run) |
| — | `main.py` is a stub, no CLI | **STILL PRESENT** | `main.py` prints a hello string; no CLI exists |

### B.2 — `SDK_AUDIT_Antigravity_Gemini3.1_pro.md` (Technical Debt)

| Finding | Status | Evidence |
|---------|--------|----------|
| Multi-tenant eviction uses `next(iter(...))` — evicts oldest-initialized, not true LRU | **PARTIALLY FIXED / STILL PRESENT** | `for_tenant` now moves an entry to the end **on lookup** (`dependency_injection.py:86-88`), so it is LRU-on-lookup; but eviction still `close()`es a possibly-live container and recency tracks *lookups*, not validation activity (see `02_FAILURE_PATHS.md` B9). The deeper bug remains |
| Process-local `CircuitBreaker`/`LFUCache` (scattered in K8s) | **STILL PRESENT (by design, Phase 0)** | per-process; distributed variants are Phase 3 |
| Heavy async bridge (thread offload inside asyncio) | **STILL PRESENT (by design)** | `run_with_timeout_async` wraps futures; correct trade-off for CPU-bound validation |

### B.3 — `SDK_AUDIT_Antigravity_Gemini3.5_Flash.md` §1.4 (Technical Debt)

| Finding | Status | Evidence |
|---------|--------|----------|
| Blocking file I/O inside `async fetch_active_contracts` | **STILL PRESENT** | `file_contract_repository.py:53` is `async` but does sync `glob`/`open`. Low impact: boot-time, bounded by `max_contract_files`; only blocks the loop if used via `bootstrap_async`. Worth `asyncio.to_thread` or documenting as boot-only |
| `json.dumps` size check on the hot path | **STILL PRESENT** | `validate_contract_usecase.py:127,145`; bounded by 1 MiB cap (also see A-adjacent B10 byte-vs-char) |
| Eviction thrashing at 128 tenants | **STILL PRESENT** | same root as B9; cold-tenant re-init cost real past the cap |
| `portalocker` lock contention on shared NFS/EFS | **STILL PRESENT (operational)** | `snapshot_lock_timeout_seconds` is now configurable (`config.py:127`), which lets operators tune ride-out vs fail-fast — a real mitigation, not a fix |

### B.4 — `CHANGELOG.md` FIX-01..FIX-14 remediations: spot-verified present in code

All audit-ID remediations the CHANGELOG claims are traceable in source (the code comments carry the IDs):
FIX-01 hostname parse (`config.is_local_base_url`), FIX-02 `re2` required (`pyproject` core dep + `validator.py`),
FIX-03 semantic breach cap (`jsonschema_validator.py:_max_breaches`), FIX-04 PII sanitize (`pii_sanitize.py` +
`_finalize`), FIX-05 multi-tenant `get_default` disable + `for_tenant` (`dependency_injection.py:60-65,72`),
FIX-06 input bounds (`security_limits.py` + use-case guards), FIX-07 LangChain shared container + bounded buffers
(`langchain_handler.py`), FIX-08 auto log redaction + blocklist (`logger.py:31-40`, `config.effective_log_safe_fields`),
FIX-10 `ICircuitBreaker` port (`ports/circuit_breaker.py`), FIX-11 HALF_OPEN single-probe
(`circuit_breaker.py:_probe_in_flight`), FIX-13 HTTP response cap (`http_contract_repository.py:121`),
FIX-14 `start_background_services` (`config.py:149` + container). **RESOLVED** as claimed. (FIX-12 unlisted — A5.)

---

## Part C — Where the CODE is MORE correct than the SPEC (do NOT "fix" toward a worse spec)

The analysis prompt is explicit: if the implementation is more correct than a document, recommend updating the
document, not regressing the code. These are those cases.

1. **Synchronous, in-process validation (not an async/queue pipeline).** Some earlier framing imagined validation
   as an async/queued step. The code runs validation **synchronously in-process** through a bounded executor — the
   right call for a sub-100ms output firewall. Latency is deterministic and there is no queue to back up. *Keep the
   code; ensure any spec that implies a queue is corrected.* (Both Gemini audits and the Builder's Codex affirm the
   synchronous determinism as the product's identity.)

2. **Telemetry-before-raise ordering in STRICT mode.** `_finalize` publishes the `TelemetryEvent` **before**
   `_handle_failure` raises (`validate_contract_usecase.py:225` then `:228`). This guarantees a strict-mode block is
   always observable in telemetry. It's a subtle correctness property the README documents and the integration test
   asserts (`test_strict_mode_raises_end_to_end` checks one event was published before the raise). Correct; preserve.

3. **Cache prime-in-place, never clear-then-refill.** `_prime_cache` (`sync_contracts_usecase.py:239`) updates keys
   in place so a concurrent hot-path `get` never observes an empty cache mid-sync. More correct than a naive
   clear-and-reload. Preserve.

4. **`re2` as a *required* core dependency, not an optional `[redos]` extra.** `pyproject.toml` lists `google-re2`
   in core `dependencies`; `[redos]` is a backward-compatible alias. Earlier docs implied "re2 when installed." The
   code makes the linear-time guarantee unconditional — stronger than the doc. Update any "when installed" phrasing
   (the README already mostly does).

5. **Snapshot security posture exceeds a typical Phase-0 bar.** Per-tenant SHA-256 scoping + per-user app dir +
   atomic temp-replace + cross-process portalocker + symlink/owner refusal on load. This is more hardened than the
   threat model strictly requires for a single-node Phase 0. Keep; it's a genuine differentiator.

---

## Part D — Reconciliation against the prior `docs/context/` analysis (Document-3-style artifacts)

A prior analysis set exists at `docs/context/` (`01_SYSTEM_STATE.md`, `02_COMPONENT_MAP.md`,
`03_EXECUTION_TRACES.md`, `04_PHASE_ROADMAP.md`, `05_QUICKSTART_TEST.md`), dated 2026-06-14 and grounded directly
in source. I re-verified its principal claims against the current code:

- Its **9-item Known-Bugs table** (requires-python, example enum defect, multi-tenant eviction, char-vs-byte size,
  stale `TelemetryEvent` docstring, `pii_sanitize` stdlib-`re`, composite-on-non-dict, ignored schema keywords,
  deprecated `ValidationTimer`) — **all nine still reproduce in the current code.** They are carried forward into
  `02_FAILURE_PATHS.md` (B9–B15) and Part A here, with the same severities.
- Its **seven hot-path-guarantee verifications** — **all still hold** (re-confirmed independently in
  `00_SYSTEM_MAP.md` Step 3 and `02_FAILURE_PATHS.md` B3–B8).
- Its **phase roadmap** (P0-1..P0-6 completion items, then Phase 1 MCP/CLI/SQLite) is consistent with the Builder's
  Codex and is adopted (re-stated) in `CONGINE_PROGRESS.md`.

**These two analysis sets do not conflict.** `docs/context/` is preserved as-is; `docs/system-analysis/` (this set)
is the re-runnable map the analysis prompt specifies, and `CONGINE_PROGRESS.md` is the shared source of truth that
anchors both.

---

## Bottom line

The code and the docs are **mostly aligned**, and where they diverge the divergences are **documentation lag, not
code defects** — with three exceptions that are genuine code/correctness items, in priority order: **A1**
(`requires-python` floor), **B9** (multi-tenant eviction lifecycle), and **B14** (silently-ignored schema
keywords). Everything else is either by-design Phase-0 scope, a stale comment/table, or an example defect (B15).
Notably, **none of the seven hot-path security/reliability guarantees has regressed** since the prior analyses.
