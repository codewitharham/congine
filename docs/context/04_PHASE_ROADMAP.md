# CONGINE PHASED ROADMAP

## Based on Current Code State + Strategic Direction

Generated: 2026-06-14
Grounded in `01_SYSTEM_STATE.md` (what exists) and the audit-ID remediations already in code.

---

## PHASE 0 COMPLETION CHECKLIST (Complete Before Moving On)

Phase 0 — the deterministic hot-path guard — is **substantially done and well-tested**. The remaining items are correctness/polish, not new capability. Ordered by priority.

### P0-1. Fix the `requires-python` floor contradiction
- **Task:** Reconcile `requires-python` with the stated 3.10 support, or drop the 3.10 claim everywhere. Pick one floor and make pyproject, classifiers, ruff, and `.claude/CLAUDE.md` agree.
- **Files:** `libs/congine-sdk/pyproject.toml:6` (and `:18`, `:69`).
- **Acceptance:** `uv sync` succeeds on the lowest claimed Python; CI matrix matches `requires-python`.
- **Complexity:** S

### P0-2. Fix the LangChain example contract defect
- **Task:** Align the offline-fallback `action` and the Pydantic enum with the contract enum (`approve_return | reject_return | escalate`). Today the offline path returns `manual_review` and, under `mode="raise"`, the "clean" scenario raises whenever `GOOGLE_API_KEY` is unset.
- **Files:** `examples/LangChain/agent.py:75,91`; cross-check `examples/LangChain/contracts/return_processing.json:7`.
- **Acceptance:** `python agent.py` with no API key completes Scenario 1 without raising; demo runs end-to-end offline.
- **Complexity:** S

### P0-3. Harden multi-tenant container eviction
- **Task:** Make `for_tenant()` eviction safe. Two sub-fixes: (a) do not `close()` a container that may still be referenced — use refcounting or an idle-time policy; (b) document that LRU is keyed on `for_tenant()` lookups, not validation activity (or bump on validation).
- **Files:** `src/congine_core/adapters/dependency_injection.py:84-118`.
- **Acceptance:** a new `tests/unit/test_container_tenant_lru.py` asserting: 129th distinct tenant evicts exactly the least-recently-*looked-up* one; an evicted container's daemons stop; a still-referenced container is not torn down mid-use.
- **Complexity:** M

### P0-4. Count payload/schema bounds in bytes, not characters
- **Task:** Measure `len(json.dumps(...).encode("utf-8"))` (or stream-encode) so the byte-named budget is honored for multibyte payloads.
- **Files:** `src/congine_core/usecases/validate_contract_usecase.py:125-159`.
- **Acceptance:** a test with a multibyte payload just over `max_payload_bytes` in bytes (but under in chars) is rejected with `INPUT_BOUNDS`.
- **Complexity:** S

### P0-5. Close the "silently-ignored schema keyword" trap
- **Task:** Either (a) warn at sync time when a contract uses JSON-Schema keywords the rule engine ignores (`minLength`, `maxLength`, `format`, …) while semantic validation is off, or (b) document the rule-engine vocabulary as authoritative. This is the highest-leverage correctness item for real users.
- **Files:** `src/congine_core/domain/validator.py:333-367`; sync path in `usecases/sync_contracts_usecase.py:_prime_cache`.
- **Acceptance:** loading a contract with `minLength` while `semantic_validation_enabled=False` emits one WARNING naming the unenforced keyword.
- **Complexity:** M

### P0-6. Doc + dead-code cleanup
- **Task:** Fix the stale `TelemetryEvent` "mutable" docstring; decide whether to delete the deprecated `ValidationTimer` (and `test_timer.py`) or keep it explicitly quarantined.
- **Files:** `src/congine_core/domain/models.py:5-6`; `src/congine_core/infrastructure/timer.py`.
- **Acceptance:** docstring matches `frozen=True`; a single decision recorded on `ValidationTimer`.
- **Complexity:** S

