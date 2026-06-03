"""Unit tests for :mod:`congine_core.infrastructure.queue_event_bus`."""

from __future__ import annotations

from typing import Callable, List

import httpx

from congine_core.config import CongineConfig, Region
from congine_core.domain.models import TelemetryEvent
from congine_core.infrastructure.queue_event_bus import QueueEventBus
from tests.conftest import FakeLogger


def _config() -> CongineConfig:
    return CongineConfig(
        base_url="http://cp.test",
        api_key="key-123",
        project_id="proj",
        tenant_id="tenant",
        region=Region.US,
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
