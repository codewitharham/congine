"""Compatibility re-export of the canonical value contracts (Layer 2 path).

The types below moved to :mod:`congine_core.models` (L0 kernel) in P1; see that
module's docstring for the rationale. This module is retained so the historical
``congine_core.domain.models`` import path keeps working for existing callers.

**This is a compatibility path, not an architectural escape hatch.** The
architecture gate resolves ``congine_core.domain.models`` by its directory, so
importing through here still counts as an **L2** dependency. L1 ports and L4
infrastructure must import :mod:`congine_core.models` directly; routing through
this module is a layer violation and is rejected by
``tools/check_architecture.py``.
"""

from __future__ import annotations

from congine_core.models import (
    BreachDetail,
    DegradedReason,
    DriftResult,
    TelemetryEvent,
    ValidationResult,
)

__all__ = [
    "BreachDetail",
    "DegradedReason",
    "DriftResult",
    "TelemetryEvent",
    "ValidationResult",
]
