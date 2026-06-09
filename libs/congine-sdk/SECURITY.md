# Security policy — `congine-sdk`

## Supported versions

| Version | Supported |
| ------- | --------- |
| `0.x`   | ✅ (current Phase 0) |
| `< 0.1` | ❌ pre-release; do not deploy |

The SDK is pre-1.0 and on a fast iteration cadence; security fixes are released
in patch versions and announced in [`CHANGELOG.md`](./CHANGELOG.md).

## Reporting a vulnerability

**Please do not open a public GitHub issue.** Send disclosure to
`security@congine.io` with:

- A description of the issue and its impact.
- Steps to reproduce (or a proof-of-concept payload / patch).
- Your name and affiliation (for credit, if you want it).

We commit to:

| Step                | SLA               |
| ------------------- | ----------------- |
| Initial acknowledgement | within 2 business days |
| Triage + severity assessment | within 5 business days |
| Coordinated disclosure date | within 90 days for critical findings |

We follow responsible-disclosure norms: please give us time to patch before
publishing details. We are happy to credit researchers in the changelog
release notes.

## Scope

### In-scope

- **Validation engine integrity** — rule-engine logic, schema cache poisoning,
  bypasses, ReDoS, JSON Schema injection.
- **Snapshot integrity & isolation** — symlink attacks, snapshot poisoning,
  cross-tenant snapshot collision, predictable path attacks.
- **Transport security** — credential leakage over cleartext, header injection,
  TLS verification bypasses.
- **Failure-mode safety** — fail-mode escalation bypasses, telemetry-before-raise
  ordering violations, log-redaction bypasses.
- **Multi-tenant boundary enforcement** — any cross-tenant data leakage in
  cache, snapshot, telemetry, or logs.
- **Denial of service via control-plane interactions** — anything that allows
  a malicious or compromised control plane to stall, crash, or memory-bomb
  the host application beyond the documented bounded-executor capacity.

### Out-of-scope

- **Downstream LLM provider security** — OpenAI / Anthropic / Ollama API
  guarantees, prompt-injection from the LLM provider, etc.
- **Bring-your-own-model (BYOM) code** — any healing-loop adapter the host
  application supplies; the SDK only owns the validation / orchestration
  seams.
- **Host application logic** — bugs in caller code outside the SDK surface.
- **Self-DoS via misconfiguration** — e.g. setting `validation_max_workers=1`
  and then issuing 1k concurrent guards.
- **Plaintext development credentials** — credentials placed in a checked-in
  `.env` are the operator's responsibility; the SDK warns loudly when
  `allow_cleartext=true` is in effect.

## Hardened defaults reference

These defaults are part of the SDK's stated security posture; any change is
treated as a breaking security change:

- `require_https = True` — non-local URLs must be HTTPS unless
  `CONGINE_ALLOW_CLEARTEXT=true` is explicitly set.
- `is_local_base_url()` exempts exact loopback hosts only (`localhost`, `127.0.0.1`,
  `::1`, `0.0.0.0`) via parsed hostname — substring false positives rejected.
- Snapshot paths are scoped per `(base_url, project_id, tenant_id)` SHA-256
  hash; symlinks and non-owner-owned files are refused on load.
- `google-re2` is a **required** core dependency; pattern length capped at 1000
  chars; value length at 50 000 chars (defense-in-depth).
- Semantic validation: `semantic_format_checking=false` by default;
  `semantic_max_breaches=100` cap on `iter_errors`.
- `deployment_mode=multi_tenant` forbids `ServiceContainer.get_default()` —
  explicit per-tenant containers required.
- Non-local deployments auto-enable log redaction; `api_key`, `payload`, and
  `breach_details` keys are unconditionally blocklisted from logs.
- `CircuitBreaker` defaults: 5 failures → OPEN, 30 s cooldown → HALF_OPEN.
- API key and tenant headers are never logged: API key transit is HTTPS-only
  when defaults are kept; logs are gated through a per-record allowlist when
  `log_safe_fields` is configured.
