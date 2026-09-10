"""The ``@congine_guard`` decorator (Layer 5).

Wraps a function so its output is validated against a Congine contract via the
:class:`ValidateContractUseCase`. Both synchronous and ``async`` callables are
supported.

Return modes (audit M5) — the wrapped function need no longer be rewritten to
unwrap an envelope, and non-dict outputs are supported via an ``extractor``:

- ``"envelope"`` (default): returns ``{"output": ..., "validation_result": ...}``.
- ``"output"``: returns the original output unchanged (validation still runs and
  is enforced by the use case's ``fail_mode``).
- ``"raise"``: returns the original output, but raises
  :class:`CongineValidationError` if validation fails.
"""

from __future__ import annotations

import functools
import inspect
from typing import Any, Callable, Optional

from congine_core.adapters.dependency_injection import ServiceContainer
from congine_core.exceptions import CongineValidationError

_MODES = ("envelope", "output", "raise")


def congine_guard(
    contract_id: str,
    version: str = "latest",
    container: Optional[ServiceContainer] = None,
    mode: str = "envelope",
    extractor: Optional[Callable[[Any], dict[str, Any]]] = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Validate a function's output against a Congine contract.

    Args:
        contract_id: Contract identifier (e.g. ``"sentiment-v1"``).
        version: Contract version recorded in telemetry (default ``"latest"``).
        container: A :class:`ServiceContainer`. When ``None``, the process-wide
            shared default (:meth:`ServiceContainer.get_default`) is resolved
            lazily at call time — every default-guarded function shares ONE
            cache, telemetry worker, and validation pool. Production code should
            pass an explicit, bootstrapped ``container=``.
        mode: ``"envelope"`` | ``"output"`` | ``"raise"`` (see module docstring).
        extractor: Optional callable mapping the raw output to the ``dict``
            payload to validate (e.g. wrap a string completion as
            ``{"text": out}``). Required when the function returns a non-dict.

    Returns:
        A decorator producing the appropriate wrapper for *mode*.
    """
    if mode not in _MODES:
        raise ValueError(f"mode must be one of {_MODES}, got {mode!r}")

    def _resolve() -> ServiceContainer:
        return container if container is not None else ServiceContainer.get_default()

    def _payload(output: Any) -> Any:
        return extractor(output) if extractor is not None else output

    def _finish(output: Any, validation_result: Any) -> Any:
        if mode == "raise":
            if not validation_result.is_pass():
                raise CongineValidationError(
                    f"Contract {contract_id} validation failed"
                )
            return output
        if mode == "output":
            return output
        return {"output": output, "validation_result": validation_result}

    def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(fn)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = _resolve()
            ctx.ensure_open()
            output = fn(*args, **kwargs)
            validation_result = ctx.validate_contract_usecase.execute(
                payload=_payload(output),
                contract_id=contract_id,
                contract_version=version,
            )
            return _finish(output, validation_result)

        @functools.wraps(fn)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            ctx = _resolve()
            ctx.ensure_open()
            output = await fn(*args, **kwargs)
            # Validation is synchronous and CPU-bound. ``execute_async`` runs it
            # OFF the event loop (H2) AND through the bounded, load-shedding pool
            # with the same timeout the sync path uses (H1) — never the raw,
            # unbounded run_in_executor that silently bypassed both guarantees.
            validation_result = await ctx.validate_contract_usecase.execute_async(
                payload=_payload(output),
                contract_id=contract_id,
                contract_version=version,
            )
            return _finish(output, validation_result)

        if inspect.iscoroutinefunction(fn):
            return async_wrapper
        return sync_wrapper

    return decorator
