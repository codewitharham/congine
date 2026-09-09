"""Lifecycle & observability seams (Layer 1).

Small, composable protocols for the two cross-cutting concerns every stateful
concrete shares: **being torn down** and **reporting its own state**. They exist
because :class:`~congine_core.adapters.dependency_injection.ServiceContainer`
calls methods on its components that the functional ports never declared —
``close()`` calls ``stop()``/``shutdown()``, and ``health()`` reads counters —
so an implementation that faithfully satisfied, say, ``IEventBus`` (one method,
``publish``) would raise ``AttributeError`` the first time the container was torn
down (audit F-15 / Q8).

Keeping them separate rather than folding them into each functional port means a
port still describes **one job**: ``ISchemaStorage`` is about caching schemas,
``IEventBus`` is about publishing events. Lifecycle is composed in, not mixed in.

The composition is explicit — :class:`ISchemaStorage` and
:class:`IValidationRunner` inherit the relevant protocol below, and
:class:`IEventBus` declares a widened ``stop(drain=...)`` of its own because its
teardown takes an argument.

Both protocols are ``@runtime_checkable``, so conformance stays structural: a
plain object with the right methods satisfies them without importing anything.
"""

from __future__ import annotations

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class IStoppable(Protocol):
    """A component the container tears down in :meth:`ServiceContainer.close`.

    Implementations must guarantee that :meth:`stop`:

    - is **idempotent** — it is called from explicit ``close()``, from
      ``__exit__``, from ``atexit`` hooks, and from a ``weakref.finalize``
      running on an arbitrary thread during garbage collection;
    - **never raises** — teardown runs inside exception-suppressing contexts and
      a raise from a finalizer is unroutable;
    - is **bounded** — it may join a worker thread, but must do so with a
      timeout rather than waiting indefinitely on a remote peer.
    """

    def stop(self) -> None:
        """Release this component's threads and handles. Idempotent."""
        ...


@runtime_checkable
class IObservable(Protocol):
    """A component that can describe its own runtime state.

    :meth:`health` is polled by operators and must therefore be cheap and
    non-blocking — a snapshot read under a short-lived lock at most, never I/O.
    It must not raise, and it must return a flat mapping of JSON-serialisable
    values so it can be embedded directly in a health endpoint.
    """

    def health(self) -> Dict[str, Any]:
        """Return a flat, JSON-safe mapping of metric name to current value."""
        ...


__all__ = ["IStoppable", "IObservable"]
