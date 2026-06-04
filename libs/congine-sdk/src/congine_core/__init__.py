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
    ISemanticValidator,
)

# Layer 2: Domain
from congine_core.domain import (
    BreachDetail,
    CompositeValidator,
    DriftResult,
    LocalValidator,
    RuleEngine,
    TelemetryEvent,
    ValidationResult,
)

# Layer 3: Use cases
from congine_core.usecases import SyncContractsUseCase, ValidateContractUseCase

# Layer 4: Infrastructure
from congine_core.infrastructure import (
    BackgroundSyncWorker,
    HttpContractRepository,
    JsonSchemaSemanticValidator,
    KSDriftEngine,
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
    "ISemanticValidator",
    # Domain
    "BreachDetail",
    "ValidationResult",
    "DriftResult",
    "TelemetryEvent",
    "RuleEngine",
    "LocalValidator",
    "CompositeValidator",
    # Use cases
    "ValidateContractUseCase",
    "SyncContractsUseCase",
    # Infrastructure
    "LFUCache",
    "HttpContractRepository",
    "QueueEventBus",
    "StructuredLogger",
    "ValidationTimer",
    "BackgroundSyncWorker",
    "JsonSchemaSemanticValidator",
    "KSDriftEngine",
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
