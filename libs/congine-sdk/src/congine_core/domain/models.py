"""Domain models (Layer 2).

Pure data structures with zero framework dependencies. :class:`BreachDetail`
and :class:`ValidationResult` are immutable (``frozen=True``); the outbound
:class:`TelemetryEvent` is mutable to allow post-init defaulting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Tuple


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
        degraded_reason: Optional machine-readable tag when ``degraded`` is
            ``True`` (e.g. ``"timeout"``, ``"internal_error"``).
    """

    status: str
    breaches: Tuple[BreachDetail, ...] = ()
    duration_ms: float = 0.0
    degraded: bool = False
    degraded_reason: Optional[str] = None

    def is_pass(self) -> bool:
        """Return ``True`` if validation passed."""
        return self.status == "pass"


@dataclass(frozen=True)
class DriftResult:
    """Outcome of a two-sample drift test between a reference and a sample.

    Attributes:
        statistic: The Kolmogorov-Smirnov D statistic (max ECDF distance).
        p_value: Asymptotic p-value for the two-sample KS test.
        drift_detected: ``True`` when drift exceeds the configured threshold.
        n_reference: Number of reference observations used.
        n_sample: Number of current-sample observations used.
    """

    statistic: float
    p_value: float
    drift_detected: bool
    n_reference: int
    n_sample: int


@dataclass(frozen=True)
class TelemetryEvent:
    """A validation telemetry event published fire-and-forget.

    Frozen (audit L7): once enqueued for the background drain worker, a caller
    cannot mutate it and race the worker. Post-init defaulting uses
    ``object.__setattr__`` as required for frozen dataclasses.

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
    breach_details: list[dict[str, Any]] = field(default=None)  # type: ignore[arg-type]
    created_at: datetime = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.breach_details is None:
            object.__setattr__(self, "breach_details", [])
        if self.created_at is None:
            object.__setattr__(self, "created_at", datetime.now(timezone.utc))
