# 06 — Durable Evidence, History, Data Spine & Control Plane

## Goal

Turn validation events into an enterprise-grade evidence substrate without coupling the hot path to a dashboard or storing unsafe amounts of source content.

The durable event store should be treated as the **data spine of the wider product**, not merely a history feature.

---

# Decision D-01 — Build durable evidence before the real Control Plane

Today the control plane can only be an honest prototype because live durable data does not exist.

Correct order:

```text
Phase 0 deterministic validation
→ MCP/CLI integration
→ durable event/evidence store
→ history queries + aggregates
→ real Control Plane backend
```

Do not build production dashboard infrastructure before the sensor/data source exists.

---

# Decision D-02 — Define a durable store abstraction; SQLite is an implementation

Use an explicit durable-event/evidence interface rather than hard-coding SQLite into domain logic.

Possible implementations:

```text
SQLite/WAL     → local/offline/single-host
PostgreSQL     → shared enterprise/control-plane deployment
```

The validation use case should publish through a stable port; storage technology remains infrastructure.

---

# Decision D-03 — Separate write path from query/read path

Use a lightweight CQRS-style separation:

```text
validation hot path
→ append event

history/control plane
→ indexed queries / projections / aggregates
```

Do not make complex dashboard queries part of validation latency.

For SQLite, WAL is appropriate for concurrent append/read. For PostgreSQL, use proper indexes and derived aggregates/materialized views as scale requires.

---

# Decision D-04 — Version every durable event envelope

Include an event schema version from day one.

Why:

Future events will add fields such as:

- tenant/project/session;
- agent/provider;
- git SHA/files;
- evaluator version;
- contract language version;
- enforcement action;
- correction/convergence metadata;
- architecture references.

Without event versioning, historical replay/migration becomes fragile.

---

# Decision D-05 — Separate canonical judgment from observation metadata

A deterministic verdict hash should not depend on volatile observation metadata such as timestamp.

Conceptual event:

```text
EvidenceEvent
  identity / tenant / project
  observation metadata (time, agent, session)
  canonical judgment payload
  contract/evaluator versions
  enforcement action
  durability metadata
  chain hash
```

This allows replay to prove judgment equivalence while retaining operational context.

---

# Decision D-06 — Do not store raw source payloads in immutable evidence by default

Default immutable event content should contain:

- hashes;
- IDs;
- contract version;
- rule/breach metadata;
- evaluator version;
- timing;
- action;
- minimal file references/hashes.

If human-readable source/content must be retained, store it separately in an erasable, access-controlled store.

---

# Decision D-07 — Design GDPR/erasure behavior now

Recommended split:

```text
immutable evidence log
→ hashes + tombstones + integrity chain

erasable content store
→ optional human-readable content
```

Erasure deletes content while preserving the integrity of the audit sequence.

Add retention and compaction policy before volume grows.

---

# Decision D-08 — Add tamper evidence when persistence is introduced

Use canonical event serialization and hash chaining, e.g. conceptually:

```text
chain_hash = H(previous_chain_hash || canonical_event)
```

Store enough metadata to verify the chain.

Do not market this as cryptographic non-repudiation beyond what the design actually provides; it is tamper evidence, not magic immutability.

---

# Decision D-09 — Evidence durability and telemetry are distinct

Telemetry may be best-effort.

Compliance evidence may need stronger guarantees.

Introduce explicit durability posture eventually, e.g.:

```text
BEST_EFFORT
DURABLE_LOCAL
DURABLE_REQUIRED
```

A strict regulated deployment may choose:

```text
cannot durably record required evidence
→ do not claim governed success
```

Do not silently upgrade a lossy telemetry queue into an audit log.

---

# Decision D-10 — Tenant scope is part of durable identity

Every durable event/query key should include tenant context and usually project context.

Prefer APIs that require scope:

```python
get_history(tenant_id, project_id, ...)
```

rather than global queries with optional filters.

For PostgreSQL enterprise deployment, consider row-level security as defense in depth.

---

# Decision D-11 — Structured history before vector search

First implement exact queries:

- recent violations;
- violation frequency;
- contract history;
- file/component hotspots;
- retry/convergence counts;
- agent performance aggregates.

Add vector/semantic retrieval only when actual users need fuzzy similarity that structured queries cannot answer.

---

# Decision D-12 — Compact memory before injecting it into agent context

Never dump raw event history into prompts.

Use hierarchy:

```text
recent high-value structured events
+ deterministic aggregates
+ architecture slice
+ compact recurring-pattern summary
```

Use an LLM to summarize free text only when deterministic structure is insufficient, and keep that outside the verdict path.

---

# Decision D-13 — Real Control Plane consumes repository interfaces

Prototype and real UI must depend on domain repository interfaces, not mock JSON directly.

Now:

```text
UI → repository interface → MockRepository
```

Later:

```text
UI → repository interface → APIRepository → NestJS/Postgres
```

This turns the prototype into a replaceable data implementation rather than throwaway UI.

---

# Decision D-14 — Real Control Plane backend after durable data

NestJS + PostgreSQL is a reasonable later stack, but only once Phase C data exists.

The Python SDK remains independently publishable and should not become a build-time dependency of web apps.

---

# Decision D-15 — Every dashboard number must drill into evidence

Enterprise governance UI should not display opaque aggregate claims.

Examples:

- violation count → underlying events;
- convergence trend → attempts/events;
- contract coverage → actual contract mappings;
- agent profile → sample count and confidence/context.

If a number cannot be traced to evidence, it should not be used as an authoritative governance metric.
