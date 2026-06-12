# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`congine-sdk` is a Python library (`congine_core`) inside an **Nx + uv** monorepo
(`congine_workspace`). The workspace-root `CLAUDE.md` covers Nx conventions; this
file covers the SDK itself. It is the Phase 0 core validation engine for AMCE:
a hot-path guard that validates an LLM call's output against a contract schema
and degrades/blocks/heals before the payload reaches application logic.

## Commands

Run from the **workspace root** (`congine_workspace/`), not this directory. Targets
are defined in `project.json` and shell out to `uv`.

| Task | Nx                    | Direct uv                                                                                                                       |
| ---- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Test | `nx test congine-sdk` | `uv run --package congine-sdk --extra langchain --extra stats pytest libs/congine-sdk/tests`                                    |
| Lint | `nx lint congine-sdk` | `uv run --package congine-sdk ruff format --check libs/congine-sdk && uv run --package congine-sdk ruff check libs/congine-sdk` |

Single test / by name (append to the direct `pytest` command):

```bash
# one file
uv run --package congine-sdk --extra langchain --extra stats pytest libs/congine-sdk/tests/unit/test_guard.py
# one test
... pytest libs/congine-sdk/tests/unit/test_guard.py::test_name
# by keyword
... pytest libs/congine-sdk/tests -k drift
```

The `--extra langchain --extra stats` flags matter: those features are optional
deps (see below) and their tests are skipped/error without them. Prefix Nx with
the workspace package manager (e.g. `pnpm nx test congine-sdk`).

## Architecture — strict 6-tier hexagonal monolith

Dependencies point **inward only**; no inner layer imports a concrete from an
outer layer. (`README.md` and `ARCHITECTURE.md` are the authoritative specs.)

| Layer | Package                | Contents                                                                                                                                                                                   |
| ----- | ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| L0    | `config`, `exceptions` | Frozen `CongineConfig`, exception hierarchy. Imported by all, depend on none.                                                                                                              |
| L1    | `ports/`               | `typing.Protocol` seams: `IContractRepository`, `IEventBus`, `ILogger`, `ISchemaStorage`, `ISemanticValidator`, `IValidationRunner`, `ICircuitBreaker`.                                    |
| L2    | `domain/`              | Pure logic + immutable models: `RuleEngine`, `LocalValidator`, `CompositeValidator`, `BreachDetail`, `ValidationResult`. No I/O.                                                           |
| L3    | `usecases/`            | Stateless orchestration: `ValidateContractUseCase`, `SyncContractsUseCase`. Depends only on L1 ports.                                                                                      |
| L4    | `infrastructure/`      | Side-effecting impls: `LFUCache`, `HttpContractRepository`, `FileContractRepository`, `QueueEventBus`, `BoundedValidationExecutor`, `CircuitBreaker`, `KSDriftEngine`, `StructuredLogger`. |
| L5    | `adapters/`            | Composition root + framework entry points: `ServiceContainer`, `congine_guard`, `CongineCallbackHandler` (langchain).                                                                      |

Critical layering rules when adding/moving code:

- **Protocol placement.** Every protocol injected _across_ a layer boundary lives
  in `ports/` (L1). The sole exception is `IValidator` in `domain/validator.py` —
  an in-domain strategy seam that `LocalValidator`/`CompositeValidator` implement.
  An L1 protocol may reference an L2 value object (e.g. `BreachDetail`) — that is
  an inward reference; prefer a `TYPE_CHECKING` import to keep L1 import-light.
- **Wiring.** `ServiceContainer.__init__` is the _only_ place concretes are
  constructed. It builds bottom-up (infra → domain → usecases) and injects via
  constructors. No module-level globals; the one sanctioned global is the lazy
  process-wide singleton `ServiceContainer.get_default()`.
- **Thread every config knob through (avoid "dead-configurable").** When a
  concrete's `__init__` exposes a parameter that maps to a `CongineConfig` field,
  the container **must** pass it — e.g. `LFUCache(sweep_interval=…)`,
  `QueueEventBus(max_queue_size=…, batch_size=…, …)`,
  `JsonSchemaSemanticValidator(jsonschema_draft=…)`,
  `HttpContractRepository` reading `config.control_plane_http_timeout_seconds`. An
  `__init__` hook the container silently drops is a recurring bug class
  (a developer-facing knob that does nothing); `tests/unit/test_config_wiring.py`
  guards the env → `from_env()` → container → concrete path for each.
- `src/congine_core/__init__.py` is the stable public surface (`__all__`). Adding
  a public symbol means re-exporting it there.

## Entry points & lifecycle

