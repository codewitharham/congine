"""No-op event bus (Layer 4).

Standalone / offline drop-in for :class:`QueueEventBus` that satisfies
:class:`congine_core.ports.event_bus.IEventBus` while doing nothing: it starts no
drain thread, opens no HTTP client, and performs no network I/O. The container
selects it when ``telemetry_enabled`` is ``False`` so air-gapped deployments and
test suites incur zero telemetry overhead and leave no trailing background daemon
to join at shutdown.

It additionally implements the small observability/lifecycle surface the
:class:`ServiceContainer` calls on its bus (``queue_depth``, ``dropped_total``,
``stop``) so ``health()`` and ``close()`` treat it identically to the real bus.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.domain.models import TelemetryEvent


class NoOpEventBus:
    """Discard every published event; no threads, no sockets, no buffering."""

    def publish(self, event: "TelemetryEvent") -> None:
        """Drop *event* on the floor — telemetry is disabled."""
        return None

    def queue_depth(self) -> int:
        """Always ``0``: nothing is ever buffered."""
        return 0

    def dropped_total(self) -> int:
        """Always ``0``: events are intentionally discarded, not lost under load."""
        return 0

    def stop(self, drain: bool = True) -> None:
        """No-op teardown hook (kept for container ``close()`` symmetry)."""
        return None
