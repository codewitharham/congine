# Security Policy

Congine is security-adjacent infrastructure: it decides whether AI-generated output is permitted to
proceed. A defect in Congine can cause a system to believe a rule was enforced when it was not. We
treat that class of defect — **silent non-enforcement** — as the most serious category of bug in this
project, above crashes.

We welcome reports and will credit reporters who want credit.

---

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

**Preferred:** use GitHub's private vulnerability reporting —
[Report a vulnerability](https://github.com/codewitharham/congine/security/advisories/new).
It is private, gives us a coordinated disclosure workflow, and needs no email exchange.

**Alternative:** email `codewitharham.remote@gmail.com`.
<!-- TODO(founders): replace with a real monitored address, or delete this line and rely on GitHub
     private reporting alone. An unmonitored address is worse than no address. -->

### What to include

- What the issue is and why it is a security problem
- Reproduction steps, ideally a minimal contract + payload
- Affected version or commit SHA
- Impact as you assess it
- Any suggested remediation

### What to expect

| Stage | Target |
|---|---|
| Acknowledgement | 3 business days |
| Initial assessment | 10 business days |
| Fix or documented mitigation for accepted high-severity issues | 90 days |

This is a small team on a pre-release project. If a deadline slips we will tell you rather than go
quiet.

### Disclosure

Coordinated disclosure. We ask that you give us the assessment window before publishing. We will
credit you in the advisory unless you prefer otherwise.

---

## Supported versions

Congine is **pre-release and not yet published to a package index**. There are no supported released
versions.

| Version | Supported |
|---|---|
| `main` (HEAD) | ✅ Security fixes applied here |
| Branches, tags, forks | ❌ Not supported |
| Published releases | — none yet |

When the first release ships, this table will name supported versions and a support window.

---

## Scope

### In scope

Anything that causes Congine to be **wrong about enforcement**, or to endanger the host process:

- **Silent non-enforcement** — an output reported as conforming that the applicable contract should
  have rejected. **This is the highest-priority category.**
- **Admission bypass** — an unsafe or unenforceable contract reaching the evaluator as if admitted.
- **Determinism violation** — identical input, contract, evaluator version and configuration producing
  different verdicts.
- **Evaluation-completeness violation** — certifying an output the adapter could not completely
  represent (truncated, flattened, partially extracted, or one candidate of several).
- Denial of service against the host: unbounded CPU or memory from crafted contracts or payloads,
  including pattern-based exhaustion.
- Escaping the configured latency and capacity bounds.
- Cross-tenant leakage of cached contracts, configuration, telemetry or state.
- Credential or PII disclosure through logs, telemetry, breach messages, exceptions or health output.
- Integrity failures in locally cached contract snapshots (substitution, symlink, ownership,
  time-of-check/time-of-use).
- Supply-chain issues in declared dependencies.

### Out of scope

- Vulnerabilities in the AI models or agents Congine governs. Congine governs their output; it does
  not secure them.
- Contracts written to be permissive. Congine enforces the contract you give it — an under-specified
  contract is a policy authoring issue, not a Congine vulnerability. *(But if the engine ignores a
  declaration it accepted, that **is** in scope — see silent non-enforcement.)*
- Issues requiring an attacker who already controls the host process, the configuration environment,
  or the contract source. Those are inside the trust boundary by design.
- Anything in the unbuilt roadmap surfaces (MCP server, CLI, control plane, persistence). They do not
  exist; there is nothing to report against.
- Findings from automated scanners with no demonstrated exploit path. Please include reproduction.

---

## Known limitations at this stage

Published deliberately, because a security policy that implies more assurance than exists is itself a
security problem.

- **No published release.** Package integrity, provenance and signing are not yet established.
- **No third-party security audit.**
- **No persistence.** Telemetry is in-memory; evidence does not survive process restart. Congine cannot
  currently serve as a durable audit record.
- **Version-blind schema cache.** Congine protects last-known-good contracts from invalid replacement,
  but cannot yet prove that *exactly* the requested contract version was the one evaluated.
- **Platform coverage is incomplete.** At least one snapshot-integrity test (symlink refusal) does not
  execute on all developer platforms.
- **Contract expressiveness is bounded.** The rule engine evaluates a specific keyword set; admission
  refuses contracts it cannot honour. Read the contract reference before authoring.

These are tracked and scheduled. If any of them is load-bearing for your use case, do not deploy
Congine for that use case yet.

---

## Security model in one paragraph

Congine treats as untrusted: the output under validation, **contract definitions themselves** (they
carry patterns), remote contract-source responses, locally cached snapshots, and configuration. Every
one of those is bounded and validated before use. The validation core performs no I/O. Regex
evaluation is length-capped, with a linear-time engine available and recommended. Breach messages are
sanitised before they reach telemetry or logs, and credential-shaped fields are redacted
unconditionally. When Congine cannot completely and safely evaluate an output, it fails closed rather
than reporting conformance.
