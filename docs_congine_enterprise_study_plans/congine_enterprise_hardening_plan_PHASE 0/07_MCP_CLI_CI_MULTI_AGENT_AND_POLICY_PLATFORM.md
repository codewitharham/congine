# 07 — MCP, CLI/CI, Multi-Agent Normalization & Future Policy Platform

## Goal

Define how CONGINE expands from an SDK into an agent control boundary without making MCP a single point of trust or introducing probabilistic behavior into the verdict path.

---

# Decision M-01 — MCP is the earliest feedback surface, not the only enforcement boundary

MCP is ideal for:

```text
agent proposes
→ CONGINE evaluates
→ BLOCK + precise breach
→ agent corrects
→ revalidate
→ PASS
```

But an agent can potentially fail to call an advisory tool.

Therefore the long-term enforcement ladder is:

```text
MCP             → earliest in-loop feedback
pre-commit/CLI  → developer boundary
CI              → authoritative repository boundary
```

All use the same contract and same core evaluator.

---

# Decision M-02 — CLI and CI are integration surfaces, not separate engines

CLI should parse change/input context and invoke existing use cases.

CI should consume canonical result/action semantics and fail/publish evidence according to configured posture.

Do not implement CI-only policy logic.

---

# Decision M-03 — Correction hints are deterministic

Add correction hints as table-driven/machine-readable output derived from the breach:

```text
rule + field + expected constraint
→ deterministic correction hint
```

No LLM call is needed in CONGINE to generate the authoritative hint.

The coding agent may use the hint to generate a patch.

---

# Decision M-04 — Measure convergence, not just violations

Future evidence should measure:

- first-pass conformance;
- retries after block;
- median retries to PASS;
- correction success rate;
- token/context cost per retry;
- time to convergence.

This is a stronger product/economic metric than raw validation count.

---

# Decision M-05 — Agent adapters are anti-corruption layers

Core rule:

```text
agent-specific dialect
→ adapter
→ canonical internal representation
→ core
```

After adapter normalization, the core should not need to know whether output came from Claude, OpenAI, or a self-hosted model.

---

# Decision M-06 — Never train the core to learn each agent

Do not use model training/fine-tuning in the deterministic judgment path.

Instead:

1. one shared contract standard;
2. thin deterministic adapters;
3. statistical capability profiles built from historical events;
4. optional future routing outside verdicting.

This preserves the determinism moat and avoids a data-hungry research project.

---

# Decision M-07 — Capability profiles are statistics, not learned truth

Profile fields may include:

- sample count;
- pass rate;
- median retries;
- cost;
- latency;
- performance by contract/task category;
- confidence interval where appropriate;
- drift indicators.

Never present sparse data as certainty.

---

# Decision M-08 — Adaptive routing is late and optional

Only consider contextual-bandit-style routing after:

- durable event history exists;
- enough per-agent/task observations exist;
- profile quality is measurable;
- routing can be kept outside the judgment path.

Do not build RL/model training into Phases A–E.

---

# Decision M-09 — Architecture graph is for enforcement first, visualization second

The architecture graph should support deterministic questions such as:

- forbidden dependency edge;
- layer violation;
- cycle introduction;
- reachability restriction;
- ownership/boundary rule.

The UI graph is a consequence of the enforceable model, not the primary purpose.

---

# Decision M-10 — Business Policy DSL remains a later authoring layer

Do not build the DSL before:

- contract semantics stabilize;
- compiler/admission boundary exists;
- Policy IR exists;
- engineering-policy use cases prove value.

Future pipeline:

```text
human policy
→ optional model-assisted draft
→ human review
→ DSL/API/UI
→ compiler
→ Policy IR
→ deterministic evaluator
```

---

# Decision M-11 — Model assistance never grants itself authority

If a model drafts a policy, it is an untrusted authoring suggestion until:

- syntactically valid;
- semantically admitted;
- reviewed/approved according to organizational workflow;
- versioned and activated.

The model cannot approve its own policy into runtime enforcement.

---

# Decision M-12 — Every integration emits common evidence

MCP, CLI, CI, SDK and future API should all produce compatible evidence fields:

- tenant/project;
- integration surface;
- contract ID/version;
- evaluator version;
- evaluation state;
- conformance;
- enforcement action;
- reason/breaches;
- duration;
- correlation/session identifiers.

This makes the Control Plane integration-agnostic.
