"""JSON Schema semantic validator (Layer 4).

:class:`JsonSchemaSemanticValidator` implements
:class:`congine_core.ports.semantic_validator.ISemanticValidator` using
the ``jsonschema`` library.
"""

from __future__ import annotations

from typing import Any, List

import jsonschema
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from congine_core.domain.models import BreachDetail
from congine_core.pii_sanitize import sanitize_breach_message
from congine_core.security_limits import (
    DEFAULT_SEMANTIC_MAX_BREACHES,
    MAX_PATTERN_LENGTH,
)


class JsonSchemaSemanticValidator:
    """Validate payloads against a JSON Schema, surfacing violations."""

    def __init__(
        self,
        validator_cls: type = Draft202012Validator,
        max_breaches: int = DEFAULT_SEMANTIC_MAX_BREACHES,
        format_checking: bool = False,
    ) -> None:
        """Args:
        validator_cls: The ``jsonschema`` validator class to use.
        max_breaches: Hard cap on errors drained from ``iter_errors`` (FIX-03).
        format_checking: When ``False`` (default), format assertions are off.
        """
        self._validator_cls = validator_cls
        self._max_breaches = max_breaches
        self._format_checking = format_checking

    def validate(self, payload: dict, schema: dict) -> List[BreachDetail]:
        """Return a :class:`BreachDetail` for every JSON Schema violation."""
        pattern_breaches = self._check_schema_patterns(schema)
        if pattern_breaches:
            return pattern_breaches

        try:
            self._validator_cls.check_schema(schema)
        except SchemaError as exc:
            return [
                BreachDetail(
                    rule="SEMANTIC_SCHEMA",
                    field="<schema>",
                    message=sanitize_breach_message(f"Invalid schema: {exc.message}"),
                )
            ]

        format_checker = None
        if self._format_checking:
            format_checker = getattr(self._validator_cls, "FORMAT_CHECKER", None)
        validator = self._validator_cls(schema, format_checker=format_checker)
        breaches: List[BreachDetail] = []
        truncated = False
        for error in validator.iter_errors(payload):
            if len(breaches) >= self._max_breaches:
                truncated = True
                break
            breaches.append(
                BreachDetail(
                    rule="SEMANTIC_SCHEMA",
                    field=self._field_path(error),
                    message=sanitize_breach_message(error.message),
                )
            )
        if truncated:
            breaches.append(
                BreachDetail(
                    rule="SEMANTIC_TRUNCATED",
                    field="<root>",
                    message=(
                        f"Semantic validation truncated after {self._max_breaches} "
                        "breaches"
                    ),
                )
            )
        return breaches

    def _check_schema_patterns(self, schema: dict) -> List[BreachDetail]:
        """Reject schemas whose property patterns exceed the safe length budget."""
        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            return []
        breaches: List[BreachDetail] = []
        for field_name, spec in properties.items():
            if not isinstance(spec, dict):
                continue
            pattern = spec.get("pattern")
            if isinstance(pattern, str) and len(pattern) > MAX_PATTERN_LENGTH:
                breaches.append(
                    BreachDetail(
                        rule="SEMANTIC_SCHEMA",
                        field=str(field_name),
                        message=(
                            f"Pattern for '{field_name}' exceeds the safe length budget"
                        ),
                    )
                )
        return breaches

    @staticmethod
    def _field_path(error: jsonschema.ValidationError) -> str:
        parts: List[Any] = list(error.absolute_path)
        if not parts:
            return "<root>"
        return ".".join(str(p) for p in parts)
