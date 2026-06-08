# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This file scopes to the `libs/congine-sdk/` Nx package (the published `congine-sdk` Python distribution). For workspace-wide Nx guidance see the repo-root `CLAUDE.md`.

## Build / lint / test commands

This package is an Nx project member. **Always run via Nx from the repo root** so workspace tooling resolves; never invoke `pytest` or `ruff` directly unless debugging a single test.

```bash
# Lint (ruff format --check + ruff check)
pnpm nx lint congine-sdk

# Full test suite (auto-installs --extra langchain --extra stats via uv)
pnpm nx test congine-sdk

# Run a single test or a single test file (bypasses Nx; assumes deps already synced)
uv run --package congine-sdk --extra langchain --extra stats \
    pytest libs/congine-sdk/tests/unit/test_cache.py -v

# Single test method
uv run --package congine-sdk --extra langchain --extra stats \
    pytest libs/congine-sdk/tests/test_circuit_breaker.py::test_trips_open_after_threshold -v
```

`uv` (Astral) is the Python package manager. The workspace is `[tool.uv].package = true` so `--package congine-sdk` is required when running anything via `uv` from the repo root.

## Critical invariant: `[tool.ruff].target-version = "py310"` (pyproject.toml)

This pin is load-bearing. The declared Python floor is 3.10, but `ruff format` on its default modern target will rewrite parenthesised `except (A, B):` clauses into PEP-758 unparenthesised `except A, B:` syntax, which is a **SyntaxError on Python 3.10–3.13** and silently breaks the test suite's collection on every supported interpreter except 3.14.

**If you see ruff format rewriting except tuples, do not commit it. The `target-version = "py310"` line is the guard.** Audit history: this regression already happened twice in `tests/adversarial/test_remediations.py:189`, `src/congine_core/infrastructure/http_contract_repository.py`, and `src/congine_core/adapters/langchain_handler.py`.

## Architecture (high-level — read this before editing across layers)

Strict hexagonal monolith, **6 tiers, dependencies flow inward only.** No L_n module ever imports a concrete from L_(n+1).

```
L5 adapters/        framework entry points (ServiceContainer, @congine_guard, LangChain)
L4 infrastructure/  concrete side-effecting impls (cache, http, queue, logger, executor,
                    drift, circuit_breaker, file_contract_repository, jsonschema)
L3 usecases/        stateless orchestration (validate, sync, single-flight boot, healing)
L2 domain/          pure logic + immutable models (RuleEngine, validators, models)
L1 ports/           typing.Protocol seams — IContractRepository, IEventBus, ILogger,
                    ISchemaStorage, ISemanticValidator, IValidationRunner
L0 (root)           config.py, exceptions.py — imported by all, depend on none
```

**Note:** `ARCHITECTURE.md` and `Phase0_congine_audit.md` still reference an L1 directory named `repositories/`. **It has been renamed to `ports/`** (since the directory holds non-repository ports — `ILogger`, `IEventBus`, `IValidationRunner`). Trust the source tree, not those two historical docs. Update them when you next edit them.

### Protocol-placement rule

- Every cross-layer collaborator must have an L1 `typing.Protocol` seam. There is exactly one sanctioned exception: `IValidator` lives in `domain/validator.py` (an in-domain strategy interface, not a cross-layer port).
- The validation-runner seam is `IValidationRunner` in `ports/validation_runner.py`. `ValidateContractUseCase` types its `timer` parameter against this port; the production implementation is `BoundedValidationExecutor`. **Never type L3 code against an L4 concrete.**

### Composition root and lifecycle

- `ServiceContainer.get_default()` (`adapters/dependency_injection.py:48-64`) is a process-wide, lazy, double-checked-locked singleton. `@congine_guard` with no explicit `container=` resolves it at call time.
- The container owns: cache sweeper thread, telemetry drain thread, sync worker thread, the bounded validation pool. All released by `container.close()`.
- `bootstrap()` (sync) raises `RuntimeError` if called inside a running event loop — use `bootstrap_async()` instead.
- `bootstrap()` routes through `SyncContractsUseCase.sync_once_single_flight()` which uses per-scope `portalocker` to ensure only one worker per host issues the initial control-plane fetch (D-7 mitigation).

## Hot-path invariants (do not break these without explicit founder/architect sign-off)

