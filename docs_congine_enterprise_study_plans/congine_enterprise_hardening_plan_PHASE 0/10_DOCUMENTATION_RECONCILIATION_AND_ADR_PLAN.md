# 10 — Documentation Reconciliation & ADR Plan

## Goal

Prevent the formal document suite and developer docs from fossilizing obsolete behavior.

The previous architecture snapshot drifted because it predated a remediation commit that closed many of its own open questions. The repair should preserve valid architecture analysis while updating facts that changed.

---

# Decision DOC-01 — Do not regenerate everything blindly

Prefer targeted reconciliation of sections/facts that drifted, followed by verification against current HEAD.

At minimum update:

- current source/module/LOC/test/config/port counts;
- port inventory including lifecycle interfaces;
- contract semantics changed by fixes;
- configuration behavior;
- test/evidence facts;
- debt register;
- open/resolved questions.

If current HEAD has drifted more deeply than the earlier analysis, expand scope accordingly.

---

# Decision DOC-02 — `ARCHITECTURE_CURRENT.md` must identify its source commit

Required header fields:

```text
Source commit
Verification date
Working tree status
Test baseline
Architecture document version
```

The name `CURRENT` is not enough without a verifiable snapshot.

---

# Decision DOC-03 — Debt register has stable IDs and statuses

Do not delete or renumber historical debt.

Use states such as:

```text
OPEN
RESOLVED
ACCEPTED
DEFERRED
SUPERSEDED
```

Each item should include:

- severity;
- impact;
- evidence;
- decision/ADR;
- resolution commit if fixed;
- verification test.

---

# Decision DOC-04 — Replace obsolete "Open Questions" with decision history

Old Q1–Q12 decisions should become resolved architecture decisions or ADR references.

New founder questions should be tracked separately until resolved.

Do not keep a heading implying a decided behavior is still open.

---

# Decision DOC-05 — Patch downstream prompts before running them

Known stale prompt classes include instructions that still treat fixed union behavior/region behavior as current defects.

Before D2/W1/formal authoring:

1. compare every hard-coded current-state claim to reconciled architecture;
2. replace resolved defect language with historical/resolution language;
3. update config counts and status labels;
4. preserve real remaining sharp edges such as dotted-path ambiguity and semantic-validation cost.

---

# Decision DOC-06 — ADRs are the durable home for founder intent

Create ADRs for at least:

- why hexagonal architecture;
- native rule subset philosophy;
- contract language versioning;
- unknown type policy;
- dotted path/path-language decision;
- regex semantics/migration;
- result/evaluation state model;
- strict configuration parsing;
- semantic validation budget strategy;
- supported production platforms;
- MCP + CI enforcement ladder;
- evidence durability policy;
- no-model-in-verdict rule;
- multi-agent adapters/statistical profiles;
- future Policy IR/DSL separation.

---

# Decision DOC-07 — Do not fabricate historical rationale

Where the original reason is unknown, ADR should say:

```text
Historical rationale was not recorded.
This ADR establishes the decision going forward based on current evidence.
```

Do not rewrite history as if a later inference was the original reason.

---

# Decision DOC-08 — Generated/measured facts should be automated

Examples:

- source file count;
- config field count;
- exported public symbols;
- test count;
- supported Python matrix;
- docs config-reference completeness.

Prefer tests/scripts that detect drift rather than manual prose maintenance.

---

# Decision DOC-09 — Every capability uses one maturity vocabulary

Use consistently:

- `Available`;
- `Partial`;
- `Planned — Phase X`;
- `Prototype`.

The docs, Control Plane, formal suite, and external demos must agree.

---

# Decision DOC-10 — Formal suite begins only after technical truth stabilizes

Recommended order remains:

```text
hardening/reconciliation
→ F03 ARD
→ F04 SRS
→ F02 Domain Compendium
→ F06 Use/Edge Cases
→ F07 Security
→ F05 Evidence
→ F08 Roadmap
→ F01 Concept summary
→ F09 ADR archive (can proceed partly in parallel after decisions settle)
```

Do not author a polished permanent suite around semantics that are about to change.
