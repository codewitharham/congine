# 05 — IMPLEMENTATION ROADMAP (Task 2)

**Purpose:** The strict, linear build order for the core engine, with each phase broken into
from-scratch steps, an explicit "done" test, and the security framework that phase must satisfy. This is
written for someone taking the codebase over cold, so nothing is assumed. Follow it top to bottom; do not
skip; do not parallelize across phases (parallelize *within* a phase if you must).

**Prerequisite reading:** `00`–`04`. This roadmap assumes you've internalized that the three problems are
*layered*, not parallel, and that everything stands on the Phase 0 core.

---

## THE ORDER, AND WHY IT IS FORCED

You have three problems. They do not map to three sequential phases, because they interleave by
dependency. The correct build order is six phases:

```
A. Harden the foundation + make it addressable   (finish Phase 0 debt + CLI)
B. MCP server                                     (the substrate all three problems need)
C. Persistence / History foundation               (Problem 2, Phase 1 — the data spine)
D. Correction hints + context compression         (Problem 1, deepened — needs B, benefits from C)
E. History intelligence + agent adapters          (Problem 2 Phase 2 + Problem 3 Phase 2 — need C running)
F. Adaptive routing                               (Problem 3 Phase 3 — optional before funding)
```

The dependency logic, stated once so you never doubt the order:
- **B before everything clever**, because the MCP server is how the engine reaches the agent; without a
  mouth, none of the three problems can act in-loop.
- **C early (before D and E)**, because the event log is the *data spine*: Problem 1's compressed context
  wants relevant history, and Problem 3's capability profiles are *computed from* the log. Build the well
  before you drink from it.
- **D after B/C**, because correction hints are delivered *through* the MCP surface and the compressed
  context *includes* history.
- **E after C has run a while**, because the architectural graph and capability profiles need
  *accumulated* events to be meaningful. A profile from three data points is noise.
- **F last and optional**, because routing is a polish layer on top of profiles; you can raise funding
  without it.

Your three "problems" therefore spread across phases like this:

| Problem | Seeded | Activated | Completed |
|---|---|---|---|
| 1 — Token optimization | A (RuleEngine exists) | B (in-loop validation) | D (hints + compression + caching) |
| 2 — Tracking history | C (event log) | C | E (graph + patterns) |
| 3 — Normalization | B (contract = one standard) | E (adapters + profiles) | F (routing) |

---

## PHASE A — HARDEN THE FOUNDATION + MAKE IT ADDRESSABLE

**Why first:** You cannot build higher floors on a cracked foundation, and — bluntly — investors and
design partners will *run your demo*. A silent-failure bug during a demo kills trust faster than a missing
feature. This phase is unglamorous and non-negotiable. Everything here is drawn from your own audit files
(`01_SYSTEM_STATE.md` debts, `04_PHASE_ROADMAP.md` Phase 0 checklist).

**From-scratch steps:**
1. **Fix the Python version contradiction (debt #3 / Bug A1).** Pick one floor (recommend 3.11 to match
   `requires-python`), make pyproject classifiers, ruff `target-version`, and CI matrix all agree.
