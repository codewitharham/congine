# CONGINE PHASE 0 — COMPLETION ROADMAP

Date: 2026-07-20 | Derived from: `PHASE0_AUDIT_AND_HEALTH.md`

> Scope fence: this roadmap **finishes the existing Phase 0 core**. It does not design or build the
> MCP server, CLI, SQLite event store, agent adapters, arch graph, or routing (see §E). Every task is
> minimal-diff and preserves determinism (no LLM/network/nondeterminism in the validation hot path).

---

## A. Definition of Done (Exit Criteria for Phase 0)

Phase 0 is COMPLETE when ALL of the following are true:

1. The one **HIGH** finding (H-1, tenant eviction) is resolved and covered by a direct test.
2. All **MEDIUM** correctness/security findings (F-2, F-3, F-4, F-5, F-6, F-7, F-8) are resolved, or
   carry a recorded, justified deferral in this file.
3. Each of the seven hot-path guarantees holds **and** is backed by ≥1 test — including the two current
   asterisks: guarantee 6 eviction safety (new test) and guarantee 4 on **Windows** (platform test).
4. The composition root has direct tests for: `bootstrap()` in-loop guard ✅(exists), `health()` shape
   ✅(exists), `evaluate_drift()` event ✅(exists), `reset_default()` ✅(exists), **and `for_tenant()`
   eviction safety** ❌(to add). (The first four already pass — see reconciliation; only eviction remains.)
5. Full suite passes on the **declared floor (Python 3.11, singular)**; branch coverage for
   hot-path-critical modules (`bounded_executor`, `lfu_cache`, `circuit_breaker`,
   `http_contract_repository`, `validate_contract_usecase`, `sync_contracts_usecase`,
   `dependency_injection`) is **≥ 90%**, and the eviction branch (`dependency_injection.py:110-114`) is
   specifically exercised.
6. `ruff check`, `ruff format --check`, `mypy`, and `pip-audit` are clean **OR** every remaining item is
   explicitly documented (bandit B101/B104 already triaged as benign in the audit F-16).
7. `python examples/LangChain/agent.py` runs end-to-end **offline** (no `GOOGLE_API_KEY`) without raising,
   and the 5-minute standalone quickstart in `05_QUICKSTART_TEST.md` works as written.
8. Determinism preserved: no LLM/network/nondeterminism in the validation hot path (audit re-checks it).
9. A recorded decision on every dead-code item: `ValidationTimer` (F-13), `_DEFAULT_SAFE_FIELDS` (F-20),
   `region` dead-configurable (F-17).
10. The dual-schema-vocabulary foot-gun is resolved: loading a contract that uses an unenforced keyword
    (`minLength`/`maxLength`/`format`) under default config emits exactly one WARNING naming the keyword.

> **Adjustment vs the 2026-06-14 roadmap (justified by findings):**
> - Baseline P0-4 "count bytes not chars" is **downgraded to a doc/no-op** — F-9 proves the current
>   guard is conservative, not a bypass; the proposed `.encode("utf-8")` fix changes nothing.
> - Baseline coverage tasks for `reset_default`/`health`/`evaluate_drift`/`bootstrap-guard` are **already
>   done** (see reconciliation) — do not re-do them; only eviction coverage remains.

---

## B. Ordered Task List

### TASK P0-1: Make `for_tenant()` eviction safe (never close a live container; never block under the lock)
- **Status:** ✅ **DONE (2026-07-20).** Eviction now removes the registry entry and arms a `weakref.finalize` (components passed as args, never `self`) instead of calling `close()`; teardown is deferred until the container is unreferenced and uses `drain=False`. `close()` is idempotent (`_closed` flag) and detaches the finalizer; `reset_default()` was also moved to close containers outside both class locks. New `tests/unit/test_container_tenant_lru.py` (7 tests) passes and fails against the pre-fix code. No `_tenant_lock`-held teardown remains.
- **Rationale:** closes **H-1** (and folds in **F-5**). The only place the SDK can crash a live tenant.
- **Severity:** HIGH.
- **Files:** `src/congine_core/adapters/dependency_injection.py:107-118` (eviction), `:346-351` (`close()`).
- **Change summary (minimal-diff):** (a) do not `close()` a container that may still be referenced —
  add reference/idle tracking, or mark-evicted-and-defer teardown; (b) perform any teardown **outside**
  `_tenant_lock`; (c) keep LRU-by-lookup semantics honest (bump on lookup already done at `:87-88`).
  Do not touch L2/L3.
