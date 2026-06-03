"""Canonical Congine exceptions.

Tier 1 exposes the six canonical exception types raised throughout the SDK.
Tier 2 provides semantic aliases that map onto the canonical types for
backwards/ergonomic compatibility.

This module has zero internal dependencies and may be imported from any layer.
"""

from __future__ import annotations


# --------------------------------------------------------------------------- #
# Tier 1: Canonical exceptions
# --------------------------------------------------------------------------- #
class CongineValidationError(Exception):
    """Validation logic breach (includes contract violations)."""


class CongineContractNotFoundError(Exception):
    """Schema/contract not found."""


class CongineConfigurationError(Exception):
    """Configuration is invalid."""


class CongineSyncError(Exception):
    """Synchronization with control plane failed."""


class CongineCacheError(Exception):
    """Cache operation failed."""


class CongineTelemetryError(Exception):
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
