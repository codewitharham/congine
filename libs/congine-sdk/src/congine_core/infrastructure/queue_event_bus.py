"""Queue-based event bus (Layer 4).

:class:`QueueEventBus` implements
:class:`congine_core.ports.event_bus.IEventBus`. Publishing is
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
import contextlib
import queue
import threading
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

import httpx

from congine_core.config import CongineConfig
from congine_core.exceptions import CongineLifecycleError
from congine_core.ports.logger import ILogger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.models import TelemetryEvent
    from congine_core.ports.circuit_breaker import ICircuitBreaker

#: Default control-plane path for telemetry ingestion.
_TELEMETRY_PATH = "/api/v1/telemetry"
_WORKER_JOIN_TIMEOUT_SECONDS = 2.0


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
        circuit_breaker: "Optional[ICircuitBreaker]" = None,
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
        self._client: Optional[httpx.Client] = None
        self._ship_lock = threading.RLock()
        self._stop_event = threading.Event()
        self._daemon: Optional[threading.Thread] = None
        self._lifecycle_lock = threading.Lock()
        self._closed = False
        self._shutdown_complete = threading.Event()
        self._drain_requested = False
        self._final_attempts: Optional[int] = None
        self._atexit_callback: Optional[Callable[[], None]] = None
        self._circuit_breaker = circuit_breaker
        # Cumulative count of telemetry events lost (audit D-10): queue-full on
        # publish + batch-drop after retries. Exposed via :meth:`dropped_total`
        # and surfaced in :meth:`ServiceContainer.health` so operators have a
        # visible loss signal under sustained back-pressure.
        self._dropped_total = 0
        self._dropped_lock = threading.Lock()

        if start_worker:
            self.start()

    # ------------------------------------------------------------------ #
    # Public API (IEventBus)
    # ------------------------------------------------------------------ #
    def publish(self, event: "TelemetryEvent") -> None:
        """Enqueue *event* without blocking; drop and count if the queue is full.

        Args:
            event: The telemetry event to publish.
        """
        with self._lifecycle_lock:
            accepting = not self._closed
            if accepting:
                try:
                    self._queue.put_nowait(event)
                    return
                except queue.Full:
                    pass
        if not accepting:
            message = "Event bus closed, dropping event"
        else:
            message = "Event queue full, dropping event"
        with self._dropped_lock:
            self._dropped_total += 1
            dropped = self._dropped_total
        if self._logger:
            self._logger.warning(
                message,
                contract_id=getattr(event, "contract_id", None),
                dropped_total=dropped,
            )

    def start(self) -> None:
        """Start the drain worker once; a stopped bus cannot restart."""
        with self._lifecycle_lock:
            if self._closed:
                raise CongineLifecycleError(
                    "QueueEventBus is closed and cannot accept new work"
                )
            if self._daemon is not None and self._daemon.is_alive():
                return
            self._stop_event.clear()
            daemon = threading.Thread(
                target=self._drain_loop,
                name="congine_event_bus",
                daemon=True,
            )
            callback = self._drain_on_exit
            atexit.register(callback)
            self._atexit_callback = callback
            self._daemon = daemon
            try:
                daemon.start()
            except BaseException:
                self._daemon = None
                self._atexit_callback = None
                with contextlib.suppress(Exception):
                    atexit.unregister(callback)
                raise

    @property
    def closed(self) -> bool:
        """Whether the bus has entered terminal shutdown."""
        with self._lifecycle_lock:
            return self._closed

    def queue_depth(self) -> int:
        """Approximate number of telemetry events currently buffered."""
        return self._queue.qsize()

    def dropped_total(self) -> int:
        """Cumulative count of telemetry events lost (queue-full + ship-failure)."""
        with self._dropped_lock:
            return self._dropped_total

    def stop(self, drain: bool = True) -> None:
        """Stop the drain worker, optionally flushing remaining events.

        Args:
            drain: When ``True`` ship whatever is still queued before stopping.
        """
        self._stop(drain=drain, max_attempts=None)

    def _stop(self, *, drain: bool, max_attempts: Optional[int]) -> None:
        start_finisher = False
        with self._lifecycle_lock:
            first_stop = not self._closed
            self._closed = True
            self._drain_requested = self._drain_requested or drain
            if max_attempts is not None:
                current = self._final_attempts
                self._final_attempts = (
                    max_attempts if current is None else min(current, max_attempts)
                )
            self._stop_event.set()
            daemon = self._daemon
            if daemon is None and first_stop:
                daemon = threading.Thread(
                    target=self._finish_without_worker,
                    name="congine_event_bus_shutdown",
                    daemon=True,
                )
                self._daemon = daemon
                start_finisher = True
            callback = self._atexit_callback
            self._atexit_callback = None

        if callback is not None:
            with contextlib.suppress(Exception):
                atexit.unregister(callback)

        if daemon is None:
            return

        if start_finisher:
            try:
                daemon.start()
            except BaseException as exc:  # stop() is a no-raise boundary
                self._shutdown_complete.set()
                if self._logger:
                    self._logger.error(
                        "Telemetry shutdown worker could not start",
                        error_type=type(exc).__name__,
                    )
                return

        if daemon.is_alive() and daemon is not threading.current_thread():
            daemon.join(timeout=_WORKER_JOIN_TIMEOUT_SECONDS)

    def _get_client(self) -> httpx.Client:
        """Return a reused, long-lived HTTP client (connection reuse)."""
        if self._client is None:
            self._client = self._client_factory()
        return self._client

    # ------------------------------------------------------------------ #
    # Background worker
    # ------------------------------------------------------------------ #
    def _drain_loop(self) -> None:
        """Drain, perform the final flush, and close the client on this thread."""
        try:
            while not self._stop_event.is_set():
                batch = self._collect_batch()
                if batch:
                    self._ship(batch)
            with self._lifecycle_lock:
                drain = self._drain_requested
                max_attempts = self._final_attempts
            if drain:
                self._flush_remaining(max_attempts=max_attempts)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:  # noqa: BLE001 - daemon errors must never escape
            if self._logger:
                self._logger.error(
                    "Telemetry worker failed during shutdown",
                    error_type=type(exc).__name__,
                )
        finally:
            self._close_client()
            self._shutdown_complete.set()

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
        """atexit hook: bounded best-effort flush (M2 — must not stall exit).

        Uses a single attempt per batch (no long backoff) so a dead control
        plane cannot add retry×backoff seconds to interpreter shutdown.
        """
        self._stop(drain=True, max_attempts=1)

    def _finish_without_worker(self) -> None:
        """Own final drain/client close when no drain worker was ever started."""
        try:
            if self._drain_requested:
                self._flush_remaining(max_attempts=self._final_attempts)
        except (KeyboardInterrupt, SystemExit):
            raise
        except Exception as exc:  # noqa: BLE001 - stop() is a no-raise boundary
            if self._logger:
                self._logger.error(
                    "Telemetry flush failed during shutdown",
                    error_type=type(exc).__name__,
                )
        finally:
            self._close_client()
            self._shutdown_complete.set()

    def _close_client(self) -> None:
        """Close the client after the last ship; serialized against direct tests."""
        with self._ship_lock:
            client = self._client
            self._client = None
            if client is not None:
                with contextlib.suppress(Exception):
                    client.close()

    def _flush_remaining(self, max_attempts: Optional[int] = None) -> None:
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
            self._ship(batch, max_attempts=max_attempts)

    # ------------------------------------------------------------------ #
    # Shipping
    # ------------------------------------------------------------------ #
    def _ship(
        self, batch: List["TelemetryEvent"], max_attempts: Optional[int] = None
    ) -> bool:
        """Ship *batch* to the telemetry endpoint with exponential backoff.

        Reuses a single long-lived HTTP client across batches/retries (M2 —
        connection reuse). Returns ``True`` on a successful POST; a batch that
        still fails after the attempt budget is dropped (returns ``False``) —
        telemetry is fire-and-forget and must never raise to the host.

        Args:
            batch: Events to ship.
            max_attempts: Override the retry budget (used by the bounded
                exit-flush to avoid stalling shutdown).
        """
        with self._ship_lock:
            return self._ship_locked(batch, max_attempts=max_attempts)

    def _ship_locked(
        self, batch: List["TelemetryEvent"], max_attempts: Optional[int] = None
    ) -> bool:
        """Implementation of :meth:`_ship`, serialized with client closure."""
        if self._config is None:
            # No control plane configured: drain-and-observe only.
            if self._logger:
                self._logger.debug("Telemetry drained", count=len(batch))
            return True

        # Skip the network entirely if the breaker is OPEN — a persistently
        # dead plane should not eat 7.5s of backoff per batch on the bus thread.
        if self._circuit_breaker is not None and not self._circuit_breaker.allow():
            with self._dropped_lock:
                self._dropped_total += len(batch)
                dropped = self._dropped_total
            if self._logger:
                self._logger.warning(
                    "Circuit breaker OPEN; dropping telemetry batch",
                    count=len(batch),
                    dropped_total=dropped,
                )
            return False

        attempts = max_attempts if max_attempts is not None else self._max_retries
        url = f"{self._config.base_url}{_TELEMETRY_PATH}"
        headers = {
            "X-API-Key": self._config.api_key or "",
            "X-Project-ID": self._config.project_id or "",
            "X-Tenant-ID": self._config.tenant_id or "",
        }
        payload = {"events": [self._serialize(e) for e in batch]}

        delay = self._backoff_base
        for attempt in range(1, attempts + 1):
            try:
                response = self._get_client().post(url, json=payload, headers=headers)
                response.raise_for_status()
                if self._logger:
                    self._logger.debug(
                        "Telemetry shipped",
                        count=len(batch),
                        attempt=attempt,
                    )
                if self._circuit_breaker is not None:
                    self._circuit_breaker.record_success()
                return True
            except Exception as exc:  # noqa: BLE001 - telemetry never reaches host
                if self._logger:
                    self._logger.warning(
                        "Telemetry ship failed",
                        attempt=attempt,
                        max_retries=attempts,
                        error=str(exc),
                    )
                if attempt >= attempts:
                    if self._circuit_breaker is not None:
                        self._circuit_breaker.record_failure()
                    with self._dropped_lock:
                        self._dropped_total += len(batch)
                        dropped = self._dropped_total
                    if self._logger:
                        self._logger.error(
                            "Telemetry chunk dropped after retries",
                            count=len(batch),
                            dropped_total=dropped,
                        )
                    return False
                # Interruptible backoff so stop() wakes us promptly.
                if self._stop_event.wait(delay):
                    with self._dropped_lock:
                        self._dropped_total += len(batch)
                        dropped = self._dropped_total
                    if self._logger:
                        self._logger.warning(
                            "Telemetry batch dropped during shutdown",
                            count=len(batch),
                            dropped_total=dropped,
                        )
                    return False
                delay = min(delay * 2, self._backoff_max)
        return False

    @staticmethod
    def _serialize(event: "TelemetryEvent") -> Dict[str, Any]:
        """Serialize a :class:`TelemetryEvent` to a JSON-ready mapping."""
        created_at = getattr(event, "created_at", None)
        if created_at is not None and hasattr(created_at, "isoformat"):
            created_at = created_at.isoformat()
        return {
            "contract_id": getattr(event, "contract_id", None),
            "contract_version": getattr(event, "contract_version", None),
            "status": getattr(event, "status", None),
            "duration_ms": getattr(event, "duration_ms", None),
            "breach_details": getattr(event, "breach_details", None),
            "created_at": created_at,
        }
