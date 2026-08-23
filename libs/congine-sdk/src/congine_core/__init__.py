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
    IObservable,
    ISchemaStorage,
    ISemanticValidator,
    IStoppable,
    IValidationRunner,
)

# Layer 2: Domain
from congine_core.domain import (
    BreachDetail,
    CompositeValidator,
    ContractAdmissionCode,
    ContractAdmissionIssue,
    ContractAdmissionLevel,
    ContractAdmissionResult,
    DegradedReason,
    EvaluationStage,
    DriftResult,
    LocalValidator,
    RuleEngine,
    TelemetryEvent,
    ValidationResult,
    admit_contract,
    find_unenforced_keywords,
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
from congine_core.config import (
    CongineConfig,
    ContractAdmissionMode,
    ContractSource,
    DeploymentMode,
    FailMode,
    Region,
)
from congine_core.exceptions import (
    CongineBaseException,
    CongineCacheError,
    CongineConfigurationError,
    CongineContractNotFoundError,
    CongineLifecycleError,
    CongineSyncError,
    CongineTelemetryError,
    CongineValidationError,
    ContractBreachException,
    LoadShedError,
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
    "IStoppable",
    "IObservable",
    # Domain
    "BreachDetail",
    "ValidationResult",
    "DegradedReason",
    "EvaluationStage",
    "DriftResult",
    "TelemetryEvent",
    "RuleEngine",
    "LocalValidator",
    "CompositeValidator",
    # Contract admission (audit P0-03/P0-04). Exported so external loaders can
    # run the same safety check the SDK's own loader does — it was previously
    # reachable only via a private module path.
    "admit_contract",
    "ContractAdmissionResult",
    "ContractAdmissionIssue",
    "ContractAdmissionCode",
    "ContractAdmissionLevel",
    "find_unenforced_keywords",
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
    "ContractSource",
    "ContractAdmissionMode",
    # Exceptions
    "CongineBaseException",
    "CongineValidationError",
    "CongineContractNotFoundError",
    "CongineConfigurationError",
    "CongineSyncError",
    "CongineCacheError",
    "CongineTelemetryError",
    "CongineLifecycleError",
    # Capacity signalling (audit P0-06). Subclasses TimeoutError, so existing
    # handlers keep working; catch it first to distinguish "not evaluated" from
    # "evaluated too slowly".
    "LoadShedError",
    "ContractBreachException",
    "SchemaCacheMissException",
    "ValidationTimeoutException",
    "TenantIsolationViolationException",
]
