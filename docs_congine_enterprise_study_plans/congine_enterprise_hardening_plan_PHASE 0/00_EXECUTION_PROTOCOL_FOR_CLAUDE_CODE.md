# 00 — Execution Protocol for Claude Code

## Mission

Implement the enterprise-hardening decisions in this package **without weakening determinism, silently changing contract meaning, inventing unsupported product capabilities, or creating a large unreviewable rewrite**.

This document is intentionally procedural. Claude Code should treat it as the execution contract for all other files.

---

## 1. Code is the runtime truth; decisions are the intended destination

The evidence used to write this package was centered around repository state near commit `49a2f93`. Before editing anything:

1. Record current branch and HEAD.
2. Confirm working tree status.
3. Locate the current equivalents of the files mentioned in this package.
4. Run the existing full test suite.
5. Re-check whether the named defects still exist.
6. Mark each task as:
   - `STILL PRESENT`;
   - `ALREADY FIXED`;
   - `CHANGED SHAPE`;
   - `CANNOT VERIFY`.

Do **not** reintroduce an old defect merely because this package describes it.

---

## 2. Work in reviewable slices

One semantic decision per commit where practical.

Recommended pattern:

```text
inspect
→ reproduce defect
→ add/adjust failing test
→ implement smallest structural fix
→ run focused tests
→ run full tests
→ update docs/comments if semantics changed
→ commit
```

Do not bundle contract-language changes, lifecycle changes, and persistence changes into one commit.

---

## 3. Never hide a failing test or benchmark

Forbidden responses to a failing test:

- deleting the test without proving it is invalid;
- relaxing assertions merely to get green CI;
- increasing timeouts without explaining the semantic consequence;
- converting exceptions to warnings if the failure is safety-relevant;
- changing examples so they stop demonstrating a real defect.

If a test reveals a contradiction, record the contradiction first.

---

## 4. Preserve the deterministic verdict boundary

No implementation in this package authorizes an LLM/model call inside:

- rule evaluation;
- contract admission decision;
- conformance verdict;
- enforcement-action selection;
- replay verification.

A model may later assist **authoring**, summarization, or optional routing outside the verdict path, but runtime policy judgment must remain deterministic.

---

## 5. Backward compatibility rule

Before changing any public type, constructor, enum, result field, or contract semantics:

1. Search repository consumers and examples.
2. Identify API compatibility impact.
3. Prefer an additive compatibility stage where possible.
4. If a semantic change is breaking, version it rather than silently changing old contract meaning.

Examples:

- add `is_enforced()` before redesigning `ValidationResult`;
- preserve v1 regex semantics while introducing a future contract-language version;
- do not remove `null_forbidden` abruptly if existing contracts may use it.

---

## 6. Required pre-change report

Before mutation, produce:

```markdown
# Enterprise Hardening Pre-Change Report

- HEAD:
- Branch:
- Working tree:
- Test baseline:
- Python version:

## P0 findings
| ID | Decision | Current status | Evidence | Planned files |
|---|---|---|---|---|

## Contradictions with this package
...

## Proposed first commit
...
```

Wait for founder review if current code materially contradicts an assumption that changes the decision.

---

## 7. Mandatory verification after every P0 semantic change

At minimum:

- focused unit tests;
- full test suite;
- ruff format/check;
- mypy once it is restored;
- relevant GAP3 examples;
- relevant GAP4 measurement if latency/resource behavior changed.

For contract semantics, also execute representative real contracts, including a pass and a deliberate breach.

---

## 8. Do not implement future phases early

Unless explicitly told otherwise, this package authorizes **hardening and architecture preparation**, not building every planned capability now.

Do not prematurely implement:

- production Control Plane before durable data;
- Business Policy DSL before a stable contract/compiler/IR boundary;
- adaptive routing before real history exists;
- model training in the core;
- vector search before structured history queries prove insufficient.

---

## 9. Documentation is part of correctness

When semantics change, update the authoritative documentation in the same change or immediately after the code stabilizes.

Never leave:

```text
code says A
architecture says B
prompt tells future author to publish B
```

That exact failure already occurred with the union-type and region fixes.

---

## 10. Definition of success

The implementation is not successful merely because tests pass.

A change is done when:

- runtime semantics are explicit;
- failure is controlled;
- the public contract is documented;
- test evidence proves the intended behavior;
- no stale documentation tells users the opposite;
- later phases can build on the seam without rewriting the core.
