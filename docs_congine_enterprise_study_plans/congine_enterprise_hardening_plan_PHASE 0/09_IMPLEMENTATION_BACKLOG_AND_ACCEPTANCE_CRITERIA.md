# 09 — Ordered Implementation Backlog & Acceptance Criteria

## Purpose

Provide Claude Code and the CONGINE team with an execution order. This order prioritizes **trust failures first**, then structural hardening, then future-facing architecture.

Do not interpret all tasks as one sprint.

---

# Stage 0 — Re-verify current HEAD

**Priority:** Mandatory before mutation.

- reproduce test baseline;
- confirm which named debts remain;
- record current files/line locations;
- confirm whether latest local work already changed D15 or other statuses;
- create pre-change report.

**Exit criterion:** founder/team agrees current-state matrix is accurate.

---

# P0 — Trust-critical fixes

## P0-01 — Finish `IValidationRunner` abstraction

**Change:** `ServiceContainer.health()` consumes `IValidationRunner.health()` rather than undeclared concrete properties.

**Tests:** minimal conforming runner; built-in runner; health before/after load; close.

**Done when:** no container call requires an undeclared runner member.

---

## P0-02 — Fail closed on unmeasurable payload/contract size

**Change:** serialization failure does not set size to zero.

**Tests:** unserializable payload; oversize payload; normal payload; strict/degrade semantics.

**Done when:** no input can bypass the size bound because measurement failed.

---

## P0-03 — Make dotted property semantics safe

**Immediate implementation:** admission/scanner flags or rejects dotted property keys until explicit path semantics exist.

**Tests:** existing false-safety case using `user.email`; literal dotted JSON key; nested object.

**Done when:** a contract cannot silently appear to enforce nested type/pattern through ambiguous dotted keys.

---

## P0-04 — Reject unknown contract type names at load/admission

**Tests:** scalar unknown type; union containing unknown; valid union; valid `null`.

**Done when:** invalid contract never becomes active.

---

## P0-05 — Add explicit evaluated/enforced signal

**Immediate compatibility step:** `ValidationResult.is_enforced()` (or equivalent additive property) with correct semantics.

**Tests:** pass, breach, timeout, load shed, internal error.

**Done when:** callers can distinguish "policy evaluated and failed" from "policy not successfully evaluated" without inspecting message text.

---

## P0-06 — Distinguish load shed vs timeout

**Change:** dedicated error/reason code.

**Done when:** telemetry/result/evidence can distinguish the two conditions.

---

## P0-07 — Strict configuration parsing

Includes:

- malformed bool raises;
- `contract_source` enum;
- empty local-contract path rejected;
- one timeout default source;
- all config validated before resource start.

**Done when:** typo cannot silently disable/switch a subsystem.

---

## P0-08 — Remove or disable placeholder regional routing

**Done when:** SDK never sends credentials to an unconfirmed regional hostname.

---

# P1 — Structural hardening

## P1-01 — Restore blocking mypy

- dependency + config;
- clean baseline;
- CI blocks failure.

---

## P1-02 — Runtime port checks

- validate injectable implementations at composition boundary;
- useful errors;
- minimal fake conformance tests.

---

## P1-03 — Transactional composition root

- prevalidate configuration;
- cleanup partial construction;
- test injected failure after each resource-owning stage;
- assert no thread/client leakage.

---

## P1-04 — Lifecycle cleanup

- unregister atexit;
- fix telemetry stop ordering;
- context-manager lifecycle;
- repeated create/close test.

---

## P1-05 — RE2 sanitizer

- replace stdlib regex;
- adversarial test;
- verify sanitization output compatibility.

---

## P1-06 — Remove dead `ValidationTimer`

Only after confirming no compatibility consumer exists.

---

## P1-07 — Public scanner + admission API skeleton

- export `find_unenforced_keywords`;
- introduce initial `ContractAdmissionResult`/compiler facade without forcing full IR rewrite yet.

---

## P1-08 — Fix shipped examples

- LangChain fallback matches its contract;
- every example runs in CI;
- docs embed executable examples.

---

# P1.5 — Semantic validation safety

## P1.5-01 — Honest semantic-validation warnings

Warn that semantic mode has materially higher cost and may require an appropriate budget.

## P1.5-02 — Separate semantic/native budget policy

Introduce configuration/architecture without changing every default blindly.

## P1.5-03 — Complexity/admission prototype

Measure representative contract complexity and reject/warn before activation when reliable evaluation cannot be supported.

## P1.5-04 — Evaluate compiled-validator caching

Benchmark immutable preprocessing/caching. Do not share validator objects until thread safety is proven.

---

# P2 — Verification and release gates

- branch coverage report;
- golden determinism corpus;
- Python support matrix;
- Linux production CI;
- `pip-audit`;
- SBOM;
- security Ruff rules;
- performance regression scripts.

**Exit criterion:** a release can state exactly what has been measured and on which matrix.

---

# P3 — Documentation reconciliation

After code semantics stabilize:

- update `ARCHITECTURE_CURRENT.md` against new HEAD;
- update §16 current/resolved debt;
- replace obsolete §17 open questions with resolved decisions/current founder decisions;
- correct scale facts programmatically;
- patch stale D2/W1/V2 prompts;
- create ADRs;
- rerun gap-critical examples/measurements.

Do this before generating the formal suite.

---

# Future Phase A/B/C/D/E/F alignment

## Phase A — SDK hardening + CLI

Must inherit all P0/P1 fixes before wider adoption.

## Phase B — MCP

Must use common result semantics and correction hints; MCP is advisory/early feedback, not sole enforcement.

## Phase C — Durable evidence/history

Add event versioning, tenant scope, privacy, tamper evidence, retention/erasure design.

## Phase D — Convergence/token optimization

Deterministic correction hints, context compression, measured savings.

## Phase E — Architecture intelligence + agent adapters

Graph-based enforcement, adapters, statistical profiles.

## Phase F — Adaptive routing only if data justifies it

Outside verdict path.

## Beyond F — Policy DSL / Executable Organizational Policy

Only after contract compiler/IR and organizational workflows are mature.
