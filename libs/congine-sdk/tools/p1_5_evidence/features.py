"""Static structural features evaluated as semantic-cost predictors (Slice E).

Every feature here is a deterministic, cheap, semantically explainable property
of the schema **document** — never of a payload, never of a measured time, never
of the machine. That restriction is the whole point: Slice E asks whether a
*static* property can justify a production admission decision, and a feature that
needs a stopwatch could not, however well it correlated.

This module deliberately lives in ``tools/`` and stays there. It is evidence
tooling, not a domain classifier; nothing in ``src/congine_core`` imports it, and
a negative Slice-E result means nothing here ever moves inward (Slice E §12/§14).

Relationship to :mod:`tools.p1_5_evidence.fixtures`: that module's
``static_features`` is frozen Slice-A/B evidence methodology and is **not**
modified. :func:`extract` is a superset computed the same way — from the
canonical form, so key ordering cannot change a feature value.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Set

from tools.p1_5_evidence import fixtures

#: Bumped when a feature definition changes meaning. A recorded observation that
#: cites a different version must not be compared against a newer one.
FEATURE_SCHEMA_VERSION = 1

#: Keywords whose value is a nested schema, a list of schemas, or a map of them.
#: Used for structural traversal, not for admission decisions.
_SCHEMA_VALUED = (
    "items",
    "contains",
    "not",
    "if",
    "then",
    "else",
    "propertyNames",
    "additionalProperties",
)
_SCHEMA_LIST_VALUED = ("allOf", "anyOf", "oneOf", "prefixItems")
_SCHEMA_MAP_VALUED = ("properties", "patternProperties", "$defs", "definitions")

_COMBINATORS = ("allOf", "anyOf", "oneOf")

_ARRAY_CONSTRAINTS = (
    "items",
    "prefixItems",
    "contains",
    "minContains",
    "maxContains",
    "minItems",
    "maxItems",
    "uniqueItems",
)

#: Documented in the Slice-E report. Kept beside the code so a future reader does
#: not have to reconstruct a definition from an implementation.
FEATURE_DEFINITIONS: Dict[str, str] = {
    "bytes": "Length of the canonical (sorted-key, separator-tight) serialisation.",
    "nodes": "Total schema nodes, counted as in Slice A/B so the two agree.",
    "max_depth": "Deepest nested mapping level reachable from the root.",
    "properties": "Total declared properties across every 'properties' map.",
    "semantic_keywords": "Count of keywords a semantic evaluator (not the rule engine) executes.",
    "regexes": "Number of 'pattern' clauses.",
    "regex_chars": "Total characters across all 'pattern' values.",
    "max_regex_chars": "Longest single 'pattern' value, in characters.",
    "enum_values": "Total enum members summed across every 'enum' clause.",
    "enum_max_cardinality": "Largest single 'enum' clause, in members.",
    "combinators": "Number of allOf/anyOf/oneOf clauses.",
    "max_combinator_breadth": "Largest branch count in any single combinator clause.",
    "combinator_product": (
        "Product of every combinator's branch count, capped at 10**9. An "
        "*approximate* worst-case expansion, not an evaluation count: real "
        "evaluators short-circuit anyOf and do not expand allOf combinatorially."
    ),
    "max_combinator_depth": "Deepest nesting of combinators inside combinators.",
    "array_constraints": "Count of array-shaping keywords (items, contains, minItems, ...).",
    "prefix_items": "Number of 'prefixItems' entries summed across the document.",
    "contains_count": "Number of 'contains' clauses.",
    "refs": "Total '$ref' occurrences, including repeats of one target.",
    "distinct_ref_targets": "Number of distinct '$ref' pointer values.",
    "repeated_refs": "refs minus distinct_ref_targets: how much reuse the graph has.",
    "ref_graph_depth": (
        "Longest chain of $ref-to-$ref hops resolvable inside the document. 0 when "
        "no reference target itself contains a reference."
    ),
    "defs_count": "Number of entries under '$defs'/'definitions'.",
}


def extract(schema: Mapping[str, Any]) -> Dict[str, int]:
    """Return every static feature for *schema*, order-independently."""
    canonical = fixtures.canonical(dict(schema))
    breadths = _combinator_breadths(schema)
    ref_pointers = _ref_pointers(schema)
    enum_sizes = _enum_sizes(schema)
    regex_lengths = _regex_lengths(schema)

    return {
        "bytes": len(canonical),
        "nodes": fixtures.count_nodes(dict(schema)),
        "max_depth": _depth(schema),
        "properties": _count_properties(schema),
        "semantic_keywords": _count_semantic(schema),
        "regexes": len(regex_lengths),
        "regex_chars": sum(regex_lengths),
        "max_regex_chars": max(regex_lengths, default=0),
        "enum_values": sum(enum_sizes),
        "enum_max_cardinality": max(enum_sizes, default=0),
        "combinators": len(breadths),
        "max_combinator_breadth": max(breadths, default=0),
        "combinator_product": _product(breadths),
        "max_combinator_depth": _combinator_depth(schema),
        "array_constraints": sum(_count_key(schema, k) for k in _ARRAY_CONSTRAINTS),
        "prefix_items": _prefix_items(schema),
        "contains_count": _count_key(schema, "contains"),
        "refs": len(ref_pointers),
        "distinct_ref_targets": len(set(ref_pointers)),
        "repeated_refs": len(ref_pointers) - len(set(ref_pointers)),
        "ref_graph_depth": _ref_graph_depth(schema),
        "defs_count": _defs_count(schema),
    }


#: Feature order used wherever a stable column sequence is needed.
FEATURE_NAMES = tuple(sorted(FEATURE_DEFINITIONS))


def _walk(node: Any) -> "List[Mapping[str, Any]]":
    """Every mapping node in the document, root first, order-stable."""
    found: List[Mapping[str, Any]] = []
    if isinstance(node, Mapping):
        found.append(node)
        for value in node.values():
            found.extend(_walk(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk(item))
    return found


def _depth(node: Any, level: int = 0) -> int:
    if not isinstance(node, Mapping):
        return level
    best = level
    for value in node.values():
        if isinstance(value, Mapping):
            best = max(best, _depth(value, level + 1))
        elif isinstance(value, list):
            for item in value:
                best = max(best, _depth(item, level + 1))
    return best


def _count_key(node: Any, key: str) -> int:
    return sum(1 for found in _walk(node) if key in found)


def _count_properties(node: Any) -> int:
    total = 0
    for found in _walk(node):
        properties = found.get("properties")
        if isinstance(properties, Mapping):
            total += len(properties)
    return total


def _count_semantic(node: Any) -> int:
    return sum(
        1
        for found in _walk(node)
        for key in found
        if key in fixtures._SEMANTIC_KEYS  # noqa: SLF001 - one shared definition
    )


def _regex_lengths(node: Any) -> "List[int]":
    lengths: List[int] = []
    for found in _walk(node):
        pattern = found.get("pattern")
        if isinstance(pattern, str):
            lengths.append(len(pattern))
        properties = found.get("patternProperties")
        if isinstance(properties, Mapping):
            lengths.extend(len(str(k)) for k in properties)
    return lengths


def _enum_sizes(node: Any) -> "List[int]":
    sizes: List[int] = []
    for found in _walk(node):
        enum = found.get("enum")
        if isinstance(enum, list):
            sizes.append(len(enum))
    return sizes


def _combinator_breadths(node: Any) -> "List[int]":
    breadths: List[int] = []
    for found in _walk(node):
        for keyword in _COMBINATORS:
            branches = found.get(keyword)
            if isinstance(branches, list):
                breadths.append(len(branches))
    return breadths


def _product(values: "List[int]") -> int:
    """Capped product. Uncapped this overflows into meaningless magnitudes."""
    total = 1
    for value in values:
        total *= max(1, value)
        if total >= 10**9:
            return 10**9
    return total


def _combinator_depth(node: Any, inside: int = 0) -> int:
    """Deepest combinator-within-combinator nesting."""
    if isinstance(node, Mapping):
        here = inside
        best = inside
        for keyword in _COMBINATORS:
            if isinstance(node.get(keyword), list):
                here = inside + 1
                break
        for key, value in node.items():
            child = here if key in _COMBINATORS else inside
            best = max(best, _combinator_depth(value, child))
        return max(best, here)
    if isinstance(node, list):
        return max((_combinator_depth(item, inside) for item in node), default=inside)
    return inside


def _prefix_items(node: Any) -> int:
    total = 0
    for found in _walk(node):
        entries = found.get("prefixItems")
        if isinstance(entries, list):
            total += len(entries)
    return total


def _defs_count(node: Any) -> int:
    total = 0
    for found in _walk(node):
        for keyword in ("$defs", "definitions"):
            entries = found.get(keyword)
            if isinstance(entries, Mapping):
                total += len(entries)
    return total


def _ref_pointers(node: Any) -> "List[str]":
    pointers: List[str] = []
    for found in _walk(node):
        ref = found.get("$ref")
        if isinstance(ref, str):
            pointers.append(ref)
    return pointers


def _ref_graph_depth(schema: Mapping[str, Any]) -> int:
    """Longest resolvable ``$ref`` → ``$ref`` chain inside the document.

    Cycles are impossible in an admitted contract — admission refuses them — but
    this is evidence tooling that also runs over refusal controls, so the walk
    carries a visited set rather than trusting that guarantee.
    """
    best = 0
    for pointer in set(_ref_pointers(schema)):
        best = max(best, _chain_length(schema, pointer, set()))
    return best


def _chain_length(schema: Mapping[str, Any], pointer: str, seen: "Set[str]") -> int:
    if pointer in seen:
        return len(seen)
    seen = seen | {pointer}
    target = _resolve(schema, pointer)
    if target is None:
        return len(seen) - 1
    nested = _ref_pointers(target)
    if not nested:
        return len(seen)
    return max(_chain_length(schema, child, seen) for child in nested)


def _resolve(schema: Mapping[str, Any], pointer: str) -> "Mapping[str, Any] | None":
    """Resolve a local JSON pointer, or ``None`` when it does not resolve."""
    if not pointer.startswith("#"):
        return None
    current: Any = schema
    for token in pointer[1:].split("/"):
        if not token:
            continue
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, Mapping) and token in current:
            current = current[token]
        else:
            return None
    return current if isinstance(current, Mapping) else None
