"""Layer 2: Pure business logic (domain).

Zero framework dependencies; depends on no other Congine layer.
"""

from congine_core.domain.models import (
    BreachDetail,
    DriftResult,
    TelemetryEvent,
    ValidationResult,
)
from congine_core.domain.schema_vocabulary import find_unenforced_keywords
from congine_core.domain.validator import (
    CompositeValidator,
    IValidator,
    LocalValidator,
    RuleEngine,
)

__all__ = [
    "BreachDetail",
    "ValidationResult",
    "DriftResult",
    "TelemetryEvent",
    "RuleEngine",
    "LocalValidator",
    "CompositeValidator",
    "IValidator",
    # Contract-loading diagnostic. Every path that writes a schema into
    # ISchemaStorage must call this (audit P0-2 / Q4) — see the module docstring
    # of congine_core.domain.schema_vocabulary.
    "find_unenforced_keywords",
]
