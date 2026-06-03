"""Layer 1: Abstractions (Protocols).

Pure structural interfaces with no implementation logic and no dependency on
any other Congine layer.
"""

from congine_core.repositories.contract_repository import IContractRepository
from congine_core.repositories.event_bus import IEventBus
from congine_core.repositories.logger import ILogger
from congine_core.repositories.schema_storage import ISchemaStorage

__all__ = [
    "ISchemaStorage",
    "IContractRepository",
    "IEventBus",
    "ILogger",
]