- `@congine_guard(contract_id, version, mode=...)` wraps a function and validates
  its output. With no `container=`, it lazily resolves the process-wide singleton
  at call time (never one container per decoration). `mode` is `"envelope"`
  (default), `"output"`, or `"raise"`; `extractor=` maps non-dict outputs to the
  dict payload to validate.
- Production pattern: construct **one** container, `bootstrap()` (or
  `await bootstrap_async()` inside an event loop) to prime the schema cache,
  share it, `close()` on shutdown. The container owns all background daemons
  (cache sweeper, telemetry drain, sync worker) and the bounded validation pool.
- The async guard path goes through the **same** bounded, load-shedding executor
  (`execute_async`) as the sync path — no raw `run_in_executor` bypass.
- Config is environment-driven: every `CongineConfig` field maps to a `CONGINE_*`
  var read by `CongineConfig.from_env()`. `fail_mode` is `strict|degrade|silent`;
  in `strict`, telemetry is published **before** the raise.
- **Standalone / offline topology (two independent switches).**
  `CONGINE_LOCAL_CONTRACTS_DIR` binds a `FileContractRepository` to that directory
  and leaves the sync worker **unallocated** (`container.sync_worker is None` — the
  four worker call sites guard for `None`); `CONGINE_TELEMETRY_ENABLED=false` swaps
  `QueueEventBus` for `NoOpEventBus` (no drain thread, no network). Set both for a
  pure in-process validator with zero control-plane I/O (air-gapped / test runs).

## Hot-path guarantees (don't regress these)

These are the SDK's reason for existing — each has a dedicated guard and tests:

1. **Bounded latency / no pool exhaustion** — `BoundedValidationExecutor` caps
   `capacity = max_workers + max_pending` and sheds load with `TimeoutError`
   rather than queueing unboundedly (sync _and_ async).
2. **No control-plane stall on boot** — `CircuitBreaker` short-circuits
   `bootstrap()` to the on-disk snapshot when OPEN (5 failures → OPEN, 30 s cooldown).
3. **No thundering herd** — `sync_once_single_flight` uses a per-scope
   `portalocker` lock so one worker per host issues the initial fetch.
4. **Snapshot integrity** — paths are scoped per `(base_url, project_id, tenant_id)`
   SHA-256; writes are atomic (`tempfile + os.replace`); symlinks/non-owner files
   refused on load.
5. **No ReDoS** — schema-supplied patterns/values are length-capped (1000 / 50 000
   chars, fail-closed) and always use `google-re2` (required core dependency).
6. **Multi-tenant isolation** — `CONGINE_DEPLOYMENT_MODE=multi_tenant` disables
   `get_default()`; use `ServiceContainer.for_tenant()` or explicit `container=`.
7. **PII-safe telemetry** — breach messages are sanitized before publish; logs
   auto-redact on non-local URLs unless `CONGINE_LOG_REDACTION=off`.

`tests/adversarial/` exercises 1, 5, and remediations specifically. Treat changes
near these as security-sensitive (see `SECURITY.md` for in/out-of-scope).

## Optional extras (gated, never hard deps)

The core stays dependency-light (`httpx`, `jsonschema`, `portalocker`). Optional
features import lazily and raise/skip when their extra is absent:

- `[langchain]` → `CongineCallbackHandler` adapter.
- `[stats]` → `KSDriftEngine` drift detection (NumPy); raises
  `CongineConfigurationError` if NumPy missing.
- `[redos]` → backward-compatible alias (`google-re2` is already a core dep).
- `[dev]` → pytest + ruff toolchain.

## Conventions

- Tests use plain structural-typing fakes in `tests/conftest.py` (`FakeLogger`,
  `FakeEventBus`, `FakeSchemaStorage`, `ImmediateTimer`, `FakeContractRepository`)
  that satisfy L1 protocols **without** importing or subclassing them. Prefer these
  over mocks. `asyncio_mode = "auto"` — async tests need no marker.
- ruff `target-version = py310` is pinned to the supported floor; do not introduce
  3.11+ syntax. `from __future__ import annotations` is used throughout.
- Adding a `CongineConfig` field is a 4-touch change: the frozen dataclass field,
  the `from_env()` reader (`CONGINE_*`), the `ServiceContainer` wiring (per the
  Wiring rule above), and the **README config-reference table** — that table is the
  canonical, user-facing config doc and is easy to leave stale.
- Code comments reference audit IDs (e.g. `audit M5`, `H3`, `D-4`, `FIX-02`) from
  the workspace-root audit docs (`phase0-congine-newAudit.md`,
  `phase0-congine-postSessionAudit.md`) — preserve these when editing nearby code.
