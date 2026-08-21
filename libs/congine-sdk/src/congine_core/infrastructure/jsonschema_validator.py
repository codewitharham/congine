"""JSON Schema semantic validator (Layer 4).

:class:`JsonSchemaSemanticValidator` implements
:class:`congine_core.ports.semantic_validator.ISemanticValidator` using
the ``jsonschema`` library.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import jsonschema
from jsonschema import (
    Draft4Validator,
    Draft6Validator,
    Draft7Validator,
    Draft201909Validator,
    Draft202012Validator,
)
from jsonschema.exceptions import SchemaError
from jsonschema.protocols import Validator

from congine_core.models import BreachDetail
from congine_core.exceptions import CongineConfigurationError
from congine_core.pii_sanitize import sanitize_breach_message
from congine_core.security_limits import (
    DEFAULT_SEMANTIC_MAX_BREACHES,
    MAX_PATTERN_LENGTH,
)

#: Maps a normalized ``jsonschema_draft`` config string to its validator class.
#: Keys are stripped of non-alphanumerics and lower-cased (see ``_resolve_draft``)
#: so spellings like ``"Draft 2020-12"``, ``"draft202012"`` and ``"2020"`` unify.
_DRAFT_VALIDATORS: Dict[str, type[Validator]] = {
    "draft202012": Draft202012Validator,
    "202012": Draft202012Validator,
    "2020": Draft202012Validator,
    "draft201909": Draft201909Validator,
    "201909": Draft201909Validator,
    "2019": Draft201909Validator,
    "draft7": Draft7Validator,
    "draft07": Draft7Validator,
    "7": Draft7Validator,
    "07": Draft7Validator,
    "draft6": Draft6Validator,
    "draft06": Draft6Validator,
    "6": Draft6Validator,
    "draft4": Draft4Validator,
    "draft04": Draft4Validator,
    "4": Draft4Validator,
}


def _resolve_draft(draft: str) -> type[Validator]:
    """Map a ``jsonschema_draft`` config string to its validator class.

    Fail-closed: an unrecognised dialect raises :class:`CongineConfigurationError`
    rather than silently defaulting, so a typo'd ``CONGINE_JSONSCHEMA_DRAFT`` is
    surfaced at container construction instead of validating under the wrong spec.
    """
    key = re.sub(r"[^a-z0-9]", "", str(draft).lower())
    try:
        return _DRAFT_VALIDATORS[key]
    except KeyError:
        raise CongineConfigurationError(
            f"Unsupported jsonschema_draft {draft!r}. Supported dialects: "
            "draft202012, draft201909, draft7, draft6, draft4."
        ) from None


class JsonSchemaSemanticValidator:
    """Validate payloads against a JSON Schema, surfacing violations."""

    def __init__(
        self,
        validator_cls: Optional[type[Validator]] = None,
        max_breaches: int = DEFAULT_SEMANTIC_MAX_BREACHES,
        format_checking: bool = False,
        jsonschema_draft: str = "draft202012",
    ) -> None:
        """Args:
        validator_cls: Explicit ``jsonschema`` validator class. When ``None``
            (the container default) the class is resolved from *jsonschema_draft*;
            passing a class directly still works and takes precedence (test seam).
        max_breaches: Hard cap on errors drained from ``iter_errors`` (FIX-03).
        format_checking: When ``False`` (default), format assertions are off.
        jsonschema_draft: Config-driven dialect string (e.g. ``"draft202012"``,
            ``"draft7"``) resolved to a validator class when *validator_cls* is
            ``None``. Unrecognised values fail closed (``CongineConfigurationError``).
        """
        self._validator_cls: type[Validator] = (
            validator_cls
            if validator_cls is not None
            else _resolve_draft(jsonschema_draft)
        )
        self._max_breaches = max_breaches
        self._format_checking = format_checking

    def validate(
        self, payload: dict[str, Any], schema: dict[str, Any]
    ) -> List[BreachDetail]:
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

    def _check_schema_patterns(self, schema: dict[str, Any]) -> List[BreachDetail]:
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
