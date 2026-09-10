Yes. The right deliverable now is a **single master prompt** that Claude Design can treat as the governing context for the whole CONGINE product.

I’ve merged the two contexts without changing the underlying product direction:

* the original **CONGINE Product/System Design master prompt**;
* the complete **Business Policy DSL + Executable Organizational Policy** context;
* a new **document authority and usage guide** explaining what Claude should extract from each attachment, its technical depth, and which design decisions it should drive;
* a built-in **CONGINE Product Language contract**, so you do **not** need a separate `CONGINE_PRODUCT_LANGUAGE.md` file right now.

You can paste the following directly into Claude Design after attaching the documents we discuss in the `DOCUMENT INPUT MANIFEST` section.

---

# CONGINE — MASTER CLAUDE DESIGN PROMPT

## Product, System Design, Stakeholder Experience, Business Policy DSL & Executable Organizational Policy

> **Purpose of this prompt**
> Treat this prompt and the attached CONGINE documents as the governing context for designing the complete CONGINE product ecosystem: public product experience, Landing Page, Documentation, Control Plane, Contracts and Policies, agent integrations, MCP experience, enforcement workflows, governance telemetry, evidence/history, architecture intelligence, enterprise administration, and the strategic path toward Business Policy DSL and Executable Organizational Policy.
>
> **Core proposition**
>
> # “Outputs conform to our rules, or they are stopped.”

---

# 0. YOUR ROLE

You are acting as the:

* Lead Product Designer
* Enterprise UX Architect
* Systems Architect
* Information Architect
* Developer Platform Product Strategist
* Enterprise Documentation Designer
* Design System Lead

for an enterprise product named **CONGINE**.

Your task is **not** to design isolated screens.

Your task is **not** to produce another generic SaaS administration dashboard.

Your task is to transform CONGINE from its current engineering foundation into a coherent enterprise product system through which organizations can:

* understand the governance problem created by autonomous software development;
* understand why CONGINE exists;
* adopt CONGINE;
* connect AI coding/autonomous agents;
* connect repositories and engineering workflows;
* define organizational standards;
* create and govern contracts;
* enforce those standards deterministically;
* understand why an output passed or failed;
* return actionable correction into the AI-agent loop;
* preserve evidence;
* observe policy behavior;
* measure retries, convergence and token economics;
* maintain institutional memory;
* understand architectural relationships;
* govern heterogeneous AI agents consistently;
* and ultimately move toward **Executable Organizational Policy**.

The final product must feel like a new enterprise infrastructure category.

Do **not** make it feel like:

* another AI coding assistant;
* another security scanner;
* another code review product;
* another LLM observability dashboard;
* another generic governance SaaS;
* another “AI guardrail” wrapper.

It should feel like:

> **the deterministic policy and enforcement plane for autonomous software development.**

---

# 1. DOCUMENT INPUT MANIFEST

Before doing any design work, inspect the attached documents.

The expected document set is:

## Tier 1 — Current authoritative sources

Attach these wherever available:

1. **CONGINE Product Brief**
2. **CONGINE Technical Requirements / Technical Specification**
3. **CONGINE Business Workflow Document**
4. **CONGINE System / Architecture Design**
5. **CONGINE Current Roadmap / Implementation Status**
6. **CONGINE Market / Competitive Research**, if available

These define the current product reality.

---

## Tier 2 — Strategic context supplied inside this prompt

Standalone documents for the following concepts do not currently exist:

1. **Business Policy DSL**
2. **Executable Organizational Policy**
3. **CONGINE Product Language / Messaging Contract**

Therefore, the corresponding sections of this prompt are the authoritative strategic source for those areas.

Treat them as:

> **strategic product direction**

not as proof that those capabilities are already implemented.

---

## Tier 3 — Historical material

If historical research, ChatGPT discussions, earlier product concepts, architecture explorations or old drafts are attached, use them to understand:

* product evolution;
* strategic reasoning;
* why particular decisions were made;
* why deterministic enforcement became central;
* why MCP became important;
* why architectural governance became a wedge;
* why Business Policy DSL emerged.

Historical material is useful for context.

It does **not** override the current authoritative documents.

---

# 2. SOURCE-OF-TRUTH PRECEDENCE

When sources conflict, use this hierarchy.

## Technical behavior

**Technical Requirements / Technical Specification wins.**

---

## Current implementation status

**Current Roadmap / Implementation Status wins.**

---

## Build order

**Implementation Roadmap wins.**

The dependency order:

> **Phase 0 → P1 → P1.5 → P2 → P3 → A → B → C → D → E → F**

must not be changed.

> **Corrected 2026-08-22.** This prompt originally wrote the order as
> `Phase 0 → A → B → C → D → E → F`. Four hardening/verification stages sit between Phase 0 and
> Phase A and must not be skipped: **P0** (trust-critical hardening, CLOSED), **P1** (structural
> hardening, CLOSED), **P1.5** (semantic validation safety, **NEXT**), **P2** (verification and
> release gates), **P3** (formal documentation + ADR reconciliation: D1, D2, D3, F01–F09, ADR
> stabilization). The **W1** docs site and **W2** control-plane prototype are downstream of P3, not
> part of it. Phase A does not begin until those are
> done.

---

## Stakeholder workflow

**Business Workflow Document wins.**

---

## Business positioning and conceptual product narrative

**Product Brief wins.**

---

## System component relationships

**Current System / Architecture Design wins**, unless contradicted by the Technical Specification.

---

## Future strategic direction

The:

* Business Policy DSL;
* Executable Organizational Policy;
* Product Language;

sections of this prompt are the strategic source.

---

## Historical discussion

Historical material explains reasoning only.

Do not silently combine conflicting information.

If necessary, explicitly distinguish:

* **CURRENT**
* **NEXT**
* **PLANNED**
* **STRATEGIC**

---

# 3. DOCUMENT USAGE GUIDE

Do not treat every attached document as though it answers the same question.

Each has a different role.

---

## 3.1 CONGINE Product Brief

### Primary purpose

The Product Brief explains:

> **why CONGINE exists and what category of problem it solves.**

### Contains

Use it to understand:

* product identity;
* governance gap;
* original problem framing;
* functional vs organizational correctness;
* contract-centric governance;
* target users;
* stakeholder pain;
* value proposition;
* connected problem domains;
* conceptual positioning;
* enterprise relevance;
* competitive distinction;
* original product vision.

### Technical depth

**Low-to-medium.**

This is primarily a:

> product strategy / product definition source

rather than a low-level implementation specification.

### Use it heavily for

* Landing Page;
* product overview;
* hero messaging;
* enterprise positioning;
* stakeholder narrative;
* “Why CONGINE?” pages;
* use cases;
* category definition;
* executive narrative;
* product copy.

### When the question is

> Why does CONGINE exist?

Start with this document.

### When the question is

> What problem is being solved?

Start with this document.

### Do not use it as final authority for

* exact technical runtime behavior;
* detailed architecture implementation;
* storage implementation;
* current implementation status;
* failure semantics.

For those, use the Technical Specification and Roadmap.

---

# 3.2 CONGINE Technical Requirements / Technical Specification

### Primary purpose

This document explains:

> **how CONGINE actually works technically.**

### Contains

Use it to understand:

* hexagonal architecture;
* L0 Kernel;
* L1 Ports;
* L2 Domain;
* L3 Use Cases;
* L4 Infrastructure;
* L5 Adapters;
* deterministic RuleEngine;
* contracts;
* rule evaluation;
* validation semantics;
* enforcement;
* bounded execution;
* caching;
* circuit breaking;
* event bus;
* resilience;
* security boundaries;
* isolation;
* failure behavior;
* offline/local behavior;
* integration modes;
* CLI;
* service/library integration;
* adapter boundaries;
* technical invariants.

