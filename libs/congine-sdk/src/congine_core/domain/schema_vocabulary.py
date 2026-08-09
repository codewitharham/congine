"""Rule-engine schema vocabulary (Layer 2).

Pure domain knowledge that mirrors what :meth:`LocalValidator._extract_params`
in :mod:`congine_core.domain.validator` actually reads. It lets callers detect
contract keywords the rule engine will silently ignore under default (rule-only)
configuration, so the "false-safety" foot-gun (audit F-2 / P0-2) becomes an
observable warning instead of a silent pass.

This module is pure: no I/O, no logging, no config. It only inspects a schema
mapping and returns the ``field.keyword`` paths the rule engine does not enforce.
It deliberately does **not** import ``validator`` — the vocabulary is mirrored
here and guarded against drift by ``tests/unit/test_schema_vocabulary.py``.

.. important:: **Calling this is a required step for every contract loader.**

   The warning it powers is the *only* signal a user gets that part of their
   contract is decorative. It is not enough to scan on one path: today
   :meth:`SyncContractsUseCase._prime_cache` is the only writer into
   :class:`ISchemaStorage`, but every entry point on the roadmap (MCP server,
   CLI, direct schema injection) will add another, and each one that forgets
   silently reopens the false-safety foot-gun (audit Q4).

   **The rule: any code path that writes a schema into ``ISchemaStorage`` must
   run this scan and surface the result.** It is enforced by
   ``tests/unit/test_schema_vocabulary.py::test_every_schema_writer_scans_for_unenforced_keywords``,
   which fails when a new ``put(...)`` call site appears in a module that does
   not reference the scan.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Top-level schema keys the rule engine reads (mirror of the keys consulted in
# ``LocalValidator._extract_params``): ``required``, ``null_forbidden`` and the
# ``properties`` map itself.
ENFORCED_TOP_LEVEL_KEYWORDS: frozenset[str] = frozenset(
    {"properties", "required", "null_forbidden"}
)

# Per-property keys the rule engine reads (``type`` via TYPE_MATCH, ``enum`` via
# ENUM_VALUES, ``min``/``max``/``minimum``/``maximum`` via RANGE_CHECK,
# ``pattern`` via REGEX_PATTERN).
ENFORCED_PROPERTY_KEYWORDS: frozenset[str] = frozenset(
    {"type", "enum", "min", "max", "minimum", "maximum", "pattern"}
)

# Documentation/metadata keywords that never carry enforcement intent — a
# contract may use them freely and must not be warned about. Applied at both the
# top level and per property.
IGNORABLE_METADATA_KEYWORDS: frozenset[str] = frozenset(
    {
        "description",
        "title",
        "default",
        "examples",
        "$comment",
        "deprecated",
        "readOnly",
        "writeOnly",
        "$schema",
        "$id",
    }
)

# JSON-schema type names the rule engine's ``_type_matches`` understands (mirror
# of ``validator._JSON_TYPE_MAP`` keys). A ``type`` value outside this set is
# read but not meaningfully enforced, so it is surfaced at load.
#
# Union types (``["string", "null"]``) ARE enforced — every member must be a
# recognised name. Before union support landed (Q2), a list declaration raised
# ``TypeError`` inside the rule engine and degraded every validation against
# that contract; it is now a first-class, enforced spelling.
RECOGNISED_TYPE_NAMES: frozenset[str] = frozenset(
    {"string", "number", "integer", "boolean", "object", "array", "null"}
)

#: Field segment used for top-level keywords, matching the ``field="<root>"``
#: convention already used in ``LocalValidator.validate``.
_ROOT = "<root>"

#: Cap on reported paths so a pathological schema cannot produce an unbounded log
#: line (consistent with the codebase's "cap everything" posture).
_MAX_REPORTED = 20

__all__ = [
    "ENFORCED_TOP_LEVEL_KEYWORDS",
    "ENFORCED_PROPERTY_KEYWORDS",
    "IGNORABLE_METADATA_KEYWORDS",
    "RECOGNISED_TYPE_NAMES",
    "find_unenforced_keywords",
]


def _type_is_enforceable(value: Any) -> bool:
    """Return ``True`` only for a ``type`` value the rule engine can honour.

    Accepts a single recognised name, or a **non-empty union** (list/tuple) whose
    members are all recognised names — TYPE_MATCH evaluates unions member-wise.
    An empty union declares nothing and is reported, as is any union containing
    an unrecognised name (such a union matches everything, so it enforces
    nothing).
    """
    if isinstance(value, (list, tuple)):
        return bool(value) and all(
            isinstance(member, str) and member in RECOGNISED_TYPE_NAMES
            for member in value
        )
    return isinstance(value, str) and value in RECOGNISED_TYPE_NAMES


def find_unenforced_keywords(schema: Mapping[str, Any]) -> list[str]:
    """Return a sorted list of ``field.keyword`` paths the rule engine will NOT enforce.

    Allowlist semantics: any key not in the enforced set (minus a metadata
    allowlist) is reported, so keywords nobody thought to blocklist are still
    caught as JSON Schema evolves. Reports keyword *names* only, never values.

    Defensive and non-recursive by design:

    - Malformed input never raises: a non-mapping *schema*, a non-mapping
      ``properties``, or a non-mapping property spec is skipped, not coerced.
    - Nested subtrees are not enumerated: a property carrying ``properties`` or
      ``items`` is reported once at that field; descending would add noise, not
      information (the whole subtree is unenforced regardless).
    - A top-level ``type`` of ``"object"`` is treated as honoured (the rule
      engine already rejects non-dict payloads); any other top-level ``type`` is
      reported.
    - A property ``type`` is reported only when the rule engine cannot honour it:
      an unrecognised name, an empty union, or a union containing an
      unrecognised name. A well-formed union such as ``["string", "null"]`` is
      enforced and is **not** reported.

    The result is de-duplicated, sorted (deterministic), and capped at
    ``_MAX_REPORTED`` with a trailing ``"... (+N more)"`` marker when truncated.
    """
    if not isinstance(schema, Mapping):
        return []

    findings: list[str] = []

    # --- top-level keys --- #
    for key, value in schema.items():
        if key in ENFORCED_TOP_LEVEL_KEYWORDS or key in IGNORABLE_METADATA_KEYWORDS:
            continue
        if key == "type":
            # "object" is effectively honoured; any other top-level type is not.
            if value != "object":
                findings.append(f"{_ROOT}.type")
            continue
        findings.append(f"{_ROOT}.{key}")

    # --- per-property keys (no recursion into nested schemas) --- #
    properties = schema.get("properties")
    if isinstance(properties, Mapping):
        for field_name, spec in properties.items():
            if not isinstance(spec, Mapping):
                # A bare-string / None spec carries no enforceable constraint and
                # TYPE_MATCH tolerates it — nothing to warn about.
                continue
            for key, value in spec.items():
                if key in IGNORABLE_METADATA_KEYWORDS:
                    continue
                if key == "type":
                    if not _type_is_enforceable(value):
                        findings.append(f"{field_name}.type")
                    continue
                if key in ENFORCED_PROPERTY_KEYWORDS:
                    continue
                findings.append(f"{field_name}.{key}")

    unique = sorted(set(findings))
    if len(unique) > _MAX_REPORTED:
        extra = len(unique) - _MAX_REPORTED
        unique = unique[:_MAX_REPORTED] + [f"... (+{extra} more)"]
    return unique
