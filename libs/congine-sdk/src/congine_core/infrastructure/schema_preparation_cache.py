"""Bounded semantic schema-preparation cache (Layer 4).

``jsonschema``'s ``check_schema`` validates a contract against its dialect's
metaschema, and measurement (P1.5 Slice E/F) put it at essentially **all** of
semantic preparation — 8–105 ms on the evidence corpora, against 0.01–0.02 ms for
constructing the validator itself. It is also perfectly deterministic: the same
schema bytes under the same validator class always reach the same verdict. Yet the
evaluator repaid it on every single validation of an unchanged contract.

This module removes that repetition **without** the unsafe shortcut. A prepared
``jsonschema`` validator is never stored, never shared and never reused: it holds
mutable evaluation state, and lending one across requests would trade a latency
problem for a correctness one. What is cached instead is a single immutable fact:

    :data:`CHECK_SCHEMA_VALID` — ``validator_class.check_schema(this exact owned
    schema)`` already completed successfully for this exact cache context.

**A hit skips ``check_schema`` and nothing else.** Every other defence the evaluator
runs — the RE2 pattern guard, the no-retrieval registry, format semantics, fresh
validator construction, payload evaluation — still executes, at its existing point,
in its existing order. Contract admission is untouched and stays at its own
activation boundary in the domain and use-case layers; nothing here duplicates or
weakens it.

Deliberately absent: no process-global state, no cross-container singleton, no
background thread, no executor, no configuration surface, no telemetry. The cache
belongs to one semantic evaluator and is collected with it.
"""

from __future__ import annotations

import hashlib
import json
import math
import sys
import threading
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

__all__ = [
    "CHECK_SCHEMA_CACHE_VERSION",
    "CHECK_SCHEMA_VALID",
    "DEFAULT_CACHE_ENTRIES",
    "SchemaPreparationCache",
    "canonical_blob",
    "content_digest",
    "own_and_audit",
]

#: Bumped if what a marker asserts ever changes, so markers from an older meaning
#: can never authorise a skip under a newer one. Named for the single operation the
#: marker proves rather than for "policy" in general — policies that still run on
#: every validation have no business being represented as cached truth.
CHECK_SCHEMA_CACHE_VERSION = 1

#: The only value ever stored. Immutable, shared, and carrying no payload truth,
#: no result truth and no schema body.
CHECK_SCHEMA_VALID = "CHECK_SCHEMA_VALID"

#: Entries hold a digest string, a fixed-shape key tuple and a shared marker — no
#: schema bodies and no canonical blobs — so bounding by entry count is sufficient.
#: Measured at ~270 bytes per entry (~69 KB full) on the P1.5 reference platform;
#: the exact figure is interpreter- and platform-dependent.
DEFAULT_CACHE_ENTRIES = 256

#: ``(content digest, concrete validator class, format policy, cache version)``.
#: The **class object** is used rather than its name: ``jsonschema.validators.extend``
#: produces an unrelated class, so a name-keyed cache could let a marker prepared
#: against the stock metaschema authorise the RE2-extended class, or the reverse.
CacheKey = Tuple[str, type, bool, int]


def own_and_audit(node: Any) -> Tuple[Any, bool]:
    """Return ``(owned_snapshot, cacheable)`` from a single traversal.

    Two jobs, one walk, because doing them separately would double the cost of the
    thing that has to stay cheap: the snapshot gives the evaluator content the
    caller can no longer mutate, and the audit decides whether that content can be
    canonicalised into a stable identity at all.

    Cache-safe content is exactly plain JSON — ``None``, ``bool``, ``int``, a
    **finite** ``float``, ``str``, inside built-in ``dict`` (string keys only) and
    ``list``. Everything else returns ``cacheable=False``:

    * ``NaN`` / ``±Inf`` have no JSON spelling, so they cannot yield a stable digest.
    * Non-string keys would be coerced to strings by serialisation, making two
      different schemas share one identity.
    * Custom ``Mapping``/``list`` subclasses may carry behaviour that a plain copy
      would silently drop, so they are refused rather than optimistically owned.
    * Container cycles would otherwise recurse forever.

    ``bool`` is tested **before** ``int`` on purpose: ``isinstance(True, int)`` is
    ``True`` in Python, so the obvious ordering would re-own ``True`` as ``1`` and
    digest content the caller never supplied.

    A ``False`` result is an **optimization boundary, never a validation verdict**.
    The caller takes the ordinary uncached path with entirely unchanged semantics;
    inability to cache must never become a new way for a contract to fail.
    """
    return _own(node, frozenset())


def _own(node: Any, active: "frozenset[int]") -> Tuple[Any, bool]:
    # `active` holds the containers on the current path so a self-referential
    # structure is refused rather than recursed into. Only the *path* is tracked,
    # not every visited node: a schema legitimately repeats sub-objects, and
    # treating repetition as a cycle would needlessly refuse valid contracts.
    if node is None or isinstance(node, (str, bool)):
        return node, True
    if isinstance(node, int):
        return node, True
    if isinstance(node, float):
        return (node, True) if math.isfinite(node) else (None, False)
    if type(node) is dict:
        if id(node) in active:
            return None, False
        nested = active | {id(node)}
        owned: Dict[str, Any] = {}
        for key, value in node.items():
            if type(key) is not str:
                return None, False
            child, ok = _own(value, nested)
            if not ok:
                return None, False
            owned[key] = child
        return owned, True
    if type(node) is list:
        if id(node) in active:
            return None, False
        nested = active | {id(node)}
        items: List[Any] = []
        for value in node:
            child, ok = _own(value, nested)
            if not ok:
                return None, False
            items.append(child)
        return items, True
    return None, False


