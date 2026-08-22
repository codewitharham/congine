"""P1.5 Slice B — semantic safety: capability truth, RE2 regex, reference policy.

Every test here corresponds to a defect that was *measured* in Slice A0 rather
than imagined. Each defect had the same shape and it is the shape G12 forbids:
**contract admission advertised enforcement the wired evaluator did not deliver**,
so a clause looked like active policy while asserting nothing.

Grouped by the finding they close:

* ``TestRegexEngine`` — semantic ``pattern`` ran on CPython's backtracking ``re``
  while the native engine used RE2, so a catastrophic pattern could run orders of
  magnitude past the configured budget.
* ``TestReferencePolicy`` — an external ``$ref`` performed a real network fetch,
  letting a remote document decide enforcement.
* ``TestCapabilityTruth`` — admission was dialect-blind and advertised keywords
  the configured draft silently ignores.
"""

from __future__ import annotations

import time

import pytest
from jsonschema import Draft7Validator, Draft202012Validator

from congine_core import admit_contract
from congine_core.domain.contract_admission import (
    ContractAdmissionCode,
    ContractAdmissionMode,
)
from congine_core.infrastructure.jsonschema_validator import (
    JsonSchemaSemanticValidator,
    derive_capability,
)
from congine_core.semantic_capability import SemanticCapability

DRAFTS = ("draft4", "draft6", "draft7", "draft201909", "draft202012")


def _admit(schema: object, capability: SemanticCapability) -> object:
    return admit_contract(
        schema,
        mode=ContractAdmissionMode.STRICT,
        enforced_keywords=capability.enforced_keywords,
        capability=capability,
    )


def _capability(draft: str = "draft202012", *, formats: bool = False):
    return JsonSchemaSemanticValidator(
        jsonschema_draft=draft, format_checking=formats
    ).capability


def _codes(result: object) -> set[str]:
    return {str(issue.code) for issue in result.errors}  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
class TestRegexEngine:
    """Semantic regex must be RE2, and must keep JSON Schema search semantics."""

    @pytest.mark.parametrize(
        ("value", "breaches"),
        [("xxabcxx", False), ("abc", False), ("xyz", True)],
    )
    def test_pattern_uses_search_not_full_match(
        self, value: str, breaches: bool
    ) -> None:
        """``pattern`` is a *search*: ``"abc"`` matches ``"xxabcxx"``.

        The native rule engine full-matches; inheriting that here would silently
        tighten every semantic contract, rejecting payloads JSON Schema accepts.
        """
        schema = {"type": "object", "properties": {"f": {"pattern": "abc"}}}
        found = JsonSchemaSemanticValidator().validate({"f": value}, schema)
        assert bool(found) is breaches

    def test_pattern_properties_matches_names_by_search(self) -> None:
        """``patternProperties`` searches property *names*, not full-matches them."""
        schema = {"type": "object", "patternProperties": {"n_": {"type": "number"}}}
        validator = JsonSchemaSemanticValidator()
        assert validator.validate({"xxn_yy": "not-a-number"}, schema)
        assert not validator.validate({"other": "anything"}, schema)

    def test_catastrophic_pattern_stays_linear(self) -> None:
        """A pattern that was exponential under ``re`` must stay flat under RE2.

        Measured pre-P1.5 on this exact input family: 7.6 ms at 16 characters,
        7 689 ms at 26 — and because the match held the GIL, the executor's
        deadline could not be observed on time. The bound here is deliberately
        loose (it must survive slow CI), because the property under test is the
        *absence of exponential growth*, not a latency figure.
        """
        schema = {"type": "object", "properties": {"f": {"pattern": "^(a+)+$"}}}
        validator = JsonSchemaSemanticValidator()
        started = time.perf_counter()
        validator.validate({"f": "a" * 60 + "!"}, schema)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        assert elapsed_ms < 1000.0, f"regex took {elapsed_ms:.1f}ms; RE2 not in use?"

    @pytest.mark.parametrize("pattern", ["(?<=a)b", "(?!x)y"])
    def test_non_re2_pattern_is_refused_at_admission(self, pattern: str) -> None:
        """RE2 supports neither lookaround nor backreferences.

        Since evaluation runs on RE2, a pattern it cannot compile must never
        become active policy — otherwise the clause would be unenforceable at
        exactly the moment it mattered.
        """
        schema = {"type": "object", "properties": {"f": {"pattern": pattern}}}
        result = _admit(schema, _capability())
        assert not result.admitted  # type: ignore[attr-defined]
        assert ContractAdmissionCode.INVALID_PATTERN in _codes(result)

    def test_nested_and_pattern_properties_regexes_are_checked(self) -> None:
        """Regex validation is recursive, and covers ``patternProperties`` keys.

        Admission previously inspected only top-level ``properties``, so a
        pattern nested inside another object — or used as a
        ``patternProperties`` key, which is itself a regex — reached the
        evaluator entirely unchecked.
        """
        nested = {
            "type": "object",
            "properties": {
                "o": {"type": "object", "properties": {"x": {"pattern": "(?<=a)b"}}}
            },
        }
        keys = {"type": "object", "patternProperties": {"(?<=a)b": {"type": "number"}}}
        combinator = {
            "type": "object",
            "properties": {"f": {"allOf": [{"pattern": "(?<=a)b"}]}},
        }
        for schema in (nested, keys, combinator):
            result = _admit(schema, _capability())
            assert not result.admitted  # type: ignore[attr-defined]
            assert ContractAdmissionCode.INVALID_PATTERN in _codes(result)

    def test_re2_safe_patterns_still_admitted_and_enforced(self) -> None:
        """The RE2 subset must not cost ordinary, well-formed contracts."""
        schema = {"type": "object", "properties": {"f": {"pattern": "^[a-z0-9]+$"}}}
        assert _admit(schema, _capability()).admitted  # type: ignore[attr-defined]
        assert JsonSchemaSemanticValidator().validate({"f": "NOPE!"}, schema)


