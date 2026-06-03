"""Unit tests for :mod:`congine_core.infrastructure.lfu_cache`."""

from __future__ import annotations

import threading
import time

import pytest

from congine_core.infrastructure.lfu_cache import LFUCache


def _cache(capacity: int = 3, ttl: int = 300) -> LFUCache:
    # Deterministic: no background sweeper thread.
    return LFUCache(capacity=capacity, ttl_seconds=ttl, start_sweeper=False)


def test_put_get_roundtrip() -> None:
    c = _cache()
    c.put("a", {"v": 1})
    assert c.get("a") == {"v": 1}
    assert c.exists("a") is True


def test_get_miss_returns_none() -> None:
    assert _cache().get("absent") is None


def test_exists_false_for_absent() -> None:
    assert _cache().exists("absent") is False


def test_clear() -> None:
    c = _cache()
    c.put("a", {"v": 1})
    c.put("b", {"v": 2})
    c.clear()
    assert c.get("a") is None
    assert c.get("b") is None


def test_capacity_zero_is_noop() -> None:
    c = LFUCache(capacity=0, start_sweeper=False)
    c.put("a", {"v": 1})
    assert c.get("a") is None


def test_negative_capacity_rejected() -> None:
    with pytest.raises(ValueError):
        LFUCache(capacity=-1, start_sweeper=False)


def test_lfu_evicts_least_frequently_used() -> None:
    c = _cache(capacity=2)
    c.put("a", {"v": 1})
    c.put("b", {"v": 2})
    # Bump "a" so "b" is the least-frequently-used.
    c.get("a")
    c.put("c", {"v": 3})  # evicts "b"
    assert c.get("b") is None
    assert c.get("a") == {"v": 1}
    assert c.get("c") == {"v": 3}


def test_lru_tiebreak_within_same_frequency() -> None:
    c = _cache(capacity=2)
    c.put("a", {"v": 1})
    c.put("b", {"v": 2})
    # Both at frequency 1; "a" was inserted first → evicted first.
    c.put("c", {"v": 3})
    assert c.get("a") is None
    assert c.get("b") == {"v": 2}


def test_ttl_lazy_expiry_on_get() -> None:
    c = _cache(ttl=1)
    c.put("a", {"v": 1}, ttl_seconds=0)  # already expired
    assert c.get("a") is None
    assert c.exists("a") is False


def test_update_existing_key_refreshes_value() -> None:
    c = _cache()
    c.put("a", {"v": 1})
    c.put("a", {"v": 2})
    assert c.get("a") == {"v": 2}


def test_sweep_expired_purges() -> None:
    c = _cache(ttl=300)
    c.put("fresh", {"v": 1}, ttl_seconds=300)
    c.put("stale", {"v": 2}, ttl_seconds=0)
    purged = c.sweep_expired()
    assert purged == 1
    assert c.get("fresh") == {"v": 1}


def test_background_sweeper_runs() -> None:
    c = LFUCache(
        capacity=5,
        ttl_seconds=300,
        sweep_interval=0.05,
        start_sweeper=True,
    )
    try:
        c.put("stale", {"v": 1}, ttl_seconds=0)
        # Give the daemon a couple of cycles to purge.
        deadline = time.time() + 2.0
        while time.time() < deadline and c._key_to_value:
            time.sleep(0.05)
        assert "stale" not in c._key_to_value
    finally:
        c.stop()


def test_stop_is_idempotent() -> None:
    c = LFUCache(sweep_interval=0.05, start_sweeper=True)
    c.stop()
    c.stop()  # second call must not raise


def test_thread_safety_smoke() -> None:
    c = LFUCache(capacity=100, start_sweeper=False)

    def worker(base: int) -> None:
        for i in range(100):
            key = f"k{(base + i) % 50}"
            c.put(key, {"v": i})
            c.get(key)

    threads = [threading.Thread(target=worker, args=(b,)) for b in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # No assertion on contents (eviction is racy); we assert no crash + bound.
    assert len(c._key_to_value) <= 100
