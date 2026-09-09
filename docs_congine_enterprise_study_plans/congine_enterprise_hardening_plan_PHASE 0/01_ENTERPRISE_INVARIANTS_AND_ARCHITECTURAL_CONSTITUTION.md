# 01 — Enterprise Invariants & Architectural Constitution

## Purpose

Define the rules that all current and future CONGINE features must obey. These rules should be treated as architectural invariants and referenced by ADRs, code reviews, CI checks, roadmap decisions, and documentation.

The aim is to prevent a future team from accidentally trading CONGINE's trust properties for feature velocity.

---

# I-01 — Deterministic judgment

## Decision

For a fixed:

- input;
- contract/policy version;
- configuration affecting evaluation;
- evaluator version;

the judgment must be reproducible.

No probabilistic model may render the runtime verdict.

## Why

CONGINE's product claim depends on auditability. A policy engine that may approve the same output today and reject it tomorrow under identical conditions cannot serve as an organizational control boundary.

The existing evidence already demonstrated one distinct verdict across 5,000 repeated executions in the measured environment. That result should become a continuously protected release property rather than a one-time benchmark.

## Consequences

Allowed outside verdict path:

- model-assisted contract drafting;
- free-text summarization;
- optional agent prompt framing;
- optional routing recommendations.

Not allowed inside verdict path:

- LLM classification of whether a rule was violated;
- LLM-generated final ALLOW/BLOCK decision;
- stochastic correction approval;
- probabilistic fallback when deterministic evaluation fails.

---

# I-02 — No silent non-enforcement

## Decision

If CONGINE could not evaluate a required policy, the result must make that explicit and machine-readable.

## Why

The most dangerous state is false confidence. Examples already found include:

- unsupported schema vocabulary that looked enforced;
- dotted-path property rules that appeared valid but did not behave as expected;
- unknown type names that could fail open;
- semantic validation timing out and returning a degraded failure with zero breaches.

A loud refusal is safer than an apparently successful enforcement path that did not evaluate the policy.

## Required design implication

Distinguish:

```text
POLICY VIOLATED
```

from:

```text
POLICY NOT FULLY EVALUATED
```

Do not encode both only as `status="fail"`.

---

# I-03 — Same policy semantics across every integration surface

## Decision

SDK, MCP, CLI, pre-commit, CI, and the future service API must call the same core use cases and policy semantics.

## Why

If MCP has one interpretation and CI has another, the organization does not have one policy—it has multiple incompatible policy engines.

## Rule

Integration surfaces may differ in:

- transport;
- user experience;
- timing;
- how they present a breach;
- enforcement position.

They must not duplicate or fork judgment rules.

---

# I-04 — Bounded host impact

## Decision

CONGINE must remain safe to embed in a process it does not own.

Bound:

- CPU time/wait time;
- input size;
- contract size;
- queue depth;
- concurrent validation;
- background retries;
- cache growth;
- shutdown time;
- network initialization delay.

## Why

A governance engine that destabilizes the host will be disabled, bypassed, or rejected by enterprise operators.

## Important nuance

A bound is only useful if exceeding it has a precise semantic result. `timeout` and `load_shed` must not be conflated simply because both protect latency.

---

# I-05 — Evidence before claim

## Decision

A capability must not be described as `Available`, `durable`, `production-supported`, `deterministic across platforms`, or `secure` beyond what has actually been demonstrated.

## Why

The existing tooling documents correctly use status labels:

- `Available`;
- `Partial`;
- `Planned — Phase X`;
- `Prototype`.

This same honesty must extend to all product surfaces.

## Examples

Until cross-version determinism is tested:

> Say determinism was demonstrated in the measured environment, not universally proven across every runtime.

Until the event store exists:

> The Control Plane is prototype/sample data, not live governance telemetry.

---

# I-06 — Core remains boring; intelligence attaches around it

## Decision

Keep `RuleEngine` and validation orchestration small, deterministic, bounded, and understandable.

History, token economics, agent profiling, dashboards, routing, and model-assisted authoring should attach around the core unless a genuine domain-rule requirement forces a core change.

## Why

The existing architecture was deliberately designed so future capabilities attach at L5/L4/L1 or through additive domain value fields. Preserve that property.

## Review question

Whenever a future feature proposes changing `RuleEngine`, ask:

> "Is this actually a judgment rule, or are we pushing infrastructure/intelligence into the core?"

---

# I-07 — Explicit versioning wherever meaning can change

Version:

- contract language semantics;
- organization contract revision;
- durable event schema;
- future Policy IR;
- public protocol/API when necessary.

Do not silently reinterpret historical policy definitions.

---

# I-08 — Fail early for authoring errors; fail controlled for runtime resource failures

Contract authoring problems should fail before runtime:

- unknown types;
- malformed regex;
- unsupported/ambiguous language constructs;
- invalid references;
- impossible complexity budgets.

Runtime resource failures should produce explicit evaluation state/reason and an enforcement action based on posture.

This separates:

```text
bad policy definition
```

from:

```text
healthy policy but runtime environment temporarily unable to evaluate it
```

---

# I-09 — Tenant and agent isolation are structural, not optional filters

Every future durable key, cache key, credential context, and query must be scoped correctly.

Do not depend on a caller remembering to add `WHERE tenant_id = ...`.

Use structural identity and, where applicable, database-level enforcement.

---

# I-10 — Documentation is a controlled artifact

Architecture/current-state documents must identify:

- source commit;
- verification date;
- status;
- evidence commands where applicable.

Facts that can be generated or tested should not be hand-maintained if automation can protect them.
