"""Domain models (Layer 2).

Pure data structures with zero framework dependencies. :class:`BreachDetail`
and :class:`ValidationResult` are immutable (``frozen=True``); the outbound
:class:`TelemetryEvent` is mutable to allow post-init defaulting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class BreachDetail:
    """A single validation breach.

    Attributes:
        rule: Identifier of the breached rule (e.g. ``"TYPE_MATCH"``).
        field: Offending field name, or ``"<root>"`` for the whole payload.
        message: Optional human-readable detail.
    """

    rule: str
    field: str
    message: Optional[str] = None


@dataclass(frozen=True)
class ValidationResult:
    """Outcome of validating a payload against a schema.

    Attributes:
        status: ``"pass"`` or ``"fail"``.
        breaches: Tuple of :class:`BreachDetail` describing every failure.
        duration_ms: Wall-clock validation time in milliseconds.
        degraded: ``True`` when the result is a timeout/error fallback rather
            than a genuine evaluation.
    """

    status: str
    breaches: Tuple[BreachDetail, ...] = ()
    duration_ms: float = 0.0
    degraded: bool = False

    def is_pass(self) -> bool:
        """Return ``True`` if validation passed."""
        return self.status == "pass"


@dataclass
class TelemetryEvent:
    """A validation telemetry event published fire-and-forget.

    Attributes:
        contract_id: Identifier of the validated contract.
        contract_version: Version of the validated contract.
        status: ``"pass"`` or ``"fail"``.
        duration_ms: Wall-clock validation time in milliseconds.
        breach_details: List of serialized breach mappings.
        created_at: UTC creation timestamp (defaulted if omitted).
    """

    contract_id: str
    contract_version: str
    status: str
    duration_ms: float
    breach_details: List[Dict] = field(default=None)  # type: ignore[assignment]
    created_at: datetime = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.breach_details is None:
            self.breach_details = []
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
