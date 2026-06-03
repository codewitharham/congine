"""The ``@congine_guard`` decorator (Layer 5).

Wraps a function so its output is validated against a Congine contract via the
:class:`ValidateContractUseCase`. Both synchronous and ``async`` callables are
supported; the wrapper returns ``{"output": ..., "validation_result": ...}``.
"""

from __future__ import annotations

import functools
import inspect
from typing import Callable, Optional

from congine_core.adapters.dependency_injection import ServiceContainer


def congine_guard(
    contract_id: str,
    version: str = "latest",
    container: Optional[ServiceContainer] = None,
) -> Callable:
    """Validate a function's output against a Congine contract.

    Args:
        contract_id: Contract identifier (e.g. ``"sentiment-v1"``).
        version: Contract version recorded in telemetry (default ``"latest"``).
        container: A :class:`ServiceContainer`. When ``None``, one is built from
            the environment the first time the decorator is applied.

    Returns:
        A decorator producing a wrapper that returns a mapping with both the
        original ``output`` and its ``validation_result``.

    Example:
        >>> container = ServiceContainer.from_env()
        >>> @congine_guard(contract_id="sentiment-v1", container=container)
        ... def analyze(text: str) -> dict:
        ...     return {"score": 0.8}
    """

    def decorator(fn: Callable) -> Callable:
        # Resolve the container once, at decoration time.
        ctx = container or ServiceContainer.from_env()

        @functools.wraps(fn)
        def sync_wrapper(*args, **kwargs) -> dict:
            output = fn(*args, **kwargs)
            validation_result = ctx.validate_contract_usecase.execute(
                payload=output,
                contract_id=contract_id,
                contract_version=version,
            )
            return {"output": output, "validation_result": validation_result}

        @functools.wraps(fn)
        async def async_wrapper(*args, **kwargs) -> dict:
            output = await fn(*args, **kwargs)
            # Validation itself is synchronous.
            validation_result = ctx.validate_contract_usecase.execute(
                payload=output,
                contract_id=contract_id,
                contract_version=version,
            )
            return {"output": output, "validation_result": validation_result}

        if inspect.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    return decorator