### Technical depth

**Highest technical depth.**

This is the:

> **technical behavior and architecture authority.**

### Use it heavily for

* technical system diagrams;
* Docs architecture section;
* MCP/integration documentation;
* developer setup;
* platform views;
* failure states;
* Trust Center;
* security messaging;
* validation semantics;
* enforcement modes;
* technical product states;
* infrastructure diagrams.

### Example

If a UI says:

> ENFORCED

the Technical Specification should define what that statement technically means.

If the UI says:

> NOT ENFORCED

the technical specification should determine under which system conditions that can occur.

### Translation rule

Do not dump internal implementation names directly into stakeholder UI unless needed.

For example:

**BoundedValidationExecutor**

should normally be expressed to enterprise users as:

> bounded deterministic evaluation

or:

> protected validation execution.

Similarly:

**Ports and adapters**

can be explained as:

> a protected deterministic core with integrations attached at its boundaries.

Use implementation terminology in engineering documentation, not everywhere in the product.

---

# 3.3 CONGINE Business Workflow Document

### Primary purpose

This document explains:

> **how CONGINE operates as an enterprise workflow.**

### Contains

Use it to understand:

* stakeholders;
* responsibilities;
* triggers;
* start conditions;
* end conditions;
* decision points;
* hand-offs;
* validation loop;
* correction loop;
* contract lifecycle;
* ownership;
* program lifecycle;
* adoption;
* ROI;
* success metrics;
* pilot success;
* governance;
* source-of-truth relationships.

### Technical depth

**Medium technical depth.**

### Workflow depth

**Very high.**

This is the:

> **enterprise operating-model authority.**

### Use it heavily for

* information architecture;
* user journeys;
* wireframes;
* Control Plane;
* contract lifecycle;
* approval workflows;
* compliance experience;
* audit flows;
* evidence;
* telemetry;
* stakeholder dashboards;
* customer onboarding;
* pilot scorecard;
* governance interfaces.

### Design test

If a major product screen cannot be tied to:

* an actor;
* a trigger;
* a goal;
* a decision;
* an outcome;

question whether it belongs in the primary workflow.

### Relationship to technical specification

The:

> Business Workflow defines **how the product is operated**.

The:

> Technical Specification defines **what the system can truthfully do**.

Use both.

---

# 3.4 CONGINE System / Architecture Design

### Primary purpose

This document explains:

> **how the major system pieces relate.**

### Contains

Use it to understand:

* system boundaries;
* runtime components;
* agents;
* contracts;
* MCP;
* enforcement;
* telemetry;
* history;
* evidence;
* architecture analysis;
* adapters;
* storage;
* product-facing services;
* extension points.

### Technical depth

**Medium-to-high architectural depth.**

### Use it heavily for

* system diagrams;
* platform architecture;
* developer documentation;
* architecture pages;
* data flow;
* deployment model;
* integration architecture;
* Control Plane system model.

### Critical design principle

A:

> **system architecture**

is not the same thing as:

> **product information architecture.**

Do not reproduce every technical component as a navigation item.

Expose what users need to:

* understand;
* configure;
* inspect;
* approve;
* operate;
* govern.

---

# 3.5 CONGINE Current Roadmap / Implementation Status

### Primary purpose

This document explains:

> **what currently exists and what must be built next.**

### Contains

* Phase 0 status;
* Phase A;
* Phase B;
* Phase C;
* Phase D;
* Phase E;
* Phase F;
* forced dependency order;
* implementation constraints;
* done-tests;
* current sequencing priority.

### Technical depth

**Medium implementation depth.**

### Status authority

**Highest.**

### Use it heavily for

* maturity labels;
* roadmap;
* prototype scope;
* feature availability;
* what should appear as current;
* what should appear as planned;
* what should appear as strategic.

### Critical rule

Do not allow visually attractive future features to distort the real implementation sequence.

The design may show the destination.

It must not lie about product maturity.

---

# 3.6 CONGINE Market / Competitive Research

Where attached:

### Primary purpose

Explains:

* category landscape;
* adjacent products;
* market timing;
* autonomous development trends;
* competitive overlap;
* differentiation;
* enterprise need.

### Technical depth

**Low.**

### Market/category depth

**High.**

### Use it for

* Landing Page positioning;
* category map;
* differentiation;
* enterprise narrative;
* investor/stakeholder messaging.

### Do not use it to

* copy competitor features;
* copy competitor navigation;
* copy competitor visual identity.

The purpose is to understand:

> **where CONGINE belongs**

not:

> which existing product it should resemble.

---

# 3.7 Business Policy DSL Context

There is currently no standalone Business Policy DSL document.

Use the relevant sections of this prompt as the source.

### Contains

* why a DSL is needed;
* human intent → formal policy;
* AI-assisted extraction;
* policy compilation;
* Policy IR;
* deterministic evaluation;
* Policy Studio implications.

### Technical depth

**Strategic architecture depth.**

It is **not** currently a detailed language specification.

### Use it for

* strategic information architecture;
* Policy Studio;
* policy authoring UX;
* future policy workflows;
* diagrams;
* long-term Docs;
* strategic Control Plane evolution.

### Do not infer

* finalized grammar;
* current implementation;
* compiler internals;
* production syntax.

---

# 3.8 Executable Organizational Policy Context

There is currently no standalone Executable Organizational Policy document.

Use this prompt as the strategic source.

### Contains

* product north star;
* policy-as-infrastructure concept;
* organization-wide policy surface;
* relationship between architecture, contracts, security, data, business and compliance;
* long-term enterprise category.

### Technical depth

**Strategic / system-product architecture depth.**

### Use it for

* executive narrative;
* future product architecture;
* future navigation;
* Policy Studio;
* positioning;
* strategic roadmap;
* product north star.

### Do not present it as

a fully implemented current capability.

---

# 3.9 CONGINE Product Language Context

There is currently **no separate `CONGINE_PRODUCT_LANGUAGE.md` file**.

Do not assume one exists.

The Product Language section of this prompt is the authoritative language contract for this design exercise.

Use it for:

* Landing Page copy;
* headings;
* navigation;
* error states;
* policy language;
* metrics;
* Docs;
* Trust Center;
* demos;
* executive views;
* Control Plane.

---

# 4. PRODUCT DEFINITION — NON-NEGOTIABLE

CONGINE is an enterprise product that gives organizations a:

> **deterministic policy layer for autonomous software development**

and:

> **deterministic output governance layer for AI-assisted development.**

The core proposition is:

# “Outputs conform to our rules, or they are stopped.”

CONGINE is:

* a deterministic policy plane;
* an enforcement plane;
* organizational correctness infrastructure;
* an agent control boundary;
* a closed-loop validation/correction system;
* infrastructure for human-owned machine-readable standards;
* a common policy layer across heterogeneous AI agents;
* an evidence-producing governance system;
* eventually an executable organizational policy platform.

---

# 5. WHAT CONGINE IS NOT

CONGINE is NOT:

* an AI coding assistant;
* a coding copilot;
* a prompt library;
* a prompt manager;
* a generic AI guardrail;
* an LLM;
* an AI reviewer;
* an AI “judge”;
* a generic static analyzer;
* a replacement for GitHub;
* a replacement for GitLab;
* a replacement for Snyk;
* a replacement for Semgrep;
* a replacement for CI/CD;
* an autonomous development agent.

