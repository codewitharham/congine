"""Unit tests for :mod:`congine_core.infrastructure.queue_event_bus`."""

from __future__ import annotations

import threading
import time
from typing import Callable, List

import httpx
import pytest

from congine_core.config import CongineConfig, Region
from congine_core.domain.models import TelemetryEvent
from congine_core.infrastructure import queue_event_bus as queue_event_bus_module
from congine_core.infrastructure.queue_event_bus import QueueEventBus
from tests.conftest import FakeLogger


def _config() -> CongineConfig:
    return CongineConfig(
        base_url="http://cp.test",
        api_key="key-123",
        project_id="proj",
        tenant_id="tenant",
        region=Region.US,
        allow_cleartext=True,  # cleartext test control plane (declared)
    )


def _event(cid: str = "c1") -> TelemetryEvent:
    return TelemetryEvent(
        contract_id=cid,
        contract_version="1.0",
        status="fail",
        duration_ms=1.5,
        breach_details=[{"rule": "RANGE_CHECK", "field": "score", "message": None}],
    )


def _client_factory(
    handler: Callable[[httpx.Request], httpx.Response],
) -> Callable[[], httpx.Client]:
    return lambda: httpx.Client(transport=httpx.MockTransport(handler))


def test_publish_is_non_blocking_and_enqueues() -> None:
    bus = QueueEventBus(start_worker=False)
    bus.publish(_event())
    assert bus._queue.qsize() == 1


def test_publish_drops_when_full() -> None:
    logger = FakeLogger()
    bus = QueueEventBus(logger=logger, max_queue_size=1, start_worker=False)
    bus.publish(_event("a"))
    bus.publish(_event("b"))  # dropped
    assert bus._queue.qsize() == 1
    assert "WARNING" in logger.levels()


def test_ship_posts_payload_and_headers() -> None:
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = request.headers
        captured["body"] = request.read().decode()
        return httpx.Response(202)

    logger = FakeLogger()
    bus = QueueEventBus(
        config=_config(),
        logger=logger,
        client_factory=_client_factory(handler),
        start_worker=False,
    )
    assert bus._ship([_event("c1")]) is True
    assert captured["url"] == "http://cp.test/api/v1/telemetry"
    assert captured["headers"]["X-Tenant-ID"] == "tenant"
    assert '"contract_id":"c1"' in captured["body"]
    assert '"events"' in captured["body"]


def test_ship_without_config_drains_only() -> None:
    logger = FakeLogger()
    bus = QueueEventBus(logger=logger, start_worker=False)
    assert bus._ship([_event()]) is True
    assert "DEBUG" in logger.levels()


def test_ship_retries_then_drops() -> None:
    attempts: List[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(1)
        return httpx.Response(500)

    logger = FakeLogger()
    bus = QueueEventBus(
        config=_config(),
        logger=logger,
        client_factory=_client_factory(handler),
        max_retries=3,
        backoff_base=0.001,
        backoff_max=0.002,
        start_worker=False,
    )
    assert bus._ship([_event()]) is False
    assert len(attempts) == 3
    assert "ERROR" in logger.levels()


def test_ship_does_not_leak_api_key_in_logs() -> None:
    logger = FakeLogger()
    bus = QueueEventBus(
        config=_config(),
        logger=logger,
        client_factory=_client_factory(lambda r: httpx.Response(500)),
        max_retries=1,
        start_worker=False,
    )
    bus._ship([_event()])
    blob = repr(logger.records)
    assert "key-123" not in blob


def test_flush_remaining_ships_everything() -> None:
    shipped: List[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        shipped.append(len(request.read()))
        return httpx.Response(202)

    bus = QueueEventBus(
        config=_config(),
        client_factory=_client_factory(handler),
        batch_size=2,
        start_worker=False,
    )
    for i in range(3):
        bus.publish(_event(f"c{i}"))
    bus._flush_remaining()
    assert bus._queue.qsize() == 0
    assert len(shipped) == 2  # batches of 2 then 1


def test_collect_batch_caps_at_batch_size() -> None:
    bus = QueueEventBus(batch_size=2, start_worker=False)
    for i in range(5):
        bus.publish(_event(f"c{i}"))
    batch = bus._collect_batch()
    assert len(batch) == 2


def test_serialize_shapes_event() -> None:
    record = QueueEventBus._serialize(_event("c9"))
    assert record["contract_id"] == "c9"
    assert record["status"] == "fail"
    assert isinstance(record["created_at"], str)  # ISO-formatted
    assert record["breach_details"][0]["rule"] == "RANGE_CHECK"


# --- D-10: dropped_total counter (telemetry loss visibility) -------------- #


def test_dropped_total_increments_on_queue_full() -> None:
    bus = QueueEventBus(max_queue_size=1, start_worker=False)
    assert bus.dropped_total() == 0
    bus.publish(_event("a"))
    bus.publish(_event("b"))  # dropped — queue full
    bus.publish(_event("c"))  # dropped — queue full
    assert bus.dropped_total() == 2


def test_dropped_total_increments_after_ship_retries_fail() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    bus = QueueEventBus(
        config=_config(),
        client_factory=_client_factory(handler),
        max_retries=2,
        backoff_base=0.001,
        backoff_max=0.001,
        start_worker=False,
    )
    assert bus._ship([_event("a"), _event("b")]) is False
    # Both batched events are counted as dropped.
    assert bus.dropped_total() == 2


def test_publish_after_stop_is_rejected_and_counted() -> None:
    bus = QueueEventBus(start_worker=False)
    bus.stop(drain=False)
    assert bus._shutdown_complete.wait(1.0)

    bus.publish(_event("late"))

    assert bus.queue_depth() == 0
    assert bus.dropped_total() == 1


def test_no_worker_stop_is_bounded_and_finisher_owns_client_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_started = threading.Event()
    release_request = threading.Event()

    def handler(request: httpx.Request) -> httpx.Response:
        request_started.set()
        release_request.wait(2.0)
        return httpx.Response(202)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    bus = QueueEventBus(
        config=_config(),
        client_factory=lambda: client,
        start_worker=False,
    )
    ship_thread = threading.Thread(target=lambda: bus._ship([_event()]), daemon=True)
    ship_thread.start()
    assert request_started.wait(1.0)

    monkeypatch.setattr(queue_event_bus_module, "_WORKER_JOIN_TIMEOUT_SECONDS", 0.05)
    started = time.perf_counter()
    bus.stop(drain=False)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5
    assert client.is_closed is False

    release_request.set()
    ship_thread.join(1.0)
    assert bus._shutdown_complete.wait(1.0)
    assert client.is_closed is True


def test_interrupted_retry_batch_is_counted_as_dropped() -> None:
    request_attempted = threading.Event()
    result: list[bool] = []

    def handler(request: httpx.Request) -> httpx.Response:
        request_attempted.set()
        return httpx.Response(500)

    bus = QueueEventBus(
        config=_config(),
        client_factory=_client_factory(handler),
        max_retries=3,
        backoff_base=5.0,
        backoff_max=5.0,
        start_worker=False,
    )
    batch = [_event("a"), _event("b")]
    ship_thread = threading.Thread(
        target=lambda: result.append(bus._ship(batch)), daemon=True
    )
    ship_thread.start()
    assert request_attempted.wait(1.0)

    bus.stop(drain=False)
    ship_thread.join(1.0)

    assert result == [False]
    assert bus.dropped_total() == len(batch)
