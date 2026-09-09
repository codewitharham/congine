# CONGINE — CURRENT ARCHITECTURE (verified)

**Generated:** 2026-08-09 · **Commit:** `a561992c69bf5ca334492706314f6ffc9d5ece10` (branch
`ahmed-main-v2`), **plus an uncommitted working tree** carrying the P0-2 change ·
**Supersedes:** the 2026-06-14 audit set (`docs/system-analysis/00_SYSTEM_MAP.md`,
`docs/system-analysis/01_FILE_INVENTORY.md`, `docs/context/01_SYSTEM_STATE.md`,
`docs/context/02_COMPONENT_MAP.md`)

**Package root:** `libs/congine-sdk/src/congine_core/` — 37 Python files, 31 implementation modules,
5 075 lines. **Test suite at time of writing: 293 passed, 1 skipped** (34 test files).

---

## 0. How to read this document

**What this is.** A forensic reverse-engineering of the Congine SDK as it exists in this repository
today. It describes only what is built. Anything planned, partially designed, or described in the
`docs_v2/` roadmap but absent from the code appears **exclusively** in §15 and nowhere else.

**Evidence rules.** Every structural claim carries a `file:line` reference. Where a behaviour was
verified by executing it rather than by reading it, the section says so and gives the observed
result. Where something could not be determined, it is marked `UNVERIFIED:` with the reason.

**Terminology.** One name per concept, used consistently:

| Term | Means |
|---|---|
| **the container** | `ServiceContainer` (`adapters/dependency_injection.py`) |
| **the hot path** | guard → use case → cache → executor → rules → telemetry → enforcement (§8.1) |
| **the control plane** | the external HTTP service the SDK talks to; it is **not** in this repository |
| **a port** | a `typing.Protocol` in `ports/` (L1), plus the in-domain `IValidator` |
| **a concrete** | a class in `infrastructure/` (L4) implementing a port structurally |
| **the composition root** | `ServiceContainer.__init__`, the only place concretes are constructed |
| **degraded** | `ValidationResult.degraded is True` — a timeout/error fallback, **not** a real evaluation |
| **load shed** | a validation rejected before it ran, because capacity was exhausted |
| **standalone** | `local_contracts_dir` is set: file repository, **no sync worker allocated at all** |
| **L0–L5** | the six tiers (§3) |
| **TC edge** | an import guarded by `if TYPE_CHECKING:` — no runtime dependency |

**Citation.** Section numbers are stable. Cite as `ARCHITECTURE_CURRENT.md §9.3`.

**Reading orders.** To understand *what it does*: §1 → §8 → §13. To *change* it: §3 → §4 → §6 → §16.
To *extend* it: §5 → §15. To *operate* it: §7 → §9 → §12 → §14.

**Provenance.** Working notes are in `docs/_workbench/arch_pass_1.md` … `arch_pass_15.md`, with the
pass ledger in `docs/_workbench/arch_progress.md`. Each pass file is the body of one section here.

---

## 1. Orientation — the system in one page

Congine is a **synchronous output firewall shipped as a Python library**. A developer decorates a
function with `@congine_guard("some-contract")`; when that function returns, Congine intercepts the
return value, looks up a JSON contract schema in an in-memory cache, runs the value through six
deterministic rules under a hard millisecond deadline on a bounded thread pool, enqueues a telemetry
event without blocking, and then passes the value through, wraps it in an envelope, or raises —
depending on the configured mode.

It is a **library, not a service**. There is no server, no database, no CLI, no persistence. Every
piece of state — schema cache, circuit-breaker state, telemetry queue, tenant registry, drift window
— is process-local. If the process dies, queued telemetry dies with it.

Everything else in the codebase exists to make that one hot path safe:

- **safe under load** — a bounded, load-shedding executor that sheds rather than queues (§14.1)
- **safe under failure** — a circuit breaker plus an on-disk snapshot, so a dead control plane
  cannot stall application boot (§14.2)
- **safe under attack** — linear-time `re2`, length caps everywhere, payload and schema bounds, PII
  scrubbing (§14.5, §14.7, §13.5)
- **safe across tenants** — per-tenant caches, snapshots, breakers and containers (§14.6)

**The shape.** A strict six-tier hexagon (L0 kernel → L1 ports → L2 domain → L3 use cases →
L4 infrastructure → L5 adapters), with dependencies pointing inward only. This was re-verified by
AST analysis of every import in all 37 files, distinguishing runtime edges from `TYPE_CHECKING`
edges: **no violations were found** (§4.4). The hexagon is real, and it is the asset — six of the
nine planned future capabilities attach as pure additions behind seams that already exist (§15.10).

**What is genuinely good.** The composition root is the only construction site — sixteen
constructions, one file, zero exceptions. The ports are real duck-typed seams, proven by test fakes
that satisfy them without importing them. The bounded executor's permit accounting is subtle and
correct. All eleven invariants in §14 hold.

**What a reader must not miss.** Three things, each covered in full below:

1. **A union `type` declaration (`{"type": ["string","null"]}`) — legal, idiomatic JSON Schema —
   makes every validation against that contract degrade silently, forever** (§13.6, debt D18).
2. **The rule engine reads eight schema keywords. Everything else — `minLength`, `format`, `const`,
   `additionalProperties`, `items`, `allOf` — is silently ignored** unless semantic validation is
   on (§13.1, §13.2). Since P0-2 this is *warned about at load*, but only on the cache-prime path.
3. **`region` is a fully validated, documented configuration field that nothing reads** (§12.4,
   debt D1).

**Since the 2026-06-14 audit.** P0-1 (safe tenant eviction) landed and is committed. P0-2
(unenforced-keyword warning) landed and is **uncommitted** in the working tree. One prior debt claim
turned out to be wrong in direction. Full reconciliation in §2.

---