- **Acceptance test:** new `tests/unit/test_container_tenant_lru.py` asserting all of:
  1. `test_eviction_does_not_disable_live_container`: fill to `_MAX_TENANTS`, keep a reference `c1` to
     the first; look up one more distinct tenant to force eviction; assert `c1.validation_executor.health()["capacity"] > 0` **and** `c1.validate_contract_usecase.execute({"x":1}, "cid", "v")` returns a `ValidationResult` (pool not shut down) after priming `c1.schema_storage.put("cid", {...})`.
  2. `test_eviction_targets_least_recently_looked_up`: after filling, `for_tenant()` an early key to bump
     it, then insert a new key; assert the bumped key is still in `ServiceContainer._tenant_registry` and
     the genuine LRU key is gone.
  3. `test_for_tenant_eviction_returns_promptly`: with `telemetry_enabled=True` and a `client_factory`
     that connects to an unreachable address, the `for_tenant()` call that triggers eviction returns in
     `< 1.0s` (asserts teardown/drain is not blocking the lock).
- **Effort:** M | **Depends on:** none | **Risk if skipped:** a >128-tenant deployment intermittently
  crashes live requests with `RuntimeError: cannot schedule new futures after shutdown`.

### TASK P0-2: Warn on unenforced schema keywords (kill the false-safety foot-gun)
- **Rationale:** closes **F-2**; satisfies DoD #10. Highest-leverage correctness item for real users.
- **Severity:** MEDIUM.
- **Files:** `src/congine_core/usecases/sync_contracts_usecase.py` (`_prime_cache`, `:239-252`); read-only
  reference to `src/congine_core/domain/validator.py:333-367` for the enforced-keyword set. (Prefer the
  sync/prime seam so the warning fires once at load, not per-validation on the hot path.)
- **Change summary:** when `semantic_validation_enabled` is False, scan each primed contract's
  `properties[*]` for keywords the rule engine ignores (`minLength`, `maxLength`, `format`, and any
  other non-vocabulary keyword) and emit **one** `logger.warning` per contract naming the field(s) and
  keyword(s). Do not change enforcement semantics.
- **Acceptance test:** `tests/unit/test_sync_usecase.py::test_unenforced_keyword_warns` — prime a
  contract `{"id":"c","schema":{"properties":{"summary":{"type":"string","minLength":10}}}}` with a
  `FakeLogger` and `semantic_validation_enabled=False`; assert exactly one WARNING record whose kwargs
  contain `minLength` and `summary`. Negative: with `semantic_validation_enabled=True`, **no** such warning.
- **Effort:** M | **Depends on:** none | **Risk if skipped:** authors ship contracts that look enforced
  and silently aren't.

### TASK P0-3: Resolve the Python-version contradiction to a single 3.11 floor
- **Rationale:** closes **F-3**; enables DoD #5.
- **Severity:** MEDIUM.
- **Files:** `libs/congine-sdk/pyproject.toml:18` (drop the 3.10 classifier), `:69` (`target-version="py311"`);
  `.github/workflows/ci.yml:26,65` (drop `3.10` from matrix + `PYTHON_MIN_VERSION`);
  `libs/congine-sdk/.claude/CLAUDE.md` (3.10→3.11 references).
- **Change summary:** pick **3.11** as the one floor (matches `requires-python`); make classifiers, ruff,
  CI matrix, and docs agree. Do not lower `requires-python`.
