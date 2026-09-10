"""Canonical Congine exceptions.

Tier 1 exposes a single root (:class:`CongineBaseException`) and the canonical
canonical exception types raised throughout the SDK — every concrete error
derives from the root so host code can guard the entire SDK with one
``except CongineBaseException`` clause.

Tier 2 provides semantic aliases that map onto the canonical types for
backwards/ergonomic compatibility. Aliases are assignment-bound to their
canonical class — they are never independent subclasses.

This module has zero internal dependencies and may be imported from any layer.
"""

from __future__ import annotations


# --------------------------------------------------------------------------- #
# Tier 1: Canonical exceptions
# --------------------------------------------------------------------------- #
class CongineBaseException(Exception):
    """Root of the Congine exception tree.

    Every Congine error derives from this class, so a single
    ``except CongineBaseException`` clause guards the whole SDK.
    """


class CongineValidationError(CongineBaseException):
    """Validation logic breach (includes contract violations)."""


class CongineContractNotFoundError(CongineBaseException):
    """Schema/contract not found."""


class CongineConfigurationError(CongineBaseException):
    """Configuration is invalid."""


class CongineSyncError(CongineBaseException):
    """Synchronization with control plane failed."""


class CongineCacheError(CongineBaseException):
    """Cache operation failed."""


class CongineTelemetryError(CongineBaseException):
    """Telemetry publishing failed."""


class CongineLifecycleError(CongineBaseException):
    """Work was requested after an SDK component entered terminal shutdown."""


# --------------------------------------------------------------------------- #
# Capacity signalling (audit P0-06)
# --------------------------------------------------------------------------- #
class LoadShedError(TimeoutError):
    """Work was refused because validation capacity was exhausted.

    Load shedding and deadline expiry both protect the latency budget but mean
    different things:

    ``TimeoutError``
        the validation ran and took too long.
    ``LoadShedError``
        the validation **never ran at all** — the system was saturated.

    Collapsing both into ``TimeoutError`` left callers, telemetry and evidence
    unable to distinguish "evaluated too slowly" from "not evaluated", which is
    the silent non-enforcement this hardening pass exists to remove.

    Two inheritance decisions, both load-bearing:

    - It subclasses **``TimeoutError``** so every existing
      ``except TimeoutError`` handler keeps catching both conditions unchanged.
      Handlers that care catch this type *first*.
    - It deliberately does **not** subclass :class:`CongineBaseException`.
      :class:`ValidateContractUseCase` re-raises ``CongineBaseException``
      untouched so SDK/wiring faults reach the host; a shed load is a runtime
      capacity condition that must *degrade* instead. Deriving from the Congine
      root would silently turn back-pressure into an exception in the host's
      face.

    It lives in Layer 0 rather than beside the executor that raises it because
    Layer 3 must catch it, and an L3 → L4 import would invert the one
    dependency direction the architecture most protects.
    """


# --------------------------------------------------------------------------- #
# Tier 2: Semantic aliases (compatibility shims)
# --------------------------------------------------------------------------- #
# These are assignment-bound to canonical classes, never independent subclasses.
# Note (audit L4): not all are raised by the current SDK — a validation timeout
# degrades to a ``ValidationResult(degraded=True)`` rather than raising
# ``ValidationTimeoutException``, and ``TenantIsolationViolationException`` is a
# forward-compat placeholder. They exist so host ``except`` clauses written
# against these names keep working; prefer the canonical Tier-1 types.
ContractBreachException = CongineValidationError
SchemaCacheMissException = CongineContractNotFoundError
ValidationTimeoutException = CongineValidationError
TenantIsolationViolationException = CongineValidationError


__all__ = [
    # Tier 1
    "CongineBaseException",
    "CongineValidationError",
    "CongineContractNotFoundError",
    "CongineConfigurationError",
    "CongineSyncError",
    "CongineCacheError",
    "CongineTelemetryError",
    "CongineLifecycleError",
    # Capacity signalling (audit P0-06)
    "LoadShedError",
    # Tier 2 aliases
    "ContractBreachException",
    "SchemaCacheMissException",
    "ValidationTimeoutException",
    "TenantIsolationViolationException",
]
