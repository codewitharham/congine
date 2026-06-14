# CONGINE — CLAUDE CODE SYSTEM ANALYSIS PROMPT
## Master Prompt for Deep Codebase Reverse Engineering and Phased Context Recovery


You are performing a deep reverse-engineering analysis of the **Congine SDK** — a deterministic contract enforcement engine for AI agent outputs. This is not a code review. This is a system archaeology task: you will read the actual code, understand what has been built, what it means strategically, and produce structured context documents that restore the builder's complete mental model of this project.

## YOUR MANDATE

You have four jobs in this session:

1. **Read and map the actual codebase** — every module, every class, every meaningful method. Understand what each piece does, not what its comments say it does.
2. **Produce Phase Context Documents** — markdown files that give the builder (a non-expert founder/developer) an accurate, honest picture of: what exists, what it does, what is missing, and what to build next.
3. **Never hallucinate or guess** — if a file doesn't exist, say it doesn't exist. If a feature is partially implemented, say it's partial. The worst thing you can do here is pretend something is done when it isn't.
4. **Think like a senior backend engineer, not a documentation writer** — give hard opinions, point out real problems, and be specific about what to build in what order.
5. **Donot read any .md files in the directory** - if needed ask first, so that you will be exact about what is inside codebase.

---

## PHASE 0: ENVIRONMENT ORIENTATION

Before reading any code, do this:

```bash
# 1. Map the workspace structure
find . -type f -name "*.py" | grep -v __pycache__ | grep -v .venv | sort

# 2. Show the package structure
cat libs/congine-sdk/pyproject.toml

# 3. Check what tests exist
find . -type f -name "test_*.py" | sort

# 4. Check what examples exist
find . -path "*/examples/*" -type f | sort

# 5. Check git log for recent commits (understand what has changed)
git log --oneline -20

# 6. Show what environment variables are expected
grep -r "CONGINE_" libs/congine-sdk/src/ --include="*.py" | grep "os.getenv\|os.environ" | sort -u
```

After running these commands, write a brief orientation summary covering:
- Total module count and directory structure
- Test coverage footprint (how many test files, what are they testing)
- Any obvious gaps in the directory structure (e.g., missing `__init__.py`, missing test modules)

---

## PHASE 1: LAYER-BY-LAYER CODE ARCHAEOLOGY

Read each layer in dependency order (inner layers first). For each layer, you will:
1. Read the actual source files
2. Identify what each class/function does
3. Flag any bugs, incomplete implementations, or TODOs
4. Note any deviations from hexagonal architecture

### Step 1.1: Read Layer 0 (Config, Exceptions, Security)

```bash
cat libs/congine-sdk/src/congine_core/config.py
cat libs/congine-sdk/src/congine_core/exceptions.py
cat libs/congine-sdk/src/congine_core/security_limits.py
cat libs/congine-sdk/src/congine_core/pii_sanitize.py
```

For each file, note:
- Every configuration field and its default value
- Every exception class and when it should be raised
- Every security limit constant and its value
- Any PII patterns being redacted and what they cover

### Step 1.2: Read Layer 1 (Ports / Protocols)

```bash
ls libs/congine-sdk/src/congine_core/ports/
cat libs/congine-sdk/src/congine_core/ports/*.py
```

For each Protocol, note:
- What capability it abstracts
- Every method signature and what it expects/returns
- Whether the interface is minimal (good) or leaky (bad)

### Step 1.3: Read Layer 2 (Domain — Core Logic)

```bash
cat libs/congine-sdk/src/congine_core/domain/models.py
cat libs/congine-sdk/src/congine_core/domain/validator.py
```

For `RuleEngine`, document each rule:
- Rule name
- What it checks
- What a `BreachDetail` looks like when this rule fires
- Any edge cases you can spot that are not handled

For `LocalValidator` and `CompositeValidator`, document:
- How they compose the rule engine
- What the merge logic is for composite validation
- The exact shape of the returned `ValidationResult`

### Step 1.4: Read Layer 3 (Use Cases)

```bash
cat libs/congine-sdk/src/congine_core/usecases/validate_contract_usecase.py
cat libs/congine-sdk/src/congine_core/usecases/sync_contracts_usecase.py
```

For `ValidateContractUseCase`:
- Trace the exact execution path from `execute()` entry to exit for the happy path (valid payload)
- Trace the path for an invalid payload in DEGRADE mode
- Trace the path for an invalid payload in STRICT mode
- Document every exception that can be raised and why

