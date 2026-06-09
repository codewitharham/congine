# Congine SDK — Phase 0 Production Lockdown

This document records the remediation backlog executed to elevate `congine-sdk`
from ~72% Phase 0 audit readiness to production-grade enterprise posture.

## Status: COMPLETE

All FIX-01 through FIX-14 items from the adversarial audit have been implemented.
See [`CHANGELOG.md`](./CHANGELOG.md) under **Security — Phase 0 Lockdown** for the
full change list.

## Verification

From `congine_workspace` root:

```bash
uv run --package congine-sdk --extra langchain --extra stats pytest libs/congine-sdk/tests
uv run --package congine-sdk ruff format --check libs/congine-sdk
uv run --package congine-sdk ruff check libs/congine-sdk
```

Last verified: **251 passed**, ruff clean.

## Key files added/changed

| Area        | Files                                                             |
| ----------- | ----------------------------------------------------------------- |
| L0 security | `security_limits.py`, `pii_sanitize.py`                           |
| L1 ports    | `ports/circuit_breaker.py` (`ICircuitBreaker`)                    |
| Config      | `config.py` — host parsing, bounds, deployment mode               |
| Domain      | `validator.py` — required `google-re2`                            |
| Validation  | `validate_contract_usecase.py`, `jsonschema_validator.py`         |
| DI          | `dependency_injection.py` — `for_tenant()`, multi-tenant guard    |
| Adapters    | `langchain_handler.py` — shared container, bounded buffers        |
| Tests       | `tests/adversarial/test_*.py` (host bypass, PII, bounds, tenants) |

## For future Claude Code sessions

When extending the SDK, preserve:

1. Hexagonal layering (L3 → L1 ports only)
2. Hot-path guarantees in `CLAUDE.md` (bounded executor, breaker, ReDoS, PII)
3. Adversarial test coverage for any security-sensitive change
