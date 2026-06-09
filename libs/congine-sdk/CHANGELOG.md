# Changelog

All notable changes to `congine-sdk` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Security — Phase 0 Lockdown

- **FIX-01:** `is_local_base_url()` now parses hostname exactly (no substring bypass).
- **FIX-02:** `google-re2` promoted to required core dependency; linear-time regex always on.
- **FIX-03:** Semantic validation bounded (`semantic_max_breaches`); format checking off by default.
- **FIX-04:** PII sanitization for breach messages in telemetry and logs; `ValidationResult.degraded_reason`.
- **FIX-05:** `deployment_mode=multi_tenant` disables `get_default()`; `ServiceContainer.for_tenant()` added.
- **FIX-06:** Input bounds (`max_payload_bytes`, `max_schema_bytes`, `max_contract_files`, etc.).
- **FIX-07:** LangChain handler uses shared container; per-run results; bounded stream buffers.
- **FIX-08:** Auto log redaction for non-local deployments; unconditional sensitive-key blocklist.
- **FIX-09:** Narrow exception handling in validation/sync/LangChain paths.
- **FIX-10:** `ICircuitBreaker` L1 port.
- **FIX-11:** HALF_OPEN single-probe semantics on circuit breaker.
- **FIX-13:** HTTP response size cap (`max_http_response_bytes`).
- **FIX-14:** `start_background_services` config flag; honest container lifecycle docs.

### Added

- **Apache-2.0 LICENSE** at the repo root — unblocks OSS distribution and
  commercial use; previously the codebase was implicitly all-rights-reserved.
- **`CircuitBreaker` (L4)** — process-local in-memory state machine (CLOSED →
  OPEN → HALF_OPEN → CLOSED) wrapping the control-plane boundary. `bootstrap()`
  consults the breaker and short-circuits to the on-disk snapshot when OPEN,
  so a cold/hung control plane can no longer stall application boot for 10 s
  per attempt (audit D-5).
- **`IValidationRunner` L1 port** — closes audit D-4. The validation runner
  was the only cross-layer collaborator without a `typing.Protocol` seam;
  `ValidateContractUseCase` is now typed against the port rather than a string
  literal `"ValidationTimer"`, and the `getattr` shim for `run_with_timeout_async`
  is removed.
- **`sync_once_single_flight` / `sync_once_single_flight_async`** —
  `bootstrap()` is now coordinated across N Gunicorn/Uvicorn workers via a
  per-scope `portalocker` lock. Only one worker per host issues the initial
  fetch; the rest fall through to the on-disk snapshot the lock-holder just
  wrote (audit D-7).
- **`load_snapshot_only`** — explicit fast-fail snapshot path used by
  `bootstrap` when the circuit breaker is OPEN.
- **`telemetry_dropped_total`** in `health()` — cumulative count of telemetry
  events lost to queue-full or after-retries drop (audit D-10). Closes the
  silent-telemetry-loss gap; operators now have a visible loss signal.
- **`breaker_state`** in `health()` — `"CLOSED" | "OPEN" | "HALF_OPEN"`.
- **`CongineConfig.allow_cleartext`** (`CONGINE_ALLOW_CLEARTEXT`) — explicit
  opt-out for non-prod / internal deployments that need to hit cleartext
  control planes. Defaults to `False`.
- **`CongineConfig.log_safe_fields`** (`CONGINE_LOG_SAFE_FIELDS`) — optional
  allowlist of structured-extra log keys; everything not in the allowlist is
  emitted as `"<redacted>"` (PII safety in multi-tenant log pipelines).
- **`CongineConfig.breaker_failure_threshold`** /
  **`CongineConfig.breaker_cooldown_seconds`** with `CONGINE_BREAKER_*`
  env vars.
- **`redos` extra** in `pyproject.toml` — declares `google-re2` as an
  installable optional dependency; closes the audit gap between
  `ARCHITECTURE.md`'s "re2 when installed" claim and the actual package
  metadata.
- **`FileContractRepository` (L4)** — reads contracts from a local directory
  (JSON, plus YAML when `PyYAML` is available). Enables the local-first /
  GitOps positioning; route to it via `CONGINE_CONTRACT_SOURCE=file`.
- **`SECURITY.md`** — responsible-disclosure policy with SLAs and a scope
  table.
- **`CHANGELOG.md`** (this file).
- Full **`README.md`** with install, quickstart, config reference table,
  architecture diagram, failure-mode table, observability table.
- **CI matrix** for Python 3.10–3.14 on the `lint`, `typecheck`, and `test`
  jobs — proves the declared `>=3.10` floor.
- **Project URLs and classifiers** in `pyproject.toml` for PyPI metadata.

### Changed

- **`validation_timeout_ms` default raised from 15 ms to 100 ms** — accommodates
  `CompositeValidator + jsonschema` semantic validation without false-positive
  timeouts under `FailMode.STRICT` (audit D-8).
- **`require_https` default flipped from `False` to `True`** — secure default.
  Loopback URLs are auto-exempt; for non-local cleartext deployments set
  `CONGINE_ALLOW_CLEARTEXT=true` (audit D-6).
- **`repositories/` renamed to `ports/`** — the directory held non-repository
  ports (`ILogger`, `IEventBus`); the new name matches the meaning before the
  public API ossifies (audit D-11). All internal imports updated.
- **`__version__` single-sourced** via `importlib.metadata.version("congine-sdk")`
  with a `"0.0.0+unknown"` fallback; eliminates the version-drift trap
  between `__init__.py` and `pyproject.toml` (audit §8.5).
- **`StructuredLogger`** gains a `log_safe_fields` constructor parameter and
  redacts non-allowlisted kwargs at emit time.
- **`BoundedValidationExecutor`** exposes `capacity` as a `@property` and
  implements `health()`, conforming to `IValidationRunner`.

### Removed

- **`ValidationTimer` public export** — removed from
  `congine_core.__init__` and `congine_core.infrastructure.__init__`. The
  class remains importable from `congine_core.infrastructure.timer` for
  legacy reference, but it now raises a `DeprecationWarning` on construction.
  Wiring it directly defeated the load-shedding and async-symmetric
  guarantees of `BoundedValidationExecutor` (audit D-3/D-11).
- **`*.egg-info/`** committed to the VCS — stale `requires.txt` would have
  reintroduced removed runtime dependencies on a wheel build.

### Fixed

- **`tests/adversarial/test_remediations.py:189`** — PEP-758 comma-separated
  `except OSError, NotImplementedError, AttributeError:` parses only on
  CPython 3.14+. Parenthesised so the suite collects on the declared
  `>=3.10` floor (audit D-1).
- **`evaluate_drift` no longer raises raw `ImportError`** when the `[stats]`
  extra is missing — wraps it as `CongineConfigurationError`, keeping the
  SDK's exception family contained (audit D-10).

### Security

- See **Changed → `require_https` default** above.
- See **Added → `log_safe_fields` allowlist** above.

---

## [0.1.0] — Initial Phase 0 baseline (pre-remediation)

The initial Phase 0 deliverable. The validation core is architecturally
strong — O(1) LFU cache, bounded/load-shedding executor symmetric across
sync+async, atomic snapshot writes with portalocker, ReDoS-safe regex,
telemetry-before-raise ordering — but several seams flagged in the
adversarial audit (`Phase0_congine_audit.md`) are addressed in the
Unreleased section above before the first public tag.
