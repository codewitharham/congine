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
from typing import Any, Final, Iterator, Optional

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
from congine_core.semantic_capability import SemanticCapability

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
    #: A $ref CONGINE cannot resolve deterministically and locally:
    #: external, unresolvable, or part of a cycle (P1.5).
    UNSUPPORTED_REFERENCE = "unsupported_reference"


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
    capability: Optional[SemanticCapability] = None,
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

    # P1.5 semantic-safety checks. `capability` describes what the wired
    # evaluator genuinely enforces; without one, only the checks that need no
    # evaluator knowledge run, so older callers keep their existing behaviour.
    effective = capability or SemanticCapability(
        draft="unspecified", enforced_keywords=enforced_keywords
    )
    _check_exclusive_bounds(schema, effective, issues)
    _check_references(schema, effective, issues)
    _check_nested_patterns(schema, issues)
    if capability is not None:
        _check_formats(schema, effective, issues)

    if mode is ContractAdmissionMode.WARN:
        _add_legacy_advisories(schema, issues)

    if len(issues) > _MAX_ISSUES:
        issues = issues[:_MAX_ISSUES]

    admitted = not any(i.level is ContractAdmissionLevel.ERROR for i in issues)
    return ContractAdmissionResult(admitted=admitted, issues=tuple(issues))


#: Keywords whose value is itself a schema.
_SCHEMA_VALUED: Final = (
    "items",
    "contains",
    "not",
    "if",
    "then",
    "else",
    "propertyNames",
    "additionalProperties",
    "unevaluatedItems",
    "unevaluatedProperties",
)

#: Keywords whose value is a list of schemas.
_SCHEMA_LIST_VALUED: Final = ("allOf", "anyOf", "oneOf", "prefixItems")

#: Keywords whose value maps names to schemas.
_SCHEMA_MAP_VALUED: Final = (
    "properties",
    "patternProperties",
    "$defs",
    "definitions",
    "dependentSchemas",
)


def _walk_subschemas(node: Any, path: str) -> "Iterator[tuple[str, Mapping[str, Any]]]":
    """Yield ``(path, subschema)`` for every schema-bearing node beneath *node*.

    Admission previously inspected only top-level ``properties``, so a pattern
    or reference nested inside ``items``, a combinator or ``$defs`` was never
    examined and reached the evaluator unchecked. The traversal follows the
    schema-bearing keywords of every supported draft; a keyword the configured
    dialect ignores is harmless to visit, whereas missing one is not.
    """
    if not isinstance(node, Mapping):
        return
    yield path, node
    for keyword in _SCHEMA_VALUED:
        child = node.get(keyword)
        if isinstance(child, Mapping):
            yield from _walk_subschemas(child, f"{path}.{keyword}")
    for keyword in _SCHEMA_LIST_VALUED:
        children = node.get(keyword)
        if isinstance(children, list):
            for index, child in enumerate(children):
                yield from _walk_subschemas(child, f"{path}.{keyword}[{index}]")
    for keyword in _SCHEMA_MAP_VALUED:
        children = node.get(keyword)
        if isinstance(children, Mapping):
            for name, child in children.items():
                yield from _walk_subschemas(child, f"{path}.{keyword}.{name}")
    # `items` may be a list in draft4-2019 (tuple validation).
    items = node.get("items")
    if isinstance(items, list):
        for index, child in enumerate(items):
            yield from _walk_subschemas(child, f"{path}.items[{index}]")


def _unescape_pointer_token(token: str) -> str:
    """Decode one RFC 6901 pointer token (``~1`` -> ``/``, ``~0`` -> ``~``).

    Order matters: ``~01`` must decode to ``~1`` and not ``/``.
    """
    return token.replace("~1", "/").replace("~0", "~")


def _resolve_pointer(root: Mapping[str, Any], pointer: str) -> Any:
    """Resolve a local JSON pointer, returning ``_MISSING`` when absent."""
    if pointer in ("", "#"):
        return root
    body = pointer[1:] if pointer.startswith("#") else pointer
    if not body.startswith("/"):
        return _MISSING
    current: Any = root
    for raw in body[1:].split("/"):
        token = _unescape_pointer_token(raw)
        if isinstance(current, Mapping):
            if token not in current:
                return _MISSING
            current = current[token]
        elif isinstance(current, list):
            try:
                current = current[int(token)]
            except (ValueError, IndexError):
                return _MISSING
        else:
            return _MISSING
    return current


