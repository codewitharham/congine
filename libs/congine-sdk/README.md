# congine-sdk

**Phase 0 — Core validation engine for AMCE (LLM output governance).**

`congine-sdk` is a hot-path Python SDK that wraps an LLM call with a contract: a payload that does not match the contract's schema is degraded, blocked, or healed before it reaches your application logic. The validation engine is built for sub-100 ms latency in a multi-tenant production deployment — bounded concurrency, load-shedding, an O(1) LFU schema cache, atomic per-tenant disk snapshots, and a circuit breaker on the control-plane boundary.

The SDK is structured as a strict **hexagonal monolith** (L0 kernel → L5 adapters); the public surface is documented below.

---

## Installation

```bash
pip install congine-sdk
```

### Optional extras

| Extra        | Purpose                                                            | Install                                  |
| ------------ | ------------------------------------------------------------------ | ---------------------------------------- |
| `langchain`  | LangChain `BaseCallbackHandler` integration                        | `pip install 'congine-sdk[langchain]'`   |
| `stats`      | KS-test drift detection (requires NumPy)                           | `pip install 'congine-sdk[stats]'`       |
| `redos`      | Linear-time regex backend (`re2`) for the rule engine              | `pip install 'congine-sdk[redos]'`       |
| `dev`        | Test / lint toolchain (pytest, pytest-asyncio, pytest-cov, ruff)   | `pip install 'congine-sdk[dev]'`         |

`congine-sdk[redos]` is recommended for any deployment that ingests adversarial user input — pattern length caps are still applied by default, but `re2` provides hard linear-time guarantees.

---

## 30-second quickstart

```python
import os
from congine_core import congine_guard, ServiceContainer

# 1. Configure via environment
os.environ["CONGINE_BASE_URL"] = "https://api.congine.io"
os.environ["CONGINE_API_KEY"] = "..."
os.environ["CONGINE_PROJECT_ID"] = "..."
os.environ["CONGINE_TENANT_ID"] = "..."

# 2. Prime the schema cache once at startup
ServiceContainer.get_default().bootstrap()

# 3. Guard your LLM call
@congine_guard(contract_id="customer.support.reply", contract_version="1.0")
def reply(prompt: str) -> dict:
    # ... your LLM call here, returning a dict to validate against the contract
    ...
```

For an async hot path:

```python
@congine_guard(contract_id="customer.support.reply", contract_version="1.0")
async def reply(prompt: str) -> dict:
    ...
```

The async path goes through the **same bounded, load-shedding executor** as the sync path — there is no `run_in_executor` bypass.

---

## Configuration reference

Every field of `CongineConfig` is settable via `CONGINE_*` environment variables and read by `CongineConfig.from_env()`.

