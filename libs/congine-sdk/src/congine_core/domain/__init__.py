"""Layer 2: Pure business logic (domain).

Zero framework dependencies; depends on no other Congine layer.
"""

from congine_core.domain.contract_admission import (
    ContractAdmissionCode,
    ContractAdmissionIssue,
    ContractAdmissionLevel,
    ContractAdmissionResult,
    admit_contract,
)
from congine_core.models import (
    BreachDetail,
    DegradedReason,
    EvaluationStage,
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
    "DegradedReason",
    "EvaluationStage",
    "DriftResult",
    "TelemetryEvent",
    "RuleEngine",
    "LocalValidator",
    "CompositeValidator",
    "IValidator",
    # Contract admission (audit P0-03/P0-04). The boundary that decides whether a
    # contract may become active policy; every schema writer must pass through it.
    "admit_contract",
    "ContractAdmissionResult",
    "ContractAdmissionIssue",
    "ContractAdmissionCode",
    "ContractAdmissionLevel",
    # Contract-loading diagnostic. Every path that writes a schema into
    # ISchemaStorage must call this (audit P0-2 / Q4) — see the module docstring
    # of congine_core.domain.schema_vocabulary.
    "find_unenforced_keywords",
]
