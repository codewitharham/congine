## 15. Extension seams — where the next phases attach

Everything in this section **does not exist today**. Each entry states the absence with evidence,
then identifies the exact attachment point in the current architecture and what would have to
change. Where a seam is already adequate the entry says so; where the current code would have to
move, it says that too, plainly.

The governing observation: of the eight planned capabilities, **six attach cleanly at L1/L4/L5 with
no change to L2 or L3**. Two (history queries and correction hints) require additive changes to L2
value objects or a new L3 use case. **Nothing requires modifying `RuleEngine` or
`ValidateContractUseCase`'s orchestration.**

### 15.1 MCP server

**Confirmed absent.** No `mcp/` directory under `src/congine_core/`. No `IMCPTransport` — `ports/`
contains exactly seven modules (§3.2). No `mcp` extra in `pyproject.toml:41-57` (which declares
`langchain`, `stats`, `redos`, `dev`).

**Where it attaches.** L5, as a **third entry point** beside `guard.py` and `langchain_handler.py`.
An `MCPServer` wraps a `ServiceContainer` exactly as `CongineCallbackHandler` does
(`langchain_handler.py:52`) and calls `container.validate_contract_usecase.execute(...)` — the same
call `guard.py:79` makes. It is a peer of the existing adapters, not a layer.

**What must change:** nothing in L0–L4. A new `ports/mcp_transport.py` if transport is to be
swappable (`IMCPTransport` would be the eighth port, following the same `@runtime_checkable
Protocol` shape). A new `[mcp]` extra following the `[langchain]` gating pattern, and lazy exposure
via `adapters/__init__.py.__getattr__` (`:18-26`) so the core stays dependency-light.

**Existing precedent to copy.** `langchain_handler.py` is the reference implementation of "optional
L5 adapter": module-level try/except for the dependency (`:8-16`), function-local Congine imports
(`:38-40`), a directed `ImportError` in the constructor (`:33-37`), a multi-tenant guard (`:42-51`),
and never letting a validation exception escape the framework callback (`:105-119`).

**Two things the MCP surface must supply that no current caller does.** First, an MCP tool call is
untrusted external input — `contract_id` and any payload arrive from outside the process, whereas
today every caller is in-process host code. Second, `list_contracts` would be the first API that
*enumerates* contracts; `ISchemaStorage` has no enumeration method (`get`/`put`/`clear`/`exists`
only, §5.1), so either the port grows a method or the server reads from the repository. Growing the
port is the cleaner move and is backward-compatible for `LFUCache`.

### 15.2 Persistent event store (`SqliteEventBus`)

**Confirmed absent.** `infrastructure/` contains exactly two `IEventBus` implementations,
`QueueEventBus` and `NoOpEventBus` (`infrastructure/__init__.py:19-20`). No SQLite anywhere in
`src/`.

**Where it attaches.** L4, as a **third implementation of the existing `IEventBus` port**. This is
the cleanest seam in the entire system: `publish(event)` is a one-method Protocol
(`ports/event_bus.py:24`), and `ValidateContractUseCase` never learns which bus it holds.

**What must change:** one new L4 file, plus **one new branch in `dependency_injection.py:261-280`**
and the corresponding config fields (`event_store`, `event_store_path`). Nothing in L2 or L3.

**The non-obvious obligation.** Beyond `publish`, the container calls `queue_depth()`
(`:411`), `stop(drain)` (`:452`) and optionally `dropped_total()` (`:406`) — none of which is
declared on `IEventBus` (§5.9). A `SqliteEventBus` must implement all three or `health()` and
`close()` will `AttributeError`. `NoOpEventBus` implements them for exactly this reason
(`noop_event_bus.py:30-40`) and is the template to copy.

**The second obligation, which is a design constraint rather than a signature.** `publish` runs on
the hot path and must not block (G11, §14.11). A synchronous SQLite write in `publish` would put
disk I/O inside the validation path. The correct shape reuses `QueueEventBus`'s architecture —
enqueue on the hot path, write from the daemon — which means `SqliteEventBus` is closer to "swap
`_ship`'s HTTP POST for a SQLite `INSERT`" than to a from-scratch implementation. WAL mode is what
keeps history reads from blocking those writes.

### 15.3 Extended `TelemetryEvent`

**Confirmed absent.** `domain/models.py:91-96` declares exactly six fields:
`contract_id`, `contract_version`, `status`, `duration_ms`, `breach_details`, `created_at`. No
`project_id`, `agent_id`, `file_paths`, `git_commit_sha`, `session_id`, `payload_hash`.

**Where it attaches.** L2, as **additive fields with defaults** on a frozen dataclass. Because
`frozen=True` and every existing construction site uses keyword arguments
(`validate_contract_usecase.py:211-224`, `dependency_injection.py:388-401`), adding defaulted fields
is backward-compatible for construction.

