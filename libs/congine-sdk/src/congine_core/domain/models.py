"""Domain models (Layer 2).

Pure data structures with zero framework dependencies. :class:`BreachDetail`
and :class:`ValidationResult` are immutable (``frozen=True``); the outbound
:class:`TelemetryEvent` is mutable to allow post-init defaulting.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Optional, Tuple


class DegradedReason(StrEnum):
    """Why CONGINE could not complete a deterministic evaluation (audit P0-05/P0-06).

    These values are **machine-facing** and cross process boundaries: they are
    written to structured logs and to :class:`TelemetryEvent`, and the planned
    MCP surface and durable evidence store will consume them. Downstream
    behaviour must switch on these values, never on human-readable message text.

    :class:`enum.StrEnum` rather than ``(str, Enum)`` is deliberate. Both
    serialise correctly through :func:`json.dumps`, but a plain ``(str, Enum)``
    renders as ``"DegradedReason.LOAD_SHED"`` under ``str()``, f-strings and
    ``%s`` — so a single interpolation anywhere on the logging path would leak
    an implementation name onto the wire. ``StrEnum`` renders as the value on
    every path.

    ``TIMEOUT``, ``RESOURCE_ERROR`` and ``INTERNAL_ERROR`` existed as bare
    string literals before this enum and keep their exact wire values, so
    existing comparisons such as ``degraded_reason == "timeout"`` continue to
    hold.

    Note what is deliberately absent: a *measurable* payload or schema that
    exceeds its budget is a genuine deterministic verdict and produces an
    ``INPUT_BOUNDS`` breach, not a degradation. Only the inability to reach a
    verdict belongs here.
    """

    #: The validation callable exceeded ``validation_timeout_ms``.
    TIMEOUT = "timeout"
    #: The bounded executor was saturated, so the work never ran (audit P0-06).
    #: Distinct from :attr:`TIMEOUT`: "we did not evaluate" rather than
    #: "we evaluated too slowly".
    LOAD_SHED = "load_shed"
    #: ``MemoryError`` / ``RecursionError`` raised inside the validator.
    RESOURCE_ERROR = "resource_error"
    #: Any other unexpected exception raised inside the validator.
    INTERNAL_ERROR = "internal_error"
    #: The payload could not be measured (not serialisable), so its size bound
    #: could not be enforced (audit P0-02).
    INVALID_PAYLOAD = "invalid_payload"
    #: The cached schema could not be measured, so its size bound could not be
    #: enforced (audit P0-02).
    INVALID_CONTRACT = "invalid_contract"


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
        degraded_reason: Optional :class:`DegradedReason` when ``degraded`` is
            ``True``. Typed, but ``StrEnum``-backed, so it compares equal to its
            wire value (``result.degraded_reason == "timeout"``).
    """

    status: str
    breaches: Tuple[BreachDetail, ...] = ()
    duration_ms: float = 0.0
    degraded: bool = False
    degraded_reason: Optional[str] = None

    def is_pass(self) -> bool:
        """Return ``True`` if validation passed.

        .. warning:: This alone cannot tell you whether the policy was actually
           evaluated. A degraded result carries ``status="fail"`` with **zero**
           breaches, so ``is_pass()`` is ``False`` both when the output violated
           the contract and when CONGINE never managed to check it. Ask
           :meth:`is_enforced` first.
        """
        return self.status == "pass"

    def is_enforced(self) -> bool:
        """Return ``True`` if CONGINE reached a real deterministic judgment (P0-05).

        This is the "was the policy actually evaluated?" question, kept separate
        from "did the output conform?". The two together give callers the three
        states that matter::

            is_enforced() and is_pass()          -> evaluated, conforming
            is_enforced() and not is_pass()      -> evaluated, violated
            not is_enforced()                    -> NOT evaluated; see
                                                    degraded_reason

        The third state is the dangerous one, and it is why this method exists:
        a caller that inspects only :meth:`is_pass` cannot distinguish a genuine
        contract violation from a validator that timed out, was load-shed, or
        crashed — and would therefore believe a policy was enforced when it was
        not.

        Enterprise postures should treat "not enforced" as unknown conformance
        rather than as a pass, and strict deployments should refuse to proceed
        on it.
        """
        return not self.degraded


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
