"""Congine SDK — public API.

Re-exports the supported surface across all five layers plus configuration and
exceptions. Internal modules should be imported from their layer packages; this
module is the stable entry point for SDK consumers.
"""

# Layer 1: Abstractions
from congine_core.repositories import (
    IContractRepository,
    IEventBus,
    ILogger,
    ISchemaStorage,
)

# Layer 2: Domain
from congine_core.domain import (
    BreachDetail,
    LocalValidator,
    RuleEngine,
    TelemetryEvent,
    ValidationResult,
)

# Layer 3: Use cases
from congine_core.usecases import ValidateContractUseCase

# Layer 4: Infrastructure
from congine_core.infrastructure import (
    HttpContractRepository,
    LFUCache,
    QueueEventBus,
    StructuredLogger,
    ValidationTimer,
)

# Layer 5: Adapters
from congine_core.adapters import ServiceContainer, congine_guard

# Config & exceptions
from congine_core.config import CongineConfig, FailMode, Region
from congine_core.exceptions import (
    CongineBaseException,
    CongineCacheError,
    CongineConfigurationError,
    CongineContractNotFoundError,
    CongineSyncError,
    CongineTelemetryError,
    CongineValidationError,
    ContractBreachException,
    SchemaCacheMissException,
    TenantIsolationViolationException,
    ValidationTimeoutException,
)

__version__ = "0.1.0"

__all__ = [
    # Abstractions
    "ISchemaStorage",
    "IContractRepository",
    "IEventBus",
    "ILogger",
    # Domain
    "BreachDetail",
    "ValidationResult",
    "TelemetryEvent",
    "RuleEngine",
    "LocalValidator",
    # Use cases
    "ValidateContractUseCase",
    # Infrastructure
    "LFUCache",
    "HttpContractRepository",
    "QueueEventBus",
    "StructuredLogger",
    "ValidationTimer",
    # Adapters
    "ServiceContainer",
    "congine_guard",
    # Config
    "CongineConfig",
    "Region",
    "FailMode",
    # Exceptions
    "CongineBaseException",
    "CongineValidationError",
    "CongineContractNotFoundError",
    "CongineConfigurationError",
    "CongineSyncError",
    "CongineCacheError",
    "CongineTelemetryError",
    "ContractBreachException",
    "SchemaCacheMissException",
    "ValidationTimeoutException",
    "TenantIsolationViolationException",
]