- **Acceptance test:** objective checks — `uv pip install --python 3.11 ./libs/congine-sdk` exits 0
  (already true); a repo check asserts `"Programming Language :: Python :: 3.10"` is absent from
  `pyproject.toml` classifiers and `target-version = "py311"`; the CI matrix JSON no longer contains
  `'3.10'`. Optionally a `tests/unit/test_packaging.py` parsing `pyproject.toml` with `tomllib`.
- **Effort:** S | **Depends on:** none | **Risk if skipped:** 3.10 installs fail; CI stays red/blind on 3.10.

### TASK P0-4: Harden the semantic-validation ReDoS surface (or record a justified deferral)
- **Rationale:** closes **F-4**; keeps guarantee 5 honest when semantic validation is enabled.
- **Severity:** MEDIUM.
- **Files:** `src/congine_core/infrastructure/jsonschema_validator.py:148-168`.
- **Change summary:** recurse the pattern-length check over the whole schema (nested `properties`,
  `items`, `patternProperties`, `$defs`), and cap the payload **value** length before `iter_errors` (reuse
  `MAX_REGEX_VALUE_LENGTH`). Keep it deterministic; no engine swap required. **Deferral option (record
  here if chosen):** since it is off-by-default and input-bounded (1 MB), document the residual and gate.
- **Acceptance test:** `tests/adversarial/test_semantic_bounds.py::test_nested_over_long_pattern_rejected`
  — a schema `{"properties":{"a":{"items":{"pattern":"x"*(MAX_PATTERN_LENGTH+1)}}}}` under semantic
  validation yields a `SEMANTIC_SCHEMA` breach (not a hang); and `test_semantic_value_length_capped` —
  a payload value longer than `MAX_REGEX_VALUE_LENGTH` against a `pattern` field is bounded/short-circuited.
- **Effort:** M | **Depends on:** none | **Risk if skipped:** enabling semantic validation *reduces*
  ReDoS protection vs the rule engine.

### TASK P0-5: Fix and format the LangChain example (first-impression demo runs offline)
- **Rationale:** closes **F-8** and **F-6**; satisfies DoD #7.
- **Severity:** MEDIUM.
- **Files:** `examples/LangChain/agent.py:75,91` (+ `:19,62` for the fragility notes).
- **Change summary:** change the offline-fallback `action` to `"escalate"` and fix the Pydantic field
  `description` to list the real enum; run `ruff format` on the file. Optionally make the langchain
  import lazy and move `bootstrap()` out of import scope.
- **Acceptance test:** `python examples/LangChain/agent.py` with `GOOGLE_API_KEY` unset completes
  Scenario 1 and exits 0 without a `CongineValidationError`; `ruff format --check examples/LangChain/agent.py`
  exits 0.
- **Effort:** S | **Depends on:** none | **Risk if skipped:** the demo crashes for anyone trying it offline.

### TASK P0-6: Bump the `[langchain]` extra off the known-vulnerable line
- **Rationale:** closes **F-7**.
- **Severity:** MEDIUM.
- **Files:** `libs/congine-sdk/pyproject.toml:44`; refresh `uv.lock`.
- **Change summary:** raise the `langchain-core` (and transitively `langsmith`) floor to a patched
  version per `pip-audit`, or document the exposure and keep it opt-in.
- **Acceptance test:** `uv run --with pip-audit --extra langchain pip-audit` reports **0** known vulns
  for `langchain-core`/`langsmith` (or a `SECURITY.md` note records the accepted risk with IDs).
- **Effort:** S | **Depends on:** none | **Risk if skipped:** `[langchain]` consumers pull CVEs.

### TASK P0-7: Make type-checking gating and fix the 4 mypy errors (incl. the `IEventBus` port)
- **Rationale:** closes **F-14** and **F-15**; enables DoD #6.
- **Severity:** LOW.
- **Files:** `libs/congine-sdk/pyproject.toml:52-57` (add `mypy` to `[dev]`);
  `.github/workflows/ci.yml:207` (drop `|| true`); `src/congine_core/ports/event_bus.py`
  (declare `queue_depth`/`dropped_total`/`stop`); `dependency_injection.py:172`;
  `jsonschema_validator.py:108`.
