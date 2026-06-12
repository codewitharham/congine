"""Congine SDK — public API.

Re-exports the supported surface across all five layers plus configuration and
exceptions. Internal modules should be imported from their layer packages; this
module is the stable entry point for SDK consumers.
"""

# Layer 1: Abstractions
from congine_core.ports import (
    ICircuitBreaker,
    IContractRepository,
    IEventBus,
    ILogger,
    ISchemaStorage,
    ISemanticValidator,
    IValidationRunner,
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
    BoundedValidationExecutor,
    CircuitBreaker,
    FileContractRepository,
    HttpContractRepository,
    JsonSchemaSemanticValidator,
    KSDriftEngine,
    LFUCache,
    NoOpEventBus,
    QueueEventBus,
    StructuredLogger,
)

# Layer 5: Adapters
from congine_core.adapters import ServiceContainer, congine_guard

# Config & exceptions
from congine_core.config import CongineConfig, DeploymentMode, FailMode, Region
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

# Single-sourced from pyproject.toml via the installed distribution's metadata.
# The fallback covers editable installs where the distribution metadata is
# unavailable (e.g. running from a source checkout without `pip install -e .`).
try:
    from importlib.metadata import (
        PackageNotFoundError as _PackageNotFoundError,
    )
    from importlib.metadata import version as _pkg_version

    try:
        __version__ = _pkg_version("congine-sdk")
    except _PackageNotFoundError:
        __version__ = "0.0.0+unknown"
except ImportError:  # pragma: no cover - importlib.metadata is stdlib in 3.10+
    __version__ = "0.0.0+unknown"

__all__ = [
    # Abstractions
    "ISchemaStorage",
    "IContractRepository",
    "IEventBus",
    "ILogger",
    "ISemanticValidator",
    "IValidationRunner",
    "ICircuitBreaker",
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
    "FileContractRepository",
    "QueueEventBus",
    "NoOpEventBus",
    "StructuredLogger",
    "BackgroundSyncWorker",
    "BoundedValidationExecutor",
    "CircuitBreaker",
    "JsonSchemaSemanticValidator",
    "KSDriftEngine",
    # Adapters
    "ServiceContainer",
    "congine_guard",
    # Config
    "CongineConfig",
    "Region",
    "FailMode",
    "DeploymentMode",
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
