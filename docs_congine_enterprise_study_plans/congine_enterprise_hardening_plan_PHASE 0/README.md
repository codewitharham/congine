# CONGINE Enterprise Hardening & Future-Proofing Decision Package

**Purpose:** Turn the current CONGINE Phase-0 SDK into a safer, more scalable, more controlled foundation for enterprise use without sacrificing the core differentiator: deterministic organizational-policy enforcement.

**Audience:** CONGINE founders, maintainers, reviewers, and Claude Code acting as an implementation agent.

**Important status:** This package is an **engineering decision and implementation plan**, not a claim that every described capability already exists. It was derived from the supplied CONGINE concept/technical documents, GAP1–GAP4 evidence, the latest founder-question report, the roadmap, and the existing architecture/tooling plans. Claude Code MUST re-verify the current repository before changing code because the evidence snapshot was centered around commit `49a2f93` and later local/repository changes may exist.

---

## Governing principle

CONGINE should be engineered so that the most dangerous failures are not merely tested against but made structurally difficult to introduce.

The worst failure mode for a governance product is not a loud crash. It is:

> **The system appears to have enforced a policy when the policy was not actually evaluated.**

Every decision in this package therefore prefers:

- explicit state over ambiguous state;
- contract-load failure over runtime silent degradation;
- typed machine-readable reasons over message parsing;
- one source of truth over duplicated defaults;
- composition through ports over concrete implementation leakage;
- bounded resource ownership over best-effort cleanup;
- evidence-backed claims over aspirational claims;
- additive peripheral growth over mutation of the deterministic verdict core.

---

## Files in this package

| File | Purpose |
|---|---|
| `00_EXECUTION_PROTOCOL_FOR_CLAUDE_CODE.md` | Rules Claude Code must follow before and during implementation. |
| `01_ENTERPRISE_INVARIANTS_AND_ARCHITECTURAL_CONSTITUTION.md` | Product-wide invariants that should govern every future feature. |
| `02_VALIDATION_RESULT_AND_ENFORCEMENT_SEMANTICS.md` | Redesign of evaluation/conformance/action semantics, degradation, timeout, load shedding, failure reasons. |
| `03_CONTRACT_LANGUAGE_COMPILER_AND_POLICY_IR.md` | Future-proof contract admission, versioning, unknown types, dotted paths, regex semantics, Policy IR direction. |
| `04_CORE_ARCHITECTURE_LIFECYCLE_CONFIG_HARDENING.md` | Ports, mypy/runtime conformance, composition root, lifecycle, config strictness, shutdown, dead code. |
| `05_SECURITY_SUPPLY_CHAIN_AND_PLATFORM_SUPPORT.md` | RE2, payload bounds, dependency scans, Windows posture, credentials, tenant/agent isolation. |
| `06_EVIDENCE_EVENT_STORE_HISTORY_AND_CONTROL_PLANE.md` | Durable evidence architecture, event versioning, tamper evidence, privacy, tenant scoping, real control plane sequence. |
| `07_MCP_CLI_CI_MULTI_AGENT_AND_POLICY_PLATFORM.md` | Enforcement ladder, MCP/CLI/CI roles, agent adapters, capability profiles, correction hints, future DSL. |
| `08_VERIFICATION_CI_RELEASE_ENGINEERING.md` | Determinism corpus, branch coverage, CI gates, benchmarks, supply-chain verification, release gates. |
| `09_IMPLEMENTATION_BACKLOG_AND_ACCEPTANCE_CRITERIA.md` | Ordered P0/P1/P2 backlog with concrete acceptance criteria. |
| `10_DOCUMENTATION_RECONCILIATION_AND_ADR_PLAN.md` | How to repair `ARCHITECTURE_CURRENT.md`, debt status, stale prompts, and create durable ADRs. |
| `11_CLAUDE_CODE_MASTER_IMPLEMENTATION_PROMPT.md` | Ready-to-use master prompt for Claude Code. |

---

## Evidence basis

The recommendations are grounded in the supplied materials, especially:

- `GAP1.md` — code/document drift and remaining debt;
- `GAP2.md` — design decisions and rationale quality;
- `GAP3.md` — executed examples and the `IValidationRunner`/`health()` failure;
- `GAP4.md` — measurements: 350 passed / 1 skipped, 92% statement coverage, 5,000-run determinism result, latency, semantic-validation timeout rates, load shedding, cache behavior, dead-control-plane behavior, static-analysis gaps;
- latest pasted founder-question report — 17 founder decisions, remaining debt, new findings;
- `01_Congine_Project_Concept_Brief.pdf` and `Congine_Technical_Specification.pdf` — automatic, fast, deterministic enforcement; bounded host behavior; peripheral planned growth;
- `01_CORE_ENGINE_ARCHITECTURE.md`, `05_IMPLEMENTATION_ROADMAP.md`, token/history/multi-agent problem documents — additive future architecture;
- `WEB_ARCHITECTURE_AND_TOOLING.md`, W1/W2 prompts — honesty rule, docs-first, mock control-plane seam, real backend after durable data exists.

---

## How to use this package

1. Give the whole directory to Claude Code.
2. Start with `00_EXECUTION_PROTOCOL_FOR_CLAUDE_CODE.md`.
3. Have Claude Code inspect the current repository and produce a **pre-change verification report**.
4. Apply P0 tasks in small commits. Do not combine unrelated changes.
5. Re-run tests and measurements after every semantic change.
6. Only after P0/P1 stabilization should `ARCHITECTURE_CURRENT.md` and the formal document-generation prompts be reconciled.
7. Build MCP, persistence, and the real control plane only in their dependency order.

---

## Non-goal

This package does **not** recommend a rewrite. The existing hexagonal architecture and deterministic core are worth preserving. Most future capabilities should attach around the core rather than replace it.
