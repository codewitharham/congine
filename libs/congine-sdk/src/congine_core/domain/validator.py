"""Validation logic (Layer 2).

This module is pure business logic: no I/O, no framework dependencies, no
shared mutable state. :class:`RuleEngine` provides six independent, side-effect
free rules. :class:`LocalValidator` composes them (composition, not
inheritance) into an :class:`IValidator`.
"""

from __future__ import annotations

import functools
import time

import re2 as _re2  # type: ignore[import-untyped]
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Tuple,
    runtime_checkable,
)

from congine_core.domain.models import BreachDetail, ValidationResult
from congine_core.security_limits import MAX_PATTERN_LENGTH, MAX_REGEX_VALUE_LENGTH

if TYPE_CHECKING:  # pragma: no cover - typing only
    from congine_core.ports.semantic_validator import ISemanticValidator

# Backward-compatible aliases for tests and external references.
_MAX_PATTERN_LENGTH = MAX_PATTERN_LENGTH
_MAX_REGEX_VALUE_LENGTH = MAX_REGEX_VALUE_LENGTH

# google-re2 is a required core dependency (FIX-02) — linear-time matching.
_RE2_AVAILABLE = True


@functools.lru_cache(maxsize=512)
def _compiled_pattern(pattern: str) -> Any:
    """Compile and cache *pattern* using RE2 (linear-time, no catastrophic backtracking)."""
    return _re2.compile(pattern)


#: Mapping from JSON-schema type names to acceptable Python types. ``bool`` is
#: deliberately excluded from the numeric types (a bool is not a number here).
_JSON_TYPE_MAP: Dict[str, Tuple[type, ...]] = {
    "string": (str,),
    "number": (int, float),
    "integer": (int,),
    "boolean": (bool,),
    "object": (dict,),
    "array": (list,),
}


def _path_present(payload: dict[str, Any], dotted_field: str) -> bool:
    """Return ``True`` if *dotted_field* resolves to a present key in *payload*.

    Supports dot-notation traversal (``"a.b.c"``): each segment must exist and
    every intermediate segment must itself be a mapping. A missing leaf, or a
    non-dict encountered mid-path, means the field is absent. A key whose value
    is ``None`` still counts as *present* (nullability is NULL_GUARD's concern).
    """
    node: Any = payload
    for segment in dotted_field.split("."):
        if not isinstance(node, dict) or segment not in node:
            return False
        node = node[segment]
    return True


def _type_matches(value: Any, json_type: str) -> bool:
    """Return ``True`` if *value* satisfies JSON-schema *json_type*."""
    expected = _JSON_TYPE_MAP.get(json_type)
    if expected is None:
        # Unknown type declaration: do not flag a breach we cannot evaluate.
        return True
    # A bool is an int in Python; reject it for numeric/integer expectations.
    if json_type in ("number", "integer") and isinstance(value, bool):
        return False
    # Only accept an int for "boolean" if it is a genuine bool.
    if json_type == "boolean":
        return isinstance(value, bool)
    return isinstance(value, expected)


