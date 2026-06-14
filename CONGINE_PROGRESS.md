# CONGINE — PROGRESS (Shared Source of Truth)

> This is the durable, re-runnable anchor. The **SYSTEM STATE** and **PHASES** sections are regenerated each time
> the deep-analysis prompt runs; the **DAILY LOG** at the bottom is append-only and must never be erased on re-run.
> Full detail lives in `docs/system-analysis/` (00 system map · 01 inventory · 02 failure paths · 03 reconciliation).

---

## SYSTEM STATE AS OF 2026-06-14

Congine is a **synchronous, in-process output firewall** for LLM/agent outputs: a `@congine_guard` decorator (or
LangChain callback) intercepts a function's return value, validates it against a cached JSON contract under a hard
millisecond budget, emits fire-and-forget telemetry, and passes / wraps / blocks per mode. It is a **library, not
a service** — there is no server, database, or CLI in this repo. The architecture is a clean, genuinely-enforced
6-tier hexagon (L0 kernel → L5 adapters); the dependency direction holds everywhere I checked.

### Built and trustworthy (verified against code + tests)
- **The hot path** end-to-end: guard → use case → O(1) LFU schema cache → bounded load-shedding executor →
  6-rule `RuleEngine` (+ optional jsonschema) → telemetry enqueue → fail-mode enforcement. Sync **and** async go
  through the *same* bounded pool (no `run_in_executor` bypass).
- **The seven hot-path guarantees, all confirmed and un-regressed:** (1) bounded latency / load shed, (2) no
  control-plane stall on boot (circuit breaker → snapshot), (3) no thundering herd (portalocker single-flight),
  (4) snapshot integrity (per-tenant scoping, atomic write, symlink/owner refusal), (5) no ReDoS (`re2` + length
  caps), (6) multi-tenant isolation (`get_default()` disabled in multi_tenant mode; per-tenant cache/snapshot),
  (7) PII-safe telemetry (breach sanitization + log redaction).
- **Configuration & security policy:** one frozen `CongineConfig`, env-driven, fail-loud on incomplete/cleartext
  non-local config, loopback-only exemption by parsed hostname.
- **Offline / standalone topology:** `FileContractRepository` + `NoOpEventBus` give a pure in-process validator
  with zero control-plane I/O (two independent switches).
- **Test coverage** is genuinely strong for Phase 0: dedicated unit *and* adversarial suites for the
  hot-path-critical components (executor, cache, breaker, repository, validator, single-flight boot, tenant
  isolation, ReDoS, PII, input bounds).

### Built but broken / risky (fix in Phase 0 hardening)
- **Multi-tenant container eviction** (`dependency_injection.py:72-118`): LRU is keyed on `for_tenant()` *lookups*,
  not validation activity, and eviction calls `close()` on a container a caller may still hold live — tearing the
  cache/telemetry/pool out from under it. Top correctness item. *No direct test.*
- **Shipped LangChain example raises on its own "clean" path** (`examples/LangChain/agent.py`): offline fallback
  returns `action="manual_review"`, not in the contract enum → `mode="raise"` raises on Scenario 1 when no API key
  is set. First-impression defect.
- **Silently-ignored schema keywords**: with semantic validation off (default), the rule engine ignores
  `minLength`/`maxLength`/`format`/nested objects — a contract can *look* enforced and not be. Highest-leverage
  real-user correctness trap.
- **`requires-python = ">=3.11"`** contradicts the 3.10 floor claimed by classifiers/ruff/CLAUDE.md.
- Smaller: payload/schema size bounds count characters not bytes; `pii_sanitize` uses stdlib `re` not `re2`;
  `CompositeValidator` runs the semantic validator even on a non-dict; stale `TelemetryEvent` "mutable" docstring;
  deprecated `ValidationTimer` retained as dead code.

### Absent (not built — and correctly out of Phase 0 scope)
- No persistence / durable telemetry (in-memory queue; events die with the process).
- No contract version resolution (cache keyed on `contract_id` only; `version` is a telemetry label).
- No MCP server, no CLI, no git-hook / CI integration.
- No distributed state (cache, breaker, registry all process-local).
- No RBAC/ABAC, no OpenTelemetry/Prometheus, no architectural graph / history / pattern detection.
- `TenantIsolationViolationException` / `ValidationTimeoutException` are forward-compat **aliases**, never raised
  as distinct types (a timeout degrades to `ValidationResult(degraded=True)`).

### What changed since the previous analysis
This is the first `CONGINE_PROGRESS.md`. It supersedes nothing but **re-verifies** the prior `docs/context/`
analysis (same date): all nine of its known bugs still reproduce, and all seven hot-path guarantees still hold —
**no regressions.**

---

## PHASES