> Optional but recommended before Phase 1: add a direct `tests/unit/test_container.py` covering `bootstrap()` loop-guard, `health()` shape, `evaluate_drift()` telemetry, and `reset_default()`. The container is the most integration-heavy module with the least direct coverage.

---

## PHASE 1: INTEGRATION LAYER (MCP + CLI + Persistence)

The core validates; Phase 1 makes it **callable** by agents, **runnable** in CI, and **persistent** across restarts.

### 1A: MCP Server (make Congine callable by coding agents)

**What to build:** an MCP server exposing validation as tools Claude Code / Cursor / other MCP clients call mid-reasoning.

**New files:**
- `src/congine_core/mcp/__init__.py`
- `src/congine_core/mcp/server.py` — `MCPServer` wrapping a `ServiceContainer`
- `src/congine_core/mcp/tools.py` — tool definitions/handlers
- `src/congine_core/mcp/transport.py` — stdio + HTTP/SSE transport

**Port:** `src/congine_core/ports/mcp_transport.py` → `IMCPTransport`.

**Dependency:** `mcp` (Anthropic MCP SDK) as a new optional extra `[mcp]` (keep the core dependency-light — follow the existing `[langchain]`/`[stats]` gating pattern).

**Tools:**
```
validate_output    { output: dict, contract_id: str, version?: str }
                   -> { valid: bool, violations: [BreachDetail], correction_hints: [str] }
validate_code_change { files_changed: [FileChange], contracts: [str] }
                   -> { valid: bool, violations: [ArchViolation] }
list_contracts     { project_id: str, tenant_id?: str }
                   -> { contracts: [ContractSummary] }
```
Reuse `ValidateContractUseCase.execute` for `validate_output`; `list_contracts` reads `schema_storage`/repository.

**Acceptance:** a Claude Code session with the Congine MCP server connected calls `validate_output` and gets a structured breach report. Integration test drives the server over stdio.

**Complexity:** L

### 1B: CLI Tool (make Congine runnable from git hooks + CI)

**What to build:** a `congine` CLI.

**New files:**
- `src/congine_core/cli/__init__.py`
- `src/congine_core/cli/main.py` — entry point (`click` or stdlib `argparse` to avoid a new dep; prefer argparse to honor dependency-light)
- `src/congine_core/cli/diff_parser.py` — parse `git diff` into file changes

**`[project.scripts]`** in `pyproject.toml`: `congine = "congine_core.cli.main:main"`.

**Commands:**
```
congine validate --payload <json> --contract <id> [--version v]
congine validate-diff (--diff <file> | --stdin) --contracts-dir <dir>
congine health
congine list-contracts --project-id <id>
```
`validate`/`validate-diff` build a standalone container (`CONGINE_LOCAL_CONTRACTS_DIR` / `--contracts-dir`, `telemetry_enabled=False`) so no control plane is needed. Exit code 0 on pass, 1 on violation; breach details to stderr.

**Acceptance:** `git diff --cached | congine validate-diff --stdin --contracts-dir ./contracts` returns 0 on valid, 1 on violation with breaches on stderr.

**Complexity:** M

### 1C: Persistent Event Store (make Congine remember)

**What to build:** `SqliteEventBus` implementing `IEventBus`, persisting events to local SQLite (WAL).

**New files:**
- `src/congine_core/infrastructure/sqlite_event_bus.py`
- extend `src/congine_core/domain/models.py` `TelemetryEvent` (it is `frozen=True`; add fields with defaults to stay backward-compatible):
  ```python
  project_id: Optional[str] = None
  agent_id: Optional[str] = None       # "cursor" | "claude_code" | "copilot" | "human"
  file_paths: list[str] = field(default_factory=list)
  git_commit_sha: Optional[str] = None
  session_id: Optional[str] = None
  ```