class _Missing:
    """Sentinel distinguishing "absent" from a legitimately present ``None``."""


_MISSING = _Missing()


def _check_references(
    schema: Mapping[str, Any],
    capability: SemanticCapability,
    issues: list[ContractAdmissionIssue],
) -> None:
    """Refuse references CONGINE cannot resolve deterministically and locally.

    P1.5 supports **verified local JSON-pointer references only**. External
    references are refused because resolving them means a real network or
    filesystem fetch: measured during A0, an ``http`` reference caused a live
    fetch whose content then determined enforcement, making policy remotely
    mutable, adding unbounded latency inside the validation budget, and creating
    an SSRF vector in a governance SDK.

    Cycles are refused as an **unsupported CONGINE contract subset**, not as
    invalid JSON Schema — recursive schemas are legal, and supporting them is
    deliberately out of P1.5 scope. A cycle currently exhausts the stack during
    evaluation, so refusing it at admission converts a runtime crash into an
    actionable rejection.
    """
    for path, node in _walk_subschemas(schema, _ROOT):
        ref = node.get("$ref")
        if ref is None:
            continue
        if not isinstance(ref, str):
            issues.append(
                ContractAdmissionIssue(
                    code=ContractAdmissionCode.INVALID_STRUCTURE,
                    path=f"{path}.$ref",
                    message=f"'$ref' must be a string, got {type(ref).__name__}",
                )
            )
            continue
        if not ref.startswith("#"):
            issues.append(
                ContractAdmissionIssue(
                    code=ContractAdmissionCode.UNSUPPORTED_REFERENCE,
                    path=f"{path}.$ref",
                    message=(
                        f"External reference {ref!r} is not supported. Resolving it "
                        "would fetch a remote document, letting content outside this "
                        "contract determine enforcement. Inline the schema, or move "
                        "it into '$defs' and reference it locally."
                    ),
                )
            )
            continue
        target = _resolve_pointer(schema, ref)
        if isinstance(target, _Missing):
            issues.append(
                ContractAdmissionIssue(
                    code=ContractAdmissionCode.UNSUPPORTED_REFERENCE,
                    path=f"{path}.$ref",
                    message=(
                        f"Local reference {ref!r} does not resolve to anything in this "
                        "contract, so the clause would fail at evaluation time."
                    ),
                )
            )
            continue
        if _reference_cycle(schema, ref):
            issues.append(
                ContractAdmissionIssue(
                    code=ContractAdmissionCode.UNSUPPORTED_REFERENCE,
                    path=f"{path}.$ref",
                    message=(
                        f"Reference {ref!r} is part of a cycle. Recursive schemas are "
                        "valid JSON Schema but are an unsupported CONGINE contract "
                        "subset in this release; evaluating one exhausts the stack."
                    ),
                )
            )


def _reference_cycle(root: Mapping[str, Any], start: str) -> bool:
    """Return whether following ``$ref`` from *start* revisits a pointer."""
    seen: set[str] = set()
    pointer = start
    while True:
        if pointer in seen:
            return True
        seen.add(pointer)
        target = _resolve_pointer(root, pointer)
        if not isinstance(target, Mapping):
            return False
        next_ref = target.get("$ref")
        if not isinstance(next_ref, str) or not next_ref.startswith("#"):
            return False
        pointer = next_ref


def _check_nested_patterns(
    schema: Mapping[str, Any], issues: list[ContractAdmissionIssue]
) -> None:
    """Validate every regex anywhere in the contract, not just top-level ones.

    Two sources are checked: a ``pattern`` value, and each **key** of
    ``patternProperties`` — the keys are regexes too, and were previously
    unchecked entirely, so an uncompilable one reached the evaluator.

    Every pattern must compile under RE2, because semantic evaluation now runs
    on RE2 (P1.5-A0-1). Refusing here is what keeps that guarantee honest: a
    pattern the engine cannot compile must never become active policy.
    """
    for path, node in _walk_subschemas(schema, _ROOT):
        pattern = node.get("pattern")
        if pattern is not None and path != _ROOT:
            _check_regex_value(f"{path}.pattern", pattern, issues)
        pattern_properties = node.get("patternProperties")
        if isinstance(pattern_properties, Mapping):
            for key in pattern_properties:
                _check_regex_value(f"{path}.patternProperties[{key}]", str(key), issues)