# --------------------------------------------------------------------------- #
class TestReferencePolicy:
    """Only verified local JSON-pointer references are supported."""

    @pytest.mark.parametrize(
        "ref",
        [
            "http://example.invalid/s.json",
            "https://example.invalid/s.json",
            "file:///etc/passwd",
            "other.json#/x",
        ],
    )
    def test_external_reference_refused_at_admission(self, ref: str) -> None:
        """Resolving these means a real fetch, so a remote document would decide policy."""
        schema = {"type": "object", "properties": {"f": {"$ref": ref}}}
        result = _admit(schema, _capability())
        assert not result.admitted  # type: ignore[attr-defined]
        assert ContractAdmissionCode.UNSUPPORTED_REFERENCE in _codes(result)

    def test_external_reference_never_retrieved_even_if_admission_bypassed(
        self,
    ) -> None:
        """Defence in depth: the evaluator must fail closed on its own.

        Admission is the primary control, but a schema written straight into
        storage bypasses it (the documented D-ADM deferral), so the evaluator
        carries a no-retrieval registry independently.
        """
        schema = {
            "type": "object",
            "properties": {"f": {"$ref": "http://example.invalid/s.json"}},
        }
        with pytest.raises(Exception) as excinfo:
            JsonSchemaSemanticValidator().validate({"f": "x"}, schema)
        # Fails closed as "not evaluated" rather than silently passing.
        assert "example.invalid" in str(excinfo.value)

    def test_missing_local_reference_refused(self) -> None:
        schema = {"type": "object", "properties": {"f": {"$ref": "#/$defs/ABSENT"}}}
        result = _admit(schema, _capability())
        assert not result.admitted  # type: ignore[attr-defined]
        assert ContractAdmissionCode.UNSUPPORTED_REFERENCE in _codes(result)

    def test_cyclic_local_reference_refused(self) -> None:
        """Recursive schemas are valid JSON Schema but unsupported here.

        Refused deliberately as an unsupported CONGINE subset: evaluating one
        exhausts the stack, so admission converts a runtime crash into an
        actionable rejection.
        """
        schema = {
            "type": "object",
            "$defs": {"A": {"$ref": "#/$defs/A"}},
            "properties": {"f": {"$ref": "#/$defs/A"}},
        }
        result = _admit(schema, _capability())
        assert not result.admitted  # type: ignore[attr-defined]
        assert ContractAdmissionCode.UNSUPPORTED_REFERENCE in _codes(result)

    @pytest.mark.parametrize("container", ["$defs", "definitions"])
    def test_valid_local_reference_admitted_and_enforced(self, container: str) -> None:
        """Blocking retrieval must cost no legitimate capability."""
        schema = {
            "type": "object",
            container: {"S": {"type": "number"}},
            "properties": {"f": {"$ref": f"#/{container}/S"}},
        }
        assert _admit(schema, _capability()).admitted  # type: ignore[attr-defined]
        assert JsonSchemaSemanticValidator().validate({"f": "not-a-number"}, schema)

    def test_rfc6901_escaped_pointer_resolves(self) -> None:
        """``~1`` is ``/`` and ``~0`` is ``~``; ``~01`` must decode to ``~1``."""
        schema = {
            "type": "object",
            "$defs": {"a/b": {"type": "number"}, "c~1d": {"type": "number"}},
            "properties": {
                "f": {"$ref": "#/$defs/a~1b"},
                "g": {"$ref": "#/$defs/c~01d"},
            },
        }
        assert _admit(schema, _capability()).admitted  # type: ignore[attr-defined]


