"""JSON Schema semantic validator (Layer 4).

:class:`JsonSchemaSemanticValidator` implements
:class:`congine_core.ports.semantic_validator.ISemanticValidator` using
the ``jsonschema`` library.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Final, Iterator, List, Optional

import jsonschema
import re2 as _re2  # type: ignore[import-untyped]
from jsonschema import (
    Draft4Validator,
    Draft6Validator,
    Draft7Validator,
    Draft201909Validator,
    Draft202012Validator,
)
from jsonschema import validators as _jsonschema_validators
from jsonschema.exceptions import SchemaError, ValidationError
from jsonschema.protocols import Validator
from referencing import Registry
from referencing.exceptions import NoSuchResource

from congine_core.models import BreachDetail
from congine_core.exceptions import CongineConfigurationError
from congine_core.infrastructure.schema_preparation_cache import (
    SchemaPreparationCache,
    prepare_identity,
    preparation_key,
)
from congine_core.pii_sanitize import sanitize_breach_message
from congine_core.security_limits import (
    DEFAULT_SEMANTIC_MAX_BREACHES,
    MAX_PATTERN_LENGTH,
)
from congine_core.semantic_capability import SemanticCapability

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


#: Keywords implemented inside another keyword's handler rather than as their
#: own ``VALIDATORS`` entry. Deriving capability from handler presence alone
#: under-reports these, so the mapping is explicit and cross-checked by
#: ``tools/p1_5_evidence`` drift detection (P1.5-A0.1).
_COMPOSED_KEYWORDS: Final = {
    "then": "if",
    "else": "if",
    "minContains": "contains",
    "maxContains": "contains",
}

#: ``minContains``/``maxContains`` exist only from 2019-09 even though
#: ``contains`` appears in draft6. Measured against every validator, not
#: inferred from the specification text.
_COMPOSED_MIN_RANK: Final = {"minContains": 3, "maxContains": 3}

#: Dialect ordering, used only to gate the composed keywords above.
_DRAFT_RANK: Final[Dict[type[Validator], int]] = {
    Draft4Validator: 0,
    Draft6Validator: 1,
    Draft7Validator: 2,
    Draft201909Validator: 3,
    Draft202012Validator: 4,
}

#: Container keywords. They assert nothing on their own, but ``$ref`` resolves
#: *into* them, so the clauses they hold are genuinely reached and enforced.
#: They are therefore reported as supported whenever ``$ref`` is supported —
#: treating them as unenforced would refuse every contract that factors a
#: subschema into ``$defs``, which is ordinary, valid authoring.
_CONTAINER_KEYWORDS: Final = frozenset({"$defs", "definitions"})


def _re2_pattern(
    validator: Any, patrn: Any, instance: Any, schema: Any
) -> Iterator[ValidationError]:
    """``pattern`` evaluated with RE2 instead of CPython's backtracking ``re``.

    JSON Schema ``pattern`` uses **search**, not full-match, semantics, so
    ``"abc"`` matches ``"xxabcxx"``. That is preserved exactly here — the native
    rule engine's full-match behaviour must not leak into semantic evaluation.

    Why this override exists (P1.5-A0-1): the stock handler calls ``re.search``.
    A catastrophic pattern measured 7.6 ms at 16 characters and 7 689 ms at 26,
    and because the match holds the GIL the executor's deadline could not be
    observed on time — a 100 ms budget was enforced 20x late, or not at all.
    RE2 is linear-time, so the configured budget becomes meaningful again.

    Fails closed: a pattern RE2 cannot compile yields a breach rather than
    passing silently. Admission rejects such patterns first, so reaching that
    branch means the contract bypassed admission.
    """
    if not validator.is_type(instance, "string"):
        return
    try:
        matched = _re2.search(patrn, instance) is not None
    except Exception:  # noqa: BLE001 - any RE2 rejection must fail closed
        yield ValidationError(f"pattern {patrn!r} is not supported (RE2 rejected it)")
        return
    if not matched:
        yield ValidationError(f"{instance!r} does not match {patrn!r}")


def _re2_pattern_properties(
    validator: Any, pattern_properties: Any, instance: Any, schema: Any
) -> Iterator[ValidationError]:
    """``patternProperties`` with RE2, mirroring the stock handler's structure.

    Property **names** are matched with search semantics, identically to the
    handler this replaces; only the regex engine changes.
    """
    if not validator.is_type(instance, "object"):
        return
    for pattern, subschema in pattern_properties.items():
        try:
            compiled = _re2.compile(pattern)
        except Exception:  # noqa: BLE001 - fail closed, never skip the clause
            yield ValidationError(
                f"patternProperties key {pattern!r} is not supported (RE2 rejected it)"
            )
            continue
        for key, value in instance.items():
            if compiled.search(key):
                yield from validator.descend(
                    value, subschema, path=key, schema_path=pattern
                )


def _re2_validator_class(base: type[Validator]) -> type[Validator]:
    """Return *base* with its two regex keywords rebound to the RE2 handlers."""
    # `jsonschema.validators.extend` carries no annotations at all
    # (`extend.__annotations__ == {}`), so mypy cannot type this call. The
    # ignore is confined to the single unavoidable call site rather than the
    # module, and the returned class is exercised by the semantic-safety suite.
    extended: type[Validator] = _jsonschema_validators.extend(  # type: ignore[no-untyped-call]
        base,
        {"pattern": _re2_pattern, "patternProperties": _re2_pattern_properties},
    )
    return extended


def _no_retrieval(uri: str) -> Any:
    """Reference retriever that refuses every external resolution.

    Defence in depth beneath admission (P1.5-A0-2). Left to itself the library
    performs a **real network fetch** for an external ``$ref`` — a loopback
    server was hit and its schema enforced, which lets remote content control
    policy, adds unbounded latency inside the validation budget, and hands a
    governance SDK an SSRF vector. ``jsonschema`` deprecates the behaviour for
    the same reason.

    Admission already refuses external references; this ensures anything that
    slips past admission fails closed instead of reaching the network.
    """
    # `NoSuchResource` is an attrs class whose `ref` field mypy does not resolve
    # through the generated __init__ under this attrs/mypy combination. Verified
    # correct at runtime: the field exists with alias "ref".
    raise NoSuchResource(ref=uri)  # type: ignore[call-arg]


def _local_only_registry() -> Registry:
    """Build the no-retrieval registry used for every semantic evaluation."""
    # Same attrs/mypy gap as above: `Registry._retrieve` is exposed with alias
    # "retrieve", which mypy does not pick up. This is the only supported way to
    # disable implicit retrieval, and the behaviour is proven by the hermetic
    # retriever-spy witness in tools/p1_5_evidence.
    registry: Registry = Registry(retrieve=_no_retrieval)  # type: ignore[call-arg]
    return registry


def derive_capability(
    validator_cls: type[Validator], *, format_checking: bool
) -> SemanticCapability:
    """Describe what *validator_cls* genuinely enforces on its own dialect.

    Capability is read off the concrete class rather than assumed, because a
    static keyword list is dialect-blind: measured across the five supported
    validators, a fixed list over-claimed 11 keywords on draft4, 6 on draft6,
    5 on draft7 and 1 on 2019-09 (P1.5-A0.1). Each was a G12 violation.

    ``VALIDATORS`` membership is the primary signal, corrected by
    :data:`_COMPOSED_KEYWORDS` for keywords whose assertions live inside another
    handler — deriving from handler presence alone would *under*-report those
    and refuse valid contracts.
    """
    handlers = set(getattr(validator_cls, "VALIDATORS", {}))
    enforced = set(handlers)
    if "$ref" in handlers:
        enforced |= _CONTAINER_KEYWORDS

    rank = _DRAFT_RANK.get(_base_class(validator_cls))
    for keyword, parent in _COMPOSED_KEYWORDS.items():
        if parent not in handlers:
            continue
        floor = _COMPOSED_MIN_RANK.get(keyword)
        if floor is not None and (rank is None or rank < floor):
            continue
        enforced.add(keyword)

    formats: frozenset[str] = frozenset()
    if format_checking:
        checker = getattr(validator_cls, "FORMAT_CHECKER", None)
        formats = frozenset(getattr(checker, "checkers", {}) or {})
    else:
        # `format` asserts nothing while checking is off, so it must not be
        # advertised as enforced however well known a name is.
        enforced.discard("format")

    # Draft 4 asserts the exclusive bounds inside `minimum`/`maximum` rather
    # than through handlers of their own, so handler presence alone would
    # report a genuinely enforceable draft-4 contract as unenforceable.
    boolean_bounds = "minimum" in handlers and "exclusiveMinimum" not in handlers

    return SemanticCapability(
        draft=_draft_name(validator_cls),
        enforced_keywords=frozenset(enforced),
        format_assertion=format_checking,
        supported_formats=formats,
        allow_external_references=False,
        boolean_exclusive_bounds=boolean_bounds,
    )


def _base_class(validator_cls: type[Validator]) -> type[Validator]:
    """Resolve an RE2-extended class back to the stock draft class.

    ``jsonschema.validators.extend`` produces a new class, so identity checks
    against the stock validators must look through it.
    """
    for stock in _DRAFT_RANK:
        if validator_cls is stock or issubclass_safe(validator_cls, stock):
            return stock
    return validator_cls


def issubclass_safe(candidate: Any, parent: type) -> bool:
    """``issubclass`` that tolerates non-class inputs."""
    try:
        return isinstance(candidate, type) and issubclass(candidate, parent)
    except TypeError:  # pragma: no cover - defensive
        return False


def _draft_name(validator_cls: type[Validator]) -> str:
    """Return the canonical dialect label for *validator_cls*."""
    base = _base_class(validator_cls)
    for name, cls in (
        ("draft4", Draft4Validator),
        ("draft6", Draft6Validator),
        ("draft7", Draft7Validator),
        ("draft201909", Draft201909Validator),
        ("draft202012", Draft202012Validator),
    ):
        if base is cls:
            return name
    return str(getattr(validator_cls, "__name__", "unknown"))


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
        base_cls: type[Validator] = (
            validator_cls
            if validator_cls is not None
            else _resolve_draft(jsonschema_draft)
        )
        #: The stock draft class the dialect resolved to. Retained because
        #: ``jsonschema.validators.extend`` builds an unrelated class rather
        #: than a subclass, so the configured dialect would otherwise be
        #: unobservable from ``_validator_cls`` alone.
        self._base_validator_cls: type[Validator] = base_cls
        #: Regex keywords are rebound to RE2 so semantic evaluation is
        #: linear-time and the configured deadline stays meaningful (P1.5-A0-1).
        self._validator_cls: type[Validator] = _re2_validator_class(base_cls)
        #: Refuses every external reference resolution (P1.5-A0-2).
        self._registry = _local_only_registry()
        self._max_breaches = max_breaches
        self._format_checking = format_checking
        #: What this evaluator genuinely enforces on its own dialect. Read by
        #: the composition root and handed to contract admission, so admission
        #: can stop advertising enforcement the evaluator does not have.
        self.capability: SemanticCapability = derive_capability(
            base_cls, format_checking=format_checking
        )
        #: Remembers that ``check_schema`` already succeeded for a given schema
        #: content under this exact evaluator context (P1.5 Slice F). Owned by this
        #: instance, so independently configured containers never share markers.
        self._preparation_cache = SchemaPreparationCache()

    def validate(
        self, payload: dict[str, Any], schema: dict[str, Any]
    ) -> List[BreachDetail]:
        """Return a :class:`BreachDetail` for every JSON Schema violation.

        ``check_schema`` is the expensive half of semantic evaluation — measured at
        8-105 ms against 0.01-0.02 ms for constructing the validator — and it is
        deterministic for fixed schema content and a fixed validator class. It is
        therefore run once per (content, evaluator context) and remembered
        (P1.5 Slice F).

        **The cache changes exactly one operation.** A confirmed
        :data:`CHECK_SCHEMA_VALID` marker skips ``check_schema`` and nothing else:
        the pattern guard still runs first and on every call, a *fresh* validator is
        still constructed for every evaluation, the no-retrieval registry is still
        applied, and ``iter_errors`` is still the evaluation. No prepared validator
        is ever stored or shared — it carries mutable state, and lending one across
        requests would trade a latency problem for a correctness one.

        Evaluation works from an **owned snapshot**, so the content that was
        identified is provably the content that is judged, and a caller mutating its
        own dict afterwards cannot make a marker authorise different content. A
        schema that cannot be safely owned (non-finite floats, non-string keys,
        exotic containers, cycles) simply takes the uncached path with unchanged
        semantics — the optimization has no say in whether a contract is valid.
        """
        snapshot, digest = prepare_identity(schema)

        pattern_breaches = self._check_schema_patterns(snapshot)
        if pattern_breaches:
            return pattern_breaches

        key = (
            None
            if digest is None
            else preparation_key(digest, self._validator_cls, self._format_checking)
        )
        if key is None or not self._preparation_cache.is_prepared(key):
            try:
                self._validator_cls.check_schema(snapshot)
            except SchemaError as exc:
                return [
                    BreachDetail(
                        rule="SEMANTIC_SCHEMA",
                        field="<schema>",
                        message=sanitize_breach_message(
                            f"Invalid schema: {exc.message}"
                        ),
                    )
                ]
            if key is not None:
                # Recorded only after a genuine success, so the cache stays strictly
                # positive. A worker whose governed caller has already timed out may
                # still land here; that is permitted because the marker carries
                # preparation truth for a schema and no payload or result truth
                # whatsoever, and final-result ownership stays with the use case.
                self._preparation_cache.mark_prepared(key)

        format_checker = None
        if self._format_checking:
            format_checker = getattr(self._validator_cls, "FORMAT_CHECKER", None)
        validator = self._validator_cls(
            snapshot, format_checker=format_checker, registry=self._registry
        )
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
