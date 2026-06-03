"""Abstraction for fetching contracts (Layer 1).

Defines :class:`IContractRepository`, a structural interface for retrieving
active contracts from the control plane (over the network) with a disk
snapshot fallback for stale-ok degraded operation.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class IContractRepository(Protocol):
    """Structural interface for contract retrieval.

    Concrete implementations (Layer 4) perform network I/O and atomic disk
    snapshotting; this abstraction lets upper layers depend only on behaviour.
    """

    async def fetch_active_contracts(self) -> List[Dict]:
        """Fetch the active contracts from the control plane.

        Returns:
            A list of contract mappings, each containing at least ``id``,
            ``version`` and ``schema`` keys.

        Raises:
            Exception: Implementation-specific transport/HTTP errors.
        """
        ...

    def load_snapshot(self) -> Optional[List[Dict]]:
        """Load contracts from the on-disk snapshot (stale-ok fallback).

        Returns:
            The previously persisted list of contracts, or ``None`` if no valid
            snapshot is available.
        """
        ...

    def save_snapshot(self, contracts: List[Dict]) -> None:
        """Persist *contracts* to disk atomically.

        Args:
            contracts: The list of contract mappings to persist.
        """
        ...
