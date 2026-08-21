"""Abstraction for event publishing (Layer 1).

Defines :class:`IEventBus`, a structural interface for fire-and-forget
publication of telemetry events. Implementations (Layer 4) process events on a
background worker and may drop events under back-pressure (graceful
degradation) so that publishing never blocks the validation hot path.

The event parameter is typed only under ``TYPE_CHECKING`` to keep Layer 1 free
of any runtime dependency on Layer 2 (the domain).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only, avoids upward import
    from congine_core.models import TelemetryEvent


@runtime_checkable
class IEventBus(Protocol):
    """Structural interface for fire-and-forget event publishing.

    Beyond :meth:`publish`, the container requires :meth:`stop` (teardown) and
    :meth:`queue_depth` (health). Both are declared here rather than left
    implicit: an implementation providing only ``publish`` used to satisfy this
    port on paper and then raise ``AttributeError`` the first time
    ``ServiceContainer.close()`` or ``health()`` ran (audit F-15 / Q8).

    :meth:`stop` cannot compose
    :class:`~congine_core.ports.lifecycle.IStoppable` directly because a bus
    teardown takes a ``drain`` flag; the obligations stated there
    (idempotent, never raises, bounded) apply unchanged.

    **Durability is an implementation choice, not a port change (audit Q9).**
    The default bus is deliberately fire-and-forget: events are dropped when the
    queue fills, when retries are exhausted, when the circuit breaker is open,
    and when the process dies. That is what keeps telemetry incapable of slowing
    down validation, and it is not going to change.

    A durable event log — the planned SQLite store that history queries and
    capability profiles read from — arrives as a **second implementation of this
    same port**, selected by configuration, never by making the default bus
    blocking. Such an implementation must satisfy the full surface above and must
    still keep :meth:`publish` non-blocking: enqueue on the caller's thread,
    write from its own worker, exactly as :class:`QueueEventBus` ships from one.
    """

    def publish(self, event: "TelemetryEvent") -> None:
        """Publish *event* without blocking the caller.

        Must never raise and must never block: this runs on the validation hot
        path. Implementations may drop the event silently if their buffer is
        saturated — telemetry loss is explicitly preferred to added latency.

        Args:
            event: The telemetry event to publish.
        """
        ...

    def queue_depth(self) -> int:
        """Return the number of events currently buffered.

        Reported by :meth:`ServiceContainer.health` as ``telemetry_queue_depth``.
        An implementation that does not buffer returns ``0``.
        """
        ...

    def stop(self, drain: bool = True) -> None:
        """Tear down the bus, optionally flushing what is still buffered.

        Args:
            drain: When ``True`` (explicit ``close()``), ship whatever remains
                before stopping. When ``False`` (deferred teardown from a
                finalizer), stop promptly — an unreachable control plane must
                not be able to stall garbage collection.
        """
        ...

    # Optional extension — deliberately NOT declared as a protocol method, because
    # a Protocol member is mandatory under ``runtime_checkable`` isinstance and
    # this one genuinely is not:
    #
    #     def dropped_total(self) -> int
    #
    # The container probes for it with ``getattr``/``callable`` and reports ``0``
    # when absent. Implement it if events can be lost — it is the only visible
    # signal that they were. ``QueueEventBus`` and ``NoOpEventBus`` both do.