2. **Fix the byte-vs-char size guard (debt #4 / Bug B10).** In `validate_contract_usecase.py`, measure
   `len(json.dumps(payload).encode("utf-8"))` so the byte-named budget is honored for multibyte payloads.
3. **Close the silent-schema-keyword trap (debt #8 / Bug B14) — highest-leverage correctness item.** When
   a contract uses keywords the `RuleEngine` ignores (`minLength`, `maxLength`, `format`, …) while
   semantic validation is off, emit a WARNING naming the unenforced keyword. A firewall that silently
   passes packets is worse than none — it manufactures false confidence.
4. **Harden multi-tenant eviction (debt #2 / Bug B9) — the top correctness bug.** Make `for_tenant()`
   eviction safe: don't `close()` a container that may still be referenced (refcount or idle-time policy);
   keep the registry LRU semantics honest. Add the missing direct test.
5. **Fix the LangChain example (debt #1 / Bug B15).** Align the offline-fallback action with the contract
   enum so `python agent.py` completes the clean scenario without raising when no API key is set. This is
   your *first impression*; it must run.
6. **Doc/dead-code cleanup (debt #5, #9).** Fix the stale `TelemetryEvent` "mutable" docstring; decide the
   fate of the deprecated `ValidationTimer`.
7. **Build the CLI (Phase 1B in your roadmap).** `congine validate`, `validate-diff`, `health`,
   `list-contracts`. Prefer stdlib `argparse` (dependency-light). Add `diff_parser.py` (you'll reuse it
   for token compression and the arch graph). Add `[project.scripts]` entry point. This unlocks git-hook
   and CI usage and is the delivery vehicle for Problem 1's zero-token validation.
8. **Add the missing container tests** (`bootstrap()` loop-guard, `health()` shape, `reset_default()`) —
   the container is your most integration-heavy, least-directly-tested module.

**Done test:** `uv sync` succeeds on the declared Python floor; the multibyte payload just over
`max_payload_bytes` is rejected with `INPUT_BOUNDS`; loading a contract with `minLength` under default
config emits exactly one WARNING; the 129th tenant evicts safely with a passing
`test_container_tenant_lru.py`; `python examples/LangChain/agent.py` with no API key completes Scenario 1
without raising; `git diff --cached | congine validate-diff --stdin --contracts-dir ./contracts` returns 0
on valid input and 1 (with breaches on stderr) on a violation.

**Security framework for Phase A:**
- **Threat-model the existing surface with STRIDE** (Spoofing, Tampering, Repudiation, Information
  disclosure, Denial of service, Elevation of privilege) per component. Document it. This is your baseline.
- **Verify the seven Phase 0 guarantees still hold** after your edits (`01_SYSTEM_STATE.md` lists them:
  bounded latency, no boot stall, no thundering herd, snapshot integrity, no ReDoS, tenant isolation,
  PII-safe telemetry). Don't regress a guarantee while fixing a bug.
- **Fix the one `re2` inconsistency (debt #6)** in `pii_sanitize.py` if cheap — it's the single regex
  bypassing your project-wide linear-time rule.

---

## PHASE B — MCP SERVER (the substrate all three problems need)

**Why now:** This is the engine's mouth. Until it exists, none of the three problems can act inside a
coding agent's loop. It is also the phase that produces your funding demo. (Your `04_PHASE_ROADMAP.md`
Phase 1A.)

**From-scratch steps:**
1. **Add the port:** `ports/mcp_transport.py` → `IMCPTransport` (stdio + HTTP/SSE). Keep it a Protocol,
   like every other port.
2. **Add the optional dependency** `mcp` (Anthropic MCP SDK) as extra `[mcp]`, following the existing
   `[langchain]`/`[stats]` gating pattern — the core stays dependency-light.
3. **Build `mcp/server.py`** (`MCPServer` wrapping a `ServiceContainer`), `mcp/tools.py` (tool
   definitions/handlers), `mcp/transport.py`.
4. **Expose these tools** (reusing existing use cases — do not reimplement validation):
   - `validate_output { output, contract_id, version? } -> { valid, violations, correction_hints }`
     (thin wrapper over `ValidateContractUseCase.execute`)
   - `validate_code_change { files_changed, contracts } -> { valid, violations }`
   - `list_contracts { project_id, tenant_id? } -> { contracts }`
5. **Ship a system-prompt template** that instructs the agent to call `validate_code_change` *before*
   writing to disk. This is where your value locks in organizationally — the tool is useless if the agent
   doesn't call it, and the prompt is what makes it call it. (This is the *product*, not an afterthought.)
6. **Write an integration test** that drives the server over stdio and asserts a structured breach report.

**Done test:** a Claude Code (or MCP-client) session with the Congine server connected calls
`validate_output`, receives a structured breach report, and — the demo moment — an agent that drafts a
contract-violating change gets blocked in-loop and corrects. Integration test passes over stdio.

**Security framework for Phase B (this is a NEW attack surface — take it seriously):**
- **OWASP API Security Top 10** applies to your MCP endpoints (especially the HTTP/SSE transport):
  authenticate clients, authorize tool calls, rate-limit, reject malformed requests.
- **Schema-validate every tool input as untrusted.** An MCP call is external input. Validate
  `files_changed`, `contract_id`, etc., against strict schemas before processing. (You have a validation
  engine — use it on your own inputs.)
- **OWASP LLM Top 10 — LLM01 (Prompt Injection):** an instruction embedded in the *content* an agent
  sends to a tool is not the same as a user instruction. Treat tool-call content as data, not commands;
  never let a payload's content reconfigure the engine.
- **Tenant/authz at the MCP boundary:** ensure a client can only validate against contracts it's
  authorized for — don't leak one tenant's contracts via `list_contracts`.
- **Transport hardening:** for HTTP/SSE, TLS, origin checks, and per-client rate limits; for stdio, ensure
  the local process boundary is respected.

---

## PHASE C — PERSISTENCE / HISTORY FOUNDATION (Problem 2, Phase 1 — the data spine)

**Why now:** Everything downstream drinks from the event log. Build the well before D and E need it. (Your
`04_PHASE_ROADMAP.md` Phase 1C.)

**From-scratch steps:**
1. **Extend `TelemetryEvent`** (it's `frozen=True`; add fields with defaults to stay backward-compatible):
   `project_id`, `agent_id`, `file_paths`, `git_commit_sha`, `session_id`. Store a `payload_hash`, not the
   payload.
2. **Build `infrastructure/sqlite_event_bus.py`** implementing the existing `IEventBus` — SQLite in **WAL
   mode**, so hot-path writes and history reads don't block each other. Because it satisfies the existing
   port, the `ValidateContractUseCase` does not change.
3. **Wire it behind a config flag:** container selects `SqliteEventBus` when `CONGINE_EVENT_STORE=sqlite`
   (+ `CONGINE_EVENT_STORE_PATH`); default stays `QueueEventBus`/`NoOpEventBus`. Remember the 4-touch
   config rule (field → `from_env` → container wiring → README table).
4. **Add `usecases/history_query_usecase.py`** (cleaner than bolting queries onto the validate use case):
   `get_violation_history(project_id, file_paths?, contract_id?, limit)` and
   `get_violation_frequency(project_id, lookback_days) -> {contract_id: count}`.
5. **Index** the store for the queries you'll actually run (project_id, file_paths, contract_id,
   timestamp).

**Done test:** after 10 validation runs, `get_violation_history(project_id)` returns 10 events; after a
process restart they are still retrievable; hot-path validation latency is unaffected (WAL concurrency
verified under a concurrent read+write test).

**Security framework for Phase C (durable data = durable risk):**
- **Data minimization:** store hashes, not payloads. If content must be kept, sanitize with
  `pii_sanitize` and put it in a *separate, erasable* store — never the immutable log.
- **Tamper-evidence:** chain events (`chain_hash = SHA256(prev_chain_hash + event_content)`) so retroactive
  edits are detectable. This is a real enterprise differentiator and cheap to add now.
- **Encryption at rest** for the store; **least-privilege** DB access; **per-tenant scoping** of queries
  (don't leak tenant A's history to B, even before full RBAC exists).
- **Read-back sanitization:** anything from the log re-injected into a prompt is a prompt-injection vector
  — sanitize on read, per `03` §5.4.
- **Erasure design (GDPR):** immutable log holds hashes + tombstones; erasable content store holds
  human-readable content; erasure deletes content, keeps the integrity chain intact. Design it now.
- **Retention/compaction policy:** define up front; immutable logs grow forever.

---

## PHASE D — CORRECTION HINTS + CONTEXT COMPRESSION (Problem 1, deepened)

**Why now:** Needs the MCP surface (B) to deliver hints and the history store (C) to include relevant
context. This is where the token-optimization story reaches full form. (Your `04_PHASE_ROADMAP.md` 2C
correction hints + the compression work.)

**From-scratch steps:**
1. **Add `correction_hint` to `BreachDetail`** (backward-compatible) and build **`domain/correction_hints.py`**
   — a *pure, table-driven* mapping from `(rule, field)` → deterministic fix template (e.g. `ENUM_VALUES` →
   "expected one of […]"; `RANGE_CHECK` → "clamp to [min,max]"). **No LLM.** Determinism is the whole point.
2. **Build the compressed-context / delta protocol** in the MCP layer: use `diff_parser` (from A) to
   extract only changed regions; inject only the *relevant* contract rule(s), keyed by the fields the change
   touches. Target 90%+ reduction on the volatile prompt portion.
3. **Assemble prompts stable-prefix-first** for any LLM call Congine itself makes: `[role][contracts]
   [history summary]` (cacheable) then `[delta/task]` (volatile), with the provider cache breakpoint after
   the stable layers. This is how you *earn* provider prompt caching (see `02`, Lever 4).
4. **Add the tiered semantic path** *only if needed*: Tier 1 (RuleEngine) → Tier 2 (JSON Schema) → Tier 3
   (small model, binary output, cached prefix, result-cached by `hash(rule_id, payload_hash, contract_version)`).
   Most traffic must die in Tiers 1–2.
5. **Instrument the savings:** log attempts-to-converge and tokens-per-task with vs without Congine so you
   can produce the funding number (`savings ≈ N_violations × (T_retry − T_correction)`).

**Done test:** a violating change produces a deterministic `correction_hint` that an agent uses to fix in
one attempt; the delta protocol sends <10% of the tokens a whole-file approach would; a repeated call within
a session shows a provider cache hit on the stable prefix; instrumentation reports a concrete token-savings
figure on a benchmark task.

**Security framework for Phase D:**
- **OWASP LLM Top 10 — LLM01 (injection) + LLM02 (output handling):** every byte injected into a prompt is
  an injection surface; sanitize contracts (trusted provenance) and history (untrusted, escape on read-back).
- **Cross-tenant cache scoping:** cacheable prefixes and result-cache keys must include tenant identity, or
  you leak/contaminate across tenants (`02` §4.2, §4.4).
- **Denial-of-wallet:** rate-limit Tier-3 LLM escalation per tenant; keep load-shedding on the LLM path.
- **Cache-key completeness:** result-cache keys must cover everything affecting the verdict (contract
  version!) or a stale entry passes a payload that should fail.

---

## PHASE E — HISTORY INTELLIGENCE + AGENT ADAPTERS (Problem 2 Phase 2 + Problem 3 Phase 2)

**Why now:** Needs C to have accumulated real events. The graph and profiles are meaningless on sparse
data. (Your `04_PHASE_ROADMAP.md` 2A/2B + Problem 3 adapters from `04`.)

**From-scratch steps (two tracks; can run in parallel *within* this phase):**

*Track E1 — History intelligence:*
1. **`domain/arch_graph.py`** (pure): build the directed import/ownership graph from parsed diffs
   (`diff_parser`). Nodes = components + layer; edges = imports/calls with a `is_violation` flag.
2. **`usecases/validate_arch_usecase.py`**: check proposed edges against contracts (forbidden-edge, cycle
   detection, reachability). Output `ArchViolation(from, to, rule)` — the type `validate_code_change`
   already promises. This is your most differentiating capability: judging changes against the *current
   architecture* without the agent sending the whole codebase.
3. **`usecases/pattern_detection_usecase.py`**: over the event log, detect recurring `(contract_id, field,
   rule)` clusters and per-file hotspots; reuse `KSDriftEngine` for rate-drift on violation frequency.

*Track E2 — Agent adapters:*
4. **`ports/agent_adapter.py`** → `IAgentAdapter` (`to_agent_request`, `from_agent_output`, `frame_prompt`).
5. **`infrastructure/adapters/{claude,openai,oss}.py`** implementing it — translation + output
   normalization + agent-specific framing. Anti-corruption layer: after `from_agent_output`, the core never
   knows which agent spoke.
6. **Capability profiles:** aggregate the event log per `(agent, contract_type)` — success rate, avg
   retries, cost — and expose a `CapabilityProfile` the adapters use for prompt framing.

**Done test (E1):** proposing an edge that violates the "domain must not import infrastructure" rule yields
an `ArchViolation` *without* sending the whole codebase; a file with recurring violations is flagged as a
hotspot; KS flags an injected violation-rate shift. **Done test (E2):** the same canonical task validated
through two different agent adapters produces normalized outputs judged by the *same* contract; a
capability profile computed from ≥N events reports plausible per-agent success rates.

**Security framework for Phase E:**
- **Zero-trust agent boundary (the core rule):** validate/sanitize agent output in `from_agent_output`
  before it touches the core — *provenance is never safety* (`04` §4.1).
- **Per-agent isolation:** separate contexts, credentials, caches; cache keys include agent identity.
- **Secrets management:** per-agent credentials in a vault, scoped per tenant/agent; extend the logger's
  secret blocklist to every new credential field.
- **Supply-chain (open-source adapters):** pin deps, SBOM, `pip-audit`, validate model provenance;
  every adapter's transitive deps are new surface.
- **Graph-input validation:** the arch graph is built from parsed diffs (untrusted) — validate before
  ingesting; malformed diffs rejected, not coerced.

---

## PHASE F — ADAPTIVE ROUTING (Problem 3 Phase 3 — optional before funding)

**Why last / optional:** Routing is polish on top of profiles. You can raise without it. Build it only when
capability profiles are populated and you have multiple agents in real use.

**From-scratch steps:**
1. **Capability-based routing:** given a task + candidate agents + profiles, pick the best-fit agent.
2. **Contextual bandit** (Thompson sampling or UCB) for *online* routing — balance exploit (use the known-good
   agent) vs explore (try another to see if it's better now). A few dozen lines; **not** a neural network.
3. **Drift-triggered re-profiling:** when `KSDriftEngine` flags an agent's performance shift, re-open
   exploration for that agent.

**Done test:** on a synthetic workload where agent quality varies by contract type, the router converges to
routing each contract type to its best agent, and re-explores after an injected performance shift.

**Security framework for Phase F:**
- **Routing integrity:** routing decisions must not be manipulable by crafted inputs (an attacker shouldn't
  be able to force routing to a weak/compromised agent). Validate routing inputs.
- **Fairness/starvation:** ensure the bandit doesn't permanently starve an agent based on a transient dip
  (a availability/robustness concern).
- Carry forward all Phase E agent-boundary and secrets controls.

---

## THE ROADMAP IN ONE TABLE

| Phase | Delivers | Core new code | Security anchor | Gate to next |
|---|---|---|---|---|
| A | Trustworthy foundation + CLI | debt fixes, `cli/*`, `diff_parser` | STRIDE baseline, guarantees hold | demo doesn't silently fail |
| B | MCP surface + demo | `mcp/*`, `IMCPTransport`, prompt template | OWASP API + LLM01, authz | agent blocked in-loop, corrects |
| C | Durable memory (data spine) | `SqliteEventBus`, extended event, `HistoryQueryUseCase` | data minimization, tamper-evidence, erasure design | history survives restart |
| D | Full token story | `correction_hints`, delta protocol, cached assembly, tiers | LLM01/LLM02, cache scoping, denial-of-wallet | concrete savings number |
| E | Arch graph + adapters | `arch_graph`, `validate_arch_usecase`, `IAgentAdapter`, profiles | zero-trust agent boundary, supply-chain | graph judges change w/o whole codebase |
| F | Adaptive routing (optional) | router, contextual bandit | routing integrity | converges + re-explores on drift |

Build A→B→C→D, and you have a fundable core engine. E strengthens the story; F is post-funding polish.
Do not build F before B is rock-solid. The temptation to jump to the exciting parts (routing, learned
behavior) before the foundation is trustworthy is the single most common way early engine teams ship
"another vibe-coded app with vulnerabilities" — which you explicitly said you refuse to be.