The design must communicate this quickly.

---

# 6. THE GOVERNANCE GAP

AI coding agents have changed software production.

Developers can increasingly delegate:

* implementation;
* refactoring;
* API development;
* tests;
* configuration;
* infrastructure;
* documentation;
* repository operations;
* repeated engineering work;

to autonomous systems.

Software generation capacity is increasing faster than organizational assurance capacity.

This creates a governance gap.

---

# 7. TWO KINDS OF CORRECTNESS

## Functional correctness

> Does the software do what the task requested?

Examples:

* compiles;
* runs;
* passes tests;
* returns requested output.

---

## Organizational correctness

> Does the software obey the rules of this organization?

Examples:

* architectural layers;
* approved dependencies;
* API contracts;
* service boundaries;
* error-handling idioms;
* naming conventions;
* security requirements;
* compliance requirements;
* data rules;
* regulatory disclaimers;
* approved implementation patterns.

A change can be functionally correct and organizationally wrong.

That is a central CONGINE message.

---

# 8. WHY EXISTING CONTROLS ARE NOT ENOUGH

## Human review

Valuable but:

* slow;
* inconsistent;
* expensive;
* capacity-limited.

---

## Linters / style tooling

Useful for generic rules.

Not automatically the source of truth for organization-specific architecture.

---

## Security scanners

Important for security risk.

Not automatically the source for organizational architecture, contracts and business rules.

---

## AI review

Useful as assistance.

Not acceptable as the final deterministic governance boundary.

---

## Post-hoc review

Finds problems after:

* generation;
* tokens;
* retries;
* developer time;

have already been spent.

CONGINE moves the control into the loop.

---

# 9. CENTRAL CONTROL MODEL

```text
Human organizational intent
        ↓
Machine-readable standard
        ↓
AI/autonomous output
        ↓
Deterministic evaluation
        ↓
ALLOW / WARN / BLOCK
        ↓
Correction
        ↓
Re-validation
        ↓
Acceptance / stop
        ↓
Evidence
        ↓
Telemetry
        ↓
Institutional memory
```

The organization defines.

The agent produces.

CONGINE judges.

---

# 10. MOST IMPORTANT TRUST PRINCIPLE

# LLMs NEVER sit on the final verdict path.

AI may help:

* author;
* extract;
* translate;
* explain;
* correct;
* summarize.

AI may not determine the final policy verdict.

Use:

> **The agent may propose. CONGINE decides.**

The same:

> output + contract + configuration

must yield the same result.

Never use UI language like:

> AI believes this is compliant.

Use:

> **ENFORCED — PASS**

or:

> **BLOCKED — AR-014 violated**

---

# 11. THE DEFENSIBLE WEDGE

The wedge is:

> **organizational correctness + deterministic enforcement + agent-loop integration.**

The product compounds value through:

1. Contracts
2. Deterministic verdicts
3. Correction feedback
4. History
5. Project memory
6. Architecture graph
7. Agent profiles
8. Multi-agent normalization
9. Convergence economics
10. Business Policy DSL
11. Executable Organizational Policy

---

# 12. STRATEGIC PRODUCT EVOLUTION

```text
Contract Enforcement
        ↓
MCP / Agent Loop
        ↓
Architecture Enforcement
        ↓
History / Evidence
        ↓
Multi-Agent Governance
        ↓
Business Policy DSL
        ↓
Executable Organizational Policy
```

These are not seven products.

They are successive expansions of one policy/control plane.

---

# 13. CURRENT TECHNICAL ARCHITECTURE

CONGINE uses six-layer hexagonal architecture:

```text
L5  Adapters
      ↓
L4  Infrastructure
      ↓
L3  Use Cases
      ↓
L2  Domain
      ↓
L1  Ports
      ↓
L0  Kernel
```

The invariant:

> **Dependencies point inward only.**

---

# 14. L0 — KERNEL

Contains foundational concepts:

* limits;
* configuration;
* fundamental types;
* security boundaries;
* error model;
* sanitization;
* invariants.

---

# 15. L1 — PORTS

Stable interfaces between the core and external mechanisms.

Purpose:

> integrations can change without changing policy semantics.

---

# 16. L2 — DOMAIN

The deterministic heart.

Includes:

* contracts;
* rules;
* validation concepts;
* deterministic behavior.

No external I/O should determine the policy result.

This is the primary **trust boundary**.

---

# 17. L3 — USE CASES

Coordinates operations such as:

* contract validation;
* policy resolution;
* evaluation;
* orchestration;
* result production.

---

# 18. L4 — INFRASTRUCTURE

Includes operational mechanisms:

* caching;
* bounded execution;
* event handling;
* storage;
* resilience;
* retrieval.

---

# 19. L5 — ADAPTERS

Includes:

* MCP;
* CLI;
* agent integrations;
* external APIs;
* composition root.

New product capabilities should attach around the core rather than corrupting it.

---

# 20. CURRENT IMPLEMENTATION STATE

> **Updated 2026-08-22 against the P1 CLOSED commit `b482bc4b2c88273e2a29a0f418a53f7ba3ab0614`.**
> Phase 0 is complete, and two hardening stages have closed on top of it: **P0 Trust-Critical
> Hardening** and **P1 Structural Hardening**. **P1.5 is next** — P2, P3 and Phase A onwards have not
> started. Measured baseline: 613 passed / 1 skipped; strict blocking mypy over 40 production source
> files; a machine-enforced layer dependency matrix with zero exemptions; the P0 trust baseline green
> on all five categories and reproducible from committed harnesses.
>
> **"P1 CLOSED" is not "enterprise-release ready."** Still open: the raw `schema_storage.put()`
> admission bypass, version-aware storage identity, richer result semantics, semantic budget
> architecture, supply-chain gates/SBOM, and cross-version release evidence. Do not design surfaces
> that imply any of those exist.

Phase 0 is complete.

The current foundation includes:

* RuleEngine;
* validation rules;
* ValidateContractUseCase;
* LFUCache;
* BoundedValidationExecutor;
* CircuitBreaker;
* IEventBus;
* hexagonal architecture;
* core invariants.

Current conceptual behavior:

```text
AI output
   ↓
Contract
   ↓
Deterministic validation
   ↓
PASS / WARN / BLOCK
```

---

# 21. FORCED IMPLEMENTATION ORDER

This order is non-negotiable.

Do not present these as parallel feature streams.

---

## Phase 0 — COMPLETE

Deterministic foundation.

---

## P0 — Trust-Critical Hardening — **CLOSED**

Contract admission as a safety boundary; no silent non-enforcement; load shed distinct from timeout;
canonical configuration; fabricated region routing removed.

---

## P1 — Structural Hardening — **CLOSED**

Explicit layer dependency matrix (machine-enforced, `TYPE_CHECKING` included, zero exemptions);
canonical value contracts relocated to the L0 kernel; narrow `ISyncRunner` port; blocking strict
mypy on production source; runtime Protocol validation at composition seams; transactional
composition and terminal lifecycle; RE2 sanitizer; reproducible P0 evidence harnesses.

---

## P1.5 — Semantic Validation Safety — **NEXT**

Honest semantic-validation cost communication; separate native/semantic budget policy;
complexity/admission prototype; compiled-validator caching investigation.

---

## P2 — Verification & Release Gates — NOT STARTED

Python support matrix; Linux release CI; golden determinism corpus; branch coverage; pip-audit;
SBOM; security gates; reproducible performance evidence.

---

## P3 — Formal Documentation & ADR Reconciliation — NOT STARTED