**Query methods on `ValidateContractUseCase`** (or a new `HistoryQueryUseCase` reading the store — cleaner separation):
```python
get_violation_history(project_id, file_paths=None, contract_id=None, limit=10) -> list[TelemetryEvent]
get_violation_frequency(project_id, lookback_days=30) -> dict[str, int]   # contract_id -> count
```

**Wiring:** container selects `SqliteEventBus` when a new `CONGINE_EVENT_STORE=sqlite` (+ `CONGINE_EVENT_STORE_PATH`) is set; default stays `QueueEventBus`/`NoOpEventBus`. Remember the 4-touch config rule (field, `from_env`, container wiring, README table).

**Acceptance:** after 10 validation runs, `get_violation_history(project_id)` returns 10 events; after process restart they are still retrievable.

**Complexity:** M–L

---

## PHASE 2: INTELLIGENCE LAYER (history + pattern detection + architectural graph)

Phase 2 turns the event store (1C) into signal. Do not start until 1C persists events.

### 2A: Architectural Component Graph
- Build a directed import/ownership graph of the *host* project from parsed changes (reuse `cli/diff_parser`). Represent components + allowed-dependency edges as contracts.
- New: `src/congine_core/domain/arch_graph.py` (pure), `src/congine_core/usecases/validate_arch_usecase.py`.
- Output `ArchViolation(from, to, rule)` — the type `validate_code_change` (1A) already promises.

### 2B: Violation Pattern Detection
- Over the SQLite history, detect recurring `(contract_id, field, rule)` clusters and per-file hotspots; reuse `KSDriftEngine` for rate-drift on violation frequency.
- New: `src/congine_core/usecases/pattern_detection_usecase.py` consuming `get_violation_frequency`.

### 2C: Agent-Readable Correction Hints
- Map each `BreachDetail(rule, field)` to a structured, deterministic fix hint (e.g. `ENUM_VALUES` → "expected one of […]"). Populate the `correction_hints` field `validate_output` (1A) already returns.
- New: `src/congine_core/domain/correction_hints.py` (pure, table-driven; no LLM call — keep it deterministic to match the engine's identity).

---

## PHASE 3: ENTERPRISE LAYER (directional, not prescriptive)

- **3A: Distributed cache + control plane** — Redis-backed `ISchemaStorage` and a shared/distributed `ICircuitBreaker` once there is >1 pod. The port seams already exist; this is a new L4 impl + wiring.
- **3B: RBAC/ABAC** — authorize contract reads/writes per tenant/role at the control-plane boundary.
- **3C: OpenTelemetry + Prometheus** — an `ILogger`/metrics adapter emitting OTel spans + Prom counters from the existing `health()` surface and telemetry events.
- **3D: Durable audit trail (WAL → SIEM)** — ship the SQLite WAL (1C) to a SIEM; tamper-evident chaining.

---

## WHAT MUST NOT BE BUILT BEFORE ITS TIME

- **Redis/distributed cache (3A)** — premature until >1 production pod; the per-process `LFUCache` + `CircuitBreaker` are sufficient and tested.
- **WASM/sandbox validation isolation** — premature; `re2` + length caps + bounded executor already neutralize the hostile-input vectors that would justify a sandbox.
- **OPA/Rego policy language** — premature until JSON Schema + the rule engine are *proven* insufficient by a real contract that can't be expressed.
- **Distributed circuit breaker** — premature until multiple pods share a flapping plane; the in-process breaker already protects boot + sync.
- **LLM-powered correction hints (2C)** — keep hints deterministic/table-driven first; an LLM in the hot path contradicts the "deterministic engine" identity and adds latency the bounded executor is designed to avoid.
- **Auto-drift pipeline** — do not auto-wire validation outcomes into the drift window until there is a consumer (2B); today drift is an opt-in library call and should stay that way.
- **Multi-tenant distributed registry** — premature; fix the in-process eviction (P0-3) before scaling the abstraction.