| Field                         | Env var                                | Default     | Description                                                                              |
| ----------------------------- | -------------------------------------- | ----------- | ---------------------------------------------------------------------------------------- |
| `base_url`                    | `CONGINE_BASE_URL`                     | `http://localhost:8080` | Control-plane URL.                                                          |
| `api_key`                     | `CONGINE_API_KEY`                      | _required for non-local_ | API key.                                                                  |
| `project_id`                  | `CONGINE_PROJECT_ID`                   | _required for non-local_ | Project identifier.                                                       |
| `tenant_id`                   | `CONGINE_TENANT_ID`                    | _required for non-local_ | Tenant identifier (multi-tenant isolation).                               |
| `region`                      | `CONGINE_REGION`                       | `us`        | `us` \| `eu` \| `apac`.                                                                  |
| `validation_timeout_ms`       | `CONGINE_TIMEOUT_MS`                   | `100`       | Hard ceiling per validation. Pure rule-engine runs in <1ms; budget covers semantic.      |
| `fail_mode`                   | `CONGINE_FAIL_MODE`                    | `degrade`   | `strict` \| `degrade` \| `silent`. See **Failure modes**.                                |
| `cache_capacity`              | `CONGINE_CACHE_CAPACITY`               | `500`       | O(1) LFU cache max entries.                                                              |
| `cache_ttl_seconds`           | `CONGINE_CACHE_TTL`                    | `300`       | Default TTL per cached schema.                                                           |
| `sync_enabled`                | `CONGINE_SYNC_ENABLED`                 | `false`     | Start the periodic background sync worker on bootstrap.                                  |
| `sync_interval_seconds`       | `CONGINE_SYNC_INTERVAL`                | `300`       | Background sync cadence.                                                                 |
| `semantic_validation_enabled` | `CONGINE_SEMANTIC_VALIDATION`          | `false`     | Compose `jsonschema` validator on top of the rule engine.                                |
| `drift_threshold`             | `CONGINE_DRIFT_THRESHOLD`              | `0.1`       | KS-test p-value below which drift is flagged. Requires `[stats]`.                        |
| `drift_sample_limit`          | `CONGINE_DRIFT_SAMPLE_LIMIT`           | `500`       | Reference-window cap for the drift engine.                                               |
| `validation_max_workers`      | `CONGINE_VALIDATION_WORKERS`           | `10`        | Concurrent validation worker threads.                                                    |
| `validation_max_pending`      | `CONGINE_VALIDATION_PENDING`           | `10`        | Pending slots before load is shed. Capacity = workers + pending.                         |
| `snapshot_dir`                | `CONGINE_SNAPSHOT_DIR`                 | per-user OS-app dir | Per-user snapshot location (NOT world-shared `/tmp`).                            |
| `require_https`               | `CONGINE_REQUIRE_HTTPS`                | `true`      | Enforce HTTPS on non-local control planes. **Secure default**.                           |
| `allow_cleartext`             | `CONGINE_ALLOW_CLEARTEXT`              | `false`     | Explicit opt-out for dev / internal use. Emits a loud warning at boot.                   |
| `log_level`                   | `CONGINE_LOG_LEVEL`                    | `INFO`      | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR`.                                               |
| `log_safe_fields`             | `CONGINE_LOG_SAFE_FIELDS`              | _none_      | Comma-separated allowlist for structured-extra logging keys (PII safety).                |
| `breaker_failure_threshold`   | `CONGINE_BREAKER_FAILURE_THRESHOLD`    | `5`         | Consecutive failures before the circuit breaker trips OPEN.                              |
| `breaker_cooldown_seconds`    | `CONGINE_BREAKER_COOLDOWN_SECONDS`     | `30.0`      | Seconds the breaker stays OPEN before allowing a HALF_OPEN probe.                        |

---

## Failure modes

| Mode      | Behaviour on validation failure                                          | Use when                                  |
| --------- | ------------------------------------------------------------------------ | ----------------------------------------- |
| `strict`  | Raises `CongineValidationError`; telemetry is published **before** the raise. | Compliance-critical paths.                |
| `degrade` | Logs a warning, publishes telemetry, returns the (possibly invalid) result. | Default — gracefully degrades.            |
| `silent`  | Publishes telemetry, returns the result, **no error log**.               | Background passes or A/B-testing flows.   |

`SchemaCacheMissException` always raises (a cache miss is not a validation failure), regardless of `fail_mode`.

---

## Architecture

The SDK is a strict 6-tier hexagonal monolith — outer layers depend on inner ones, never the reverse:

| Layer | Path                                              | Purpose                                                          |
| ----- | ------------------------------------------------- | ---------------------------------------------------------------- |
| L0    | `congine_core.{config,exceptions}`                | Pure data, zero deps. Frozen `CongineConfig`, exception hierarchy. |
| L1    | `congine_core.ports`                              | `typing.Protocol` seams (`IContractRepository`, `IEventBus`, `ILogger`, `ISchemaStorage`, `ISemanticValidator`, `IValidationRunner`). |
| L2    | `congine_core.domain`                             | Pure business logic — `RuleEngine`, `LocalValidator`, `CompositeValidator`. |
| L3    | `congine_core.usecases`                           | Orchestration — `ValidateContractUseCase`, `SyncContractsUseCase`. |
| L4    | `congine_core.infrastructure`                     | Concrete implementations — `LFUCache`, `HttpContractRepository`, `QueueEventBus`, `BoundedValidationExecutor`, `CircuitBreaker`, ... |
| L5    | `congine_core.adapters`                           | Composition root + framework adapters — `ServiceContainer`, `congine_guard`, `CongineCallbackHandler` (langchain). |

The L1 directory was renamed `repositories/` → `ports/` — the seams are not all repository ports (`ILogger`, `IEventBus`, `IValidationRunner` are not).

---

## Observability (`health()` snapshot)

`ServiceContainer.health()` returns a dict with the following keys — suitable for `/healthz` and operator dashboards:

| Key                          | Meaning                                                                  |
| ---------------------------- | ------------------------------------------------------------------------ |
| `cache_entries`              | Live entries in the schema cache.                                        |
| `validation_in_flight`       | Outstanding work in the bounded executor (workers + pending).            |
| `validation_rejected_total`  | Cumulative load-shed (rejected) validations.                             |
| `telemetry_queue_depth`      | Approximate buffered telemetry events.                                   |
| `telemetry_dropped_total`    | Cumulative lost events (queue-full + ship-failure). Loss signal.         |
| `sync_running`               | Background sync worker state.                                            |
| `drift_reference_samples`    | Drift-engine reference-window depth (requires `[stats]`).                |
| `breaker_state`              | Circuit breaker state — `CLOSED` \| `OPEN` \| `HALF_OPEN`.               |

---

## Optional features

- **Drift detection** (`[stats]`): KS-test against a streaming reference window; `ServiceContainer.evaluate_drift(samples)` returns a `DriftResult` and publishes a `__drift__` telemetry event on detection. Raises `CongineConfigurationError` if NumPy is not installed.
- **Semantic validation** (set `CONGINE_SEMANTIC_VALIDATION=true`): composes a JSON Schema validator on top of the rule engine. Each violation becomes a `BreachDetail` with a dotted field path.
- **Local-first / GitOps contracts**: a `FileContractRepository` reads contracts from a local directory; set `CONGINE_CONTRACT_SOURCE=file` + `CONGINE_CONTRACTS_DIR=./contracts` to use it.
- **BYOM healing loop**: planned for Phase 1. The `validate → fail → heal → re-validate` flow is the primary enterprise differentiator (`IModelClient` L1 + `OllamaClient` / `OpenAICompatibleClient` L4 adapters — not yet shipped).

---

## Reliability guarantees

The SDK is engineered against four well-known failure modes:

1. **Pool exhaustion under burst load** — `BoundedValidationExecutor` enforces `capacity = max_workers + max_pending` and sheds load with `TimeoutError` rather than unbounded queueing. The same bound applies to async callers (no `run_in_executor` bypass).
2. **Control-plane stalls during boot** — `CircuitBreaker` short-circuits `bootstrap()` straight to the on-disk snapshot when the breaker is OPEN; boot returns in under 500 ms even against a hung registry.
3. **Multi-worker thundering herd** — `sync_once_single_flight` (used by `bootstrap`) uses a per-scope `portalocker` lock so only one worker per host issues the initial fetch.
4. **Snapshot poisoning** — snapshot paths are scoped per (`base_url`, `project_id`, `tenant_id`); writes are atomic (`tempfile + os.replace`) and inter-process serialized via a sibling `.lock` file; symlinks and non-owner-owned files are refused on load.

---

## Versioning

`congine-sdk` follows semver. `__version__` is single-sourced from the installed distribution's metadata (`importlib.metadata.version("congine-sdk")`).

---

## License

Apache-2.0. See [`LICENSE`](../../LICENSE) at the repo root and [`SECURITY.md`](./SECURITY.md) for the disclosure policy.
