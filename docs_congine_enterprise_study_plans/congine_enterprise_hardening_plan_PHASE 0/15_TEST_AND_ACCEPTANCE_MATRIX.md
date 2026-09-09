# 15 — Test & Acceptance Matrix

## Purpose

Define the minimum proof expected for the hardening decisions. Exact test names may differ from the current repository, but the behavioral coverage should exist.

---

## A. Validation semantics

| Case | Evaluation | Conformance | Action expectation |
|---|---|---|---|
| Valid payload | evaluated | conforming | allow |
| Rule breach | evaluated | non-conforming | posture-dependent |
| Native timeout | degraded/not evaluated | unknown | strict blocks; permissive warns/allows explicitly |
| Load shed | not evaluated | unknown | distinct reason from timeout |
| Internal validator error | degraded/not evaluated | unknown | explicit reason |
| Missing contract | current fail-closed behavior retained/explicit | unknown | never reported as conforming |
| Unserializable payload | not evaluated | unknown | resource/invalid-input reason, never size=0 bypass |

Test all relevant fail-mode × guard-mode combinations where public behavior differs.

---

## B. Contract admission

Required fixtures:

- valid simple contract;
- valid union `string|null`;
- unknown scalar type;
- union containing unknown type;
- invalid regex;
- unsupported keyword;
- dotted property key;
- literal JSON key containing dot (to prove ambiguity policy);
- `null_forbidden` legacy contract;
- future language-version mismatch;
- overly complex semantic contract.

Acceptance:

> invalid/unsupported contract semantics are surfaced before active runtime enforcement.

---

## C. Ports and substitution

For each port, create minimal implementation from the Protocol only.

Prove:

- `ServiceContainer` construction accepts valid implementation;
- health works;
- close works;
- validation/sync path uses only declared members;
- invalid implementation fails at composition boundary with clear error where runtime checks are enabled.

---

## D. Lifecycle

Failure injection after each resource creation stage:

```text
cache created → fail
bus created → fail
HTTP client created → fail
semantic validator created → fail
worker created → fail
```

After each failure, assert:

- no unexpected live worker remains;
- clients closed;
- singleton/default state coherent;
- no growing atexit registrations;
- subsequent clean construction succeeds.

Shutdown tests:

- double close;
- close during telemetry send;
- close after breaker open;
- use after close behavior;
- finalizer fallback.

---

## E. Configuration

Table-driven tests for every environment parser:

- valid value;
- uppercase/lowercase normalization where intended;
- empty value;
- whitespace;
- typo;
- unsupported enum;
- conflicting settings;
- region without real mapping;
- explicit base URL precedence.

No machine-significant typo may silently choose another topology.

---

## F. Determinism

Golden corpus dimensions:

- pass/fail cases for every native rule;
- union/null;
- regex;
- bounds;
- guard/fail modes where judgment output is canonical;
- different contract versions;
- ordering-sensitive multiple breaches.

Run across supported Python matrix and release OS.

Acceptance:

> identical canonical judgment payload for each supported environment, or explicit documented/versioned incompatibility.

---

## G. Performance

Keep representative benchmark cases for:

- native small/medium/large;
- semantic small/medium/upper-supported;
- saturation rejection;
- cache sizes;
- dead control plane;
- contract admission complexity.

Record p50/p95/p99 where sample quality supports it.

Do not use only arithmetic mean.

---

## H. Security

- adversarial regex/sanitizer cases;
- secret redaction;
- cross-tenant query denial;
- event chain tampering detection;
- invalid event schema version;
- unsafe history read-back sanitization;
- agent adapter malformed envelope rejection;
- dependency audit clean/triaged.

---

## I. Durable evidence

Once Phase C exists:

- 10 validations → 10 retrievable events;
- restart → events remain;
- tenant A cannot query tenant B;
- canonical verdict hash replay stable;
- chain verifies;
- tampered row breaks verification;
- content erasure removes erasable content but preserves evidence/tombstone chain;
- concurrent read/write does not materially damage validation latency budget.

---

## J. MCP/CLI/CI equivalence

For the same canonical input/contract:

```text
SDK verdict
MCP verdict
CLI verdict
CI verdict
```

must agree on judgment semantics.

Differences may exist only in transport/presentation/enforcement location.

---

## K. Documentation integrity

CI should verify:

- config reference completeness;
- runnable examples;
- public API snippets/imports;
- no stale "Planned"/"Available" mismatch where machine-checkable;
- architecture source commit is present;
- generated scale facts match code.
