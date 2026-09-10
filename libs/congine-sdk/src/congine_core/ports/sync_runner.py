"""Contract-sync seam (Layer 1).

:class:`ISyncRunner` is the one-method port that decouples the L4 mechanism
(:class:`~congine_core.infrastructure.background_sync.BackgroundSyncWorker`, a
daemon thread that wakes on an interval) from the L3 policy
(:class:`~congine_core.usecases.sync_contracts_usecase.SyncContractsUseCase`,
which decides what a sync pass actually does).

**Why this port exists (P1).** The worker previously typed its collaborator as
the concrete use case, which is an ``L4 -> L3`` dependency: infrastructure
reaching into orchestration. The edge was hidden under ``if TYPE_CHECKING`` and
so escaped the architecture gate. The worker only ever calls ``sync_once()``, so
naming that single obligation as a port makes the real dependency ``L4 -> L1``
and lawful, with no loss of type safety — ``SyncContractsUseCase`` satisfies it
structurally and needed no change.

Follows the same narrow-seam convention as :mod:`congine_core.ports.lifecycle`:
one job per port, ``@runtime_checkable`` so conformance stays structural.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ISyncRunner(Protocol):
    """A component that can perform one contract-synchronisation pass.

    :meth:`sync_once` is driven on a timer by the background worker, which
    swallows any exception so a single failed pass never kills the loop.
    Implementations should therefore surface failure through their own logging
    and telemetry rather than relying on the caller to report it.
    """

    def sync_once(self) -> int:
        """Run one sync pass and return the number of contracts now cached."""
        ...


__all__ = ["ISyncRunner"]