For `SyncContractsUseCase`:
- Document the single-flight boot mechanism
- Document what happens if the HTTP fetch fails (snapshot fallback)
- Identify the background sync interval and what triggers it

### Step 1.5: Read Layer 4 (Infrastructure)

```bash
ls libs/congine-sdk/src/congine_core/infrastructure/
cat libs/congine-sdk/src/congine_core/infrastructure/bounded_executor.py
cat libs/congine-sdk/src/congine_core/infrastructure/lfu_cache.py
cat libs/congine-sdk/src/congine_core/infrastructure/circuit_breaker.py
cat libs/congine-sdk/src/congine_core/infrastructure/queue_event_bus.py
cat libs/congine-sdk/src/congine_core/infrastructure/http_contract_repository.py
cat libs/congine-sdk/src/congine_core/infrastructure/file_contract_repository.py
cat libs/congine-sdk/src/congine_core/infrastructure/jsonschema_validator.py
```

For each infrastructure component, document:
- **BoundedValidationExecutor:** semaphore capacity formula, re-entrancy mechanism, timeout behavior, async path
- **LFUCache:** O(1) put/get proof, TTL sweep mechanism, eviction policy, thread safety
- **CircuitBreaker:** state machine (CLOSED → OPEN → HALF_OPEN), thresholds, probe timeout
- **QueueEventBus:** queue max size, drain loop behavior, what happens when queue is full, daemon thread lifecycle
- **HttpContractRepository:** retry logic, authentication mechanism, snapshot atomic write path
- **FileContractRepository:** directory scanning, what file format it expects, error handling

### Step 1.6: Read Layer 5 (Adapters)

```bash
cat libs/congine-sdk/src/congine_core/adapters/dependency_injection.py
cat libs/congine-sdk/src/congine_core/adapters/guard.py
cat libs/congine-sdk/src/congine_core/adapters/langchain_handler.py
```

For `ServiceContainer`:
- Document the single-tenant vs multi-tenant initialization path
- Document the `for_tenant()` method and how tenant isolation works
- Identify the tenant eviction bug (evicts oldest, not LRU) and note it clearly as TECHNICAL DEBT

For `@congine_guard`:
- Document all three modes: `envelope`, `output`, `raise`
- Document sync vs async wrapper behavior
- Document the `extractor` parameter and what it does

For `CongineCallbackHandler`:
- Document which LangChain callbacks are hooked
- Document what events trigger validation

---

## PHASE 2: SYSTEM STATE ASSESSMENT

After reading all code, generate a document at `docs/context/01_SYSTEM_STATE.md` with this exact structure:

```markdown
# CONGINE SYSTEM STATE
Generated: [DATE]
Revision: Based on code analysis, no documentation assumed

## What Is Fully Implemented and Tested
[List each component with its test file reference]

## What Is Implemented but Untested (or Under-Tested)
[List each component and what test scenarios are missing]

## What Is Partially Implemented
[List each half-built feature with what's done and what's missing]

## What Does Not Exist Yet (Referenced in Docs but Not in Code)
[List missing features that appear in comments or TODOs but have no implementation]

## Known Bugs and Technical Debt
[List each one with: location (file:line), severity (LOW/MEDIUM/HIGH/CRITICAL), effort to fix (SMALL/MEDIUM/LARGE)]

## Hot Path Guarantees: Verify Each One
For each guarantee listed in the README/audit files, confirm whether the code actually
implements it or if it's aspirational:
- [ ] Bounded latency / load shedding
- [ ] No control-plane stall on boot
- [ ] No thundering herd
- [ ] Snapshot integrity
- [ ] No ReDoS
- [ ] Multi-tenant isolation in MULTI_TENANT mode
- [ ] PII-safe telemetry
```

---

## PHASE 3: COMPONENT DEPENDENCY MAP

Generate `docs/context/02_COMPONENT_MAP.md` with:

```markdown
# CONGINE COMPONENT DEPENDENCY MAP

## Dependency Graph (who calls who)
[Generate a text-based dependency graph showing which modules import which other modules]

## Public API Surface
[List every class and function that is exported from congine_core/__init__.py]
[For each: what it does, who the intended caller is, what it requires]

## Extension Points
[For each Port (Protocol), list: the interface, the current concrete implementations,
 and what a new implementation would need to provide]

## Wiring Map
[Show exactly how ServiceContainer wires each Port to its Implementation]
[This should be readable as: "When X is configured, IY is implemented by Z"]
```

