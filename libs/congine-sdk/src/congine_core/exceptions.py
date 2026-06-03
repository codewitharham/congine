"""Canonical Congine exceptions.

Tier 1 exposes a single root (:class:`CongineBaseException`) and the six
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


# --------------------------------------------------------------------------- #
# Tier 2: Semantic aliases (for backwards compatibility)
# --------------------------------------------------------------------------- #
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
    # Tier 2 aliases
    "ContractBreachException",
    "SchemaCacheMissException",
    "ValidationTimeoutException",
    "TenantIsolationViolationException",
]
