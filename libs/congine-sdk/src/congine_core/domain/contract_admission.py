"""Contract admission (Layer 2).

The boundary that decides whether a contract is fit to become **active policy**
(audit P0-03 / P0-04). It answers one question:

    Can CONGINE determine exactly what this contract means, and will some active
    evaluator actually execute every clause in it?

If the answer is no, the contract is a **publication error** and must never reach
the schema cache. Discovering the problem during every subsequent validation is
too late, and — worse — the current engine's failure shapes are quiet: an unknown
type name disables checking for that field, a dotted property key silently
matches nothing, an unsupported keyword is ignored outright. Each produces
``status="pass"`` on output that was never really checked.

Design constraints:

- **Pure.** No I/O, no logging, no storage, no config, no infrastructure import.
  It takes a schema and returns a verdict; the caller decides what to do.
- **The rule engine is not touched.** ``RuleEngine`` stays deliberately defensive
  at runtime (it declines to judge what it cannot evaluate). Authoring errors
  belong here, at admission, not in the hot path.
- **Machine-facing codes, human-facing messages.** Integrations switch on
  :class:`ContractAdmissionCode`; they never parse prose.
- **Composed, not duplicated.** Vocabulary knowledge lives in
  :mod:`congine_core.domain.schema_vocabulary` and is reused from there.

This is the narrow seam a future ``ContractCompiler`` / Policy IR grows from. It
is deliberately *not* that compiler yet.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import re2 as _re2  # type: ignore[import-untyped]

# Layer 0 policy enum. Admission *applies* the mode; configuration *declares* it.
# Importing inward to L0 keeps this module free of any outward dependency.
from congine_core.config import ContractAdmissionMode
from congine_core.domain.schema_vocabulary import (
    IGNORABLE_METADATA_KEYWORDS,
    RECOGNISED_TYPE_NAMES,
    find_unenforced_keywords,
    type_is_enforceable,
)
from congine_core.security_limits import MAX_PATTERN_LENGTH

__all__ = [
    "ContractAdmissionCode",
    "ContractAdmissionLevel",
    "ContractAdmissionMode",
    "ContractAdmissionIssue",
    "ContractAdmissionResult",
    "admit_contract",
]

_ROOT = "<root>"

#: Cap on reported issues so a pathological contract cannot produce an unbounded
#: log line, consistent with the codebase's cap-everything posture.
_MAX_ISSUES = 50


class ContractAdmissionCode(StrEnum):
    """Stable, machine-facing reason a contract was refused or flagged.

    These values cross process boundaries into logs today and into MCP responses
    and durable evidence later. Treat them as a published vocabulary: add
    members, never repurpose or rename existing ones.
    """

    #: A ``type`` name the rule engine does not recognise (e.g. ``"str"``).
    UNKNOWN_TYPE = "unknown_type"
    #: ``"type": []`` — declares nothing, so it constrains nothing.
    EMPTY_TYPE_UNION = "empty_type_union"
    #: A ``pattern`` that does not compile, or exceeds the safe length budget.
    INVALID_PATTERN = "invalid_pattern"
    #: A property key containing ``.`` — ambiguous between a nested path and a
    #: literal key of that name.
    AMBIGUOUS_PROPERTY_PATH = "ambiguous_property_path"
    #: A recognised keyword that no active evaluator will execute.
    UNSUPPORTED_KEYWORD = "unsupported_keyword"
    #: The contract does not conform to CONGINE's admitted grammar.
    INVALID_STRUCTURE = "invalid_structure"
    #: A supported CONGINE extension whose portable spelling is preferred.
    LEGACY_CONSTRUCT = "legacy_construct"


class ContractAdmissionLevel(StrEnum):
    """Whether an issue blocks admission."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True)
class ContractAdmissionIssue:
    """One reason a contract was refused or flagged.

    Attributes:
        code: Machine-facing :class:`ContractAdmissionCode`. Switch on this.
        path: Where in the contract, e.g. ``"summary.minLength"`` or
            ``"<root>.required"``.
        message: Human-readable explanation. Never parse this.
        level: Whether the issue blocks admission.
    """

    code: ContractAdmissionCode
    path: str
    message: str
    level: ContractAdmissionLevel = ContractAdmissionLevel.ERROR


