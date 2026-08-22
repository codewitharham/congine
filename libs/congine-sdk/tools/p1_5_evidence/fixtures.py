"""Fixed, content-hashed schema corpus for P1.5 evidence.

Every fixture is built by a pure function of its parameters and hashed with the
same canonical serialisation, so two runs can prove they measured identical
inputs. If a fixture is edited, its hash changes and stale comparisons become
visibly invalid rather than silently wrong.

Shapes vary along more than property count deliberately — P1.5-03 asks whether a
*static* property predicts semantic cost, and a corpus that only varies width
could not answer that.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, Tuple

#: Every fixture keeps this literal size so payload construction is comparable.
_VALUE = "abc123"


def canonical(schema: Dict[str, Any]) -> str:
    """Serialise *schema* stably so its hash is order-independent."""
    return json.dumps(schema, sort_keys=True, separators=(",", ":"))


def digest(schema: Dict[str, Any]) -> str:
    """Return the content digest used to identify a fixture across runs."""
    return hashlib.sha256(canonical(schema).encode("utf-8")).hexdigest()


def _flat(count: int, extra: Dict[str, Any] | None = None) -> Dict[str, Any]:
    properties: Dict[str, Any] = {}
    for index in range(count):
        spec: Dict[str, Any] = {"type": "string"}
        if extra:
            spec.update(extra)
        properties[f"f{index}"] = spec
    return {
        "type": "object",
        "properties": properties,
        "required": [f"f{i}" for i in range(min(3, count))],
    }


def _nested(depth: int, width: int = 3) -> Dict[str, Any]:
    node: Dict[str, Any] = {"type": "string", "minLength": 1}
    for _ in range(depth):
        node = {"type": "object", "properties": {f"c{i}": node for i in range(width)}}
    return node


def _combinators(count: int) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            f"f{i}": {
                "allOf": [{"type": "string", "minLength": 1}, {"maxLength": 50}],
                "anyOf": [{"pattern": "^[a-z]"}, {"pattern": "^[0-9]"}],
            }
            for i in range(count)
        },
    }


def _enums(count: int, cardinality: int) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            f"f{i}": {"type": "string", "enum": [f"v{j}" for j in range(cardinality)]}
            for i in range(count)
        },
    }


def _refs(count: int) -> Dict[str, Any]:
    return {
        "type": "object",
        "$defs": {"S": {"type": "string", "minLength": 1, "maxLength": 40}},
        "properties": {f"f{i}": {"$ref": "#/$defs/S"} for i in range(count)},
    }


#: Semantic constraints applied to the "semantic-*" width series.
_SEM = {"minLength": 2, "maxLength": 40, "pattern": "^[a-z0-9]+$"}

#: name -> schema. Fixed corpus; edit only with a recorded reason.
CORPUS: Dict[str, Dict[str, Any]] = {
    "native-small": _flat(3),
    "native-medium": _flat(25),
    "native-large": _flat(120),
    "semantic-small": _flat(3, _SEM),
    "semantic-medium": _flat(25, _SEM),
    "semantic-large": _flat(120, _SEM),
    "semantic-nested-d4": _nested(4),
    "semantic-nested-d6": _nested(6),
    "semantic-combinator-20": _combinators(20),
    "semantic-enum-10x200": _enums(10, 200),
    "semantic-refs-40": _refs(40),
}


def payload_for(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Build a conforming payload for *schema*.

    Conforming inputs are used for cost measurement so timings reflect full
    evaluation rather than an early exit on the first breach.
    """
    if schema.get("type") == "object":
        props = schema.get("properties", {})
        if props:
            return {key: _value_for(spec, schema) for key, spec in props.items()}
        return {"f0": _VALUE}
    return {"f0": _VALUE}


def _value_for(spec: Dict[str, Any], root: Dict[str, Any]) -> Any:
    if "$ref" in spec:
        return _VALUE
    if "enum" in spec:
        return spec["enum"][0]
    if spec.get("type") == "object":
        return {k: _value_for(v, root) for k, v in spec.get("properties", {}).items()}
    return _VALUE