- **Change summary:** add `mypy` as a dev dep and a `[tool.mypy]` config; widen `IEventBus` to the
  surface the container uses (fixes `:335`,`:350`); narrow the `local_contracts_dir` type or assert; type
  the validator class so `check_schema` resolves. Make CI fail on mypy errors.
- **Acceptance test:** `uv run --package congine-sdk mypy libs/congine-sdk/src/congine_core` exits 0;
  CI `python-lint` no longer has `|| true`.
- **Effort:** S–M | **Depends on:** none | **Risk if skipped:** type regressions ship silently; the
  `IEventBus` extension point stays misleading.

### TASK P0-8: Documentation + dead-code decisions
- **Rationale:** closes **F-10, F-13, F-17, F-20, F-9**; satisfies DoD #9.
- **Severity:** LOW.
- **Files:** `src/congine_core/domain/models.py:5` (stale "mutable" clause);
  `src/congine_core/infrastructure/timer.py` (+ `tests/unit/test_timer.py`);
  `src/congine_core/infrastructure/logger.py:27-29` (`_DEFAULT_SAFE_FIELDS`);
  `src/congine_core/config.py` (`region`); `src/congine_core/usecases/validate_contract_usecase.py:127,145`
  (byte-guard comment).
- **Change summary:** fix the docstring; **delete `ValidationTimer`** (recommended — 0% coverage,
  unwired) or add an explicit quarantine note + coverage pragma; delete the unused `_DEFAULT_SAFE_FIELDS`;
  either consume `region` or annotate it informational; add a comment (or `ensure_ascii=False` rename)
  clarifying the size-budget semantics per F-9.
- **Acceptance test:** `grep -R "mutable to allow" src/` is empty; a recorded decision exists for
  `ValidationTimer` (either the module is gone and `test_timer.py` no longer imports it, or a
  `# quarantined:` note is present); `grep -R "_DEFAULT_SAFE_FIELDS" src/` is empty. Full suite still green.
- **Effort:** S | **Depends on:** none | **Risk if skipped:** ongoing confusion; dead code rots.

