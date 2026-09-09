# 02 — Validation Result & Enforcement Semantics

## Problem statement

The current result model risks conflating three distinct questions:

1. **Did CONGINE actually complete the evaluation?**
2. **If it evaluated, did the output conform?**
3. **Given the organization's posture, what action should be taken?**

Evidence from semantic-validation timeout measurements makes this ambiguity safety-relevant. A degraded result may carry `status="fail"`, zero breaches, and `degraded=True`, which is fundamentally different from a completed evaluation that found a breach.

This document defines the long-term semantic model and a compatibility-safe migration path.

---

# Decision V-01 — Separate evaluation state, conformance, and enforcement action

## Target model

Conceptually represent three axes:

```text
EvaluationState
- EVALUATED
- DEGRADED
- NOT_EVALUATED

Conformance
- CONFORMING
- NON_CONFORMING
- UNKNOWN

EnforcementAction
- ALLOW
- WARN
- BLOCK
```

Examples:

### Successful pass

```text
evaluation_state = EVALUATED
conformance      = CONFORMING
action           = ALLOW
```

### Successful evaluation with violation

```text
evaluation_state = EVALUATED
conformance      = NON_CONFORMING
action           = BLOCK   # strict posture
```

### Saturated system

```text
evaluation_state = NOT_EVALUATED
conformance      = UNKNOWN
reason           = LOAD_SHED
action           = BLOCK   # strict posture
```

### Timeout under permissive posture

```text
evaluation_state = DEGRADED
conformance      = UNKNOWN
reason           = TIMEOUT
action           = WARN
```

## Why this is future-proof

It prevents future failure reasons from being forced into an overloaded pass/fail field. It also gives MCP, CI, dashboards, and compliance evidence a stable vocabulary.

---

# Decision V-02 — Compatibility migration: add `is_enforced()` first

A full result redesign may be breaking.

Immediate additive step:

```python
def is_enforced(self) -> bool:
    return not self.degraded  # exact implementation must match actual semantics
```

But do not stop at a convenience method. The method is a migration bridge.

## Acceptance criteria

- Existing `is_pass()` behavior remains backward-compatible.
- New documentation tells consumers to ask both:
  - was evaluation completed/enforced?;
  - did it conform?
- Tests cover pass, violation, timeout, load shed, internal error, missing contract.

---

# Decision V-03 — Machine-significant reasons must be typed

Replace free-form reason interpretation with a stable enum, e.g.:

```text
DegradedReason / EvaluationReason
- TIMEOUT
- LOAD_SHED
- INTERNAL_ERROR
- CONTRACT_UNAVAILABLE
- INVALID_CONTRACT
- RESOURCE_LIMIT
- EXTERNAL_DEPENDENCY_UNAVAILABLE
```

Human messages remain separate.

## Why

Never make downstream behavior depend on matching strings like `"validation execution timed out"`.

---

# Decision V-04 — Distinguish load shedding from timeout

Introduce a dedicated error type such as:

```python
class LoadShedError(TimeoutError):
    ...
```

This preserves compatibility for broad `TimeoutError` handlers while allowing the use case to emit `LOAD_SHED` rather than `TIMEOUT`.

## Tests

- saturated executor raises `LoadShedError` immediately;
- actual deadline expiry remains `TimeoutError`/deadline-specific error;
- use case maps each to distinct machine reason;
- telemetry/evidence records distinct reasons;
- strict/degrade/silent posture behavior is asserted for both.

---

# Decision V-05 — Evaluation inability is not a breach

A timeout, saturation, missing evaluation backend, or internal crash should not fabricate a policy breach.

`breaches=[]` may be correct, but only if the result clearly says:

```text
conformance = UNKNOWN
```

rather than implying non-conformance.

---

# Decision V-06 — Enforcement posture acts after evaluation semantics

The decision pipeline should be conceptually:

```text
Evaluate
  ↓
EvaluationState + Conformance + Reason
  ↓
Apply organizational enforcement posture
  ↓
ALLOW / WARN / BLOCK
```

Do not mix policy evaluation logic with host response behavior.

This separation enables the same judgment to be reused by:

- SDK return mode;
- MCP;
- CLI;
- CI;
- future service API.

---

# Decision V-07 — Strict posture must fail closed on unknown conformance

For enterprise strict mode:

```text
Conformance.UNKNOWN
→ BLOCK
```

unless a future explicitly named policy says otherwise.

This is central to "outputs conform or are stopped."

Permissive/observational modes may warn/allow during adoption, but they must never report the result as positively conforming.

---

# Decision V-08 — One validation timeout source of truth

Current evidence identified a mismatch between a direct `ValidateContractUseCase` default and config default.

Do not merely copy one number into the other. Create one source of truth, e.g.:

```python
DEFAULT_VALIDATION_TIMEOUT_MS = 100
```

and derive all defaults from it.

If direct construction should require explicit timeout instead, choose that deliberately and remove the duplicate default.

## Test

Assert configuration and direct construction cannot silently diverge.

---

# Decision V-09 — Semantic validation receives separate budget policy

Do not solve measured semantic-validation cost by blindly increasing the global timeout.

Introduce explicit backend policy, conceptually:

```text
native_rule_budget
semantic_validation_budget
```

Possible implementation shapes:

- separate config fields;
- contract-specific complexity/budget profile;
- admission-time rejection if the contract cannot meet the configured budget.

## Immediate safe changes

- warning/hint must state semantic validation is materially more expensive;
- warn when semantic validation is enabled with a budget known to be too tight;
- expose semantic timeout metrics separately.

---

# Decision V-10 — Short-circuit impossible semantic work

If the native validator already proves the root payload structurally invalid, avoid running the semantic validator where that work cannot change a useful outcome.

This reduces latency and simplifies the semantic validator's required input tolerance.

## Guardrail

Short-circuit only when semantics are provably preserved. Add equivalence tests before and after.

---

# Decision V-11 — Result serialization must be canonical

For deterministic replay/evidence, define canonical serialization rules for verdicts:

- stable field ordering where relevant;
- stable enum values;
- deterministic breach ordering;
- no timestamps/random IDs included in the canonical judgment hash;
- separate judgment content from observation metadata.

This enables future replay verification:

```text
same input hash + contract version + evaluator version
→ same canonical verdict hash
```