def canonical_blob(snapshot: Any) -> str:
    """Serialise an owned snapshot so equal content always yields equal bytes.

    ``sort_keys`` makes key ordering irrelevant, which is the point: two callers
    building the same contract in different orders must share one cache entry.
    ``allow_nan=False`` is defence in depth — :func:`own_and_audit` has already
    refused non-finite floats, and this turns any regression there into a loud
    failure rather than a ``NaN`` token silently entering a content digest.
    """
    return json.dumps(snapshot, sort_keys=True, separators=(",", ":"), allow_nan=False)


def content_digest(blob: str) -> str:
    """Cryptographic identity of canonical schema content.

    Internal cache identity only. It is never exposed as storage or version
    identity, and it is never derived from a contract id — a contract id can be
    reused for different content, which is exactly the confusion that would let one
    contract's preparation authorise another's.
    """
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


class SchemaPreparationCache:
    """Bounded LRU of :data:`CHECK_SCHEMA_VALID` markers, owned by one evaluator.

    **The lock is metadata-only.** It guards lookup, recency, insertion, eviction
    and the counters — and is deliberately *not* held across snapshotting,
    canonicalisation, digesting, ``check_schema``, validator construction or
    evaluation. Holding it across a cold ``check_schema`` would make one expensive
    schema serialise every unrelated semantic validation in the process, turning a
    latency optimization into a throughput regression.

    The consequence is accepted openly: two threads racing on the same cold schema
    may both run ``check_schema`` before either inserts. That wastes work once and
    costs nothing in correctness, because the operation is deterministic and the
    marker is idempotent. No single-flight machinery is added for it — that would
    reintroduce exactly the shared waiting this design avoids.
    """

    __slots__ = ("_entries", "_lock", "_capacity", "_hits", "_misses", "_evictions")

    def __init__(self, capacity: int = DEFAULT_CACHE_ENTRIES) -> None:
        """Args:
        capacity: Maximum retained markers. Eviction costs a repeated
            ``check_schema``, never a different verdict, which is why this is an
            internal constant rather than a configuration knob.
        """
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self._entries: "OrderedDict[CacheKey, str]" = OrderedDict()
        self._lock = threading.Lock()
        self._capacity = capacity
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def is_prepared(self, key: CacheKey) -> bool:
        """Whether ``check_schema`` already succeeded for *key*."""
        with self._lock:
            if key in self._entries:
                self._entries.move_to_end(key)
                self._hits += 1
                return True
            self._misses += 1
            return False

    def mark_prepared(self, key: CacheKey) -> None:
        """Record that ``check_schema`` succeeded for *key*.

        Only ever called after a genuine success, so the cache is strictly positive:
        a malformed schema is not negative-cached. That keeps exception identity and
        stale error text out of the cache entirely, and admission already stops
        unsupported contracts on governed paths.
        """
        with self._lock:
            self._entries[key] = CHECK_SCHEMA_VALID
            self._entries.move_to_end(key)
            while len(self._entries) > self._capacity:
                self._entries.popitem(last=False)
                self._evictions += 1

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def capacity(self) -> int:
        return self._capacity

    def stats(self) -> Dict[str, int]:
        """Hit/miss/eviction counts.

        Internal observability for tests and P1.5 evidence. Deliberately **not**
        surfaced through health or telemetry: a cache counter is a performance
        detail, and P1.5 does not widen the public wire surface for one.
        """
        with self._lock:
            return {
                "hits": self._hits,
                "misses": self._misses,
                "evictions": self._evictions,
                "entries": len(self._entries),
                "capacity": self._capacity,
            }

    def _clear(self) -> None:
        """Drop every marker. Test and evidence use only.

        Underscore-named and referenced by no runtime path. It exists so a cold
        measurement can be re-established without rebuilding a whole evaluator,
        which would otherwise charge validator-class construction to the cold
        timing and overstate the cold overhead.
        """
        with self._lock:
            self._entries.clear()

    def _retained_bytes(self) -> int:
        """Conservative measured footprint. Test and evidence use only.

        Counts the container, each key tuple and the digest string it owns. The
        validator class and the marker are single shared objects pointed at by every
        entry, so charging each entry their full size would overstate the footprint
        several-fold.
        """
        with self._lock:
            total = sys.getsizeof(self._entries)
            for key in self._entries:
                total += sys.getsizeof(key) + sys.getsizeof(key[0])
            return total + sys.getsizeof(CHECK_SCHEMA_VALID)


def preparation_key(
    digest: str, validator_cls: type, format_checking: bool
) -> CacheKey:
    """Assemble the cache identity for one schema under one evaluator context.

    ``format_checking`` cannot actually change what ``check_schema`` decides — it
    governs assertion at evaluation time. It is included anyway, as deliberate
    defensive isolation: two differently configured evaluators never share markers,
    so a future change to that relationship cannot silently invalidate cached truth.
    """
    return (digest, validator_cls, bool(format_checking), CHECK_SCHEMA_CACHE_VERSION)


def prepare_identity(schema: Any) -> Tuple[Any, Optional[str]]:
    """Return ``(owned_snapshot, digest)``; ``digest`` is ``None`` when uncacheable.

    Convenience for the single caller, keeping the audit/canonicalise/digest
    sequence in one place so the snapshot that is digested is provably the snapshot
    that is later evaluated.
    """
    snapshot, cacheable = own_and_audit(schema)
    if not cacheable:
        return schema, None
    return snapshot, content_digest(canonical_blob(snapshot))
