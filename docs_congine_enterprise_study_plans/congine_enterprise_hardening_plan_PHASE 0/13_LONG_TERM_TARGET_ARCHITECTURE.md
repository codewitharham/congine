# 13 — Long-Term Target Architecture

## Purpose

Describe the end-state architecture that the hardening work should enable. This is a directional architecture, not authorization to build all components now.

The design preserves the existing idea that the deterministic core stays small while authoring, integrations, evidence, memory, UI, and agent-specific behavior grow around it.

---

## 1. Logical system

```text
                     ORGANIZATION / HUMANS
                             │
          ┌──────────────────┼──────────────────┐
          │                  │                  │
     JSON contracts      Policy UI        Future DSL/API
          │                  │                  │
          └──────────────────┴──────────────────┘
                             │
                             ▼
                    CONTRACT COMPILER
                 parse · validate · normalize
              version · complexity · canonicalize
                             │
                             ▼
                  COMPILED CONTRACT / POLICY IR
                             │
                             ▼
                  DETERMINISTIC EVALUATOR
                  (small, bounded, auditable)
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
       EvaluationState   Conformance       Breaches
                             │
                             ▼
                    ENFORCEMENT POLICY
                             │
                    ALLOW / WARN / BLOCK
                             │
        ┌────────────────────┼─────────────────────┐
        ▼                    ▼                     ▼
       SDK                  MCP                  CLI / CI
        │                    │                     │
        └────────────────────┴─────────────────────┘
                             │
                             ▼
                       EVIDENCE EVENT
                             │
                             ▼
                  DURABLE EVIDENCE STORE
                   tenant/project scoped
                             │
        ┌────────────────────┼─────────────────────┐
        ▼                    ▼                     ▼
      History            Aggregates          Architecture data
        │                    │                     │
        └────────────────────┼─────────────────────┘
                             ▼
                    CONTROL PLANE / MEMORY
                             │
        ┌────────────────────┼─────────────────────┐
        ▼                    ▼                     ▼
  convergence metrics   capability profiles   context summaries
        │                    │                     │
        └────────────────────┼─────────────────────┘
                             ▼
                     AGENT ADAPTER LAYER
                    Claude / OpenAI / OSS
                             │
                             ▼
                    optional routing logic
                   (outside verdict pathway)
```

---

## 2. The verdict core is an island of stability

The evaluator must remain:

- deterministic;
- bounded;
- independent of network access;
- independent of persistence;
- independent of agent identity;
- independent of UI;
- independently testable;
- replayable given versions/input.

A future feature that cannot be added without making the evaluator depend on the Control Plane, agent provider, or database should trigger architecture review.

---

## 3. Authoring plane vs runtime plane

### Authoring plane

May include richer tools:

- UI forms;
- templates;
- organizational policy catalogs;
- model-assisted drafting;
- natural-language explanation;
- simulation;
- migration tooling.

But everything must compile into a deterministic, reviewed representation.

### Runtime plane

Must include only deterministic, versioned policy evaluation and enforcement semantics.

This separation is the foundation for future Business Policy DSL.

---

## 4. Data plane

Durable evidence becomes the shared substrate for:

- audits;
- history;
- compliance proof;
- convergence/economic measurement;
- capability profiles;
- architecture hotspot analysis;
- future adaptive routing;
- dashboard projections.

It must not become required for the local judgment hot path unless a deployment explicitly selects a durability-required posture.

---

## 5. Enforcement plane

Three complementary boundaries:

```text
MCP       → early feedback and self-correction
CLI/hook  → local developer boundary
CI        → repository/organizational authority
```

They are defense in depth, not mutually exclusive product modes.

---

## 6. Translation plane

Agent adapters are translation/normalization boundaries only.

They may:

- frame request context;
- parse provider-specific output;
- validate envelope shape;
- normalize tool/result format.

They may not:

- redefine policy;
- bypass verdicts;
- approve non-conforming output;
- silently coerce malformed agent responses into valid-looking output.

---

## 7. Memory plane

Use deterministic/structured memory first:

- exact event queries;
- counts;
- recent decisions;
- current architecture slice;
- violation patterns.

Free-text model summarization is an optional convenience outside judgment and should be cached/minimized.

---

## 8. Control plane

The Control Plane is a projection over evidence and policy state, not a separate source of truth for enforcement.

It should show:

- contract registry and versions;
- posture;
- evidence stream;
- replay;
- degraded/unknown evaluation states;
- violation/convergence metrics;
- tenant health;
- agent capability statistics.

Every authoritative aggregate must be drillable to evidence.

---

## 9. Scalability path

### Local/single-host

- Python SDK;
- in-memory cache;
- local contracts;
- SQLite/WAL evidence;
- stdio MCP/CLI.

### Shared enterprise

- central contract/evidence APIs;
- PostgreSQL;
- authenticated MCP/service transport;
- tenant/RBAC isolation;
- background projections;
- WebSocket/SSE control-plane updates.

The core evaluator should remain the same conceptual component in both modes.

---

## 10. Future Policy IR

Policy IR should be:

- deterministic;
- immutable/versioned;
- canonicalizable/hashable;
- independent of authoring surface;
- rich enough for engineering and later business policy;
- explicitly evaluator-version compatible.

Do not over-design it before the contract compiler/admission needs are understood from real users.
