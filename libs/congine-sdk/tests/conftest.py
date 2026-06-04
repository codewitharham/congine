"""Shared pytest fixtures and lightweight test doubles for the Congine SDK.

These fakes are plain objects (structural typing) — they satisfy the Layer-1
protocols without importing or subclassing them.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pytest

from congine_core.config import CongineConfig, FailMode, Region
from congine_core.domain.models import TelemetryEvent


class FakeLogger:
    """Capturing :class:`ILogger` test double."""

    def __init__(self) -> None:
        self.records: List[Tuple[str, str, Dict[str, Any]]] = []

    def _record(self, level: str, message: str, **kwargs: Any) -> None:
        self.records.append((level, message, kwargs))

    def info(self, message: str, **kwargs: Any) -> None:
        self._record("INFO", message, **kwargs)

    def error(self, message: str, **kwargs: Any) -> None:
        self._record("ERROR", message, **kwargs)

    def warning(self, message: str, **kwargs: Any) -> None:
        self._record("WARNING", message, **kwargs)

    def debug(self, message: str, **kwargs: Any) -> None:
        self._record("DEBUG", message, **kwargs)

    def levels(self) -> List[str]:
        return [lvl for lvl, _msg, _kw in self.records]


class FakeEventBus:
    """Capturing :class:`IEventBus` test double."""

    def __init__(self) -> None:
        self.published: List[TelemetryEvent] = []

    def publish(self, event: TelemetryEvent) -> None:
        self.published.append(event)

    def stop(self, drain: bool = True) -> None:
        """No-op: present so a container.close() can treat it like the real bus."""

    def queue_depth(self) -> int:
        """Mirror QueueEventBus.queue_depth for health() snapshots."""
        return len(self.published)


class FakeSchemaStorage:
    """In-memory :class:`ISchemaStorage` test double (no TTL/LFU)."""

    def __init__(self, initial: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
        self._store: Dict[str, Dict[str, Any]] = dict(initial or {})

    def get(self, contract_id: str) -> Optional[Dict[str, Any]]:
        return self._store.get(contract_id)

    def put(
        self, contract_id: str, schema: Dict[str, Any], ttl_seconds: int = 0
    ) -> None:
        self._store[contract_id] = schema

    def clear(self) -> None:
        self._store.clear()

    def exists(self, contract_id: str) -> bool:
        return contract_id in self._store


class ImmediateTimer:
    """:class:`ValidationTimer` stand-in that runs *func* inline (no threads)."""

    def run_with_timeout(self, func: Any, timeout_ms: int) -> Any:
        return func()


class FakeContractRepository:
    """:class:`IContractRepository` test double.

    ``fetch_active_contracts`` returns *contracts* unless *fetch_error* is set
    (then it raises it). ``load_snapshot`` returns *snapshot*. ``save_snapshot``
    records into ``saved`` unless *save_error* is set (then it raises it).
    """

    def __init__(
        self,
        contracts: Optional[List[Dict[str, Any]]] = None,
        fetch_error: Optional[BaseException] = None,
        snapshot: Optional[List[Dict[str, Any]]] = None,
        save_error: Optional[BaseException] = None,
    ) -> None:
        self._contracts = contracts
        self._fetch_error = fetch_error
        self._snapshot = snapshot
        self._save_error = save_error
        self.saved: Optional[List[Dict[str, Any]]] = None

    async def fetch_active_contracts(self) -> List[Dict[str, Any]]:
        if self._fetch_error is not None:
            raise self._fetch_error
        return self._contracts or []

    def load_snapshot(self) -> Optional[List[Dict[str, Any]]]:
        return self._snapshot

    def save_snapshot(self, contracts: List[Dict[str, Any]]) -> None:
        if self._save_error is not None:
            raise self._save_error
        self.saved = contracts


@pytest.fixture
def fake_logger() -> FakeLogger:
    return FakeLogger()


@pytest.fixture
def fake_event_bus() -> FakeEventBus:
    return FakeEventBus()


@pytest.fixture
def fake_schema_storage() -> FakeSchemaStorage:
    return FakeSchemaStorage()


@pytest.fixture
def immediate_timer() -> ImmediateTimer:
    return ImmediateTimer()


@pytest.fixture
def config() -> CongineConfig:
    """A minimal, fully populated frozen config."""
    return CongineConfig(
        base_url="http://control-plane.test",
        api_key="test-key",
        project_id="proj-1",
        tenant_id="tenant-1",
        region=Region.US,
        validation_timeout_ms=50,
        fail_mode=FailMode.DEGRADE,
        cache_capacity=10,
        cache_ttl_seconds=300,
    )