D1 · D2 · D3 · F01–F09 · ADR stabilization.

---

## Post-P3 — Downstream Web Surfaces — NOT STARTED

**W1** documentation site · **W2** prototype control-plane site. Both consume the reconciled
documentation; neither defines P3 completion.

---

## Phase A — Harden + CLI

Focus:

* correctness debt;
* silent-keyword warnings;
* CLI;
* diff parser.

Status:

> **NEXT**

---

## Phase B — MCP Surface

Focus:

* agent integration;
* in-loop validation;
* blocked → correction → pass.

Status:

> **CRITICAL**

This is the enterprise demo moment.

---

## Phase C — History Foundation

Focus:

* durable validation events;
* evidence;
* history.

Status:

> **DATA SPINE**

---

## Phase D — Full Token Story

Focus:

* correction hints;
* delta protocol;
* context compression;
* savings metrics;
* convergence.

Status:

> **ECONOMIC PROOF**

---

## Phase E — Architecture + Agent Normalization

Focus:

* architecture graph;
* structural relationship analysis;
* agent adapters;
* capability profiles.

Status:

> **DIFFERENTIATION**

---

## Phase F — Adaptive Routing

Focus:

* evidence-informed routing.

Status:

> **OPTIONAL / LATER**

Do not make adaptive routing the core narrative.

---

# 22. THREE CONNECTED DOMAINS

The three existing problem areas are one system.

They must not become three products.

---

## Token Optimization

CONGINE reduces expensive retry loops through:

* deterministic rejection;
* precise breach information;
* correction hints;
* targeted retries;
* context efficiency;
* delta protocols;
* prompt/cache cooperation.

---

## History / Project Memory

```text
Validation event
       ↓
History
       ↓
Patterns
       ↓
Institutional memory
       ↓
Architecture intelligence
```

Supports:

* handoffs;
* resuming work;
* repeated decisions;
* recurring failure analysis.

---

## Multi-Agent Normalization

```text
Claude Code ─┐
Cursor ──────┤
Internal AI ─┤
Other agents ┘
      ↓
Translation layer
      ↓
Common representation
      ↓
Same contract
      ↓
Same deterministic judgment
```

---

# 23. PRIMARY INTEGRATION SURFACE — MCP

MCP is the primary enterprise integration.

```text
AI Agent
   ↓
MCP
   ↓
CONGINE
   ↓
Contract resolution
   ↓
Deterministic evaluation
   ↓
ALLOW / WARN / BLOCK
```

The signature demonstration:

```text
Agent proposes
      ↓
CONGINE
      ↓
BLOCK
      ↓
Precise violation
      ↓
Agent corrects
      ↓
CONGINE
      ↓
PASS
```

This must become one of the strongest product experiences.

---

# 24. SECONDARY INTEGRATION — DIRECT LLM GUARD

Conceptually:

```text
Application
     ↓
LLM
     ↓
CONGINE
     ↓
ALLOW / WARN / BLOCK
```

This is valid.

But MCP remains the primary enterprise story.

---

# 25. BUSINESS POLICY DSL — STRATEGIC CONTEXT

A standalone Business Policy DSL specification does not yet exist.

Use this section as strategic context.

The Business Policy DSL is intended to become a:

> **human- and machine-readable organizational policy language.**

Its purpose is to bridge:

> human organizational intent

to:

> deterministic machine enforcement.

Organizations possess policies concerning:

* architecture;
* dependencies;
* data;
* APIs;
* security;
* compliance;
* naming;
* business rules;
* operational constraints;
* technology restrictions;
* service communication;
* institutional conventions.

Today, these may live in:

* documentation;
* Confluence;
* architecture diagrams;
* policy files;
* review comments;
* senior-engineer knowledge;
* security documentation;
* compliance documents;
* previous decisions.

The DSL progressively turns appropriate parts into:

> explicit, versioned, machine-evaluable policy.

---

# 26. BUSINESS POLICY DSL PIPELINE

```text
Human / Organizational Intent
             ↓
AI-assisted extraction
             ↓
Business Policy DSL
             ↓
Policy validation
             ↓
Policy compilation
             ↓
Policy IR
             ↓
Deterministic evaluator
             ↓
ALLOW / WARN / BLOCK
             ↓
Evidence
```

AI may assist policy creation.

AI does not make the enforcement decision.

---

# 27. POLICY IR

The Policy Intermediate Representation allows multiple policy-authoring channels to converge.

Conceptually:

```text
Business Policy DSL ─┐
UI Policy Builder ───┤
API-defined Policy ──┤
AI-assisted Draft ───┘
          ↓
       Policy IR
          ↓
Deterministic evaluator
```

The exact IR schema is not finalized in this prompt.

Do not invent one and present it as established.

---

# 28. BUSINESS POLICY DSL STAKEHOLDERS

Future policy authoring may involve:

| Stakeholder    | Example contribution                 |
| -------------- | ------------------------------------ |
| Business owner | Business constraint                  |
| Architect      | Architecture policy                  |
| Security       | Security policy                      |
| Compliance     | Regulatory rule                      |
| Platform       | Technical enforcement                |
| Developer      | Contract understanding               |
| Agent          | Machine-readable constraint consumer |

Do not assume all policy authors are programmers.

---

# 29. EXECUTABLE ORGANIZATIONAL POLICY

The strategic destination is:

# Executable Organizational Policy

The transformation is:

### Today

```text
Organizational knowledge
       ↓
Documentation
       ↓
Humans remember
       ↓
Humans review
```

### CONGINE future

```text
Organizational knowledge
       ↓
Formal policy
       ↓
Executable contract / policy
       ↓
Deterministic enforcement
       ↓
Autonomous software
```

The central idea:

> **Do not merely document organizational policy. Make appropriate policy executable.**

---

# 30. ORGANIZATIONAL POLICY SURFACE

The future policy plane may include:

```text
                    ORGANIZATIONAL
                     CORRECTNESS
                          │
         ┌────────────────┼────────────────┐
         ↓                ↓                ↓
    Architecture        Data            Security
         │                │                │
    Dependencies     APIs/contracts   Permissions
         │                │                │
         └────────────────┼────────────────┘
                          ↓
                    Business Rules
                          ↓
                    Compliance
                          ↓
                  Institutional Rules
```

The product is not limited to schemas.

The same deterministic governance model can expand across these domains.

---

# 31. CURRENT VS FUTURE BOUNDARY

Business Policy DSL and Executable Organizational Policy are **strategic concepts**.

They should influence:

* information architecture;
* future policy navigation;
* Policy Studio;
* product roadmap;
* product diagrams;
* strategic positioning.

They must not be shown as complete current functionality.

Use maturity states:

* **AVAILABLE**
* **NEXT**
* **PLANNED**
* **STRATEGIC**

---

# 32. CONGINE PRODUCT LANGUAGE CONTRACT

There is no separate `CONGINE_PRODUCT_LANGUAGE.md`.

Treat this section as the authoritative product-language contract.

---

## Preferred terms

Use:

* deterministic;
* organizational correctness;
* policy;
* contract;
* rule;
* verdict;
* enforcement;
* conformance;
* breach;
* correction;
* evidence;
* history;
* institutional memory;
* control plane;
* agent loop;
* architecture;
* executable policy;
* organizational standard.

---

## Avoid

Avoid overusing:

* AI-powered;
* magical;
* smart governance;
* intelligent guardrails;
* AI safety;
* next-generation AI;
* autonomous magic.

The power of CONGINE comes from:

> determinism

not from AI spectacle.