1. **Sync and async validation paths converge** on `BoundedValidationExecutor._acquire_and_submit`. The async path is NOT a separate code path — it offloads to the same bounded, load-shedding pool via `run_with_timeout_async`. **Do not introduce a `loop.run_in_executor(thread_pool, ...)` shortcut anywhere** — that bypass was the H1/H2 audit defect and is permanently closed.
2. **Telemetry is published BEFORE fail-mode escalation.** `ValidateContractUseCase._finalize` (`usecases/validate_contract_usecase.py:189-202`) publishes the `TelemetryEvent`, *then* applies the fail-mode. A STRICT raise must never lose the telemetry event. There is an adversarial test that pins this.
3. **`ValidationTimer` (`infrastructure/timer.py`) is deprecated and NOT publicly exported.** Its `__init__` raises a `DeprecationWarning`. Wire `BoundedValidationExecutor` as the `IValidationRunner` implementation. The only reason `ValidationTimer` is still importable from its direct module is legacy reference and the unit tests that exercise the deprecation signal.
4. **Snapshot path safety**: `HttpContractRepository.load_snapshot` refuses symlinks and non-owner-owned files; writes are tempfile + `os.replace` under a sibling `.lock` (`portalocker LOCK_EX | LOCK_NB`). The boot-coordination lock is a *separate file* (`boot_<scope>.lock`) from the snapshot lock (`<snapshot>.lock`) so the two systems do not contend.
5. **Secure-by-default config**: `require_https=True` (was `False` pre-remediation). Non-local cleartext URLs raise `CongineConfigurationError` from `CongineConfig.validate()` unless `allow_cleartext=True` is *explicitly* set. Loopback URLs are auto-exempt via `is_local_base_url()`.
6. **ReDoS guards**: schema-supplied regex patterns and values are length-bounded (`_MAX_PATTERN_LENGTH = 1000`, `_MAX_REGEX_VALUE_LENGTH = 50_000`), compiled-and-cached via `functools.lru_cache(maxsize=512)`, fail-closed on `re.error`. The `[redos]` extra (`google-re2>=1.0`) switches to a linear-time engine when present.

## Test layout

- `tests/unit/` — per-component unit tests (`test_cache.py`, `test_validator.py`, `test_event_bus.py`, `test_timer.py`, …).
- `tests/adversarial/` — regression tests for specific audit findings (`test_remediations.py`, `test_bounded_executor.py`, `test_redos.py`). New audit-style adversarial cases belong here.
- `tests/integration/` — end-to-end paths (`test_end_to_end.py`).
- `tests/test_*.py` (root) — recent feature suites: `test_circuit_breaker.py`, `test_validation_runner_port.py`, `test_single_flight_boot.py`, `test_file_contract_repository.py`. New feature tests for L4 components belong here.
- `tests/conftest.py` — fixtures + structural-typed fakes (`FakeLogger`, `FakeEventBus`, `FakeSchemaStorage`, `ImmediateTimer`, `FakeContractRepository`). Reuse these; do not duplicate.

## Adding a new L4 implementation

Common task. The pattern (e.g., adding an `OTelEventBus` to replace `QueueEventBus`):

1. Implement the existing L1 port (`ports/event_bus.py::IEventBus` — `runtime_checkable Protocol`).
2. Place the concrete in `infrastructure/<your_class>.py`.
3. Export it from `infrastructure/__init__.py` (`__all__`).
4. If publicly stable, also export from `src/congine_core/__init__.py` (`__all__`).
5. Add a structural conformance test using `isinstance(instance, IPort)`.
6. Wire optional selection in `adapters/dependency_injection.py` if config-driven.

## Configuration plane

`CongineConfig` (`config.py`) is a frozen dataclass. Every field has a `CONGINE_*` env var binding in `from_env()`. **When adding a config field:**

- Add to the dataclass + group comment.
- Add to `from_env()` with appropriate parser (`_env_bool`, `_env_int`, `_env_float`, `_env_frozenset`).
- Update the configuration table in `README.md`.
- Update `phase0-congine-postSessionAudit.md` if the field changes a hardened default (e.g. flipping a security default).

## Strategy documents at repo root

Five Phase-0 strategy documents are authoritative for design decisions:

| File | When to consult |
|---|---|
| `phase0-congine-newAudit.md` | Pre-remediation adversarial audit (immutable baseline) |
| `phase0-congine-postSessionAudit.md` | Post-remediation engineering audit; lists current invariants |
| `phase0-congine-productionShippingRoadmap.md` | Release-engineering + commercial roadmap |
| `phase0-congine-sdkFirstBlueprint.md` | The "ship SDK before cloud" strategy + monetisation |
| `phase0-congine-modelTrainingStrategy.md` | Two-layer classifier+frontier model architecture + training plan |

The latter two contain "Decision Lockbox" sections — commitments that should not be relitigated in PRs without explicit founder sign-off.

## What this package is NOT

- Not a code-generation product. Year-1 scope is JSON-output validation + healing only (see `phase0-congine-modelTrainingStrategy.md` Part II).
- Not a wrapper around Claude / OpenAI. The hexagonal architecture is the moat; treat outer-layer concretes as swappable.
- Not multi-language. Python only for Phase 0.
- Not coupled to a Congine cloud. The SDK works fully standalone via `CONGINE_CONTRACT_SOURCE=file` (local-first / GitOps).