---

## PHASE 4: EXECUTION TRACE DOCUMENTATION

Generate `docs/context/03_EXECUTION_TRACES.md` with step-by-step traces for these five scenarios. For each scenario, show the exact method call chain with file:line references.

**Trace 1: Happy Path (valid payload, single tenant, HTTP contracts)**
- Start: `@congine_guard` intercepts function return
- End: Function caller receives `envelope` result with `is_valid=True`

**Trace 2: Validation Failure in DEGRADE Mode**
- Start: `@congine_guard` intercepts function return
- End: Function caller receives `envelope` result with `is_valid=False` and breach list
- Include: what gets logged, what gets queued to telemetry

**Trace 3: Validation Failure in STRICT Mode**
- Start: same as Trace 2
- End: `CongineValidationError` raised to the caller

**Trace 4: Load Shedding (pool saturated)**
- Start: `BoundedValidationExecutor` receives request when semaphore is full
- End: Caller receives DEGRADE fallback (not a crash)

**Trace 5: Cold Boot on Fresh Container (HTTP mode)**
- Start: `ServiceContainer.bootstrap()` called
- End: Cache is primed, background sync worker is running
- Include: what happens if HTTP fetch fails during boot

---

## PHASE 5: PHASE ROADMAP WITH REDIRECTED EXECUTION PLAN

Generate `docs/context/04_PHASE_ROADMAP.md` with this structure:

```markdown
# CONGINE PHASED ROADMAP
## Based on Current Code State + Strategic Direction

---

## PHASE 0 COMPLETION CHECKLIST (Complete Before Moving On)

[List remaining items needed to call Phase 0 "done", ordered by priority]

For each item:
- **Task:** [specific thing to build]
- **File(s) to modify:** [exact file paths]
- **Acceptance criteria:** [how you know it's done — a specific test assertion or behavior]
- **Estimated complexity:** [S/M/L]

---

## PHASE 1: INTEGRATION LAYER (MCP + CLI + Persistence)

### 1A: MCP Server (Make Congine Callable by Coding Agents)

**What to build:** A Congine MCP server that exposes validation as tools that
Claude Code, Cursor, and other MCP-compatible agents can call during their reasoning loop.

**New files needed:**
- `libs/congine-sdk/src/congine_core/mcp/server.py` — MCPServer class
- `libs/congine-sdk/src/congine_core/mcp/tools.py` — tool definitions
- `libs/congine-sdk/src/congine_core/mcp/transport.py` — stdio and HTTP/SSE transport

**Port interface needed:**
- `IMCPTransport` in `ports/mcp_transport.py`

**Dependencies to add:**
- `mcp` Python library (Anthropic's MCP SDK)

**Tool definitions to implement:**
```
Tool: validate_output
  Description: Validate a function output against a contract
  Input: { output: dict, contract_id: str, version: str? }
  Output: { valid: bool, violations: list[BreachDetail], correction_hints: list[str] }

Tool: validate_code_change
  Description: Validate a code change against architectural contracts
  Input: { files_changed: list[FileChange], contracts: list[str] }
  Output: { valid: bool, violations: list[ArchViolation] }

Tool: list_contracts
  Description: Get all active contracts for a project
  Input: { project_id: str, tenant_id: str? }
  Output: { contracts: list[ContractSummary] }
```

**Acceptance criteria:** A Claude Code session with Congine MCP connected can
call `validate_output` and receive a structured breach report.

### 1B: CLI Tool (Make Congine Runnable from Git Hooks + CI)

**What to build:** `congine-validate` command-line tool

**New files needed:**
- `libs/congine-sdk/src/congine_core/cli/main.py` — Click CLI entry point
- `libs/congine-sdk/src/congine_core/cli/diff_parser.py` — parse git diff to extract changes

**Commands to implement:**
```bash
congine validate --payload <json_file> --contract <contract_id>
congine validate-diff --diff <diff_file> --contracts-dir <dir>
congine health  # check if control plane is reachable and cache is primed
congine list-contracts --project-id <id>
```

**Acceptance criteria:** `git diff --cached | congine validate-diff --stdin` returns
exit code 0 on valid and 1 on violation, with breach details on stderr.

### 1C: Persistent Event Store (Make Congine Remember)

**What to build:** `SqliteEventBus` that implements `IEventBus` and persists all
validation events to a local SQLite database in WAL mode.

**New files needed:**
- `libs/congine-sdk/src/congine_core/infrastructure/sqlite_event_bus.py`
- `libs/congine-sdk/src/congine_core/domain/models.py` — extend `TelemetryEvent` with project context fields

**Extended TelemetryEvent fields to add:**
```python
project_id: Optional[str]
agent_id: Optional[str]        # "cursor" | "claude_code" | "copilot" | "human"
file_paths: List[str]          # files being validated/modified
git_commit_sha: Optional[str]  # current HEAD sha
session_id: Optional[str]      # groups events from same agent session
```

**Query methods to add to `ValidateContractUseCase`:**
```python
def get_violation_history(
    project_id: str, 
    file_paths: Optional[List[str]] = None,
    contract_id: Optional[str] = None,
    limit: int = 10
) -> List[TelemetryEvent]

