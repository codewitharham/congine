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
    from congine_core.domain.models import TelemetryEvent


@runtime_checkable
class IEventBus(Protocol):
    """Structural interface for fire-and-forget event publishing."""

    def publish(self, event: "TelemetryEvent") -> None:
        """Publish *event* without blocking the caller.

        Args:
            event: The telemetry event to publish. Implementations may drop the
                event silently if their buffer is saturated.
        """
        ...
