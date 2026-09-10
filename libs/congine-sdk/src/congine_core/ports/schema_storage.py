"""Abstraction for schema caching/retrieval (Layer 1).

Defines :class:`ISchemaStorage`, a structural interface (``typing.Protocol``)
for any backing store that caches compiled contract schemas. Implementations
live in Layer 4 (e.g. :class:`congine_core.infrastructure.lfu_cache.LFUCache`).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, runtime_checkable

from congine_core.ports.lifecycle import IStoppable


@runtime_checkable
class ISchemaStorage(IStoppable, Protocol):
    """Structural interface for schema caching/retrieval.

    Implementations must be safe for concurrent use and must honour TTL
    semantics: an expired entry is treated as absent.

    :meth:`get` sits on the validation hot path *outside* the timeout guard, so
    it must never block. :meth:`put` must be individually atomic and must never
    clear the store: the sync use case updates keys in place precisely so a
    concurrent ``get`` always observes a coherent cache.

    Composes :class:`~congine_core.ports.lifecycle.IStoppable` — the container
    calls ``stop()`` during ``close()`` — and additionally requires
    :meth:`size`, which ``health()`` reports (audit Q8).
    """

    def get(self, contract_id: str) -> Optional[Dict[str, Any]]:
        """Return the cached schema for *contract_id*.

        Args:
            contract_id: Identifier of the contract whose schema is requested.

        Returns:
            The cached schema mapping, or ``None`` on cache miss or TTL expiry.
        """
        ...

    def put(
        self,
        contract_id: str,
        schema: Dict[str, Any],
        ttl_seconds: int,
    ) -> None:
        """Store *schema* under *contract_id* with a time-to-live.

        Args:
            contract_id: Identifier to store the schema under.
            schema: The schema mapping to cache.
            ttl_seconds: Time-to-live, in seconds, for this entry.
        """
        ...

    def clear(self) -> None:
        """Evict every cached schema."""
        ...

    def exists(self, contract_id: str) -> bool:
        """Return ``True`` if *contract_id* is cached and not expired.

        Args:
            contract_id: Identifier to probe.

        Returns:
            ``True`` if a live (non-expired) entry exists, else ``False``.
        """
        ...

    def size(self) -> int:
        """Return the number of cached entries.

        Reported by :meth:`ServiceContainer.health` as ``cache_entries``. May
        include entries whose TTL has elapsed but which have not yet been swept.
        """
        ...