@dataclass(frozen=True)
class ContractAdmissionResult:
    """Verdict on whether a contract may become active policy."""

    admitted: bool
    issues: tuple[ContractAdmissionIssue, ...] = field(default=())

    @property
    def errors(self) -> tuple[ContractAdmissionIssue, ...]:
        """Blocking issues."""
        return tuple(i for i in self.issues if i.level is ContractAdmissionLevel.ERROR)

    @property
    def warnings(self) -> tuple[ContractAdmissionIssue, ...]:
        """Advisory issues that did not block admission."""
        return tuple(
            i for i in self.issues if i.level is ContractAdmissionLevel.WARNING
        )

    def codes(self) -> tuple[str, ...]:
        """Distinct issue codes, sorted — a compact, stable log/telemetry field."""
        return tuple(sorted({str(i.code) for i in self.issues}))


def admit_contract(
    schema: Any,
    *,
    mode: ContractAdmissionMode = ContractAdmissionMode.STRICT,
    enforced_keywords: frozenset[str],
) -> ContractAdmissionResult:
    """Decide whether *schema* may become active policy.

    Args:
        schema: The candidate contract schema, exactly as it would be cached.
        mode: See :class:`ContractAdmissionMode`. Affects advisory output only;
            it can never turn an invalid contract into a valid one.
        enforced_keywords: The keywords some **currently active** evaluator will
            execute. A capability set rather than a "semantic validation on/off"
            flag, because the real question is *"is this clause enforced?"* and
            the answer will differ per evaluator as more are added. The caller
            composes it from the evaluators it actually wired.

    Returns:
        A :class:`ContractAdmissionResult`. ``admitted`` is ``False`` if any
        issue is at ``ERROR`` level.

    This function never raises on malformed input — a contract that is too
    broken to inspect is reported as :attr:`ContractAdmissionCode.INVALID_STRUCTURE`,
    not as an exception.
    """
    issues: list[ContractAdmissionIssue] = []

    if not isinstance(schema, Mapping):
        return ContractAdmissionResult(
            admitted=False,
            issues=(
                ContractAdmissionIssue(
                    code=ContractAdmissionCode.INVALID_STRUCTURE,
                    path=_ROOT,
                    message=(
                        "Contract schema must be an object/mapping, got "
                        f"{type(schema).__name__}"
                    ),
                ),
            ),
        )

    _check_top_level_lists(schema, issues)
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, Mapping):
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.INVALID_STRUCTURE,
                path=f"{_ROOT}.properties",
                message=(
                    "'properties' must be an object/mapping, got "
                    f"{type(properties).__name__}"
                ),
            )
        )
        properties = None

    if isinstance(properties, Mapping):
        for field_name, spec in properties.items():
            _check_property(str(field_name), spec, issues)

    _check_unsupported_keywords(schema, enforced_keywords, issues)

    if mode is ContractAdmissionMode.WARN:
        _add_legacy_advisories(schema, issues)

    if len(issues) > _MAX_ISSUES:
        issues = issues[:_MAX_ISSUES]

    admitted = not any(i.level is ContractAdmissionLevel.ERROR for i in issues)
    return ContractAdmissionResult(admitted=admitted, issues=tuple(issues))


# --------------------------------------------------------------------------- #
# Grammar checks
# --------------------------------------------------------------------------- #
def _check_top_level_lists(
    schema: Mapping[str, Any], issues: list[ContractAdmissionIssue]
) -> None:
    """``required`` / ``null_forbidden`` must be lists of field names.

    A bare string is refused rather than tolerated. ``required="email"`` is
    currently iterated *character by character*, quietly requiring fields
    ``"e"``, ``"m"``, ``"a"``, ``"i"``, ``"l"`` — accidental behaviour, and
    exactly the kind of false policy interpretation this boundary exists to stop.
    """
    for key in ("required", "null_forbidden"):
        value = schema.get(key)
        if value is None:
            continue
        if isinstance(value, str) or not isinstance(value, Sequence):
            issues.append(
                ContractAdmissionIssue(
                    code=ContractAdmissionCode.INVALID_STRUCTURE,
                    path=f"{_ROOT}.{key}",
                    message=(
                        f"'{key}' must be a list of field names, got "
                        f"{type(value).__name__}"
                        + (
                            " (a bare string is iterated character-by-character)"
                            if isinstance(value, str)
                            else ""
                        )
                    ),
                )
            )
            continue
        for entry in value:
            if not isinstance(entry, str):
                issues.append(
                    ContractAdmissionIssue(
                        code=ContractAdmissionCode.INVALID_STRUCTURE,
                        path=f"{_ROOT}.{key}",
                        message=(
                            f"'{key}' entries must be field names (strings), got "
                            f"{type(entry).__name__}"
                        ),
                    )
                )


