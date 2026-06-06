"""Cross-platform timeout runner (Layer 4).

.. deprecated::
    :class:`ValidationTimer` is retained for legacy reference only. Use
    :class:`congine_core.infrastructure.bounded_executor.BoundedValidationExecutor`
    — it is the production implementation, conforms to the
    :class:`congine_core.ports.validation_runner.IValidationRunner` port, and
    enforces the bounded/load-shedding and async-symmetric guarantees that
    ``ValidationTimer`` lacks. Wiring ``ValidationTimer`` directly produces an
    *unbounded, non-load-shedding* timer (audit D-3/D-11).

:class:`ValidationTimer` runs a callable under a wall-clock deadline using a
:class:`concurrent.futures.ThreadPoolExecutor`. This is Windows-safe (unlike
``signal.alarm``) at the cost of being unable to forcibly kill a runaway
thread — a timed-out worker keeps running in the background until it returns.
"""

from __future__ import annotations

import atexit
import concurrent.futures
import warnings
from typing import Any, Callable


class ValidationTimer:
    """Run callables with a millisecond timeout (cross-platform).

    .. deprecated::
        Use :class:`BoundedValidationExecutor` for new code.
    """

    def __init__(self, max_workers: int = 10) -> None:
        """Initialize the executor pool.

        Args:
            max_workers: Maximum concurrent timed executions.
        """
        warnings.warn(
            "ValidationTimer is deprecated and provides no load-shedding or "
            "async-symmetric guarantees; use BoundedValidationExecutor instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="congine_timer",
        )
        atexit.register(self._cleanup)

    def run_with_timeout(self, func: Callable[[], Any], timeout_ms: int) -> Any:
        """Run *func* and return its result, enforcing *timeout_ms*.

        Args:
            func: Zero-argument callable to execute.
            timeout_ms: Timeout budget in milliseconds.

        Returns:
            Whatever *func* returns.

        Raises:
            TimeoutError: If *func* does not complete within the budget.
        """
        future = self._executor.submit(func)
        timeout_seconds = timeout_ms / 1000.0
        try:
            return future.result(timeout=timeout_seconds)
        except concurrent.futures.TimeoutError as exc:
            raise TimeoutError(f"Timeout after {timeout_ms}ms") from exc

    def shutdown(self, wait: bool = False) -> None:
        """Shut the executor down (idempotent).

        Args:
            wait: When ``True`` block until running futures complete.
        """
        self._executor.shutdown(wait=wait)

    def _cleanup(self) -> None:
        """Shut the executor down on interpreter exit (best-effort)."""
        self.shutdown(wait=False)
