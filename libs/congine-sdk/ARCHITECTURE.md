# CONGINE SDK — Architecture & Layering Rules

The SDK is a strict 5-layer Clean/Hexagonal design. Dependencies point **inward
only**; no inner layer imports a concrete from an outer layer.

```
L5 adapters/        framework entry points (ServiceContainer, @congine_guard, LangChain)
L4 infrastructure/  concrete, side-effecting impls (cache, http, queue, logger, timer, drift)
L3 usecases/        stateless orchestration (validate, sync)
L2 domain/          pure logic + immutable models (RuleEngine, validators, models)
L1 repositories/    typing.Protocol seams (the dependency-inversion boundary)
L0 (root)           config.py, exceptions.py — imported by all, depend on none
```

## Protocol-placement rule (resolves audit M6)

To remove the historical inconsistency between where abstractions lived:

1. **Every protocol that is injected across a layer boundary lives in
   `repositories/` (L1).** Examples: `ISchemaStorage`, `IContractRepository`,
   `IEventBus`, `ILogger`, `ISemanticValidator`.
2. **A strategy interface that is internal to the domain may live beside its
   default implementation in `domain/`.** The sole sanctioned exception is
   `IValidator` (in `domain/validator.py`), the in-domain validation-strategy
   seam that `LocalValidator` and `CompositeValidator` implement.
3. An L1 protocol **may reference an L2 value object** (e.g. `BreachDetail`) in
   its signatures — that is an inward reference and is allowed. Prefer a
   `TYPE_CHECKING` import to keep L1 import-light.

## Lifecycle & resourcing rules

- `@congine_guard` with no explicit `container=` resolves the **process-wide
  singleton** `ServiceContainer.get_default()` lazily at call time. Never builds
  a container per decorated function.
- Production code should construct one container, call `bootstrap()` (or
  `await bootstrap_async()` inside an event loop), share it, and `close()` it on
  shutdown.
- Background daemons (cache sweeper, telemetry drain, sync worker) and the
  bounded validation pool are owned by the container and released by `close()`.

## Hot-path guarantees & their guards

- **Latency / no exhaustion:** validation runs on a `BoundedValidationExecutor`
  (bounded queue + load shedding), so a burst of slow/zombie validations sheds
  rather than unbounded-queueing.
- **No event-loop stalls:** the async guard offloads validation off the loop.
- **No ReDoS:** schema-supplied regex patterns and values are length-bounded,
  compiled-and-cached, and use a linear-time engine (`re2`) when installed.
- **Tenant isolation on disk:** snapshots are per-tenant/project, app-owned, and
  symlink/owner-checked.