# --------------------------------------------------------------------------- #
class TestCapabilityTruth:
    """Admission may advertise only what the configured dialect really enforces."""

    @pytest.mark.parametrize("keyword", ["contentEncoding", "contentMediaType"])
    @pytest.mark.parametrize("draft", DRAFTS)
    def test_annotation_only_keywords_refused(self, keyword: str, draft: str) -> None:
        """Annotation-only on every supported draft — no validator asserts them."""
        schema = {"type": "object", "properties": {"f": {keyword: "base64"}}}
        result = _admit(schema, _capability(draft))
        assert not result.admitted  # type: ignore[attr-defined]
        assert ContractAdmissionCode.UNSUPPORTED_KEYWORD in _codes(result)

    def test_dialect_specific_keyword_refused_on_older_draft(self) -> None:
        """``minContains`` exists from 2019-09; draft7 ignores it silently."""
        schema = {
            "type": "object",
            "properties": {
                "f": {"type": "array", "contains": {"type": "number"}, "minContains": 2}
            },
        }
        assert not _admit(schema, _capability("draft7")).admitted  # type: ignore[attr-defined]
        assert _admit(schema, _capability("draft202012")).admitted  # type: ignore[attr-defined]

    def test_format_requires_assertion_and_a_concrete_checker(self) -> None:
        """Both conditions matter, and neither implies the other."""
        known = {"type": "object", "properties": {"f": {"format": "email"}}}
        unknown = {"type": "object", "properties": {"f": {"format": "unknown-xyz"}}}

        assert not _admit(known, _capability(formats=False)).admitted  # type: ignore[attr-defined]
        assert _admit(known, _capability(formats=True)).admitted  # type: ignore[attr-defined]
        # Assertion on, but no checker exists for this name.
        assert not _admit(unknown, _capability(formats=True)).admitted  # type: ignore[attr-defined]

    @pytest.mark.parametrize("draft", DRAFTS)
    def test_capability_reports_its_own_dialect(self, draft: str) -> None:
        assert _capability(draft).draft == draft

    def test_derived_capability_grows_with_the_draft(self) -> None:
        """A newer dialect must never advertise *fewer* keywords than an older one."""
        counts = [len(_capability(d).enforced_keywords) for d in DRAFTS]
        assert counts == sorted(counts), counts

    def test_composed_keywords_are_not_under_reported(self) -> None:
        """``then``/``else`` and ``minContains``/``maxContains`` have no handler.

        They are asserted inside the ``if`` and ``contains`` handlers, so
        deriving capability from ``VALIDATORS`` membership alone would
        under-report them and refuse valid contracts.
        """
        modern = _capability("draft202012")
        for keyword in ("then", "else", "minContains", "maxContains"):
            assert modern.enforces(keyword), keyword

    def test_capability_never_permits_external_references(self) -> None:
        for draft in DRAFTS:
            assert _capability(draft).allow_external_references is False

    def test_native_only_capability_enforces_nothing_semantic(self) -> None:
        native = SemanticCapability.native_only()
        assert native.draft == "none"
        assert not native.enforced_keywords
        assert not native.enforces_format("email")

    @pytest.mark.parametrize(
        ("validator_cls", "expected"),
        [(Draft7Validator, "draft7"), (Draft202012Validator, "draft202012")],
    )
    def test_derive_capability_reads_the_concrete_class(
        self, validator_cls: type, expected: str
    ) -> None:
        derived = derive_capability(validator_cls, format_checking=False)
        assert derived.draft == expected
        assert not derived.format_assertion
        assert not derived.supported_formats

    def test_admission_without_capability_keeps_legacy_behaviour(self) -> None:
        """The ``capability`` argument is additive; older callers are unaffected."""
        schema = {"type": "object", "properties": {"f": {"type": "string"}}}
        result = admit_contract(
            schema,
            mode=ContractAdmissionMode.STRICT,
            enforced_keywords=frozenset({"type", "properties"}),
        )
        assert result.admitted