def manifest() -> Dict[str, Dict[str, Any]]:
    """Return ``name -> {digest, bytes, nodes}`` for the whole corpus."""
    out: Dict[str, Dict[str, Any]] = {}
    for name, schema in CORPUS.items():
        out[name] = {
            "digest": digest(schema),
            "bytes": len(canonical(schema)),
            "nodes": count_nodes(schema),
        }
    return out


def count_nodes(node: Any) -> int:
    """Count schema nodes — one candidate static predictor for P1.5-03."""
    if isinstance(node, dict):
        return 1 + sum(count_nodes(v) for v in node.values())
    if isinstance(node, list):
        return sum(count_nodes(v) for v in node)
    return 0


def static_features(schema: Dict[str, Any]) -> Dict[str, int]:
    """Deterministic static properties evaluated as cost predictors (P1.5-03).

    Computed from the canonical form so equivalent schemas that differ only in
    key ordering produce identical features.
    """
    feats = {
        "nodes": count_nodes(schema),
        "bytes": len(canonical(schema)),
        "max_depth": _depth(schema),
        "properties": _count_key(schema, "properties", container=True),
        "semantic_keywords": _count_semantic(schema),
        "regexes": _count_key(schema, "pattern"),
        "regex_chars": _regex_chars(schema),
        "combinators": sum(
            _count_key(schema, k)
            for k in ("allOf", "anyOf", "oneOf", "not", "if", "then", "else")
        ),
        "enum_values": _enum_values(schema),
        "refs": _count_key(schema, "$ref"),
    }
    return feats


_SEMANTIC_KEYS = frozenset(
    {
        "minLength",
        "maxLength",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "items",
        "minItems",
        "maxItems",
        "uniqueItems",
        "contains",
        "additionalProperties",
        "minProperties",
        "maxProperties",
        "patternProperties",
        "propertyNames",
        "dependentRequired",
        "allOf",
        "anyOf",
        "oneOf",
        "not",
        "if",
        "then",
        "else",
        "const",
        "$ref",
        "$defs",
    }
)


def _depth(node: Any, level: int = 0) -> int:
    if not isinstance(node, dict):
        return level
    best = level
    for value in node.values():
        if isinstance(value, dict):
            best = max(best, _depth(value, level + 1))
        elif isinstance(value, list):
            for item in value:
                best = max(best, _depth(item, level + 1))
    return best


def _count_key(node: Any, key: str, container: bool = False) -> int:
    total = 0
    if isinstance(node, dict):
        if key in node:
            total += len(node[key]) if container and isinstance(node[key], dict) else 1
        for value in node.values():
            total += _count_key(value, key, container)
    elif isinstance(node, list):
        for item in node:
            total += _count_key(item, key, container)
    return total


def _count_semantic(node: Any) -> int:
    total = 0
    if isinstance(node, dict):
        total += sum(1 for k in node if k in _SEMANTIC_KEYS)
        for value in node.values():
            total += _count_semantic(value)
    elif isinstance(node, list):
        for item in node:
            total += _count_semantic(item)
    return total


def _regex_chars(node: Any) -> int:
    total = 0
    if isinstance(node, dict):
        pattern = node.get("pattern")
        if isinstance(pattern, str):
            total += len(pattern)
        for value in node.values():
            total += _regex_chars(value)
    elif isinstance(node, list):
        for item in node:
            total += _regex_chars(item)
    return total


def _enum_values(node: Any) -> int:
    total = 0
    if isinstance(node, dict):
        enum = node.get("enum")
        if isinstance(enum, list):
            total += len(enum)
        for value in node.values():
            total += _enum_values(value)
    elif isinstance(node, list):
        for item in node:
            total += _enum_values(item)
    return total


def corpus_items() -> Tuple[Tuple[str, Dict[str, Any], Dict[str, Any]], ...]:
    """Return ``(name, schema, payload)`` for the whole corpus, order-stable."""
    return tuple((name, schema, payload_for(schema)) for name, schema in CORPUS.items())
