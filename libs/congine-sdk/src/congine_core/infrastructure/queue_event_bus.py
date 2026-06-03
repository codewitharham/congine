"""Queue-based event bus (Layer 4).

:class:`QueueEventBus` implements
:class:`congine_core.repositories.event_bus.IEventBus`. Publishing is
fire-and-forget: events are enqueued without blocking and drained by a daemon
worker thread that ships them to the control-plane telemetry endpoint. Under
back-pressure (full queue) events are dropped silently (graceful degradation),
so telemetry can never stall the validation hot path.

Shipping uses a synchronous :class:`httpx.Client` (the worker is a plain
thread, so there is no event loop to await on). Transient HTTP failures retry
with exponential backoff; a chunk that still fails after ``max_retries`` is
dropped. The worker is a daemon — it never blocks interpreter exit — but an
:mod:`atexit` hook flushes any remaining events first.
"""

from __future__ import annotations

import atexit
import queue
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import httpx

from congine_core.config import CongineConfig
from congine_core.repositories.logger import ILogger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.domain.models import TelemetryEvent

#: Default control-plane path for telemetry ingestion.
_TELEMETRY_PATH = "/api/v1/telemetry"


class QueueEventBus:
    """Fire-and-forget event publishing via a background queue."""

    def __init__(
        self,
        config: Optional[CongineConfig] = None,
        logger: Optional[ILogger] = None,
        max_queue_size: int = 10_000,
        batch_size: int = 100,
        max_retries: int = 4,
        backoff_base: float = 0.5,
        backoff_max: float = 8.0,
        client_factory: Optional[Callable[[], httpx.Client]] = None,
        start_worker: bool = True,
    ) -> None:
        """Args:
        config: Runtime configuration providing the telemetry ``base_url`` and
            isolation headers. When ``None`` shipping is disabled and the worker
            merely drains-and-observes (used in tests / offline mode).
        logger: Optional structured logger for observability.
        max_queue_size: Maximum buffered events before new ones are dropped.
        batch_size: Maximum events shipped in a single POST.
        max_retries: Retry attempts per chunk before it is dropped.
        backoff_base: Initial backoff delay (seconds); doubles each retry.
        backoff_max: Cap (seconds) on the exponential backoff delay.
        client_factory: Factory returning an :class:`httpx.Client`; injectable
            for tests. Defaults to a 10s-timeout client.
        start_worker: When ``True`` (default) start the daemon drain worker and
            register the atexit flush; pass ``False`` for deterministic tests.
        """
        self._queue: "queue.Queue[TelemetryEvent]" = queue.Queue(maxsize=max_queue_size)
        self._config = config
        self._logger = logger
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self._client_factory = client_factory or (lambda: httpx.Client(timeout=10.0))
        self._stop_event = threading.Event()
        self._daemon: Optional[threading.Thread] = None

        if start_worker:
            self._daemon = threading.Thread(
                target=self._drain_loop,
                name="congine_event_bus",
                daemon=True,
            )
            self._daemon.start()
            atexit.register(self._drain_on_exit)

    # ------------------------------------------------------------------ #
    # Public API (IEventBus)
    # ------------------------------------------------------------------ #
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

    def stop(self, drain: bool = True) -> None:
        """Stop the drain worker, optionally flushing remaining events.

        Args:
            drain: When ``True`` ship whatever is still queued before stopping.
        """
        self._stop_event.set()
        if drain:
            self._flush_remaining()
        daemon = self._daemon
        if daemon is not None and daemon.is_alive():
            daemon.join(timeout=2.0)

    # ------------------------------------------------------------------ #
    # Background worker
    # ------------------------------------------------------------------ #
    def _drain_loop(self) -> None:
        """Daemon worker: batch events and ship them until asked to stop."""
        while not self._stop_event.is_set():
            batch = self._collect_batch()
            if batch:
                self._ship(batch)

    def _collect_batch(self) -> List["TelemetryEvent"]:
        """Block up to 1s for one event, then greedily drain up to a batch."""
        batch: List["TelemetryEvent"] = []
        try:
            batch.append(self._queue.get(timeout=1.0))
        except queue.Empty:
            return batch
        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _drain_on_exit(self) -> None:
        """atexit hook: best-effort flush of queued events before shutdown."""
        self._stop_event.set()
        self._flush_remaining()

    def _flush_remaining(self) -> None:
        """Ship every event currently in the queue (best-effort, bounded)."""
        while True:
            batch: List["TelemetryEvent"] = []
            while len(batch) < self._batch_size:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break
            if not batch:
                return
            self._ship(batch)

    # ------------------------------------------------------------------ #
    # Shipping
    # ------------------------------------------------------------------ #
    def _ship(self, batch: List["TelemetryEvent"]) -> bool:
        """Ship *batch* to the telemetry endpoint with exponential backoff.

        Returns ``True`` on a successful POST. A batch that still fails after
        ``max_retries`` attempts is dropped (returns ``False``) — telemetry is
        fire-and-forget and must never raise to the host.
        """
        if self._config is None:
            # No control plane configured: drain-and-observe only.
            if self._logger:
                self._logger.debug("Telemetry drained", count=len(batch))
            return True

        url = f"{self._config.base_url}{_TELEMETRY_PATH}"
        headers = {
            "X-API-Key": self._config.api_key or "",
            "X-Project-ID": self._config.project_id or "",
            "X-Tenant-ID": self._config.tenant_id or "",
        }
        payload = {"events": [self._serialize(e) for e in batch]}

        delay = self._backoff_base
        for attempt in range(1, self._max_retries + 1):
            try:
                with self._client_factory() as client:
                    response = client.post(url, json=payload, headers=headers)
                    response.raise_for_status()
                if self._logger:
                    self._logger.debug(
                        "Telemetry shipped",
                        count=len(batch),
                        attempt=attempt,
                    )
                return True
            except httpx.HTTPError as exc:
                if self._logger:
                    self._logger.warning(
                        "Telemetry ship failed",
                        attempt=attempt,
                        max_retries=self._max_retries,
                        error=str(exc),
                    )
                if attempt >= self._max_retries:
                    if self._logger:
                        self._logger.error(
                            "Telemetry chunk dropped after retries",
                            count=len(batch),
                        )
                    return False
                # Interruptible backoff so stop() wakes us promptly.
                if self._stop_event.wait(delay):
                    return False
                delay = min(delay * 2, self._backoff_max)
        return False

    @staticmethod
    def _serialize(event: "TelemetryEvent") -> Dict[str, Any]:
        """Serialize a :class:`TelemetryEvent` to a JSON-ready mapping."""
        created_at = getattr(event, "created_at", None)
        if hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        return {
            "contract_id": getattr(event, "contract_id", None),
            "contract_version": getattr(event, "contract_version", None),
            "status": getattr(event, "status", None),
            "duration_ms": getattr(event, "duration_ms", None),
            "breach_details": getattr(event, "breach_details", None),
            "created_at": created_at,
        }