def _check_property(
    field_name: str, spec: Any, issues: list[ContractAdmissionIssue]
) -> None:
    """Validate one entry of ``properties``."""
    # Dotted keys are ambiguous: "user.email" could mean a nested path or a
    # literal JSON key of that name. Only FIELD_PRESENCE walks dotted paths;
    # every per-property rule does a flat lookup, so type/pattern/enum/range
    # silently enforce nothing. Refuse rather than guess (audit P0-03).
    if "." in field_name:
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.AMBIGUOUS_PROPERTY_PATH,
                path=field_name,
                message=(
                    f"Property key '{field_name}' contains '.', which is ambiguous "
                    "between a nested path and a literal key. Per-property rules "
                    "match flatly, so nested constraints would not be enforced. "
                    "Use a top-level key, or express nested presence via 'required'."
                ),
            )
        )
        return

    if not isinstance(spec, Mapping):
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.INVALID_STRUCTURE,
                path=field_name,
                message=(
                    f"Property '{field_name}' must map to an object of constraints, "
                    f"got {type(spec).__name__}"
                ),
            )
        )
        return

    if "type" in spec:
        _check_type(field_name, spec["type"], issues)
    if "pattern" in spec:
        _check_pattern(field_name, spec["pattern"], issues)
    if "enum" in spec:
        _check_enum(field_name, spec["enum"], issues)
    _check_range(field_name, spec, issues)


def _check_type(
    field_name: str, declared: Any, issues: list[ContractAdmissionIssue]
) -> None:
    """``type`` must be a recognised name, or a non-empty union of them."""
    if isinstance(declared, (list, tuple)) and not declared:
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.EMPTY_TYPE_UNION,
                path=f"{field_name}.type",
                message=(
                    f"Property '{field_name}' declares an empty type union, which "
                    "constrains nothing"
                ),
            )
        )
        return

    if type_is_enforceable(declared):
        return

    known = ", ".join(sorted(RECOGNISED_TYPE_NAMES))
    if isinstance(declared, (list, tuple)):
        unknown = [
            m
            for m in declared
            if not (isinstance(m, str) and m in RECOGNISED_TYPE_NAMES)
        ]
        detail = (
            f"union member(s) {unknown!r} are not recognised. A union containing an "
            "unrecognised name matches every value, so the field would be unchecked"
        )
    else:
        detail = f"type {declared!r} is not recognised"
    issues.append(
        ContractAdmissionIssue(
            code=ContractAdmissionCode.UNKNOWN_TYPE,
            path=f"{field_name}.type",
            message=(f"Property '{field_name}': {detail}. Supported types: {known}."),
        )
    )


def _check_pattern(
    field_name: str, pattern: Any, issues: list[ContractAdmissionIssue]
) -> None:
    """``pattern`` must be a string that compiles within the safe length budget.

    Both failures are moved from runtime to admission: an over-long or
    uncompilable pattern currently produces a ``REGEX_PATTERN`` breach on *every*
    validation, which reports the output as violating a policy when the real
    fault is in the policy itself.
    """
    if not isinstance(pattern, str):
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.INVALID_STRUCTURE,
                path=f"{field_name}.pattern",
                message=(
                    f"Property '{field_name}': 'pattern' must be a string, got "
                    f"{type(pattern).__name__}"
                ),
            )
        )
        return
    if len(pattern) > MAX_PATTERN_LENGTH:
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.INVALID_PATTERN,
                path=f"{field_name}.pattern",
                message=(
                    f"Property '{field_name}': pattern exceeds the safe length "
                    f"budget of {MAX_PATTERN_LENGTH} characters"
                ),
            )
        )
        return
    try:
        _re2.compile(pattern)
    except Exception as exc:  # re2.error, and anything else the engine raises
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.INVALID_PATTERN,
                path=f"{field_name}.pattern",
                message=(
                    f"Property '{field_name}': pattern does not compile "
                    f"({type(exc).__name__}). Note RE2 supports neither "
                    "backreferences nor lookaround."
                ),
            )
        )