### TASK P0-9: Minor domain/robustness hardening (batch)
- **Rationale:** closes **F-11, F-12** and the Windows guarantee-4 gap (Open Q #2).
- **Severity:** LOW.
- **Files:** `src/congine_core/pii_sanitize.py:14`; `src/congine_core/domain/validator.py:451-453`;
  `tests/adversarial/test_remediations.py:183` (Windows snapshot assertion).
- **Change summary:** rewrite the sanitizer regex without the `\1` backreference so it can move to RE2
  (or document why it can't and keep the bounded stdlib pattern); early-return in `CompositeValidator`
  when the rule validator already failed a non-dict payload; add a Windows-appropriate snapshot-defence
  test so guarantee 4 is verified on this platform too.
- **Acceptance test:** `test_pii_sanitization.py` still passes after the regex change (same redaction
  behaviour); `tests/unit/test_composite_validator.py::test_non_dict_skips_semantic` asserts the semantic
  validator is **not** called for a non-dict payload (inject a spy); a Windows snapshot test asserts a
  non-owned/attacker-shaped snapshot is refused (or is `skipif` POSIX with a documented reason).
- **Effort:** M | **Depends on:** none | **Risk if skipped:** latent assumptions; guarantee 4 unverified on Windows.

### TASK P0-10 (OPTIONAL / defer-with-note): Snapshot TOCTOU + streaming response cap
- **Rationale:** closes **F-18, F-19** — defense-in-depth beyond the current per-user `0700` mitigation.
- **Severity:** LOW.
- **Files:** `src/congine_core/infrastructure/http_contract_repository.py:121-125,151-157`.
- **Change summary:** open-then-`fstat` (O_NOFOLLOW on POSIX) instead of check-by-path; stream the HTTP
  body with a byte limit rather than buffering then checking.
- **Acceptance test:** `test_repository.py::test_snapshot_swapped_after_check_is_refused` (POSIX);
  `test_oversize_response_streamed_not_buffered` asserts rejection without materializing the full body.
- **Effort:** M | **Depends on:** none | **Risk if skipped:** low — mitigated by the owner-only dir and
  the authenticated boundary. **Acceptable to defer past Phase 0 with this note.**

---

## C. Suggested Sequence & Grouping

Critical path (do in order): **P0-1 → P0-2 → P0-3 → P0-5**. These clear the HIGH bug, the false-safety
foot-gun, the install/CI blocker, and the demo — the four things that stop MCP or fail a live demo.

Batchable in parallel after the critical path:
- **Security batch:** P0-4 (semantic ReDoS), P0-6 (langchain CVE).
- **Quality batch:** P0-7 (mypy+port), P0-8 (docs/dead-code), P0-9 (robustness + Windows test).
- **Optional:** P0-10 (defer past Phase 0 with the recorded note if time-boxed).

Re-run after each task: `uv run --package congine-sdk --extra langchain --extra stats pytest
libs/congine-sdk/tests` + `ruff format --check` + `ruff check` + `mypy` + `pip-audit`. Verify the seven
guarantees still hold (§6 of the audit).

---

## D. GO / NO-GO Gate for MCP (Phase 1)

**All must be green before any MCP work begins.** If any is red, MCP does not start.

- [x] **G1** P0-1 done: `test_container_tenant_lru.py` passes — eviction never disables a live container and returns promptly. *(HIGH)* ✅ 2026-07-20
- [ ] **G2** P0-2 done: unenforced-keyword WARNING fires exactly once per offending contract under default config.
- [ ] **G3** P0-3 done: single 3.11 floor; `uv pip install --python 3.10` fails *by design and by docs*; no 3.10 in CI matrix; classifiers/ruff/CLAUDE.md agree.
- [ ] **G4** Full suite green on Python **3.11**; hot-path-critical modules ≥ 90% branch; eviction branch (`dependency_injection.py:110-114`) exercised.
- [ ] **G5** `ruff check` + `ruff format --check` + `mypy` all exit 0 across `libs/congine-sdk` (incl. examples); or every remaining exception documented.
- [ ] **G6** `pip-audit` clean for the core **and** the `[langchain]` extra (or accepted-risk note with IDs).
- [ ] **G7** All seven guarantees test-backed, including guarantee 6 eviction safety and guarantee 4 verified on the CI OS in use.
- [ ] **G8** `python examples/LangChain/agent.py` runs offline to completion; the `05_QUICKSTART_TEST.md` 5-minute path works verbatim.
- [ ] **G9** Determinism re-verified: no LLM/network/nondeterminism in `guard → execute → validator.validate`.
- [ ] **G10** Recorded decisions on `ValidationTimer`, `_DEFAULT_SAFE_FIELDS`, `region`; no unreviewed dead code.

> The gate deliberately does **not** require P0-10 (TOCTOU/streaming) — those are documented-deferrable
> LOWs. Everything else above is mandatory.

---

## E. Out of Scope (explicitly NOT Phase 0)

These are later-phase features. Do not build them as "completion" work; they begin only after the gate is green:

- **MCP server** — `mcp/` package, `IMCPTransport`, `server.py`, `tools.py`, transport, prompt template.
- **CLI** — `congine validate` / `validate-diff` / `health` / `list-contracts`, `diff_parser`, `[project.scripts]`.
- **Persistent event store** — `SqliteEventBus`, extended `TelemetryEvent` fields, `HistoryQueryUseCase`.
- **Correction hints + context compression / delta protocol / tiered semantic path.**
- **Architectural component graph, violation pattern detection, agent adapters, capability profiles.**
- **Adaptive routing / contextual bandit.**
- **Distributed cache / breaker, RBAC, OpenTelemetry, SIEM/WAL** (Phase 3, directional).

Do not introduce an LLM, network call, or other nondeterminism into the validation hot path at any point —
that is the property the entire product is built to sell.
