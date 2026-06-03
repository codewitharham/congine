"""Cross-platform timeout runner (Layer 4).

:class:`ValidationTimer` runs a callable under a wall-clock deadline using a
:class:`concurrent.futures.ThreadPoolExecutor`. This is Windows-safe (unlike
``signal.alarm``) at the cost of being unable to forcibly kill a runaway
thread — a timed-out worker keeps running in the background until it returns.
"""

from __future__ import annotations

import atexit
import concurrent.futures
from typing import Any, Callable


class ValidationTimer:
    """Run callables with a millisecond timeout (cross-platform)."""

    def __init__(self, max_workers: int = 10) -> None:
        """Initialize the executor pool.

        Args:
            max_workers: Maximum concurrent timed executions.
        """
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

    def _cleanup(self) -> None:
        """Shut the executor down on interpreter exit (best-effort)."""
        self._executor.shutdown(wait=False)