**What must change.** Three things, and only the first is trivial:

1. The dataclass fields themselves.
2. **`QueueEventBus._serialize`** (`:283-296`) hard-codes the six keys. New fields are silently
   dropped from the wire until it is updated. It uses `getattr(event, k, None)` throughout, so it
   will not crash — it will just omit them, which is the quiet failure mode.
3. **Something must populate them.** `_finalize` (`:211-224`) is the only construction site on the
   hot path and it has access to `contract_id`, `contract_version` and the result — nothing else.
   `project_id`/`tenant_id` live on `CongineConfig`, which `ValidateContractUseCase` does **not**
   hold (it receives `fail_mode` and the two size bounds, not the config object —
   `dependency_injection.py:301-311`). `agent_id`/`file_paths`/`session_id` are call-scoped and
   would have to travel through `execute()`'s signature.

**This is the one place where "no L3 change" is not achievable.** Populating an extended event
requires either widening `ValidateContractUseCase.__init__` to take identity fields, or widening
`execute()` to take a per-call context. The latter also touches `guard.py` and every caller. Worth
deciding deliberately rather than discovering mid-implementation.

### 15.4 History query use case

**Confirmed absent.** `usecases/` contains exactly two modules (`usecases/__init__.py:6-7`).
`ValidateContractUseCase` has no query methods (`:24-260`).

**Where it attaches.** L3, as a **new use case**, and L1, as a new read port over the event store
(the existing `IEventBus` is write-only by design — one method, `publish`). A `HistoryQueryUseCase`
would depend on an `IEventStore`-shaped port that `SqliteEventBus` also implements.

**What must change:** one new L1 port, one new L3 use case, one new attribute on `ServiceContainer`,
plus §15.2. Nothing in L2, nothing in the existing L3 orchestration. Depends on §15.2 and §15.3.

**Cross-tenant scoping is a port-design decision, not an implementation detail.** In multi-tenant
mode each tenant has its own container and therefore its own bus — but a *shared* SQLite file would
be visible to all of them. Whether tenant scoping is enforced by the file path (mirroring
`_scope_key`, `http_contract_repository.py:53-58`) or by a mandatory query parameter should be
settled in the port signature before any implementation exists.

### 15.5 Correction hints on `BreachDetail`

**Confirmed absent.** `domain/models.py:25-27` declares three fields: `rule`, `field`, `message`.

**Where it attaches.** L2, as **one additive defaulted field** (`correction_hint: Optional[str] =
None`), plus a new pure L2 module mapping `(rule, field, constraint)` → hint text.

**What must change.** Two things:

1. Each rule would populate the new field where it constructs a `BreachDetail`. There are **eleven**
   construction sites (§11.1): six in `RuleEngine` (with `REGEX_PATTERN` alone having four distinct
   messages), one non-dict-root breach, two `INPUT_BOUNDS` sites in L3, and three in the semantic
   validator. This is additive but it is not one edit.
2. **`_finalize`'s serialisation** (`validate_contract_usecase.py:216-223`) hard-codes
   `{"rule","field","message"}`. Hints would not reach telemetry until it is updated.

**The design constraint the existing code already imposes.** Hints must be **deterministic and
table-driven** — no LLM, no I/O — because they are constructed inside L2, on a pool worker, under
the validation deadline. They must also be **PII-safe by construction**: `sanitize_breach_message`
is applied to `message` only (`:220`), so a hint containing an instance value would bypass
sanitisation entirely and reach telemetry unredacted. Either extend the sanitisation to the new
field or make it structurally value-free (as every built-in message already is, §14.7).

### 15.6 Architectural graph and arch-validation use case

**Confirmed absent.** No `domain/arch_graph.py` — `domain/` contains `models.py`, `validator.py`,
`schema_vocabulary.py`, `__init__.py`. No `usecases/validate_arch_usecase.py`.

**Where it attaches.** L2 for the pure graph structure (it is exactly the kind of thing L2 is for:
no I/O, deterministic), L3 for the validation workflow, L5 for whatever feeds it diffs.

**What must change:** new files only. The existing `ValidateContractUseCase` is untouched — arch
validation is a *sibling* workflow, not an extension of contract validation. `ServiceContainer`
gains one construction and one attribute.

**The one genuine architectural question.** Where does the graph *live* between calls? Everything in
the current system is either per-call (validation) or process-local-cached (schemas). A graph of a
codebase is neither: it is durable, incrementally updated state. That is a new *kind* of state for
this architecture, and it most likely belongs behind a port with an L4 implementation (file, SQLite)
rather than as an in-memory L2 object — otherwise the "pure L2" property breaks the first time it
needs to persist.

