"""Abstraction for bounded, time-boxed validation execution (Layer 1).

Defines :class:`IValidationRunner`, the structural interface for the timed,
load-shedding executor that runs a validation callable under a millisecond
deadline. Layer 4's :class:`congine_core.infrastructure.bounded_executor.BoundedValidationExecutor`
is the production implementation; tests may substitute a synchronous fake that
runs the callable inline.

Closing this seam (audit D-4) keeps Layer 3 — :class:`ValidateContractUseCase` —
typed against a Layer-1 abstraction rather than naming a Layer-4 concrete by
string literal.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Protocol, runtime_checkable

from congine_core.ports.lifecycle import IObservable


@runtime_checkable
class IValidationRunner(IObservable, Protocol):
    """Structural interface for bounded, timed execution of validation callables.

    Implementations are expected to enforce:

    - **Capacity bounding** — load-shed (``TimeoutError``) on saturation rather
      than unbounded-queueing.
    - **Hard deadline enforcement** — abort the callable when ``timeout_ms``
      is exceeded.
    - **Re-entrancy safety** — when called from one of the implementation's own
      worker threads, run inline rather than re-submitting (no nested-pool
      deadlock).

    The async variant (:meth:`run_with_timeout_async`) is required so async
    callers receive the **identical** capacity bound and deadline as sync
    callers — closing audit H1/H2.

    Composes :class:`~congine_core.ports.lifecycle.IObservable` (the container
    reports ``in_flight`` and ``rejected_total`` in ``health()``) and
    additionally requires :meth:`shutdown`, which ``close()`` calls — both
    previously undeclared (audit Q8).
    """

    @property
    def capacity(self) -> int:
        """Total outstanding-work ceiling (workers + pending slots)."""
        ...

    def run_with_timeout(
        self,
        func: Callable[[], Any],
        timeout_ms: int,
    ) -> Any:
        """Run *func* with a millisecond timeout, shedding load when saturated.

        Args:
            func: Zero-argument callable to execute.
            timeout_ms: Timeout budget in milliseconds.

        Returns:
            Whatever *func* returns.

        Raises:
            TimeoutError: If *func* overruns the budget, OR if the runner is
                saturated (load shed).
        """
        ...

    async def run_with_timeout_async(
        self,
        func: Callable[[], Any],
        timeout_ms: int,
    ) -> Any:
        """Async-safe twin of :meth:`run_with_timeout`.

        Offloads *func* off the event loop so a slow validation never stalls
        concurrent asyncio tasks; uses the same capacity bound and deadline as
        the sync entry point.

        Args:
            func: Zero-argument callable to execute.
            timeout_ms: Timeout budget in milliseconds.

        Returns:
            Whatever *func* returns.

        Raises:
            TimeoutError: If *func* overruns the budget, OR if the runner is
                saturated (load shed).
            CongineLifecycleError: If the runner is already shut down.
        """
        ...

    def health(self) -> Dict[str, Any]:
        """Return a lightweight operational snapshot.

        Returns:
            A mapping containing at least ``in_flight`` (current outstanding
            work), ``rejected_total`` (cumulative load-shed count), and
            ``capacity`` (the outstanding-work ceiling).
        """
        ...

    def shutdown(self, wait: bool = False) -> None:
        """Release the runner's worker threads (idempotent).

        Called by :meth:`ServiceContainer.close` with ``wait=False``: teardown
        must not block on work already in flight, because a timed-out validation
        cannot be cancelled and could otherwise stall shutdown indefinitely.

        Args:
            wait: When ``True``, block until running work completes.
        """
        ...