class RuleEngine:
    """Pure validation rules — no I/O, no state.

    Every rule is a ``@staticmethod`` returning a (possibly empty) list of
    :class:`BreachDetail`. Rules never raise on well-formed inputs.
    """

    @staticmethod
    def FIELD_PRESENCE(payload: dict[str, Any], required_fields: List[str]) -> List[BreachDetail]:
        """Rule 1: every required field must be present in *payload*.

        Field names may use dot-notation (``"a.b.c"``) to require nested keys;
        a missing leaf — or a non-dict intermediate — is a breach.
        """
        breaches: List[BreachDetail] = []
        for field_name in required_fields:
            if not _path_present(payload, field_name):
                breaches.append(
                    BreachDetail(
                        rule="FIELD_PRESENCE",
                        field=field_name,
                        message=f"Required field '{field_name}' is missing",
                    )
                )
        return breaches

    @staticmethod
    def TYPE_MATCH(payload: dict[str, Any], schema_properties: dict[str, Any]) -> List[BreachDetail]:
        """Rule 2: present fields must match their declared schema type.

        *schema_properties* maps field name to either a JSON-schema property
        mapping (``{"type": "string"}``) or a bare type string (``"string"``).
        """
        breaches: List[BreachDetail] = []
        for field_name, spec in schema_properties.items():
            if field_name not in payload:
                continue
            json_type = spec.get("type") if isinstance(spec, dict) else spec
            if not json_type:
                continue
            value = payload[field_name]
            if value is None:
                # Nullability is NULL_GUARD's concern, not TYPE_MATCH's.
                continue
            if not _type_matches(value, json_type):
                breaches.append(
                    BreachDetail(
                        rule="TYPE_MATCH",
                        field=field_name,
                        message=f"Expected type '{json_type}' for field '{field_name}'",
                    )
                )
        return breaches

    @staticmethod
    def ENUM_VALUES(payload: dict[str, Any], enum_map: dict[str, Any]) -> List[BreachDetail]:
        """Rule 3: present enum fields must hold an allowed value.

        *enum_map* maps field name to a mapping containing an ``"enum"`` list.
        """
        breaches: List[BreachDetail] = []
        for field_name, spec in enum_map.items():
            if field_name not in payload:
                continue
            allowed = spec.get("enum", []) if isinstance(spec, dict) else spec
            if payload[field_name] not in allowed:
                breaches.append(
                    BreachDetail(
                        rule="ENUM_VALUES",
                        field=field_name,
                        message=f"Value for '{field_name}' is not an allowed enum value",
                    )
                )
        return breaches

    @staticmethod
    def RANGE_CHECK(payload: dict[str, Any], range_map: dict[str, Any]) -> List[BreachDetail]:
        """Rule 4: present numeric fields must lie within their range.

        *range_map* maps field name to a mapping with optional ``"min"``/
        ``"max"`` (``"minimum"``/``"maximum"`` are also accepted).
        """
        breaches: List[BreachDetail] = []
        for field_name, spec in range_map.items():
            if field_name not in payload:
                continue
            value = payload[field_name]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                # Non-numeric values are TYPE_MATCH's concern.
                continue
            minimum = (
                spec.get("min", spec.get("minimum")) if isinstance(spec, dict) else None
            )
            maximum = (
                spec.get("max", spec.get("maximum")) if isinstance(spec, dict) else None
            )
            if minimum is not None and value < minimum:
                breaches.append(
                    BreachDetail(
                        rule="RANGE_CHECK",
                        field=field_name,
                        message=f"Value for '{field_name}' is below minimum {minimum}",
                    )
                )
            elif maximum is not None and value > maximum:
                breaches.append(
                    BreachDetail(
                        rule="RANGE_CHECK",
                        field=field_name,
                        message=f"Value for '{field_name}' is above maximum {maximum}",
                    )
                )
        return breaches

    @staticmethod
    def NULL_GUARD(payload: dict[str, Any], null_forbidden: List[str]) -> List[BreachDetail]:
        """Rule 5: listed fields must not be ``None`` when present."""
        breaches: List[BreachDetail] = []
        for field_name in null_forbidden:
            if field_name in payload and payload[field_name] is None:
                breaches.append(
                    BreachDetail(
                        rule="NULL_GUARD",
                        field=field_name,
                        message=f"Field '{field_name}' must not be null",
                    )
                )
        return breaches

    @staticmethod
    def REGEX_PATTERN(payload: dict[str, Any], pattern_map: dict[str, Any]) -> List[BreachDetail]:
        """Rule 6: present string fields must match their regex.

        *pattern_map* maps field name to a mapping containing a ``"pattern"``.
        """
        breaches: List[BreachDetail] = []
        for field_name, spec in pattern_map.items():
            if field_name not in payload:
                continue
            value = payload[field_name]
            if not isinstance(value, str):
                # Non-strings are TYPE_MATCH's concern.
                continue
            pattern = spec.get("pattern") if isinstance(spec, dict) else spec
            if not pattern:
                continue
            # ReDoS guard (H3): schema patterns are untrusted input. Cap pattern
            # and value length (fail-closed), cache compiled patterns, and use a
            # linear-time engine (re2) when available. A pathological pattern can
            # therefore not burn unbounded CPU on the validation hot path.
            if len(pattern) > _MAX_PATTERN_LENGTH:
                breaches.append(
                    BreachDetail(
                        rule="REGEX_PATTERN",
                        field=field_name,
                        message=f"Pattern for '{field_name}' exceeds the safe length budget",
                    )
                )
                continue
            if len(value) > _MAX_REGEX_VALUE_LENGTH:
                breaches.append(
                    BreachDetail(
                        rule="REGEX_PATTERN",
                        field=field_name,
                        message=f"Value for '{field_name}' is too long to match safely",
                    )
                )
                continue
            try:
                matched = _compiled_pattern(pattern).fullmatch(value) is not None
            except _re2.error:
                breaches.append(
                    BreachDetail(
                        rule="REGEX_PATTERN",
                        field=field_name,
                        message=f"Invalid regex pattern for '{field_name}'",
                    )
                )
                continue
            # Anchored full-string match: the entire value must satisfy it.
            if not matched:
                breaches.append(
                    BreachDetail(
                        rule="REGEX_PATTERN",
                        field=field_name,
                        message=f"Value for '{field_name}' does not match pattern",
                    )
                )
        return breaches


@runtime_checkable
class IValidator(Protocol):
    """Interface: a validation strategy."""

    def validate(self, payload: dict[str, Any], schema: dict[str, Any]) -> ValidationResult:
        """Validate *payload* against *schema*."""
        ...


