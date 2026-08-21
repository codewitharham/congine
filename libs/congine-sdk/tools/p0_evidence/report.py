"""Shared result type and console rendering for the P0 evidence harnesses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class EvidenceResult:
    """The outcome of one P0 evidence harness.

    Attributes:
        name: Human-readable harness name.
        passed: Whether the constitutional invariant held.
        headline: One-line statement of the measured result.
        details: Supporting measurements, rendered as an indented block.
    """

    name: str
    passed: bool
    headline: str
    details: Dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        mark = "PASS" if self.passed else "FAIL"
        lines = [f"[{mark}] {self.name}: {self.headline}"]
        for key, value in self.details.items():
            lines.append(f"         {key}: {value}")
        return "\n".join(lines)