---

# 33. CORE PRODUCT PHRASES

Use these consistently.

> **Outputs conform to our rules, or they are stopped.**

> **The agent may propose. CONGINE decides.**

> **Turn organizational policy into executable infrastructure.**

> **Functional correctness is not enough. Autonomous software must also be organizationally correct.**

> **Don’t just document controls. Enforce them.**

> **One organizational standard. Many AI producers. Deterministic judgment.**

---

# 34. BRAND TONE

The product should feel:

* authoritative;
* precise;
* restrained;
* enterprise-grade;
* infrastructure-grade;
* trustworthy;
* technical;
* modern;
* controlled.

Avoid:

* robot imagery;
* cyberpunk;
* generic AI stars;
* excessive gradients;
* consumer SaaS playfulness;
* “AI magic” language;
* vague enterprise buzzwords.

---

# 35. PRODUCT EXPERIENCE ARCHITECTURE

Do not start by producing high-fidelity screens.

First define the product ecosystem.

```text
CONGINE
│
├── Public Experience
│   └── Landing / Product Narrative
│
├── Developer Experience
│   └── Docs / Integration
│
├── Governance Experience
│   └── Control Plane
│
├── Operational Experience
│   └── Telemetry / Evidence / Memory
│
└── Integration Experience
    └── MCP / Agents / API / CI
```

---

# 36. DESIGN PROCESS — NON-NEGOTIABLE

Use this order:

```text
Source understanding
      ↓
Product Experience Architecture
      ↓
Information Architecture
      ↓
Stakeholder Journeys
      ↓
Critical Workflows
      ↓
Wireframes
      ↓
Design System
      ↓
High-Fidelity UI
      ↓
Interactive Prototype
```

Do **not** start with a design system.

Do **not** start with polished dashboards.

The workflows must define the UI.

---

# 37. PRODUCT SURFACES TO DESIGN

Design a coherent product vision across:

1. Landing Page
2. Product Overview
3. Docs
4. Control Plane
5. Organizations
6. Projects
7. Contracts
8. Policies
9. Rules
10. Validation
11. Violations
12. Enforcement
13. Agents
14. MCP
15. Evidence
16. History
17. Telemetry
18. Architecture
19. Governance
20. Trust Center
21. Future Policy Studio

Maturity-label future features.

---

# 38. LANDING PAGE HERO

Recommended direction:

# AI can write the code.

# Your organization still decides what is allowed.

Subheading:

> **CONGINE is the deterministic policy layer for AI-assisted and autonomous software development.**

Core proposition:

> **Outputs conform to our rules, or they are stopped.**

CTAs:

**See the control loop**

**Explore the architecture**

**Read the docs**

---

# 39. LANDING PAGE NARRATIVE

## Section 1 — The change

Before:

```text
Developer
 ↓
Code
 ↓
Review
 ↓
Merge
```

AI era:

```text
Developer
 ↓
AI Agent
 ↓
Much more output
 ↓
Review bottleneck
```

Autonomous era:

```text
Agent
 ↓
Agent
 ↓
Agent
 ↓
Continuous software production
```

Question:

> **Where does organizational authority live?**

Answer:

# CONGINE

---

# 40. LANDING — FUNCTIONAL VS ORGANIZATIONAL CORRECTNESS

Show visually:

| Functional correctness | Organizational correctness |
| ---------------------- | -------------------------- |
| Does it work?          | Does it obey our rules?    |
| Tests                  | Architecture               |
| Behavior               | Contracts                  |
| Output                 | Dependencies               |
| Features               | Policies                   |
| Computation            | Organizational conventions |

Then:

> **CONGINE makes organizational correctness enforceable.**

---

# 41. LANDING — THE CONTROL LOOP

This should be a flagship interactive section.

```text
AI AGENT
   ↓
PROPOSE
   ↓
MCP
   ↓
CONGINE
   ↓
RESOLVE CONTRACT
   ↓
DETERMINISTIC EVALUATION
   ↓
 ┌───────┴───────┐
 ▼               ▼
PASS            BLOCK
 │                │
 │             EXPLAIN
 │                │
 │             CORRECT
 │                │
 └────────┬───────┘
          ↓
      RE-VALIDATE
          ↓
        ACCEPT
```

Use a realistic example:

```text
BLOCKED

AR-014
Architecture Boundary Violation

Observed:
payments-service → database adapter

Required:
payments-service → application port → persistence adapter
```

Then show the agent correcting.

Then:

```text
PASS
17 / 17 rules satisfied
```

This is the signature product moment.

---

# 42. LANDING — WHY DETERMINISTIC

Show:

```text
Human-authored rule
       ↓
Contract
       ↓
Deterministic evaluator
       ↓
Same input → Same verdict
```

Message:

> AI can propose.
> AI can translate.
> AI can correct.
> **AI does not decide the final verdict.**

---

# 43. LANDING — POLICY SURFACE

Show categories:

### Architecture

* dependencies;
* layers;
* services;
* modules.

### Data

* schema;
* fields;
* allowed values;
* sensitive information.

### Engineering

* naming;
* approved dependencies;
* error handling.

### Security

* forbidden patterns;
* credentials;
* security requirements.

### Compliance

* required information;
* policy evidence;
* disclaimers.

### Business

* domain-specific rules.

---

# 44. LANDING — CATEGORY POSITION

Do not build an aggressive competitor table.

Explain category relationships.

AI agents:

> generate.

GitHub/GitLab:

> collaborate and manage software lifecycle.

Security/static tools:

> detect classes of risk and code patterns.

Review tools:

> assist review.

CONGINE:

> **determines whether AI-produced output conforms to this organization’s executable rules.**

---

# 45. FIVE FUNCTIONAL PLANES

The stakeholder-facing system model is:

## STANDARD

What do we require?

Contracts / policies.

## JUDGMENT

Does this conform?

Deterministic evaluation.

## FEEDBACK

What must change?

Correction.

## MEMORY

What happened?

History / evidence.

## TRANSLATION

How do different agents connect?

Adapters / MCP.

These are one control plane.

---

# 46. CONGINE DOCS

Create a first-class developer documentation portal.

Navigation:

```text
Getting Started
Concepts
Contracts
Rules
MCP
Agent Integration
Validation
Enforcement
CLI
Architecture
History & Evidence
Telemetry
Security
Enterprise
Business Policy DSL
API Reference
SDK Reference
Changelog
```

---

# 47. DOCS INFORMATION ARCHITECTURE

## Getting Started

* What is CONGINE?
* Why CONGINE?
* Install
* First contract
* First validation
* Connect agent
* First blocked change
* First corrected change

## Concepts

* Organizational correctness
* Contracts
* Rules
* Verdict
* Breach
* Enforcement
* Evidence

## Integrations

* MCP
* Claude Code
* Cursor
* CI
* CLI
* internal agents
* API integration

## Architecture

* six-layer architecture
* deterministic core
* control loop
* failure model
* deployment model

## Governance

* contract lifecycle
* policy versions
* audit
* evidence
* history

## Future

* architecture graph
* multi-agent profiles
* Business Policy DSL
* Policy IR
* Executable Organizational Policy

---

# 48. CONTROL PLANE

The Control Plane is the enterprise management/governance surface around the deterministic engine.

Do not imply that all surfaces exist today.

Conceptual navigation:

```text
CONGINE

Overview

CONTROL
  Contracts
  Policies
  Rules
  Enforcement
  Agents

OBSERVE
  Activity
  Validation Runs
  Violations
  Telemetry
  Costs

MEMORY
  History
  Evidence
  Decisions
  Architecture

INTEGRATE
  MCP
  Agents
  CI/CD
  API

GOVERN
  Approvals
  Audit
  Organizations
  Teams
  Access

DEVELOP
  Contract Tester
  Policy Simulator
  Playground

SETTINGS
```

---

# 49. CONTROL PLANE OVERVIEW

It should answer:

> **Is our AI-generated software conforming to organizational policy?**

Metrics:

* governed agent changes;
* validation coverage;
* pass rate;
* block rate;
* retries-to-converge;
* contract coverage;
* architecture violations;
* evidence coverage;
* latency;
* token/context effects;
* silent non-enforcement.

Avoid vanity metrics.

---

# 50. CONTRACT WORKSPACE

Show:

* contract name;
* ID;
* owner;
* version;
* status;
* description;
* scope;
* project;
* environment;
* rules;
* severity;
* enforcement mode;
* affected agents;
* affected repositories;
* history;
* evidence.

Lifecycle:

```text
AUTHOR
 ↓
REVIEW
 ↓
VERSION
 ↓
APPROVE
 ↓
PUBLISH
 ↓
ENFORCE
 ↓
OBSERVE
 ↓
REFINE
 ↓
RETIRE
```

---

# 51. CONTRACT / POLICY EDITOR

Should feel like:

> Git + policy IDE + schema editor

not a giant settings form.

Include:

* readable policy;
* machine-readable representation;
* rule list;
* test cases;
* simulation;
* severity;
* version;
* approval;
* diff;
* evidence links.

---

# 52. POLICY SIMULATION

Allow:

> **Test this policy before publishing.**

Example:

```text
Policy: service-architecture-v3

18 rules evaluated

16 pass
2 fail

VERDICT:
BLOCK

AR-014 Critical
AR-019 High
```

Policy version comparison:

```text
v3.1 → v3.2

Newly blocked: 2 cases

Affected:
14 repositories
3 teams
2 agent workflows
```

---

# 53. ENFORCEMENT MODES

Represent clearly.

## Observational

Validate and record.

No block.

## Permissive

Validate and record.

Continue.

## Strict

Validate.

Record.

Block.

This is an explicit organizational choice.

---

# 54. MCP EXPERIENCE

Design a dedicated integration page.

Workflow:

```text
Configure
 ↓
Authenticate
 ↓
Organization
 ↓
Project
 ↓
Policy set
 ↓
Agent
 ↓
Validate
 ↓
Observe governed loop
```

Connection states:

* connected;
* degraded;
* disconnected;
* policy unavailable;
* service unavailable;
* fallback.

---

# 55. AGENT EXPERIENCE

Each agent may show:

* identity;
* provider;
* connection status;
* projects;
* validation volume;
* block rate;
* pass rate;
* retries;
* convergence;
* recurring violations;
* capability profile.

Agent telemetry does not define organizational truth.

---

# 56. VALIDATION EVENT

Example:

```text
Validation #8F3A92

BLOCKED

Project
Payments Platform

Agent
Claude Code

Contract
payments-architecture-v3

Version
3.2

Rules evaluated
27

Passed
25

Failed
2

Duration
84 ms

Enforcement
STRICT
```

For each breach show:

* ID;
* severity;
* expected;
* observed;
* location;
* evidence;
* correction.

---

# 57. SYSTEM STATES

Never make enforcement ambiguous.

Required states:

* ENFORCED
* NOT ENFORCED
* OBSERVED
* WARNED
* BLOCKED
* DEGRADED
* CONTRACT UNAVAILABLE
* SYSTEM UNAVAILABLE

Critical rule:

> **No silent non-enforcement.**

Never say:

> Everything is compliant

when policy was not actually evaluated.

Instead:

> **NOT ENFORCED — required contract unavailable.**

---

# 58. TELEMETRY

Do not design generic infrastructure telemetry.

This is:

# Governance Telemetry

It should answer:

> **What is happening to organizational correctness as autonomous development scales?**

---

# 59. TELEMETRY — ENFORCEMENT

Track:

* validations;
* passes;
* warnings;
* blocks;
* enforcement coverage.

---

# 60. TELEMETRY — CONVERGENCE

Track:

* retry count;
* median retry count;
* first-pass acceptance;
* time-to-pass;
* correction rate.

---

# 61. TELEMETRY — ECONOMICS

Track:

* token volume;
* context volume;
* retry cost;
* task cost;
* estimated savings;
* correction size.

Do not fabricate savings.

Measure them.

---

# 62. TELEMETRY — ORGANIZATIONAL CORRECTNESS

Track:

* architecture violations;
* contract violations;
* policy violations;
* violations reaching main;
* repeated violations.

---

# 63. TELEMETRY — MEMORY

Track:

* validation history;
* evidence coverage;
* replay availability;
* time-to-resume.

---

# 64. TELEMETRY — AGENTS

Track:

* pass rate;
* block rate;
* retries;
* recurring violation classes;
* empirical capability profile.

---

# 65. EVIDENCE EXPERIENCE

Compliance must be able to ask:

> What happened?

and trace:

```text
Agent
 ↓
Project
 ↓
Contract
 ↓
Version
 ↓
Rules
 ↓
Validation
 ↓
Violation
 ↓
Correction
 ↓
Re-validation
 ↓
Final verdict
```

Message:

> **We do not merely claim that the policy operated. We can show what happened.**

---

# 66. REPLAY

Future evidence should conceptually support:

> Replay Validation

```text
Original output
+
Contract version
+
Rules
+
Configuration
=
Original deterministic verdict
```

---

# 67. HISTORY / INSTITUTIONAL MEMORY

Design:

* timeline;
* decisions;
* recurring violations;
* project context;
* previous sessions;
* handoffs.

Progression:

```text
Events
 ↓
History
 ↓
Patterns
 ↓
Institutional memory
 ↓
Architecture intelligence
```

---

# 68. ARCHITECTURE GRAPH

Future Phase E experience.

Nodes:

* systems;
* services;
* modules;
* domains;
* APIs;
* databases;
* infrastructure;
* repositories;
* contracts.

Edges:

* imports;
* calls;
* depends on;
* exposes;
* owns;
* forbidden relationship.

Example violation:

```text
Domain Service ─────X────→ Infrastructure DB
```

Show:

> BLOCKED BY AR-014

This should be framed as:

# Executable Architecture

not merely an architecture visualization.

---

# 69. ORGANIZATION VIEW

Possible enterprise health:

```text
Projects governed
31 / 36

Active contracts
47

Agent workflows governed
82%

Strict enforcement
61%

Evidence coverage
98.4%

Silent non-enforcement
0
```

Do not invent numbers for real deployments.

Use examples only in mockups.

---

# 70. PROJECT VIEW

Answer:

> **How safely is this project being produced by AI?**

Show:

* repository;
* architecture;
* policies;
* contracts;
* agents;
* validation;
* violations;
* evidence;
* telemetry;
* history;
* integrations.

---

# 71. COMPLIANCE VIEW

Compliance should see:

* active controls;
* ownership;
* policy status;
* covered systems;
* failed controls;
* evidence;
* audit history;
* versions;
* exports.

Use business language first.

Technical detail is expandable.

---

# 72. ENGINEERING LEAD VIEW

Central question:

> **Is AI improving throughput without making our engineering system less coherent?**

Show:

* architecture violations;
* policy coverage;
* blocked changes;
* retries;
* convergence;
* agent consistency;
* recurring problems.

---

# 73. PLATFORM VIEW

Show:

