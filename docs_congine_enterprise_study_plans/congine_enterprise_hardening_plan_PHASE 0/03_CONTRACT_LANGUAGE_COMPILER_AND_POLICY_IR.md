# 03 — Contract Language, Admission Compiler & Future Policy IR

## Goal

Move contract safety failures from runtime into contract admission, while creating a clean future path toward Executable Organizational Policy without building the Business Policy DSL too early.

---

# Decision C-01 — Introduce a first-class Contract Admission / Compilation boundary

## Current risk pattern

A contract may be syntactically loadable yet contain semantics that are:

- unsupported;
- ambiguous;
- too expensive;
- partially enforced;
- accidentally fail-open.

Discovering these conditions during every runtime validation is too late.

## Target flow

```text
Authoring source
    ↓
parse
    ↓
contract admission / compiler
    ├─ language-version validation
    ├─ supported vocabulary validation
    ├─ type validation
    ├─ regex validation
    ├─ path-semantics validation
    ├─ complexity/budget analysis
    ├─ normalization
    └─ canonical hash
    ↓
CompiledContract / PolicyIR
    ↓
runtime deterministic evaluator
```

## Core principle

A malformed or unsupported contract is a **publication error**, not a runtime conformance result.

---

# Decision C-02 — Unknown type names are invalid contracts

## Current problem

An unknown type such as `"str"` can disable checking instead of failing closed. A union containing an unknown name can become even more permissive.

## Decision

Reject unknown type names at contract admission.

Examples:

```json
{"type": "str"}
```

and:

```json
{"type": ["string", "mystery"]}
```

must not become active contracts.

## Why load-time error rather than breach

The problem is in the policy definition, not in the output being judged.

---

# Decision C-03 — Dotted property keys should not remain ambiguous

## Current sharp edge

Dotted paths can work for presence checks while property-rule lookup remains flat. A key like `user.email` is ambiguous because JSON can also legally contain a literal property named `"user.email"`.

## Immediate decision

At minimum, detect dotted property keys and reject or warn before activation. For strict enterprise safety, prefer rejection until an explicit path language exists.

## Long-term path representation

If nested paths are required, introduce explicit syntax such as JSON Pointer:

```text
/user/email
```

or a dedicated CONGINE path field/rule.

Do not overload JSON property names with implicit path semantics.

---

# Decision C-04 — Version the CONGINE contract language

A contract needs two versions:

```json
{
  "congineContractVersion": "1.0",
  "id": "payments-architecture",
  "version": "3.2.0"
}
```

Meaning:

- `congineContractVersion`: semantics of the CONGINE language;
- `version`: organization's revision of this policy.

## Why

Future changes such as regex semantics or keyword behavior must not silently reinterpret historical contracts.

---

# Decision C-05 — Preserve current regex semantics in v1; remove ambiguity in future versions

Current evidence shows `pattern` uses full-string matching, while standard JSON Schema `pattern` is search-based.

Do not silently change v1 contracts.

Recommended evolution:

```text
v1: pattern = existing full-match behavior, clearly documented
v2: pattern = JSON-Schema-compatible search semantics
    fullPattern (or similar explicit extension) = full-match behavior
```

The exact names require founder/API review, but the key decision is **versioned semantics rather than silent reinterpretation**.

---

# Decision C-06 — Keep `null_forbidden` for compatibility, then deprecate gradually

Union types are now supported, making standard nullable/non-nullable schemas possible.

Recommended lifecycle:

```text
v1: supported, documented as CONGINE extension
future version: legacy/deprecated warning
later: removal only with migration tooling and major-version policy
```

Do not strand existing contracts.

---

# Decision C-07 — Keep a small native deterministic rule subset

Do not replace the native rule engine with full JSON Schema by default.

The measurements show native validation is dramatically faster than semantic validation. A small deterministic hot-path evaluator is therefore a strategic property, not merely an implementation shortcut.

## Expansion rule

Add native rules only when they are:

- deterministic;
- bounded/cheap;
- semantically clear;
- high-value to actual users.

Candidates worth evaluating include:

- `minLength`;
- `maxLength`;
- `const`.

Do not chase full JSON Schema completeness as a product goal.

---

# Decision C-08 — Unsupported vocabulary must be admission-visible

A contract author should never have to discover after production use that a keyword was decorative.

Preferred future behavior:

```text
unsupported keyword
→ ContractAdmissionIssue
→ error or explicit warning according to policy
→ cannot be mistaken for enforced vocabulary
```

The current `find_unenforced_keywords` is useful but convention-based. It should evolve into the contract compiler so every load path receives the same protection.

---

# Decision C-09 — Export `find_unenforced_keywords` now

Until the compiler exists, expose the scanner through the public package API so external loaders can perform the same mandatory safety check.

Add API tests and documentation.

Long term, users should call the compiler rather than remembering this helper manually.

---

# Decision C-10 — Add contract complexity analysis

Semantic validation measurements prove that contract size/complexity can exceed runtime budgets.

At admission time, estimate/measure relevant complexity:

- property count;
- nested depth;
- regex count/length;
- semantic validator cost proxy;
- reference expansion if later supported.

Possible policy:

```text
complexity within guaranteed budget → activate
complexity near limit             → warn / require larger budget
complexity beyond supported bound → reject
```

The exact model should be evidence-driven; do not pretend property count alone fully predicts cost.

---

# Decision C-11 — Create a canonical compiled representation

Do not let every adapter parse raw policy syntax independently.

Create an internal immutable representation such as:

```text
CompiledContract / PolicyIR
```

containing normalized:

- contract ID/version;
- language version;
- rule definitions;
- normalized paths;
- compiled/validated regex metadata;
- semantic backend requirements;
- canonical hash;
- admission warnings/errors;
- evaluator compatibility version.

Runtime evaluation should consume this representation wherever practical.

---

# Decision C-12 — Future Business Policy DSL compiles into the same IR

Long-term pipeline:

```text
Human prose / UI / DSL / API
      ↓
optional model-assisted authoring
      ↓
human review
      ↓
compiler
      ↓
Policy IR
      ↓
deterministic evaluator
```

The model never becomes the final runtime policy judge.

This lets CONGINE expand from engineering contracts to broader executable organizational policy without replacing its core trust model.