def _check_regex_value(
    path: str, pattern: Any, issues: list[ContractAdmissionIssue]
) -> None:
    """Refuse a regex that is not a string, is over-long, or RE2 rejects."""
    if not isinstance(pattern, str):
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.INVALID_STRUCTURE,
                path=path,
                message=f"pattern must be a string, got {type(pattern).__name__}",
            )
        )
        return
    if len(pattern) > MAX_PATTERN_LENGTH:
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.INVALID_PATTERN,
                path=path,
                message=(
                    f"pattern exceeds the safe length budget of "
                    f"{MAX_PATTERN_LENGTH} characters"
                ),
            )
        )
        return
    try:
        _re2.compile(pattern)
    except Exception as exc:  # noqa: BLE001 - any RE2 rejection refuses the clause
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.INVALID_PATTERN,
                path=path,
                message=(
                    f"pattern does not compile under RE2 ({type(exc).__name__}). "
                    "Semantic evaluation runs on RE2, which supports neither "
                    "backreferences nor lookaround."
                ),
            )
        )


#: Bounds whose enforceability depends on the *value form*, not the keyword.
_EXCLUSIVE_BOUNDS: Final = ("exclusiveMinimum", "exclusiveMaximum")


def _check_exclusive_bounds(
    schema: Mapping[str, Any],
    capability: SemanticCapability,
    issues: list[ContractAdmissionIssue],
) -> None:
    """Refuse an exclusive bound written in a form this dialect does not assert.

    This keyword cannot be judged at keyword level, which is why it is handled
    apart from the generic scan. Draft 4 spells it as a **boolean modifier** on
    ``minimum``/``maximum`` and asserts it inside those handlers; draft 6 and
    later spell it as a **standalone number** with its own handler. Each dialect
    silently ignores the other's spelling, so admitting on keyword presence
    alone would let a contract look enforced while asserting nothing — and
    refusing on handler absence alone would reject perfectly valid draft-4
    contracts.
    """
    for path, node in _walk_subschemas(schema, _ROOT):
        for keyword in _EXCLUSIVE_BOUNDS:
            if keyword not in node:
                continue
            value = node[keyword]
            if capability.enforces_exclusive_bound(keyword, value, node):
                continue
            sibling = "minimum" if keyword == "exclusiveMinimum" else "maximum"
            if isinstance(value, bool):
                detail = (
                    f"the boolean form requires a sibling '{sibling}' and a dialect "
                    "that asserts it (draft 4)"
                )
            else:
                detail = (
                    "this dialect expects the draft-4 boolean form "
                    f"alongside '{sibling}'"
                )
            issues.append(
                ContractAdmissionIssue(
                    code=ContractAdmissionCode.UNSUPPORTED_KEYWORD,
                    path=f"{path}.{keyword}",
                    message=(
                        f"'{keyword}' is not asserted as written under "
                        f"{capability.draft}: {detail}. As written the clause "
                        "would enforce nothing."
                    ),
                )
            )


def _check_formats(
    schema: Mapping[str, Any],
    capability: SemanticCapability,
    issues: list[ContractAdmissionIssue],
) -> None:
    """Refuse a ``format`` the configured checker cannot actually assert.

    ``format`` was previously admitted wholesale whenever format checking was
    on, so an unrecognised name such as ``"unknown-xyz"`` was admitted and then
    silently ignored — enforcement advertised but not delivered. Both halves
    matter and neither implies the other: assertion may be enabled while a
    specific name has no checker, and a well-known name is unenforceable while
    assertion is off.
    """
    for path, node in _walk_subschemas(schema, _ROOT):
        name = node.get("format")
        if not isinstance(name, str):
            continue
        if capability.enforces_format(name):
            continue
        detail = (
            f"format {name!r} has no checker in the configured evaluator"
            if capability.format_assertion
            else "format assertions are disabled, so this clause enforces nothing"
        )
        issues.append(
            ContractAdmissionIssue(
                code=ContractAdmissionCode.UNSUPPORTED_KEYWORD,
                path=f"{path}.format",
                message=(
                    f"{detail}. Remove it, or enable a checker that asserts it "
                    "(CONGINE_SEMANTIC_FORMAT_CHECKING=true)."
                ),
            )
        )


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
        if keyword in _EXCLUSIVE_BOUNDS:
            continue  # value-aware; see _check_exclusive_bounds
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
