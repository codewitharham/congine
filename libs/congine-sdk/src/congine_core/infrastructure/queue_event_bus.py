"""Queue-based event bus (Layer 4).

:class:`QueueEventBus` implements
:class:`congine_core.repositories.event_bus.IEventBus`. Publishing is
fire-and-forget: events are enqueued without blocking and drained by a daemon
worker thread. Under back-pressure (full queue) events are dropped silently
(graceful degradation), so telemetry can never stall the validation hot path.
"""

from __future__ import annotations

import queue
import threading
from typing import TYPE_CHECKING, Optional

from congine_core.repositories.logger import ILogger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.domain.models import TelemetryEvent


class QueueEventBus:
    """Fire-and-forget event publishing via a background queue."""

    def __init__(
        self, logger: Optional[ILogger] = None, max_queue_size: int = 10_000
    ) -> None:
        """Args:
        logger: Optional structured logger for observability.
        max_queue_size: Maximum buffered events before new ones are dropped.
        """
        self._queue: "queue.Queue[TelemetryEvent]" = queue.Queue(maxsize=max_queue_size)
        self._logger = logger
        self._daemon = threading.Thread(
            target=self._drain_loop,
            name="congine_event_bus",
            daemon=True,
        )
        self._daemon.start()

    def publish(self, event: "TelemetryEvent") -> None:
        """Enqueue *event* without blocking; drop silently if the queue is full.

        Args:
            event: The telemetry event to publish.
        """
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            if self._logger:
                self._logger.warning(
                    "Event queue full, dropping event",
                    contract_id=getattr(event, "contract_id", None),
                )

    def _drain_loop(self) -> None:
        """Background worker: pull events and ship them to telemetry.

        Shipping to a telemetry endpoint is a later-phase concern; for Phase 0
        events are drained and observed via the logger so the queue cannot grow
        unbounded.
        """
        while True:
            try:
                event = self._queue.get(timeout=1.0)
                # Phase 0: drain + observe. Wiring to the control-plane
                # telemetry endpoint is handled in a later phase.
                if self._logger:
                    self._logger.debug(
                        "Event published",
                        contract_id=getattr(event, "contract_id", None),
                    )
            except queue.Empty:
                continue
            except Exception as exc:  # pragma: no cover - defensive
                if self._logger:
                    self._logger.error("Event drain error", error=str(exc))