Conceptual problem areas, ordered by what must be trustworthy first. These names are stable anchors for the DAILY
LOG. (Aligned with the Builder's Codex roadmap and `docs/context/04_PHASE_ROADMAP.md`.)

### Phase 0 — Harden the core (trust what exists)
- **Problem:** the enforcement core is sound but carries a handful of correctness/lifecycle defects that would
  embarrass at adoption or bite past 128 tenants.
- **Why it matters:** everything else plugs into this core; it must be trustworthy before it is *extended*.
- **Files:** `adapters/dependency_injection.py` (eviction), `usecases/validate_contract_usecase.py` (byte sizing),
  `domain/validator.py` (schema-keyword vocabulary / warn), `pyproject.toml` (python floor), `pii_sanitize.py`,
  `domain/models.py` (docstring), `examples/LangChain/agent.py` (enum), `infrastructure/timer.py` (delete/quarantine).
- **Done:** multi-tenant eviction is refcount/idle-safe **with a direct test**; `requires-python` reconciled across
  all files; a WARNING fires when a contract uses an unenforced keyword with semantic off (or the rule vocabulary is
  documented authoritative); example runs offline without raising; byte-accurate size bounds; docstring/dead-code
  cleaned; a direct `test_container.py` covers `bootstrap()` loop-guard, `health()`, `evaluate_drift()`, `reset_default()`.

### Phase 1A — Make it integrable (MCP + CLI + git hooks)
- **Problem:** coding agents write files, they don't call your Python — so the guard is bypassed unless Congine
  inserts itself at a layer agents actually touch.
- **Why it matters:** this is the product's reach. MCP puts Congine *inside* the agent's reasoning loop; a CLI
  powers git-hook and CI enforcement.
- **Files (new):** `src/congine_core/mcp/{server,tools,transport}.py` + `ports/mcp_transport.py`;
  `src/congine_core/cli/{main,diff_parser}.py`; `[mcp]` extra + `[project.scripts]` in `pyproject.toml`. Reuses
  `ValidateContractUseCase.execute` and the standalone (`FileContractRepository` + `NoOpEventBus`) topology.
- **Done:** an MCP client (Claude Code/Cursor) calls `validate_output` and gets a structured breach report;
  `git diff --cached | congine validate-diff --stdin --contracts-dir ./contracts` exits 0 on pass, 1 on violation.
- **Depends on:** Phase 0 (don't expose a core with the eviction bug).

### Phase 1B — Make it remember (durable persistence)
- **Problem:** telemetry is in-memory; nothing survives a restart, so there is no history, no audit trail.
- **Why it matters:** history is the differentiator (recurring-violation detection, project memory) and the
  foundation for Phase 2 intelligence.
- **Files (new/changed):** `src/congine_core/infrastructure/sqlite_event_bus.py` implementing `IEventBus`; extend
  `domain/models.py::TelemetryEvent` with `project_id`/`agent_id`/`file_paths`/`git_commit_sha`/`session_id`
  (defaults, backward-compatible); a `HistoryQueryUseCase`; container wiring behind `CONGINE_EVENT_STORE=sqlite`
  (4-touch config rule).
- **Done:** after N validations, `get_violation_history(project_id)` returns N events; they survive a process restart.
- **Depends on:** Phase 0. Independent of 1A (can parallelize).

### Phase 1C — Make it teach (agent-readable correction)
- **Problem:** breaches are human-shaped; an agent re-prompts with full context instead of a targeted fix.
- **Why it matters:** token minimization — precise, machine-readable breach + fix hint turns a 5-retry loop into a
  1-correction loop.
- **Files:** add deterministic, table-driven `correction_hint` to `BreachDetail` (no LLM in the hot path);
  an agent-readable serialization mode; surface hints through MCP `validate_output` (1A) and the use-case result.
- **Done:** each `BreachDetail` carries a deterministic fix hint; the MCP tool returns `correction_hints[]`.
- **Depends on:** 1A (the consumer surface).

### Phase 2 — Intelligence (history → signal)
- **Problem:** raw events aren't insight; recurring patterns and architecture violations need derivation.
- **Files (new):** `domain/arch_graph.py`, `usecases/validate_arch_usecase.py`, `usecases/pattern_detection_usecase.py`
  (reuses `KSDriftEngine` for violation-rate drift). `validate_code_change` MCP tool.
- **Done:** recurring `(contract,field,rule)` clusters and per-file hotspots are queryable; `validate_code_change`
  returns `ArchViolation`s.
- **Depends on:** 1B (persisted events) must exist first.

### Phase 3 — Enterprise (directional, not before its time)
- Distributed cache + breaker (Redis), RBAC/ABAC at the control-plane boundary, OpenTelemetry/Prometheus adapter,
  durable audit WAL → SIEM. Each is a new L4 concrete behind an existing port.
- **Done:** per-feature, when there is a real second pod / compliance requirement driving it.
- **Depends on:** Phase 1 persistence + a real multi-pod deployment. **Do not start before that signal exists.**

> **Explicitly NOT yet (premature):** Redis/distributed cache, WASM sandbox, OPA/Rego, distributed breaker,
> LLM-powered correction hints, auto-drift pipeline, multi-tenant distributed registry. Each is premature until a
> concrete trigger appears; building them now is speculative work.

---

## DAILY LOG

<!-- Append dated entries below this line. NEVER erase existing entries on re-run. -->

### 2026-06-14
- Ran the deep system-analysis prompt (Document 2). Read all 36 source modules, config, docs, the three audits,
  key tests, the LangChain example, and the prior `docs/context/` analysis. Produced
  `docs/system-analysis/{00_SYSTEM_MAP,01_FILE_INVENTORY,02_FAILURE_PATHS,03_SPEC_RECONCILIATION}.md` and created
  this file. **Findings:** architecture is a real, disciplined 6-tier hexagon; all 7 hot-path guarantees hold and
  none has regressed; top correctness items remain (in order) the multi-tenant eviction lifecycle (B9), the
  `requires-python` floor (A1), and silently-ignored schema keywords (B14). No source code was modified (read-only
  analysis).
