# 05 — Security, Supply Chain & Platform Support

## Goal

Ensure CONGINE's security posture matches the seriousness of its governance claims, especially at untrusted-input, persistence, agent-adapter, and configuration boundaries.

---

# Decision S-01 — Payload/contract size failures must fail closed

## Current class of defect

If serialization fails and size is treated as zero, an unmeasurable payload can bypass the bound.

## Required behavior

```text
cannot serialize/measure safely
→ evaluation not performed
→ explicit RESOURCE_LIMIT / INVALID_INPUT reason
→ strict posture blocks
```

Never convert measurement failure to `size = 0`.

---

# Decision S-02 — Measure actual bytes when field names say bytes

Long-term, use the exact encoded representation the limit is intended to protect, e.g. UTF-8 encoded JSON bytes.

Do not keep a `*_bytes` configuration whose implementation counts characters.

If changing semantics is potentially breaking, introduce clear migration/release notes.

---

# Decision S-03 — Use RE2 for the PII sanitizer

If current code still uses stdlib `re` in `pii_sanitize.py`, switch to RE2 because:

- RE2 is already a required core dependency;
- this path processes untrusted/error-derived strings;
- the project already claims linear-time pattern evaluation as a security property.

Add adversarial sanitizer tests.

---

# Decision S-04 — Windows is development-only until production security parity exists

Current evidence found weaker snapshot ownership/symlink protections on Windows and skipped security coverage.

Product posture:

```text
Windows: supported for development/testing
POSIX/Linux: production-supported baseline
```

Do not claim Windows production support until all of the following exist:

- Windows owner/ACL validation;
- junction/reparse-point protection;
- equivalent integrity tests;
- Windows CI;
- documented threat-model parity.

---

# Decision S-05 — Do not ship placeholder regional endpoints

If regional endpoints are not deployed/owned, do not map `region` to plausible-looking hostnames.

Until real endpoints exist:

- require explicit `base_url`, or
- reject region-only remote configuration.

When real endpoints exist, confirm ownership and TLS deployment before enabling automatic mapping.

---

# Decision S-06 — Secrets never enter logs/evidence by default

Extend the current structured logger's secret-blocking discipline to every future credential:

- control-plane API keys;
- agent provider keys;
- MCP auth tokens;
- database credentials;
- webhook secrets;
- tenant integration secrets.

Tests should include representative secret field names and nested structures.

---

# Decision S-07 — Tenant and agent identity included in cache keys

Every cache containing data influenced by tenant/agent context must key on all relevant identity inputs.

This is critical for:

- prompt/context caches;
- capability profiles;
- result caches;
- contract caches where tenant-specific;
- future adapter caches.

A missing identity component is a cross-tenant contamination bug.

---

# Decision S-08 — Treat all agent output as hostile until normalized and validated

Per-agent adapters are security boundaries.

Required adapter sequence:

```text
raw agent response
→ structural/schema validation
→ sanitization
→ canonical normalization
→ CONGINE deterministic validation
```

Do not trust output because of provider identity or model reputation.

Malformed envelopes should be rejected rather than coerced into plausible values.

---

# Decision S-09 — Separate credentials per tenant/agent

Future agent integrations should have:

- tenant-scoped provider credentials;
- agent/provider-specific secret references;
- least privilege;
- rotation support;
- no shared mutable context across agents;
- rate limiting to reduce denial-of-wallet risk.

---

# Decision S-10 — Dependency and supply-chain controls become release gates

Minimum future controls:

- pinned/locked dependencies;
- `pip-audit` or equivalent vulnerability scan;
- SBOM generation for releases;
- dependency review on changes;
- Ruff security rule set and bugbear/async rules where useful;
- review native-extension dependencies separately.

For self-hosted/open-source model adapters, the dependency surface is expected to grow; keep those integrations isolated/optional where possible.

---

# Decision S-11 — Evidence read-back is an injection boundary

Any historical text reintroduced into an agent prompt must be treated as untrusted even if it originally came from an internal workflow.

Prefer structured deterministic summaries.

If free text is included:

- sanitize/escape;
- scope to tenant/project;
- minimize content;
- never allow stored text to override system/control instructions.

---

# Decision S-12 — Production support matrix must be explicit

Maintain a machine-readable/support document declaring:

- supported Python versions;
- supported production OSes;
- tested database/event-store modes;
- tested agent integrations;
- feature maturity.

CI should fail if a claimed supported target is not actually tested for a release.