class LocalValidator:
    """Local validation — compose all six rules in-process.

    Rules are injected (composition over inheritance). Each rule extracts its
    own parameters from the schema, so the rule set is fully configurable.
    """

    def __init__(
        self,
        rules: Optional[List[Tuple[str, Callable[..., List[BreachDetail]]]]] = None,
    ) -> None:
        """Constructor injection of rules.

        Args:
            rules: List of ``(rule_name, rule_function)`` tuples. If ``None``,
                all six built-in rules are used.
        """
        if rules is None:
            self.rules: List[Tuple[str, Callable[..., List[BreachDetail]]]] = [
                ("FIELD_PRESENCE", RuleEngine.FIELD_PRESENCE),
                ("TYPE_MATCH", RuleEngine.TYPE_MATCH),
                ("ENUM_VALUES", RuleEngine.ENUM_VALUES),
                ("RANGE_CHECK", RuleEngine.RANGE_CHECK),
                ("NULL_GUARD", RuleEngine.NULL_GUARD),
                ("REGEX_PATTERN", RuleEngine.REGEX_PATTERN),
            ]
        else:
            self.rules = rules

    @staticmethod
    def _extract_params(rule_name: str, schema: dict[str, Any]) -> Any:
        """Derive the parameter a given rule expects from *schema*.

        Supports JSON-schema-style schemas where per-field constraints live
        under ``properties`` and ``required``/``null_forbidden`` are top-level
        lists.
        """
        properties: Dict[str, Any] = schema.get("properties", {})
        if rule_name == "FIELD_PRESENCE":
            return schema.get("required", [])
        if rule_name == "TYPE_MATCH":
            return properties
        if rule_name == "ENUM_VALUES":
            return {
                f: p
                for f, p in properties.items()
                if isinstance(p, dict) and "enum" in p
            }
        if rule_name == "RANGE_CHECK":
            return {
                f: p
                for f, p in properties.items()
                if isinstance(p, dict)
                and ("min" in p or "max" in p or "minimum" in p or "maximum" in p)
            }
        if rule_name == "NULL_GUARD":
            return schema.get("null_forbidden", [])
        if rule_name == "REGEX_PATTERN":
            return {
                f: p
                for f, p in properties.items()
                if isinstance(p, dict) and "pattern" in p
            }
        return {}

    def validate(self, payload: dict[str, Any], schema: dict[str, Any]) -> ValidationResult:
        """Compose all configured rules and return a :class:`ValidationResult`.

        Args:
            payload: The data to validate.
            schema: The contract schema describing constraints.

        Returns:
            A :class:`ValidationResult` whose ``status`` is ``"pass"`` only when
            no rule produced a breach.
        """
        start = time.perf_counter()

        if not isinstance(payload, dict):
            return ValidationResult(
                status="fail",
                breaches=(
                    BreachDetail(
                        rule="TYPE_MATCH",
                        field="<root>",
                        message="Payload must be an object/dict",
                    ),
                ),
                duration_ms=(time.perf_counter() - start) * 1000.0,
            )

        all_breaches: List[BreachDetail] = []
        for rule_name, rule_fn in self.rules:
            params = self._extract_params(rule_name, schema)
            all_breaches.extend(rule_fn(payload, params))

        duration_ms = (time.perf_counter() - start) * 1000.0
        status = "pass" if not all_breaches else "fail"
        return ValidationResult(
            status=status,
            breaches=tuple(all_breaches),
            duration_ms=duration_ms,
        )


class CompositeValidator:
    """Compose a rule-based :class:`IValidator` with an :class:`ISemanticValidator`.

    Both collaborators are constructor-injected (composition, not inheritance);
    the semantic validator is consumed purely through its protocol so the domain
    never imports a concrete (e.g. ``jsonschema``-backed) implementation. The
    result merges every rule breach with every semantic breach into a single
    :class:`ValidationResult`.
    """

    def __init__(
        self,
        rule_validator: "IValidator",
        semantic_validator: "ISemanticValidator",
    ) -> None:
        """Constructor injection of both validation strategies.

        Args:
            rule_validator: The rule-engine validator (e.g. ``LocalValidator``).
            semantic_validator: A full-schema validator injected via its
                Layer-1 protocol.
        """
        self.rule_validator = rule_validator
        self.semantic_validator = semantic_validator

    def validate(self, payload: dict[str, Any], schema: dict[str, Any]) -> ValidationResult:
        """Run both validators and merge their breaches.

        Args:
            payload: The data to validate.
            schema: The contract schema.

        Returns:
            A :class:`ValidationResult` that fails if *either* validator finds a
            breach; ``duration_ms`` spans the combined run and ``degraded``
            propagates from the rule validator.
        """
        start = time.perf_counter()
        rule_result = self.rule_validator.validate(payload, schema)
        breaches: List[BreachDetail] = list(rule_result.breaches)
        breaches.extend(self.semantic_validator.validate(payload, schema))
        duration_ms = (time.perf_counter() - start) * 1000.0
        status = "pass" if not breaches else "fail"
        return ValidationResult(
            status=status,
            breaches=tuple(breaches),
            duration_ms=duration_ms,
            degraded=rule_result.degraded,
        )
