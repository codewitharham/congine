# 04 — Core Architecture, Lifecycle & Configuration Hardening

## Goal

Strengthen the existing ports-and-adapters architecture so that interfaces are real runtime/static contracts, resources cannot leak through partial construction, and configuration mistakes fail visibly before they change deployment behavior.

---

# Decision A-01 — Keep the hexagonal architecture

## Formal rationale to record in an ADR

The hexagonal architecture exists to:

1. isolate deterministic domain judgment from infrastructure;
2. make infrastructure replaceable without changing policy semantics;
3. make the core independently testable;
4. allow MCP, CLI, persistence, history, and agent adapters to attach at the edges;
5. stop service/control-plane concerns from contaminating the verdict engine.

This rationale should be documented permanently rather than inferred from folder structure.

---

# Decision A-02 — Fix `IValidationRunner`/`health()` by using the port

## Problem

The executed minimal-port example showed an implementation could satisfy `IValidationRunner` yet crash `ServiceContainer.health()` because the container read concrete properties (`in_flight`, `rejected_total`) not declared by the port.

## Fix

Prefer:

```python
runner_health = self.validation_executor.health()
```

and merge the declared health payload.

Do not add redundant properties to the interface unless a real caller needs them independently.

## Acceptance criteria

- the GAP3 minimal runner works unchanged;
- `ServiceContainer.health()` depends only on port-declared surface;
- port conformance tests exist;
- D14 can be marked fully resolved.

---

# Decision A-03 — Restore mypy as a blocking CI gate

## Required work

- add mypy to the dev dependency set;
- add explicit mypy configuration;
- remove `|| true` from CI;
- run on the SDK source and tests as appropriate;
- review existing `# type: ignore` comments and require reasoned/targeted ignores.

## Why

The architecture uses structural `Protocol`s. Static conformance is part of the architecture, not optional style.

---

# Decision A-04 — Add runtime conformance checks at composition boundaries

Static typing does not protect dynamically supplied/third-party implementations.

At `ServiceContainer` construction/injection boundaries, verify runtime-checkable ports where feasible and fail with a clear configuration/composition error.

## Principle

Fail at construction:

```text
Invalid IEventBus implementation
```

not later at:

```text
AttributeError during close/health/validation
```

---

# Decision A-05 — Make composition root construction transactional

## Problem

Background resources may start before all configuration/dependencies have been successfully constructed. A later constructor failure can leave threads/resources alive without a returned container to close them.

## Target sequence

```text
1. parse + validate all configuration
2. construct passive/pure dependencies
3. construct resource-owning components without starting if possible
4. wire complete graph
5. start background services
6. arm final cleanup
```

If any step fails:

```text
close every resource already created
re-raise controlled construction/configuration error
```

## Done condition

Constructor failure leaves:

- no leaked threads;
- no leaked HTTP clients;
- no stale atexit registrations;
- no partially registered singleton.

---

# Decision A-06 — Validate configuration before starting resources

Move all predictable configuration errors earlier:

- invalid JSON Schema draft;
- invalid enum/mode;
- invalid path;
- inconsistent regional/base URL settings;
- invalid limits;
- malformed booleans;
- empty-but-present required values.

---

# Decision A-07 — Strict boolean parsing

Unknown boolean text should raise `CongineConfigurationError` rather than silently evaluate to false.

Accepted values should be explicitly documented and tested, e.g. exact normalized set such as:

```text
true/false
1/0
```

Do not add broad natural-language truthiness (`yes please`, etc.).

---

# Decision A-08 — Convert `contract_source` to a validated enum

Replace open string semantics with an enum such as:

```text
HTTP
FILE
```

Unknown value = configuration error.

This removes silent fallback where a typo can change network topology.

---

# Decision A-09 — Empty environment values have explicit semantics

For settings such as `CONGINE_LOCAL_CONTRACTS_DIR`:

```text
unset      → feature not selected
empty      → configuration error
non-empty  → validate and use
```

Do not treat `""` as a valid offline path.

---

# Decision A-10 — One source for shared defaults

Defaults such as validation timeout must not be duplicated across config/use-case constructors.

Centralize values in the appropriate shared-kernel/defaults module and test that all public construction paths agree.

---

# Decision A-11 — Explicit lifecycle API is primary; finalizers are fallback

Preferred usage should support deterministic ownership, e.g. context manager:

```python
with ServiceContainer(config) as container:
    ...
```

Potential async context manager should be considered only where actually needed.

Guarantees:

- `close()` idempotent;
- bounded;
- does not unexpectedly raise into host;
- documented use-after-close behavior.

---

# Decision A-12 — Unregister `atexit` callbacks on normal shutdown

Any resource registering an exit callback should remove it when explicitly stopped/closed.

Add lifecycle tests that create/destroy repeated instances and prove registrations do not accumulate.

---

# Decision A-13 — Fix telemetry shutdown using coordination, not exception swallowing alone

## Short-term

Ensure telemetry background thread cannot throw an uncaught exception into stderr during shutdown.

## Long-term correct sequence

```text
signal worker stop
→ wait bounded interval for worker acknowledgement/exit
→ close client after worker no longer uses it
```

Use broad outermost worker protection as a final safety net, but do not rely on `except Exception` as the entire lifecycle design.

---

# Decision A-14 — Remove `ValidationTimer` unless real compatibility requires it

If repository verification confirms it remains:

- deprecated;
- unexported;
- unreachable from the container;
- replaced by `BoundedValidationExecutor`;

then remove implementation and obsolete tests in a dedicated commit.

If an external compatibility reason exists, document it explicitly instead of keeping dead code silently.

---

# Decision A-15 — Keep the re-entrant inline path as an explicit exception for now

Do not add a watchdog solely to time an unusual re-entrant call until evidence shows this path creates real risk.

Instead:

- document the exception to the normal millisecond budget;
- instrument/count re-entrant executions;
- retain upstream input bounds;
- revisit if real usage shows meaningful incidence.
