"""Layer 1: Abstractions (Protocols).

Pure structural interfaces with no implementation logic and no dependency on
any other Congine layer. Holds every cross-layer port — not only repository
ports — so the directory is named ``ports/`` rather than the historical
``repositories/`` (which misled consumers and was renamed before the public
API was published).
"""

from congine_core.ports.circuit_breaker import ICircuitBreaker
from congine_core.ports.contract_repository import IContractRepository
from congine_core.ports.event_bus import IEventBus
from congine_core.ports.lifecycle import IObservable, IStoppable
from congine_core.ports.logger import ILogger
from congine_core.ports.schema_storage import ISchemaStorage
from congine_core.ports.semantic_validator import ISemanticValidator
from congine_core.ports.validation_runner import IValidationRunner

__all__ = [
    "ISchemaStorage",
    "IContractRepository",
    "IEventBus",
    "ILogger",
    "ISemanticValidator",
    "IValidationRunner",
    "ICircuitBreaker",
    # Cross-cutting lifecycle/observability seams (audit Q8)
    "IStoppable",
    "IObservable",
]