def get_violation_frequency(
    project_id: str,
    lookback_days: int = 30
) -> Dict[str, int]  # contract_id -> violation count
```

**Acceptance criteria:** After 10 validation runs, `get_violation_history(project_id)` 
returns 10 events. After pod restart, events are still retrievable.

---

## PHASE 2: INTELLIGENCE LAYER (History + Pattern Detection + Architectural Graph)

[Describe Phase 2 components at the same level of detail as Phase 1]

### 2A: Architectural Component Graph
[detail]

### 2B: Violation Pattern Detection  
[detail]

### 2C: Agent-Readable Correction Hints
[detail]

---

## PHASE 3: ENTERPRISE LAYER (Distribution + Compliance + Auth)

[Describe Phase 3 at high level — this is further out, keep it directional not prescriptive]

### 3A: Distributed Cache + Control Plane
### 3B: RBAC/ABAC Integration
### 3C: OpenTelemetry + Prometheus
### 3D: Durable Audit Trail (WAL → SIEM)

---

## WHAT MUST NOT BE BUILT BEFORE ITS TIME

[Generate a list of things that should NOT be built in Phase 0 or 1,
with a one-line explanation of why each one is premature]

Examples:
- WASM validation sandbox: premature until multi-tenant isolation is actually needed
- Redis distributed cache: premature until you have >1 pod in production
- OPA/Rego policy language: premature until JSON Schema is proven insufficient
```

---

## PHASE 6: FIVE-MINUTE QUICKSTART VALIDATION

Generate `docs/context/05_QUICKSTART_TEST.md`:

```markdown
# QUICKSTART VALIDATION
## Can a New Developer Integrate Congine in 5 Minutes?

### Step 1: Install
[Exact pip install command]

### Step 2: Configure
[Minimum required environment variables and config]

### Step 3: Define a Contract
[Minimal example contract JSON — the simplest possible valid contract]

### Step 4: Apply the Guard
[Exact Python code — 3-5 lines maximum]

### Step 5: Run It
[What the developer should see when it works, and what they should see on a violation]

## Gaps Found
[List anything that would block a new developer from completing these 5 steps]
```

---

## PHASE 7: FINAL SYNTHESIS

After generating all context documents (01 through 05), write a final summary to stdout:

```
=== CONGINE SYSTEM ANALYSIS COMPLETE ===

Documents generated:
- docs/context/01_SYSTEM_STATE.md
- docs/context/02_COMPONENT_MAP.md
- docs/context/03_EXECUTION_TRACES.md
- docs/context/04_PHASE_ROADMAP.md
- docs/context/05_QUICKSTART_TEST.md

Critical findings that require immediate attention:
[List 3-5 most important issues found, ordered by severity]

Recommended first action:
[One specific task — the single most important thing to do next]

Phase 0 completion percentage (honest estimate): [X]%
Phase 1 readiness (can you start Phase 1): YES / NOT YET / BLOCKED BY [reason]
```

---

## CONSTRAINTS FOR THIS ANALYSIS

- **Read code before writing any document.** Never write a document about a file you haven't read.
- **Reference specific line numbers** when noting bugs or behaviors (e.g., "line 84 of bounded_executor.py").
- **Never describe aspirational features as implemented.** If it's not in the code, it doesn't exist.
- **Flag every TODO and FIXME** you find and include it in the technical debt list.
- **If a test is missing for a critical component**, name it explicitly as a gap.
- **If you hit a file that doesn't exist** (expected based on architecture but not found), note it as a gap.
- **Produce documents progressively** — don't wait until all analysis is done. Generate each document as you finish its corresponding phase.

Begin with Phase 0 (environment orientation). Ask for clarification if any path is ambiguous.