### 15.7 Agent adapters (`IAgentAdapter`)

**Confirmed absent.** No `ports/agent_adapter.py`; no `infrastructure/adapters/` subdirectory.

**Where it attaches.** L1 for the port, L4 for the per-agent implementations.

**What must change:** new files, plus a container branch selecting the adapter. Nothing in L2/L3 —
an agent adapter is an anti-corruption layer that normalises before the core is reached, so by
construction the core never learns which agent spoke.

**Placement caution.** `infrastructure/adapters/` as a nested package would put the word "adapters"
at two different layers, which in a codebase this disciplined about layer vocabulary is a real
readability cost. `infrastructure/agent_adapters/` avoids the collision.

**The obligation the existing security posture implies.** Everything crossing this seam is untrusted
model output. The current system's equivalent boundary — `HttpContractRepository` — validates size
(`:121`), shape (`:127-130`) and type before anything downstream sees it, and funnels every failure
into one exception type (`:131-140`). An `IAgentAdapter.from_agent_output` needs the same
discipline: bound it, validate it, and never let a novel exception type escape into L3.

### 15.8 Adaptive routing and capability profiles

**Confirmed absent.** No router, no bandit, no profile store. `KSDriftEngine` exists
(`infrastructure/ks_drift.py`) but is wired to nothing — the host must call `record_drift_sample()`
by hand (`dependency_injection.py:370-371`), and there is no automatic path from a validation
outcome into the drift window.

**Where it attaches.** L3/L4, reading from the event store (§15.2/§15.4).

**What must change:** new files. Also note the *existing* seam that already anticipates this: the
`__drift__` telemetry event (`dependency_injection.py:388-401`) already flows through the normal
bus, so drift signals will land in a persistent store for free once §15.2 exists.

**The reusable piece.** `KSDriftEngine` is already a bounded, dependency-light two-sample test with
a strictly capped reference window (`deque(maxlen=max_samples)`, `ks_drift.py:66`). Re-pointing it
at per-agent success rates requires no change to the engine — only a caller that feeds it.

### 15.9 CLI

**Confirmed absent.** No `cli/` package. `libs/congine-sdk/main.py` is a 95-byte stub outside
`src/`. `pyproject.toml` declares no `[project.scripts]`.

**Where it attaches.** L5, as a fourth entry point. A CLI constructs a `ServiceContainer` from env
(`ServiceContainer.from_env()`, `:337-344`), calls `bootstrap()`, and drives the same use cases.

**What must change:** new files plus a `[project.scripts]` entry. Nothing else.

**Two existing behaviours a CLI must work around.** `bootstrap()` refuses to run inside an event
loop (`:346-354`) — trivially satisfied by a synchronous CLI. And the container starts daemon
threads at construction (`:229-234`, `:267-280`); a short-lived CLI process should set
`CONGINE_START_BACKGROUND_SERVICES=false` to avoid spawning a sweeper and a drain thread for a
one-shot command, and must still call `close()` to flush telemetry if it is enabled.

### 15.10 Summary — attachment points

| Planned capability | Exists? | Layer | Attaches to | Changes needed in L2/L3? |
|---|---|---|---|---|
| MCP server | **no** | L5 (+ L1 for transport) | wraps `ServiceContainer`; calls `validate_contract_usecase.execute` | **none** (unless `ISchemaStorage` gains enumeration) |
| `SqliteEventBus` | **no** | L4 | existing `IEventBus` port + one container branch | **none** |
| Extended `TelemetryEvent` | **no** | L2 | additive frozen-dataclass fields | **yes** — `_serialize` and a population path through L3 |
| `HistoryQueryUseCase` | **no** | L3 + L1 | new read port over the event store | new L3 file; existing L3 untouched |
| `correction_hint` | **no** | L2 | additive `BreachDetail` field + 11 construction sites | **yes** — L2 rules and L3 serialisation |
| Architectural graph | **no** | L2 (+ L1/L4 for persistence) | new sibling workflow | **none** to existing files |
| `IAgentAdapter` | **no** | L1 + L4 | new port, new concretes, container branch | **none** |
| Routing / profiles | **no** | L3/L4 | reads the event store; reuses `KSDriftEngine` | **none** |
| CLI | **no** | L5 | `ServiceContainer.from_env()` + `bootstrap()` | **none** |

**The architecture's claim is largely borne out.** Six of nine capabilities are pure additions
behind existing seams. The two that are not — extended telemetry and correction hints — are not
blocked by the architecture but by two concrete, nameable facts: `QueueEventBus._serialize` and
`_finalize`'s breach serialisation both hard-code their key sets, and `ValidateContractUseCase` has
no access to the identity fields an extended event needs. Both are small, both are known now, and
both are cheaper to design for than to discover.
