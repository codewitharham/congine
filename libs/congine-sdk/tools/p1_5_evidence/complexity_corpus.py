"""Parameterised schema corpus for the Slice-E complexity experiment.

Slice E asks whether a deterministic **static** property of an admitted contract
predicts semantic evaluation risk well enough to justify a production admission
decision. Answering that honestly needs a corpus that varies one structural axis
at a time, so a correlation can be attributed to *something*, and it needs payload
variation, so a schema-only predictor can be falsified rather than flattered.

Design rules, all of which exist to keep the evidence trustworthy:

* **Parameterised families, never arbitrary random schemas.** Each fixture is a
  pure function of its parameters, so the corpus is reproducible and its content
  hash is meaningful.
* **The Slice-A/B corpus in :mod:`tools.p1_5_evidence.fixtures` is untouched.**
  Its digests are baselined inside ``baseline/pre_change_benchmark.json`` and
  ``baseline/post_slice_b_capability.json``; editing it would silently invalidate
  earlier evidence. This module is additive.
* **Predictor fixtures must be genuinely admissible.** Slice E measures the cost
  of *supported, admitted* contracts, not of arbitrary JSON Schema documents, so
  every predictor fixture is verified through the real admission path before it
  may be measured (see :func:`validate_corpus`). A refused predictor fixture is a
  corpus failure, never a silent omission.
* **Refusal controls are labelled and excluded from predictor statistics.** They
  keep the Slice-B *safety* axis visibly distinct from the Slice-E *cost* axis:
  Slice B refuses contracts because capability is absent, which is a different
  question from whether an enforceable contract is expensive.
* **No pathological stdlib-regex fixtures.** Slice B closed that problem by
  making RE2 the semantic engine; re-introducing catastrophic backtracking here
  would measure a defect that no longer exists.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Sequence, Tuple

from congine_core.domain.contract_admission import (
    ContractAdmissionMode,
    admit_contract,
)
from congine_core.domain.schema_vocabulary import NATIVE_ENFORCED_KEYWORDS
from congine_core.infrastructure.jsonschema_validator import (
    JsonSchemaSemanticValidator,
)
from congine_core.security_limits import DEFAULT_MAX_SCHEMA_BYTES
from congine_core.semantic_capability import SemanticCapability
from tools.p1_5_evidence import fixtures

#: Bumped when fixture generation changes. A recorded observation citing a
#: different version describes a different corpus and must not be compared.
CORPUS_VERSION = 1

#: The dialect every structural family is generated for. Dialect-sensitive
#: behaviour is measured separately by the ``dialect`` family rather than by
#: silently re-running everything five times.
PRIMARY_DRAFT = "draft202012"

#: Every draft the SDK's ``jsonschema_draft`` config accepts.
ALL_DRAFTS: Tuple[str, ...] = (
    "draft4",
    "draft6",
    "draft7",
    "draft201909",
    "draft202012",
)

#: Format names tried by the ``format`` family, in fixed order. The corpus keeps
#: only those the wired checker can genuinely assert; the rest are recorded as
#: skipped with a reason rather than generated and then refused. See
#: :func:`format_candidates` for why this is not a silent omission.
FORMAT_CANDIDATES: Tuple[str, ...] = (
    "email",
    "ipv4",
    "ipv6",
    "date-time",
    "uri",
    "uuid",
)

PREDICTOR = "predictor"
REFUSAL_CONTROL = "refusal-control"


@dataclass(frozen=True)
class CorpusCase:
    """One schema, its payload classes, and the policy it must be measured under.

    ``draft`` and ``format_checking`` are part of the case rather than of the run
    because they change which validator class is built and therefore what
    preparation actually costs — two cases sharing schema bytes but not a dialect
    are two different experiments (see ``measurement_context_id``).
    """

    family: str
    name: str
    parameters: Mapping[str, Any]
    schema: Mapping[str, Any]
    payloads: Mapping[str, Any]
    kind: str = PREDICTOR
    draft: str = PRIMARY_DRAFT
    format_checking: bool = False
    note: str = ""

    @property
    def digest(self) -> str:
        """Content hash of the schema alone."""
        return fixtures.digest(dict(self.schema))

    @property
    def canonical_bytes(self) -> int:
        return len(fixtures.canonical(dict(self.schema)))

    def context_key(self, capability_identity: str) -> str:
        """Deterministic ``measurement_context_id`` for this case.

        Preparation is payload-independent but **not** context-independent: the
        same bytes under draft 7 and under 2020-12 build different validator
        classes and run a different ``check_schema``. Identity therefore spans
        the schema *and* the evaluator configuration, so the two are recorded as
        separate observations rather than collapsed into one.
        """
        material = "|".join(
            (
                self.digest,
                self.draft,
                "format=on" if self.format_checking else "format=off",
                capability_identity,
            )
        )
        return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Structural families
# ---------------------------------------------------------------------------

#: Applied to every generated string property so the families measure semantic
#: evaluation rather than the rule engine's type check alone.
_STRING_CONSTRAINTS = {"minLength": 2, "maxLength": 40, "pattern": "^[a-z0-9]+$"}

_GOOD = "abc123"
_TOO_SHORT = "a"
_BAD_CHARS = "!!!"


def _width_family() -> List[CorpusCase]:
    """Property count, everything else fixed."""
    cases: List[CorpusCase] = []
    for count in (1, 5, 10, 25, 50, 100, 200):
        keys = [f"f{i}" for i in range(count)]
        schema = {
            "type": "object",
            "properties": {k: {"type": "string", **_STRING_CONSTRAINTS} for k in keys},
            "required": keys[: min(3, count)],
        }
        valid = {k: _GOOD for k in keys}
        early = dict(valid)
        early[keys[0]] = _BAD_CHARS
        late = dict(valid)
        late[keys[-1]] = _BAD_CHARS
        cases.append(
            CorpusCase(
                family="width",
                name=f"width-{count}",
                parameters={"properties": count},
                schema=schema,
                payloads={
                    "wide-valid": valid,
                    "early-invalid": early,
                    "late-invalid": late,
                },
            )
        )
    return cases


def _depth_family() -> List[CorpusCase]:
    """Nesting depth at fixed width, so depth is the only moving part."""
    cases: List[CorpusCase] = []
    width = 2
    for depth in (1, 2, 3, 4, 5, 6):
        node: Dict[str, Any] = {"type": "string", **_STRING_CONSTRAINTS}
        for _ in range(depth):
            node = {
                "type": "object",
                "properties": {f"c{i}": node for i in range(width)},
            }
        schema = {"type": "object", "properties": {"root": node}}

        def build(value: str, level: int = depth) -> Any:
            payload: Any = value
            for _ in range(level):
                payload = {f"c{i}": payload for i in range(width)}
            return payload

        valid = {"root": build(_GOOD)}
        deep_invalid = _replace_deepest({"root": build(_GOOD)}, depth, _BAD_CHARS)
        shallow_invalid = {"root": _GOOD if depth else _BAD_CHARS}
        cases.append(
            CorpusCase(
                family="depth",
                name=f"depth-{depth}",
                parameters={"depth": depth, "width": width},
                schema=schema,
                payloads={
                    "deep-valid": valid,
                    "deep-invalid": deep_invalid,
                    "early-invalid": shallow_invalid,
                },
            )
        )
    return cases


def _replace_deepest(payload: Any, depth: int, value: str) -> Any:
    """Return *payload* with its deepest first-branch leaf replaced."""
    if depth <= 0:
        return value
    if not isinstance(payload, dict):
        return value
    out = dict(payload)
    key = sorted(out)[0]
    out[key] = _replace_deepest(out[key], depth - 1, value)
    return out


def _combinator_family() -> List[CorpusCase]:
    """Combinator breadth, one keyword at a time.

    ``anyOf``/``oneOf`` branches are mutually exclusive ``const`` clauses, which
    makes "satisfied by an early branch" and "satisfied only by a late branch"
    genuinely different work rather than a relabelling of the same evaluation.
    """
    cases: List[CorpusCase] = []
    for keyword in ("anyOf", "oneOf"):
        for breadth in (2, 5, 10, 25):
            branches = [{"const": f"v{i}"} for i in range(breadth)]
            schema = {
                "type": "object",
                "properties": {"f0": {"type": "string", keyword: branches}},
            }
            cases.append(
                CorpusCase(
                    family=keyword.lower(),
                    name=f"{keyword.lower()}-{breadth}",
                    parameters={"breadth": breadth, "keyword": keyword},
                    schema=schema,
                    payloads={
                        "early-branch": {"f0": "v0"},
                        "late-branch": {"f0": f"v{breadth - 1}"},
                        "all-branches-fail": {"f0": "zzz"},
                    },
                )
            )

    for breadth in (2, 5, 10, 25):
        # allOf branches all have to hold, so there is no early/late distinction
        # to make; the meaningful contrast is conforming vs failing.
        branches = [{"minLength": i + 1} for i in range(breadth)]
        schema = {
            "type": "object",
            "properties": {"f0": {"type": "string", "allOf": branches}},
        }
        cases.append(
            CorpusCase(
                family="allof",
                name=f"allof-{breadth}",
                parameters={"breadth": breadth, "keyword": "allOf"},
                schema=schema,
                payloads={
                    "valid": {"f0": "x" * (breadth + 4)},
                    "invalid": {"f0": ""},
                },
            )
        )
    return cases


def _combinator_depth_family() -> List[CorpusCase]:
    """Combinators nested inside combinators."""
    cases: List[CorpusCase] = []
    for depth in (1, 2, 3):
        node: Dict[str, Any] = {"minLength": 2}
        for _ in range(depth):
            node = {"allOf": [{"anyOf": [node, {"maxLength": 200}]}]}
        schema = {
            "type": "object",
            "properties": {"f0": {"type": "string", **node}},
        }
        cases.append(
            CorpusCase(
                family="combo-depth",
                name=f"combo-depth-{depth}",
                parameters={"combinator_depth": depth},
                schema=schema,
                payloads={"valid": {"f0": _GOOD}, "invalid": {"f0": 5}},
            )
        )
    return cases


def _enum_family() -> List[CorpusCase]:
    """Enum cardinality, and cardinality spread across several properties."""
    cases: List[CorpusCase] = []
    for cardinality in (10, 50, 200, 1000):
        members = [f"v{i}" for i in range(cardinality)]
        schema = {
            "type": "object",
            "properties": {"f0": {"type": "string", "enum": members}},
        }
        cases.append(
            CorpusCase(
                family="enum",
                name=f"enum-{cardinality}",
                parameters={"properties": 1, "cardinality": cardinality},
                schema=schema,
                payloads={
                    "early-valid": {"f0": "v0"},
                    "late-valid": {"f0": members[-1]},
                    "invalid": {"f0": "absent"},
                },
            )
        )

    for count, cardinality in ((10, 50), (25, 200)):
        members = [f"v{i}" for i in range(cardinality)]
        keys = [f"f{i}" for i in range(count)]
        schema = {
            "type": "object",
            "properties": {k: {"type": "string", "enum": members} for k in keys},
        }
        cases.append(
            CorpusCase(
                family="enum",
                name=f"enum-{count}x{cardinality}",
                parameters={"properties": count, "cardinality": cardinality},
                schema=schema,
                payloads={
                    "early-valid": {k: "v0" for k in keys},
                    "late-valid": {k: members[-1] for k in keys},
                    "invalid": {k: "absent" for k in keys},
                },
            )
        )
    return cases


def _array_family() -> List[CorpusCase]:
    """Array-shaping keywords, with element counts that vary evaluation work."""
    cases: List[CorpusCase] = []

    for length in (10, 100):
        schema = {
            "type": "object",
            "properties": {
                "f0": {
                    "type": "array",
                    "items": {"type": "string", **_STRING_CONSTRAINTS},
                    "minItems": 1,
                    "maxItems": length * 2,
                }
            },
        }
        valid = [_GOOD] * length
        late = [_GOOD] * (length - 1) + [_BAD_CHARS]
        cases.append(
            CorpusCase(
                family="array",
                name=f"array-items-{length}",
                parameters={"keyword": "items", "elements": length},
                schema=schema,
                payloads={
                    "valid": {"f0": valid},
                    "late-invalid": {"f0": late},
                    "early-invalid": {"f0": [_BAD_CHARS] + valid[1:]},
                },
            )
        )

    contains_schema = {
        "type": "object",
        "properties": {
            "f0": {
                "type": "array",
                "contains": {"const": "needle"},
                "minContains": 1,
                "maxContains": 3,
            }
        },
    }
    cases.append(
        CorpusCase(
            family="array",
            name="array-contains-50",
            parameters={"keyword": "contains", "elements": 50},
            schema=contains_schema,
            payloads={
                "early-valid": {"f0": ["needle"] + ["hay"] * 49},
                "late-valid": {"f0": ["hay"] * 49 + ["needle"]},
                "invalid": {"f0": ["hay"] * 50},
            },
        )
    )

    prefix_schema = {
        "type": "object",
        "properties": {
            "f0": {
                "type": "array",
                "prefixItems": [
                    {"type": "string", "minLength": 1},
                    {"type": "integer"},
                    {"type": "boolean"},
                    {"type": "string", "pattern": "^[a-z]+$"},
                    {"type": "number"},
                ],
                "items": {"type": "string"},
            }
        },
    }
    cases.append(
        CorpusCase(
            family="array",
            name="array-prefixitems-5",
            parameters={"keyword": "prefixItems", "entries": 5},
            schema=prefix_schema,
            payloads={
                "valid": {"f0": ["a", 1, True, "abc", 1.5, "tail"]},
                "early-invalid": {"f0": [1, 1, True, "abc", 1.5]},
                "late-invalid": {"f0": ["a", 1, True, "ABC", 1.5]},
            },
        )
    )
    return cases


def _regex_family() -> List[CorpusCase]:
    """RE2-safe patterns: how many, and how long.

    Pattern length is grown by repeating a character class rather than by nesting
    quantifiers, so the fixtures stay linear-time on any engine. Slice B already
    established that catastrophic backtracking is not reachable here.
    """
    cases: List[CorpusCase] = []
    for count in (1, 5, 25, 100):
        for units in (1, 5, 25):
            pattern = "^" + "[a-z0-9]" * units + "$"
            keys = [f"f{i}" for i in range(count)]
            schema = {
                "type": "object",
                "properties": {k: {"type": "string", "pattern": pattern} for k in keys},
            }
            match = "a" * units
            cases.append(
                CorpusCase(
                    family="regex",
                    name=f"regex-{count}x{len(pattern)}",
                    parameters={
                        "patterns": count,
                        "pattern_chars": len(pattern),
                        "units": units,
                    },
                    schema=schema,
                    payloads={
                        "valid": {k: match for k in keys},
                        "early-invalid": {
                            k: (_BAD_CHARS if i == 0 else match)
                            for i, k in enumerate(keys)
                        },
                        "late-invalid": {
                            k: (_BAD_CHARS if i == count - 1 else match)
                            for i, k in enumerate(keys)
                        },
                    },
                )
            )
    return cases


def _ref_family() -> List[CorpusCase]:
    """Local reference count, graph depth, and reuse vs distinct targets."""
    cases: List[CorpusCase] = []
    leaf = {"type": "string", **_STRING_CONSTRAINTS}

    for count in (1, 10, 40, 100):
        keys = [f"f{i}" for i in range(count)]
        schema = {
            "type": "object",
            "$defs": {"S": dict(leaf)},
            "properties": {k: {"$ref": "#/$defs/S"} for k in keys},
        }
        cases.append(
            CorpusCase(
                family="refs",
                name=f"refs-repeat-{count}",
                parameters={"refs": count, "targets": 1},
                schema=schema,
                payloads={
                    "valid": {k: _GOOD for k in keys},
                    "late-invalid": {
                        k: (_TOO_SHORT if i == count - 1 else _GOOD)
                        for i, k in enumerate(keys)
                    },
                },
            )
        )

    for count in (10, 40):
        keys = [f"f{i}" for i in range(count)]
        schema = {
            "type": "object",
            "$defs": {f"S{i}": dict(leaf) for i in range(count)},
            "properties": {k: {"$ref": f"#/$defs/S{i}"} for i, k in enumerate(keys)},
        }
        cases.append(
            CorpusCase(
                family="refs",
                name=f"refs-distinct-{count}",
                parameters={"refs": count, "targets": count},
                schema=schema,
                payloads={
                    "valid": {k: _GOOD for k in keys},
                    "late-invalid": {
                        k: (_TOO_SHORT if i == count - 1 else _GOOD)
                        for i, k in enumerate(keys)
                    },
                },
            )
        )

    for depth in (1, 2, 3, 4, 5):
        defs: Dict[str, Any] = {"L0": dict(leaf)}
        for level in range(1, depth + 1):
            defs[f"L{level}"] = {"$ref": f"#/$defs/L{level - 1}"}
        schema = {
            "type": "object",
            "$defs": defs,
            "properties": {"f0": {"$ref": f"#/$defs/L{depth}"}},
        }
        cases.append(
            CorpusCase(
                family="ref-depth",
                name=f"ref-depth-{depth}",
                parameters={"ref_chain": depth},
                schema=schema,
                payloads={
                    "valid": {"f0": _GOOD},
                    "invalid": {"f0": _TOO_SHORT},
                },
            )
        )
    return cases


def _format_family(supported: Sequence[str]) -> List[CorpusCase]:
    """Format assertions, measured with format checking genuinely on.

    Only names the wired checker can actually assert are generated; see
    :func:`format_candidates`.
    """
    samples = {
        "email": ("user@example.com", "not-an-email"),
        "ipv4": ("192.0.2.1", "999.999.999.999"),
        "ipv6": ("2001:db8::1", "zzzz::1"),
        "date-time": ("2026-08-23T10:00:00Z", "not-a-date"),
        "uri": ("https://example.com/a", ":::"),
        "uuid": ("f81d4fae-7dec-11d0-a765-00a0c91e6bf6", "not-a-uuid"),
    }
    cases: List[CorpusCase] = []
    for name in supported:
        good, bad = samples[name]
        schema = {
            "type": "object",
            "properties": {"f0": {"type": "string", "format": name}},
        }
        cases.append(
            CorpusCase(
                family="format",
                name=f"format-{name}",
                parameters={"format": name},
                schema=schema,
                payloads={"valid": {"f0": good}, "invalid": {"f0": bad}},
                format_checking=True,
            )
        )
    return cases


def _dialect_family() -> List[CorpusCase]:
    """Representative fixtures across every supported draft.

    Exclusive bounds are spelled per-dialect on purpose: draft 4 asserts them as
    booleans modifying ``minimum``/``maximum``, draft 6 onward as standalone
    numbers. Using one spelling everywhere would generate a contract that is
    legitimately refused on the other dialects, which would be a corpus bug
    rather than evidence.
    """
    cases: List[CorpusCase] = []
    for draft in ALL_DRAFTS:
        core = {
            "type": "object",
            "properties": {
                f"f{i}": {"type": "string", **_STRING_CONSTRAINTS} for i in range(10)
            },
        }
        cases.append(
            CorpusCase(
                family="dialect",
                name=f"dialect-core-{draft}",
                parameters={"shape": "core"},
                schema=core,
                payloads={
                    "valid": {f"f{i}": _GOOD for i in range(10)},
                    "invalid": {f"f{i}": _BAD_CHARS for i in range(10)},
                },
                draft=draft,
            )
        )

        if draft == "draft4":
            bound: Dict[str, Any] = {
                "type": "number",
                "minimum": 0,
                "exclusiveMinimum": True,
                "maximum": 100,
                "exclusiveMaximum": True,
            }
        else:
            bound = {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 100}
        cases.append(
            CorpusCase(
                family="dialect",
                name=f"dialect-bounds-{draft}",
                parameters={"shape": "exclusive-bounds"},
                schema={"type": "object", "properties": {"f0": bound}},
                payloads={"valid": {"f0": 50}, "invalid": {"f0": 0}},
                draft=draft,
                note="draft4 uses the boolean modifier form; draft6+ the numeric form",
            )
        )

        cases.append(
            CorpusCase(
                family="dialect",
                name=f"dialect-refs-{draft}",
                parameters={"shape": "local-refs", "refs": 10},
                schema={
                    "type": "object",
                    "$defs": {"S": {"type": "string", **_STRING_CONSTRAINTS}},
                    "properties": {f"f{i}": {"$ref": "#/$defs/S"} for i in range(10)},
                },
                payloads={
                    "valid": {f"f{i}": _GOOD for i in range(10)},
                    "invalid": {f"f{i}": _TOO_SHORT for i in range(10)},
                },
                draft=draft,
            )
        )
    return cases


def _falsification_pairs() -> List[CorpusCase]:
    """Deliberately matched pairs built to break simplistic predictors.

    Each pair holds one candidate feature roughly constant while changing the
    structure underneath it. If cost tracks the feature, the pair members cost
    the same; if it does not, the pair is a counterexample — which is the useful
    outcome.
    """
    cases: List[CorpusCase] = []

    flat_keys = [f"f{i}" for i in range(12)]
    cases.append(
        CorpusCase(
            family="pair-properties",
            name="pair-properties-flat-12",
            parameters={"properties": 12, "shape": "flat"},
            schema={
                "type": "object",
                "properties": {
                    k: {"type": "string", **_STRING_CONSTRAINTS} for k in flat_keys
                },
            },
            payloads={"valid": {k: _GOOD for k in flat_keys}},
            note="same property count as pair-properties-nested-12, depth 1",
        )
    )
    nested: Dict[str, Any] = {"type": "string", **_STRING_CONSTRAINTS}
    for _ in range(3):
        nested = {"type": "object", "properties": {f"c{i}": nested for i in range(2)}}
    nested_payload: Any = _GOOD
    for _ in range(3):
        nested_payload = {f"c{i}": nested_payload for i in range(2)}
    cases.append(
        CorpusCase(
            family="pair-properties",
            name="pair-properties-nested-12",
            parameters={"properties": 12, "shape": "nested"},
            schema={
                "type": "object",
                "properties": {"a": nested, "b": nested},
            },
            payloads={"valid": {"a": nested_payload, "b": nested_payload}},
            note="same property count as pair-properties-flat-12, depth 4",
        )
    )

    cases.append(
        CorpusCase(
            family="pair-structure",
            name="pair-structure-flat",
            parameters={"shape": "flat"},
            schema={
                "type": "object",
                "properties": {
                    f"f{i}": {"type": "string", "minLength": 1, "maxLength": 40}
                    for i in range(16)
                },
            },
            payloads={"valid": {f"f{i}": _GOOD for i in range(16)}},
            note="node count matched against pair-structure-combinator",
        )
    )
    cases.append(
        CorpusCase(
            family="pair-structure",
            name="pair-structure-combinator",
            parameters={"shape": "combinator"},
            schema={
                "type": "object",
                "properties": {
                    f"f{i}": {
                        "type": "string",
                        "allOf": [{"minLength": 1}, {"maxLength": 40}],
                    }
                    for i in range(16)
                },
            },
            payloads={"valid": {f"f{i}": _GOOD for i in range(16)}},
            note="same constraints as pair-structure-flat, expressed via allOf",
        )
    )

    leaf = {"type": "string", **_STRING_CONSTRAINTS}
    cases.append(
        CorpusCase(
            family="pair-refgraph",
            name="pair-refgraph-wide",
            parameters={"shape": "wide", "refs": 20},
            schema={
                "type": "object",
                "$defs": {"S": dict(leaf)},
                "properties": {f"f{i}": {"$ref": "#/$defs/S"} for i in range(20)},
            },
            payloads={"valid": {f"f{i}": _GOOD for i in range(20)}},
            note="byte size matched against pair-refgraph-deep, flat ref graph",
        )
    )
    deep_defs: Dict[str, Any] = {"L0": dict(leaf)}
    for level in range(1, 5):
        deep_defs[f"L{level}"] = {"$ref": f"#/$defs/L{level - 1}"}
    cases.append(
        CorpusCase(
            family="pair-refgraph",
            name="pair-refgraph-deep",
            parameters={"shape": "deep", "refs": 20},
            schema={
                "type": "object",
                "$defs": deep_defs,
                "properties": {f"f{i}": {"$ref": "#/$defs/L4"} for i in range(20)},
            },
            payloads={"valid": {f"f{i}": _GOOD for i in range(20)}},
            note="byte size matched against pair-refgraph-wide, 5-deep ref chain",
        )
    )
    return cases


def _refusal_controls() -> List[CorpusCase]:
    """Contracts admission MUST refuse. Never measured as predictor cost.

    These exist to keep the two axes distinct. Slice B refuses a contract because
    the evaluator cannot enforce it — a capability-truth question. Slice E asks
    whether a contract the evaluator *can* enforce should be refused for cost.
    Mixing them would let a safety refusal masquerade as a cost boundary.
    """
    return [
        CorpusCase(
            family="control",
            name="control-external-ref",
            parameters={"reason": "external reference"},
            schema={
                "type": "object",
                "properties": {"f0": {"$ref": "http://example.invalid/s.json"}},
            },
            payloads={},
            kind=REFUSAL_CONTROL,
            note="P1.5 supports verified local JSON-pointer references only",
        ),
        CorpusCase(
            family="control",
            name="control-dangling-ref",
            parameters={"reason": "unresolvable local pointer"},
            schema={
                "type": "object",
                "$defs": {"S": {"type": "string"}},
                "properties": {"f0": {"$ref": "#/$defs/Missing"}},
            },
            payloads={},
            kind=REFUSAL_CONTROL,
        ),
        CorpusCase(
            family="control",
            name="control-unenforced-keyword",
            parameters={"reason": "annotation-only keyword"},
            schema={
                "type": "object",
                "properties": {"f0": {"type": "string", "contentEncoding": "base64"}},
            },
            payloads={},
            kind=REFUSAL_CONTROL,
            note="contentEncoding is annotation-only on every supported draft",
        ),
        CorpusCase(
            family="control",
            name="control-unsupported-format",
            parameters={"reason": "no checker for this format name"},
            schema={
                "type": "object",
                "properties": {"f0": {"type": "string", "format": "not-a-real-format"}},
            },
            payloads={},
            kind=REFUSAL_CONTROL,
            format_checking=True,
        ),
        CorpusCase(
            family="control",
            name="control-unsafe-regex",
            parameters={"reason": "pattern RE2 cannot compile"},
            schema={
                "type": "object",
                "properties": {"f0": {"type": "string", "pattern": "(a+)+\\1"}},
            },
            payloads={},
            kind=REFUSAL_CONTROL,
            note="backreference: rejected by RE2, so the clause would never assert",
        ),
    ]


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------


def format_candidates(
    supported: "frozenset[str]",
) -> Tuple[Tuple[str, ...], Dict[str, str]]:
    """Split :data:`FORMAT_CANDIDATES` into generated and skipped names.

    A format name whose checker is not installed in this environment is not a
    *refused* predictor fixture — it is a capability this evaluator does not have,
    so no admissible fixture exists to generate. Skipping is therefore correct,
    but it must never be silent: the reason is recorded and reported alongside the
    corpus so a reader can see which formats the run did and did not cover.
    """
    kept = tuple(name for name in FORMAT_CANDIDATES if name in supported)
    skipped = {
        name: "no checker installed in this environment"
        for name in FORMAT_CANDIDATES
        if name not in supported
    }
    return kept, skipped


def build(supported_formats: "frozenset[str]") -> List[CorpusCase]:
    """Return the whole corpus in canonical order, predictors then controls."""
    kept, _ = format_candidates(supported_formats)
    cases: List[CorpusCase] = []
    cases.extend(_width_family())
    cases.extend(_depth_family())
    cases.extend(_combinator_family())
    cases.extend(_combinator_depth_family())
    cases.extend(_enum_family())
    cases.extend(_array_family())
    cases.extend(_regex_family())
    cases.extend(_ref_family())
    cases.extend(_format_family(kept))
    cases.extend(_dialect_family())
    cases.extend(_falsification_pairs())
    cases.extend(_refusal_controls())
    return cases


def predictors(cases: Sequence[CorpusCase]) -> Tuple[CorpusCase, ...]:
    return tuple(c for c in cases if c.kind == PREDICTOR)


def controls(cases: Sequence[CorpusCase]) -> Tuple[CorpusCase, ...]:
    return tuple(c for c in cases if c.kind == REFUSAL_CONTROL)


def corpus_hash(cases: Sequence[CorpusCase]) -> str:
    """Content hash of the entire corpus, including policy and payloads.

    Payloads are part of the identity because a Slice-E conclusion about payload
    sensitivity is only reproducible if the payloads are.
    """
    digest = hashlib.sha256()
    digest.update(f"v{CORPUS_VERSION}".encode("utf-8"))
    for case in cases:
        digest.update(case.name.encode("utf-8"))
        digest.update(case.kind.encode("utf-8"))
        digest.update(case.draft.encode("utf-8"))
        digest.update(b"1" if case.format_checking else b"0")
        digest.update(fixtures.canonical(dict(case.schema)).encode("utf-8"))
        for label in sorted(case.payloads):
            digest.update(label.encode("utf-8"))
            digest.update(
                fixtures.canonical({"p": case.payloads[label]}).encode("utf-8")
            )
    return digest.hexdigest()


@dataclass(frozen=True)
class CorpusReport:
    """Outcome of validating the corpus against real admission and the preflight."""

    admitted: Tuple[str, ...] = field(default_factory=tuple)
    refused_controls: Tuple[str, ...] = field(default_factory=tuple)
    failures: Tuple[str, ...] = field(default_factory=tuple)
    oversize: Tuple[str, ...] = field(default_factory=tuple)
    witnesses: Mapping[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.failures and not self.oversize


# ---------------------------------------------------------------------------
# Admission + preflight gate
# ---------------------------------------------------------------------------


def evaluator(draft: str, format_checking: bool) -> Any:
    """Build the concrete semantic evaluator a case must be measured under."""
    return JsonSchemaSemanticValidator(
        jsonschema_draft=draft, format_checking=format_checking
    )


def capability_identity(capability: SemanticCapability) -> str:
    """Stable short hash of everything a capability asserts.

    Part of ``measurement_context_id``: two runs that derived different
    capabilities from the same dialect string are not comparable experiments, and
    a bare draft name would hide that.
    """
    material = "|".join(
        (
            capability.draft,
            ",".join(sorted(capability.enforced_keywords)),
            str(capability.format_assertion),
            ",".join(sorted(capability.supported_formats)),
            str(capability.allow_external_references),
            str(capability.boolean_exclusive_bounds),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def enforced_keywords_for(capability: SemanticCapability) -> "frozenset[str]":
    """Compose the admission keyword set exactly as ``SyncContractsUseCase`` does.

    Reproducing the composition rather than approximating it is the point: a gate
    that judged fixtures against a hand-written keyword list would prove nothing
    about what CONGINE actually admits.
    """
    return frozenset(set(NATIVE_ENFORCED_KEYWORDS) | set(capability.enforced_keywords))


def admit(case: CorpusCase) -> Tuple[Any, SemanticCapability]:
    """Run *case* through the real admission path under its own policy."""
    validator = evaluator(case.draft, case.format_checking)
    capability = validator.capability
    result = admit_contract(
        dict(case.schema),
        mode=ContractAdmissionMode.STRICT,
        enforced_keywords=enforced_keywords_for(capability),
        capability=capability,
    )
    return result, capability


def validate_corpus(
    cases: Sequence[CorpusCase], *, max_schema_bytes: int = DEFAULT_MAX_SCHEMA_BYTES
) -> CorpusReport:
    """Verify the corpus is measurable before any timing is taken.

    Two independent conditions, both hard failures:

    * **Admission truth.** Every predictor fixture must be admitted under its own
      draft, format policy and derived capability; every refusal control must be
      refused. A predictor fixture that is refused is a corpus bug and stops the
      experiment — it is never quietly dropped, because dropping it would bias the
      corpus toward whatever the current admission rules happen to like.
    * **Preflight non-interference.** Every predictor schema must be smaller than
      the schema-size preflight limit. Measuring a schema the ordinary safety
      preflight would refuse would attribute cost to a contract that can never
      reach the evaluator in production.
    """
    admitted: List[str] = []
    refused: List[str] = []
    failures: List[str] = []
    oversize: List[str] = []
    witnesses: Dict[str, Any] = {}

    for case in cases:
        result, capability = admit(case)
        reasons = [f"{i.code}@{i.path}: {i.message}" for i in result.issues]
        witnesses[case.name] = {
            "schema_digest": case.digest,
            "draft": case.draft,
            "format_checking": case.format_checking,
            "capability_identity": capability_identity(capability),
            "capability_draft": capability.draft,
            "admitted": result.admitted,
            "issues": reasons[:5],
            "canonical_bytes": case.canonical_bytes,
        }

        if case.kind == PREDICTOR:
            if not result.admitted:
                failures.append(
                    f"predictor {case.name!r} was REFUSED under {case.draft}"
                    f" (format_checking={case.format_checking}): {reasons[:3]}"
                )
            else:
                admitted.append(case.name)
            if case.canonical_bytes >= max_schema_bytes:
                oversize.append(
                    f"predictor {case.name!r} is {case.canonical_bytes} canonical "
                    f"bytes, at or above the {max_schema_bytes}-byte schema preflight"
                )
        else:
            if result.admitted:
                failures.append(
                    f"refusal control {case.name!r} was ADMITTED under {case.draft}"
                    f" (format_checking={case.format_checking})"
                )
            else:
                refused.append(case.name)

    return CorpusReport(
        admitted=tuple(admitted),
        refused_controls=tuple(refused),
        failures=tuple(failures),
        oversize=tuple(oversize),
        witnesses=witnesses,
    )


def supported_formats(draft: str = PRIMARY_DRAFT) -> "frozenset[str]":
    """Format names the wired checker can genuinely assert on *draft*."""
    return evaluator(draft, True).capability.supported_formats
