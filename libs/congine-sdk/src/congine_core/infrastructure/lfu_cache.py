"""O(1) LFU cache with TTL (Layer 4).

:class:`LFUCache` implements :class:`congine_core.ports.schema_storage.ISchemaStorage`
using Ketan Shah's O(1) LFU algorithm: each operation (get/put/evict) runs in
amortized constant time regardless of capacity. Entries also carry a TTL; an
expired entry is treated as a miss and lazily reclaimed.

All public operations are guarded by a re-entrant lock and are safe for
concurrent use.
"""

from __future__ import annotations

import atexit
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

#: Default interval, in seconds, between proactive TTL sweeps.
_DEFAULT_SWEEP_INTERVAL = 30.0


class LFUCache:
    """Thread-safe Least-Frequently-Used cache with per-entry TTL.

    A background daemon thread proactively purges TTL-expired entries every
    ``sweep_interval`` seconds; :meth:`get`/:meth:`exists` also lazily expire on
    read. The sweeper is a daemon (it never blocks interpreter exit) and is also
    stopped via an :mod:`atexit` hook and the explicit :meth:`stop` method.
    """

    def __init__(
        self,
        capacity: int = 500,
        ttl_seconds: int = 300,
        sweep_interval: float = _DEFAULT_SWEEP_INTERVAL,
        start_sweeper: bool = True,
    ) -> None:
        """Args:
        capacity: Maximum number of entries; the least-frequently-used
            entry is evicted (FIFO among ties) when this is exceeded.
        ttl_seconds: Default time-to-live, in seconds, for stored entries.
        sweep_interval: Seconds between proactive TTL sweeps by the daemon.
        start_sweeper: When ``True`` (default) start the background sweeper
            thread; pass ``False`` for deterministic, sweeper-free tests.
        """
        if capacity < 0:
            raise ValueError("capacity must be non-negative")
        self.capacity = capacity
        self.ttl_seconds = ttl_seconds
        self.sweep_interval = sweep_interval

        # contract_id -> (schema, expire_monotonic)
        self._key_to_value: Dict[str, Tuple[Dict[str, Any], float]] = {}
        # contract_id -> access frequency
        self._key_to_freq: Dict[str, int] = {}
        # frequency -> insertion-ordered set of keys (OrderedDict as ordered set)
        self._freq_to_keys: Dict[int, "OrderedDict[str, None]"] = {}
        self._min_freq = 0

        self._lock = threading.RLock()

        # --- Background TTL sweeper ------------------------------------- #
        self._stop_event = threading.Event()
        self._sweeper: Optional[threading.Thread] = None
        if start_sweeper:
            self._sweeper = threading.Thread(
                target=self._sweep_loop,
                name="congine_cache_sweeper",
                daemon=True,
            )
            self._sweeper.start()
            atexit.register(self.stop)

    # ------------------------------------------------------------------ #
    # Public API (ISchemaStorage)
    # ------------------------------------------------------------------ #
    def get(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """Return the cached schema, bumping its frequency, or ``None``.

        A miss, or an entry whose TTL has elapsed, yields ``None`` (an expired
        entry is evicted as a side effect).
        """
        with self._lock:
            entry = self._key_to_value.get(contract_id)
            if entry is None:
                return None
            schema, expire_at = entry
            if self._is_expired(expire_at):
                self._evict_key(contract_id)
                return None
            self._increment_freq(contract_id)
            return schema

    def put(
        self,
        contract_id: str,
        schema: Dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> None:
        """Store *schema* under *contract_id*, evicting the LFU entry if full.

        Args:
            contract_id: Key to store under.
            schema: Schema mapping to cache.
            ttl_seconds: Override TTL for this entry; falls back to the cache
                default when ``None``.
        """
        if self.capacity == 0:
            return

        ttl = self.ttl_seconds if ttl_seconds is None else ttl_seconds
        expire_at = time.monotonic() + ttl

        with self._lock:
            if contract_id in self._key_to_value:
                # Update existing entry's value/expiry and bump its frequency.
                self._key_to_value[contract_id] = (schema, expire_at)
                self._increment_freq(contract_id)
                return

            if len(self._key_to_value) >= self.capacity:
                self._evict_lfu()

            self._key_to_value[contract_id] = (schema, expire_at)
            self._key_to_freq[contract_id] = 1
            self._freq_to_keys.setdefault(1, OrderedDict())[contract_id] = None
            self._min_freq = 1

    def clear(self) -> None:
        """Evict every cached entry."""
        with self._lock:
            self._key_to_value.clear()
            self._key_to_freq.clear()
            self._freq_to_keys.clear()
            self._min_freq = 0

    def size(self) -> int:
        """Return the number of cached entries (including not-yet-swept stale)."""
        with self._lock:
            return len(self._key_to_value)

    def exists(self, contract_id: str) -> bool:
        """Return ``True`` if *contract_id* is cached and not expired."""
        with self._lock:
            entry = self._key_to_value.get(contract_id)
            if entry is None:
                return False
            if self._is_expired(entry[1]):
                self._evict_key(contract_id)
                return False
            return True

    # ------------------------------------------------------------------ #
    # Private helpers (all invoked under self._lock)
    # ------------------------------------------------------------------ #
    @staticmethod
    def _is_expired(expire_at: float) -> bool:
        """Return ``True`` if the monotonic deadline has passed."""
        return time.monotonic() >= expire_at

    def _increment_freq(self, key: str) -> None:
        """Move *key* from its current frequency bucket to the next one."""
        freq = self._key_to_freq[key]
        bucket = self._freq_to_keys[freq]
        del bucket[key]
        if not bucket:
            del self._freq_to_keys[freq]
            if self._min_freq == freq:
                self._min_freq = freq + 1

        new_freq = freq + 1
        self._key_to_freq[key] = new_freq
        self._freq_to_keys.setdefault(new_freq, OrderedDict())[key] = None

    def _evict_lfu(self) -> None:
        """Evict the least-frequently-used key (FIFO among equal frequency).

        Runs only on a capacity-full insert (rare). ``_min_freq`` may be stale if
        a TTL expiry emptied the min bucket without a scan (M4); reconcile it
        here — off the get/put hot path — instead of scanning on every expiry.
        """
        bucket = self._freq_to_keys.get(self._min_freq)
        if not bucket:
            if not self._freq_to_keys:
                return
            self._min_freq = min(self._freq_to_keys)
            bucket = self._freq_to_keys[self._min_freq]
        key, _ = bucket.popitem(last=False)
        if not bucket:
            del self._freq_to_keys[self._min_freq]
        self._key_to_value.pop(key, None)
        self._key_to_freq.pop(key, None)

    def _evict_key(self, key: str) -> None:
        """Remove *key* from every internal structure.

        Kept O(1): does NOT recompute ``_min_freq`` (no scan). Any resulting
        staleness is reconciled lazily by :meth:`_evict_lfu`, and the next
        :meth:`put` resets ``_min_freq`` to 1 regardless.
        """
        freq = self._key_to_freq.pop(key, None)
        self._key_to_value.pop(key, None)
        if freq is not None:
            bucket = self._freq_to_keys.get(freq)
            if bucket is not None:
                bucket.pop(key, None)
                if not bucket:
                    del self._freq_to_keys[freq]

    # ------------------------------------------------------------------ #
    # Background TTL sweeper
    # ------------------------------------------------------------------ #
    def _sweep_loop(self) -> None:
        """Daemon loop: purge expired entries every ``sweep_interval`` seconds.

        Uses :meth:`threading.Event.wait` so a :meth:`stop` request wakes the
        thread promptly instead of waiting out the full interval.
        """
        while not self._stop_event.wait(self.sweep_interval):
            self.sweep_expired()

    def sweep_expired(self) -> int:
        """Evict every TTL-expired entry now.

        Safe to call directly (e.g. from tests) regardless of the sweeper
        thread. Returns the number of entries evicted.
        """
        with self._lock:
            expired: List[str] = [
                key
                for key, (_schema, expire_at) in self._key_to_value.items()
                if self._is_expired(expire_at)
            ]
            for key in expired:
                self._evict_key(key)
            return len(expired)

    def stop(self) -> None:
        """Stop the background sweeper thread (idempotent)."""
        self._stop_event.set()
        sweeper = self._sweeper
        if sweeper is not None and sweeper.is_alive():
            sweeper.join(timeout=self.sweep_interval + 1.0)