def _check_enum(
    field_name: str, allowed: Any, issues: list[ContractAdmissionIssue]
) -> None:
    """``enum`` must be a list. A bare string would match by substring."""
    if isinstance(allowed, str) or not isinstance(allowed, Sequence):
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.INVALID_STRUCTURE,
                path=f"{field_name}.enum",
                message=(
                    f"Property '{field_name}': 'enum' must be a list of allowed "
                    f"values, got {type(allowed).__name__}"
                    + (
                        " (a bare string would be matched by substring)"
                        if isinstance(allowed, str)
                        else ""
                    )
                ),
            )
        )


def _check_range(
    field_name: str, spec: Mapping[str, Any], issues: list[ContractAdmissionIssue]
) -> None:
    """``min``/``max``/``minimum``/``maximum`` operands must be numeric."""
    for key in ("min", "max", "minimum", "maximum"):
        if key not in spec:
            continue
        value = spec[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            issues.append(
                ContractAdmissionIssue(
                    code=ContractAdmissionCode.INVALID_STRUCTURE,
                    path=f"{field_name}.{key}",
                    message=(
                        f"Property '{field_name}': '{key}' must be a number, got "
                        f"{type(value).__name__}"
                    ),
                )
            )


# --------------------------------------------------------------------------- #
# Enforcement-coverage check
# --------------------------------------------------------------------------- #
def _check_unsupported_keywords(
    schema: Mapping[str, Any],
    enforced_keywords: frozenset[str],
    issues: list[ContractAdmissionIssue],
) -> None:
    """Refuse any clause that no currently-active evaluator will execute.

    Reuses :func:`find_unenforced_keywords`, which already has the allowlist
    semantics and metadata handling this needs — anything not enforced and not
    documentation is reported, so keywords nobody thought to blocklist are still
    caught as JSON Schema grows.

    ``type`` findings are skipped here because :func:`_check_type` reports them
    with far better diagnostics.
    """
    for path in find_unenforced_keywords(schema):
        if path.startswith("..."):  # truncation marker from the scanner
            continue
        keyword = path.rsplit(".", 1)[-1]
        if keyword == "type":
            continue  # already covered, with a better message
        if keyword in IGNORABLE_METADATA_KEYWORDS:
            continue
        if keyword in enforced_keywords:
            continue  # an evaluator you have enabled will execute it
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.UNSUPPORTED_KEYWORD,
                path=path,
                message=(
                    f"'{keyword}' is not enforced by any active evaluator, so this "
                    "clause would be silently ignored while appearing enforced. "
                    "Remove it, or enable an evaluator that enforces it "
                    "(e.g. CONGINE_SEMANTIC_VALIDATION=true)."
                ),
            )
        )


def _add_legacy_advisories(
    schema: Mapping[str, Any], issues: list[ContractAdmissionIssue]
) -> None:
    """Non-blocking migration notes, emitted only in :attr:`ContractAdmissionMode.WARN`.

    These constructs are fully enforced and entirely valid; the note exists
    because a portable spelling is now available.
    """
    if "null_forbidden" in schema:
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.LEGACY_CONSTRUCT,
                path=f"{_ROOT}.null_forbidden",
                message=(
                    "'null_forbidden' is a CONGINE extension, not JSON Schema, so "
                    "this contract is not portable. It is fully enforced by the "
                    "rule engine. The portable spelling is a type union: "
                    '{"type": ["string", "null"]} for nullable, {"type": "string"} '
                    "for non-nullable."
                ),
                level=ContractAdmissionLevel.WARNING,
            )
        )