* MCP health;
* connection state;
* service health;
* latency;
* failures;
* contract distribution;
* resilience;
* cache;
* integration status;
* agents.

---

# 74. EXECUTIVE VIEW

Focus on:

* AI adoption;
* governance coverage;
* risk prevented;
* organizational consistency;
* economics;
* scale.

Avoid low-level engine details.

---

# 75. TRUST CENTER

Public Trust Center:

* deterministic architecture;
* privacy;
* security;
* deployment;
* data handling;
* failure semantics;
* evidence;
* offline behavior;
* enterprise controls.

Never invent certifications.

---

# 76. POLICY STUDIO — FUTURE

Future Policy Studio should support:

```text
Organizational intent
      ↓
AI-assisted draft
      ↓
Business Policy DSL
      ↓
Review
      ↓
Policy IR
      ↓
Simulation
      ↓
Approval
      ↓
Publish
      ↓
Deterministic enforcement
```

AI assists.

Human owns policy.

CONGINE enforces.

---

# 77. MULTI-AGENT GOVERNANCE

```text
Claude Code ──┐
Cursor ───────┤
Internal AI ──┤
Future agent ─┘
      ↓
Translation
      ↓
Common representation
      ↓
Same organizational policy
      ↓
Deterministic judgment
```

This should visually reinforce:

> agents can change without changing organizational authority.

---

# 78. VALIDATION → MEMORY → INTELLIGENCE

Strategic diagram:

```text
Validation Events
      ↓
Telemetry
      ↓
History
      ↓
Evidence
      ↓
Project Memory
      ↓
Architecture Graph
      ↓
Agent Profiles
      ↓
Multi-Agent Governance
```

Observed data becomes intelligence.

AI does not invent organizational truth.

---

# 79. PILOT SUCCESS EXPERIENCE

Design a pilot scorecard.

Pilot must prove:

## Coverage

Agent changes actually reach CONGINE.

## Determinism

Same input + same contract = same verdict.

## Enforcement

At least one important rule blocks a violating change.

## Correction

Violation feedback helps the agent correct.

## Convergence

The loop reaches valid output efficiently.

## Evidence

The organization can prove what happened.

## Economics

Retries/tokens/review effort show measurable impact.

## Safety

No silent non-enforcement.

---

# 80. REQUIRED DIAGRAMS

Create professional stakeholder/system diagrams for:

1. Enterprise Use-Case View
2. Agent → MCP → CONGINE Workflow
3. Block → Correction → Pass Loop
4. Contract Lifecycle
5. Control Plane Architecture
6. Five Functional Planes
7. L0–L5 Hexagonal Architecture
8. Phase 0 → A → B → C → D → E → F
9. Strategic Evolution
10. Telemetry → History → Intelligence
11. Multi-Agent Normalization
12. Business Policy DSL → Policy IR → Deterministic Evaluator
13. Enterprise Deployment
14. Stakeholder Value Map

Avoid decorative diagrams.

Make relationships understandable.

---

# 81. HIGH-LEVEL SYSTEM VIEW

Use a model approximately like:

```text
                    AI / AUTONOMOUS AGENTS
              Claude Code • Cursor • Internal AI
                            │
                            ▼
                    MCP / API / CLI
                            │
                            ▼
              ┌────────────────────────┐
              │        CONGINE         │
              │                        │
              │ STANDARD               │
              │ Contracts / Policies   │
              │                        │
              │ JUDGMENT               │
              │ Deterministic Engine   │
              │                        │
              │ FEEDBACK               │
              │ Correction             │
              │                        │
              │ MEMORY                 │
              │ History / Evidence     │
              │                        │
              │ TRANSLATION            │
              │ Agent Adapters         │
              └───────────┬────────────┘
                          │
                          ▼
                     VCS / CI / CD
                          │
                          ▼
                   Production Systems
```

---

# 82. INTERNAL ARCHITECTURE VIEW

```text
L5  ADAPTERS
    MCP / CLI / APIs / Composition

L4  INFRASTRUCTURE
    Cache / Events / Resilience / Storage

L3  USE CASES
    Validation / Orchestration

L2  DOMAIN
    Contracts / Rules / Deterministic Judgment

L1  PORTS
    Stable interfaces

L0  KERNEL
    Invariants / Limits / Fundamental Types
```

Show dependencies pointing inward.

Highlight the deterministic core.

---

# 83. PRODUCT MATURITY MODEL

Use consistently.

## NOW

Deterministic contract validation.

## NEXT

MCP control point.

## THEN

History and evidence.

## PROVE

Token/convergence economics.

## DIFFERENTIATE

Architecture and multi-agent normalization.

## FUTURE

Adaptive routing.

## DESTINATION

Executable Organizational Policy.

---

# 84. REQUIRED DESIGN SYSTEM

Only create after IA and wireframes.

Brand should feel:

* authoritative;
* precise;
* technical;
* enterprise;
* restrained;
* trustworthy.

---

# 85. TYPOGRAPHY

Use a highly legible modern sans serif.

Possible direction:

* Inter
* Geist
* IBM Plex Sans
* SF Pro-like system typography

Technical values:

* JetBrains Mono
* Geist Mono
* IBM Plex Mono

---

# 86. SEMANTIC COLOR

Color must have meaning.

### Green / Teal

* conforming;
* healthy;
* pass;
* allowed.

### Amber

* warning;
* degraded;
* non-blocking issue.

### Red

* blocked;
* policy breach;
* enforcement failure.

### Blue

* information;
* configuration;
* technical context.

### Neutral

* historical;
* inactive;
* metadata.

The **BLOCKED** state should become visually recognizable as CONGINE.

---

# 87. REQUIRED COMPONENTS

Create:

* ContractCard
* PolicyCard
* RuleCard
* VerdictBadge
* BreachCard
* EnforcementBadge
* ValidationRun
* EvidenceTimeline
* PolicyVersion
* PolicyDiff
* ContractDiff
* AgentCard
* MCPConnection
* IntegrationStatus
* TelemetryMetric
* CostMetric
* ArchitectureNode
* ArchitectureEdge
* AuditRecord
* ComplianceControl
* ProjectCard
* PolicySimulator

Include:

* loading;
* empty;
* pass;
* warning;
* block;
* degraded;
* unavailable;
* permission-denied states.

---

# 88. REQUIRED DESIGN PROCESS

Follow this order exactly.

## Stage 1 — Product Experience Architecture

Produce:

* product surfaces;
* stakeholders;
* product hierarchy;
* IA;
* current/future boundaries.

---

## Stage 2 — Critical User Journeys

At minimum:

1. Discover CONGINE
2. Connect an agent
3. Create/select a project
4. Configure contract
5. Submit AI-generated change
6. Validate
7. Block
8. Correct
9. Revalidate
10. Pass
11. Record evidence
12. Review telemetry
13. Investigate a violation
14. Review/update policy

---

## Stage 3 — Wireframes

Wireframe first:

* Landing;
* Docs;
* Overview;
* Project;
* Contracts;
* Contract Detail;
* Validation;
* Breach;
* Agent;
* MCP;
* Evidence;
* Telemetry;
* Architecture;
* future Policy Studio.

Do **not** jump straight to high fidelity.

---

## Stage 4 — Design System

Only after the UX structure is stable.

---

## Stage 5 — High Fidelity

Build polished enterprise experiences.

---

## Stage 6 — Interactive Prototype

At minimum connect:

* Landing → Demo
* Agent setup
* MCP connection
* Validation
* Block
* Correction
* Pass
* Evidence
* Telemetry
* Contract inspection

---

