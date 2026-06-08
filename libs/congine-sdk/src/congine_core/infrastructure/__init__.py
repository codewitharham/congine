"""Layer 4: Concrete implementations (infrastructure).

Depends on: config, exceptions, domain (and the Layer 1 protocols it fulfils).
"""

from congine_core.infrastructure.background_sync import BackgroundSyncWorker
from congine_core.infrastructure.bounded_executor import BoundedValidationExecutor
from congine_core.infrastructure.circuit_breaker import CircuitBreaker
from congine_core.infrastructure.file_contract_repository import (
    FileContractRepository,
)
from congine_core.infrastructure.http_contract_repository import HttpContractRepository
from congine_core.infrastructure.jsonschema_validator import (
    JsonSchemaSemanticValidator,
)
from congine_core.infrastructure.ks_drift import KSDriftEngine
from congine_core.infrastructure.lfu_cache import LFUCache
from congine_core.infrastructure.logger import StructuredLogger
from congine_core.infrastructure.queue_event_bus import QueueEventBus

# Intentionally NOT exported (audit D-3/D-11): ValidationTimer.
# Wiring it directly defeats the load-shedding / async-symmetric guarantees of
# BoundedValidationExecutor. It remains importable from
# `congine_core.infrastructure.timer` for legacy reference only.

__all__ = [
    "LFUCache",
    "HttpContractRepository",
    "FileContractRepository",
    "QueueEventBus",
    "StructuredLogger",
    "BackgroundSyncWorker",
    "JsonSchemaSemanticValidator",
    "KSDriftEngine",
    "BoundedValidationExecutor",
    "CircuitBreaker",
]
