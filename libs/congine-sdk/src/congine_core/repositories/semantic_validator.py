"""Abstraction for semantic (schema-driven) validation (Layer 1).

Defines :class:`ISemanticValidator`, a structural interface for validating a
payload against a full schema specification (e.g. JSON Schema) and returning a
flat list of every field-level violation. Concrete implementations live in
Layer 4 (e.g. the ``jsonschema``-backed validator); the domain composes this
seam via constructor injection without importing any concrete validator.

The :class:`BreachDetail` return type is the shared Layer-2 value object; Layer 1
may reference it because the dependency points inward (L1 → L2 models is along
the inward arrow used by every layer).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Protocol, runtime_checkable

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.domain.models import BreachDetail


@runtime_checkable
class ISemanticValidator(Protocol):
    """Structural interface for full-schema semantic validation."""

    def validate(self, payload: dict, schema: dict) -> "List[BreachDetail]":
        """Validate *payload* against *schema*.

        Args:
            payload: The data to validate.
            schema: The schema specification (e.g. a JSON Schema document).

        Returns:
            A (possibly empty) list of :class:`BreachDetail`, one per violation.
            An empty list means the payload is semantically valid.
        """
        ...