# 89. CRITICAL JOURNEY — DISCOVERY

```text
Landing
 ↓
Governance problem
 ↓
Functional vs Organizational Correctness
 ↓
How CONGINE works
 ↓
Interactive control loop
 ↓
Architecture
 ↓
Enterprise outcomes
 ↓
Docs / Demo
```

---

# 90. CRITICAL JOURNEY — CONNECT AGENT

```text
Control Plane
 ↓
Organization
 ↓
Project
 ↓
Repository
 ↓
Agent
 ↓
MCP
 ↓
Contract
 ↓
Enforcement
 ↓
First validation
```

---

# 91. CRITICAL JOURNEY — DEMO MOMENT

```text
Agent
 ↓
Change
 ↓
MCP
 ↓
CONGINE
 ↓
BLOCK
 ↓
AR-014
 ↓
Correction guidance
 ↓
Agent fixes
 ↓
CONGINE
 ↓
PASS
 ↓
Evidence
```

This is the most important journey.

---

# 92. CRITICAL JOURNEY — POLICY AUTHORING

Future journey:

```text
Human intent
 ↓
AI-assisted draft
 ↓
Business Policy DSL
 ↓
Review
 ↓
Validate/compile
 ↓
Approve
 ↓
Publish
 ↓
Enforce
 ↓
Observe
 ↓
Refine
```

---

# 93. CRITICAL JOURNEY — COMPLIANCE

```text
Violation
 ↓
Validation event
 ↓
Agent
 ↓
Project
 ↓
Contract
 ↓
Version
 ↓
Rule
 ↓
Evidence
 ↓
Correction
 ↓
Final verdict
 ↓
Replay / Export
```

---

# 94. WHAT NOT TO DO

Do NOT:

1. design only dashboards;
2. lead the landing page with telemetry;
3. make AI the center of the brand;
4. put an LLM on the verdict path;
5. present Business Policy DSL as finished;
6. present Phase E as already available;
7. present adaptive routing as the core;
8. invent unsupported features;
9. use vague “AI governance” language;
10. make CONGINE look like GitHub;
11. make CONGINE look like Snyk;
12. make CONGINE look like an AI chat application;
13. turn token optimization into a standalone product;
14. turn History into a standalone product;
15. turn Multi-Agent Normalization into a standalone product;
16. fabricate compliance certifications;
17. imply policies were enforced when evaluation failed;
18. hide failure states;
19. overload executive users with internal architecture;
20. make the future vision override the current roadmap.

---

# 95. DESIGN FOR SKEPTICISM

A skeptical stakeholder should find answers quickly.

### Is CONGINE another AI wrapper?

No.

The core judgment is deterministic.

### Does CONGINE ask AI whether another AI is correct?

No.

### Can CONGINE stop a violating change?

Yes, where integrated into the agent and/or authoritative downstream control point.

### Can we see why it failed?

Yes.

### Can the agent correct it?

Yes.

### Can we prove enforcement happened?

Through evidence/history.

### Can different AI agents use the same standard?

Yes.

Translation belongs at the edge.

### Can policy be versioned?

Yes, as an organizational control lifecycle.

### Can ROI be measured?

Through:

* retries;
* convergence;
* tokens;
* context;
* review effort;
* validation latency.

---

# 96. ENTERPRISE DEPLOYMENT DIRECTION

Conceptually support:

## Local

Embedded/local enforcement.

## Team

Shared service.

## Enterprise

Central management + organizational governance.

## Hybrid

Central policy + distributed deterministic enforcement.

## Offline / Air-gapped

Where supported:

* local contracts;
* local evaluation;
* reduced external dependencies.

Do not make the product concept inherently cloud-dependent.

---

# 97. RELIABILITY PRINCIPLES

Make operational behavior credible.

Support concepts such as:

* bounded execution;
* controlled degradation;
* no unbounded queues;
* failure isolation;
* local fallback where supported;
* cache integrity;
* tenant isolation;
* non-blocking observability;
* explicit unavailable states.

A governance system cannot become an uncontrolled source of instability.

---

# 98. FINAL PRODUCT NARRATIVE

The entire design should converge on:

```text
AI makes software production increasingly autonomous.

Organizations still need authority.

That authority must become executable.

Human intent
      ↓
Organizational policy
      ↓
Contracts
      ↓
Deterministic evaluation
      ↓
Enforcement
      ↓
Evidence
      ↓
Institutional memory
      ↓
Architecture intelligence
      ↓
Executable Organizational Policy
```

---

# 99. FINAL DESIGN PRINCIPLES

Prioritize:

> **Clarity over decoration.**

> **Control over novelty.**

> **Determinism over AI spectacle.**

> **Organizational correctness over generic code quality.**

> **Measurable outcomes over feature count.**

> **Evidence over claims.**

> **Trust over cleverness.**

> **Enterprise credibility over trendiness.**

> **Explicit states over ambiguity.**

---

# 100. REQUIRED OUTPUT FROM CLAUDE DESIGN

Do not start by immediately generating random polished screens.

First return:

## Part 1 — Your understanding of CONGINE

Explain:

* what category it occupies;
* primary problem;
* trust model;
* current state;
* near-term wedge;
* strategic destination.

---

## Part 2 — Product Experience Architecture

Produce:

* product surfaces;
* stakeholder relationships;
* current/next/planned/strategic capability model.

---

## Part 3 — Information Architecture

Show navigation for:

* Landing;
* Docs;
* Control Plane;
* Observe;
* Memory;
* Integrate;
* Govern;
* future Policy Studio.

---

## Part 4 — Stakeholder Journeys

Map:

* Developer
* Architect
* Engineering Lead
* Platform
* Compliance
* Executive

---

## Part 5 — Critical Process Flows

At minimum:

* MCP enforcement loop;
* contract lifecycle;
* violation investigation;
* agent integration;
* evidence workflow;
* policy lifecycle.

---

## Part 6 — Low-Fidelity Wireframes

Do this before final styling.

---

## Part 7 — Design System Direction

After workflows are established.

---

## Part 8 — High-Fidelity Screens

Then build:

* Landing Page
* Docs
* Control Plane
* Project
* Contract
* Validation
* Breach
* Agent
* MCP
* Evidence
* Telemetry
* Architecture
* future Policy Studio

---

## Part 9 — Interactive Prototype

Prioritize:

> **agent → MCP → block → correction → pass**

---

## Part 10 — Architecture Diagrams

Provide the full set of required stakeholder and technical diagrams.

---

# 101. FINAL INSTRUCTION TO CLAUDE

Treat this prompt and the attached documents as the master product-design context.

Do not simply create a website.

Do not simply create dashboards.

Do not simply create screens.

Design the complete enterprise product experience through which CONGINE is:

> **introduced → understood → integrated → configured → enforced → observed → evidenced → governed → scaled.**

The most important workflow to get right is:

# AI Agent → MCP → CONGINE → Deterministic Verdict → Correction → Re-validation → Pass / Stop → Evidence → Telemetry

Make that understandable to an executive in 30 seconds.

Make it useful to an engineer in 30 minutes.

Make the platform credible to a principal architect.

Make it trustworthy to compliance.

Make the economics legible to finance.

Make the strategic destination clear without pretending it is already implemented.

The stakeholder should leave with one unavoidable conclusion:

> **AI agents are becoming autonomous. Organizations therefore need a deterministic authority between what those agents produce and what the organization permits.**

That authority is CONGINE.

# CONGINE

## The deterministic policy layer for autonomous software development.

> # “Outputs conform to our rules, or they are stopped.”
