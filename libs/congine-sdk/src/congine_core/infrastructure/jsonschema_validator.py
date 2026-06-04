"""JSON Schema semantic validator (Layer 4).

:class:`JsonSchemaSemanticValidator` implements
:class:`congine_core.repositories.semantic_validator.ISemanticValidator` using
the ``jsonschema`` library. It drains the validator's *lazy* error stream
(:meth:`jsonschema.protocols.Validator.iter_errors`) so that every field-level
violation in a payload is reported in a single pass, each mapped to a
:class:`BreachDetail` carrying a dotted field path.

It is deliberately tolerant: a malformed schema is reported as a single
``SEMANTIC_SCHEMA`` breach rather than raising, so a bad contract can never crash
the validation hot path.
"""

from __future__ import annotations

from typing import Any, List

import jsonschema
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from congine_core.domain.models import BreachDetail


class JsonSchemaSemanticValidator:
    """Validate payloads against a JSON Schema, surfacing all violations."""

    def __init__(self, validator_cls: type = Draft202012Validator) -> None:
        """Args:
        validator_cls: The ``jsonschema`` validator class to use (defaults to
            Draft 2020-12).
        """
        self._validator_cls = validator_cls

    def validate(self, payload: dict, schema: dict) -> List[BreachDetail]:
        """Return a :class:`BreachDetail` for every JSON Schema violation.

        Args:
            payload: The instance to validate.
            schema: The JSON Schema document.

        Returns:
            One breach per error from ``iter_errors``; an empty list when valid.
            A schema that is itself invalid yields a single ``SEMANTIC_SCHEMA``
            breach instead of raising.
        """
        try:
            self._validator_cls.check_schema(schema)
        except SchemaError as exc:
            return [
                BreachDetail(
                    rule="SEMANTIC_SCHEMA",
                    field="<schema>",
                    message=f"Invalid schema: {exc.message}",
                )
            ]

        # L1: enable `format` assertions (email/uri/ipv4/…) which jsonschema
        # leaves OFF by default — otherwise declared formats are silently ignored.
        format_checker = getattr(self._validator_cls, "FORMAT_CHECKER", None)
        validator = self._validator_cls(schema, format_checker=format_checker)
        breaches: List[BreachDetail] = []
        # iter_errors is a lazy generator; draining it collects ALL violations.
        for error in validator.iter_errors(payload):
            breaches.append(
                BreachDetail(
                    rule="SEMANTIC_SCHEMA",
                    field=self._field_path(error),
                    message=error.message,
                )
            )
        return breaches

    @staticmethod
    def _field_path(error: jsonschema.ValidationError) -> str:
        """Render a ``jsonschema`` error path as dotted notation.

        ``deque(['user', 0, 'name'])`` → ``"user.0.name"``; an empty path (a
        whole-instance violation, e.g. a missing required property) → ``"<root>"``.
        """
        parts: List[Any] = list(error.absolute_path)
        if not parts:
            return "<root>"
        return ".".join(str(p) for p in parts)
