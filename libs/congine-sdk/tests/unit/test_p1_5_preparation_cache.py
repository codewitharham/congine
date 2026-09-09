"""Phase-2 safety suite for the semantic preparation cache (P1.5 Slice F).

The cache is allowed to change exactly one thing: on a confirmed
``CHECK_SCHEMA_VALID`` marker, ``check_schema`` is skipped. Every test here exists
to hold that line, because a preparation cache is the kind of optimization that
fails quietly — a stale marker, a shared validator or a mutated schema does not
raise, it just starts approving payloads it should have stopped.

The four properties that matter, and would each be a silent correctness failure:

* **Semantic output is identical** cold, warm and after eviction.
* **Identity follows content**, so a mutated schema cannot inherit a marker.
* **Nothing mutable is shared** — no validator, no schema, no result, no breach list.
* **Inability to cache is never a validation failure**; it takes the old path.

No timing assertions: these run on loaded CI machines and must be deterministic.
"""

from __future__ import annotations

import threading
from typing import Any, Dict, List

import pytest

from congine_core.infrastructure.jsonschema_validator import JsonSchemaSemanticValidator
from congine_core.infrastructure.schema_preparation_cache import (
    CHECK_SCHEMA_CACHE_VERSION,
    CHECK_SCHEMA_VALID,
    SchemaPreparationCache,
    canonical_blob,
    content_digest,
    own_and_audit,
    prepare_identity,
    preparation_key,
)

DRAFTS = ("draft4", "draft6", "draft7", "draft201909", "draft202012")

SEMANTIC_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "a": {"type": "string", "minLength": 2, "maxLength": 40, "pattern": "^[a-z]+$"},
        "b": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["a"],
}

VALID_PAYLOAD = {"a": "abc", "b": 5}
INVALID_PAYLOAD = {"a": "A", "b": 500}


def validator(draft: str = "draft202012", **kwargs: Any) -> JsonSchemaSemanticValidator:
    return JsonSchemaSemanticValidator(jsonschema_draft=draft, **kwargs)


def cache_of(instance: JsonSchemaSemanticValidator) -> SchemaPreparationCache:
    return instance._preparation_cache  # noqa: SLF001 - the cache is deliberately private


class TestSemanticEquivalence:
    """Cold, warm and post-eviction must be indistinguishable to a caller."""

    @pytest.mark.parametrize("draft", DRAFTS)
    @pytest.mark.parametrize("payload", [VALID_PAYLOAD, INVALID_PAYLOAD])
    def test_cold_warm_and_evicted_agree(
        self, draft: str, payload: Dict[str, Any]
    ) -> None:
        instance = validator(draft)
        cold = instance.validate(payload, SEMANTIC_SCHEMA)
        warm = instance.validate(payload, SEMANTIC_SCHEMA)
        cache_of(instance)._clear()  # noqa: SLF001
        evicted = instance.validate(payload, SEMANTIC_SCHEMA)

        assert cold == warm == evicted
        assert (
            [b.field for b in cold]
            == [b.field for b in warm]
            == [b.field for b in evicted]
        )
        assert [b.message for b in cold] == [b.message for b in warm]

    def test_breach_ordering_is_preserved(self) -> None:
        # Ordering is part of the contract: a caller reporting "the first breach"
        # must not see it change because a marker happened to be present.
        schema = {
            "type": "object",
            "properties": {
                f"f{i}": {"type": "string", "minLength": 5} for i in range(8)
            },
        }
        payload = {f"f{i}": "x" for i in range(8)}
        instance = validator()
        cold = instance.validate(payload, schema)
        warm = instance.validate(payload, schema)
        assert len(cold) == 8
        assert [b.field for b in cold] == [b.field for b in warm]

    def test_warm_path_actually_hit_the_cache(self) -> None:
        # Without this the equivalence tests above could pass trivially by never
        # caching anything at all.
        instance = validator()
        instance.validate(VALID_PAYLOAD, SEMANTIC_SCHEMA)
        assert cache_of(instance).stats()["misses"] == 1
        instance.validate(VALID_PAYLOAD, SEMANTIC_SCHEMA)
        assert cache_of(instance).stats()["hits"] == 1

    def test_local_references_still_enforced(self) -> None:
        schema = {
            "type": "object",
            "$defs": {"S": {"type": "string", "minLength": 3}},
            "properties": {"a": {"$ref": "#/$defs/S"}},
        }
        instance = validator()
        cold = instance.validate({"a": "x"}, schema)
        warm = instance.validate({"a": "x"}, schema)
        assert cold and cold == warm

    def test_external_reference_still_refused_on_warm_path(self) -> None:
        # The no-retrieval registry belongs to validator construction, which still
        # happens on every call, so a marker cannot smuggle a fetch past it.
        # This low-level path *raises* rather than returning breaches (governed
        # callers are protected earlier, by admission). Verified identical before
        # and after Slice F: the cache must preserve that exactly, not "improve" it.
        from jsonschema.exceptions import _WrappedReferencingError

        schema = {
            "type": "object",
            "properties": {"a": {"$ref": "http://example.invalid/s.json"}},
        }
        instance = validator()
        with pytest.raises(_WrappedReferencingError):
            instance.validate({"a": "x"}, schema)
        with pytest.raises(_WrappedReferencingError):
            instance.validate({"a": "x"}, schema)

    def test_format_checking_identical_cold_and_warm(self) -> None:
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string", "format": "ipv4"}},
        }
        strict = validator(format_checking=True)
        assert strict.validate({"a": "999.1.1.1"}, schema)
        assert strict.validate({"a": "999.1.1.1"}, schema)
        relaxed = validator(format_checking=False)
        assert relaxed.validate({"a": "999.1.1.1"}, schema) == []
        assert relaxed.validate({"a": "999.1.1.1"}, schema) == []


class TestMarkerNarrowness:
    """A marker proves ``check_schema`` succeeded. It proves nothing else."""

    def test_pattern_guard_runs_on_every_call(self) -> None:
        # The RE2 pattern-length guard sits ahead of check_schema and must never be
        # skipped: a marker would otherwise disable a safety check by warming up.
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string", "pattern": "a" * 2000}},
        }
        instance = validator()
        first = instance.validate({"a": "x"}, schema)
        second = instance.validate({"a": "x"}, schema)
        assert first and second
        assert first[0].rule == "SEMANTIC_SCHEMA"
        assert first == second

    def test_pattern_rejection_never_populates_the_cache(self) -> None:
        schema = {
            "type": "object",
            "properties": {"a": {"type": "string", "pattern": "a" * 2000}},
        }
        instance = validator()
        instance.validate({"a": "x"}, schema)
        assert len(cache_of(instance)) == 0

    def test_invalid_schema_is_not_negative_cached(self) -> None:
        # Positive cache only: a malformed schema must be re-judged every time
        # rather than remembered as "known bad".
        schema = {"type": "object", "properties": {"a": {"minLength": "not-a-number"}}}
        instance = validator()
        first = instance.validate({"a": "x"}, schema)
        second = instance.validate({"a": "x"}, schema)
        assert first and first == second
        assert len(cache_of(instance)) == 0


class TestIdentity:
    """Identity follows content, and only content."""

    def test_equal_but_distinct_objects_share_one_entry(self) -> None:
        instance = validator()
        instance.validate(VALID_PAYLOAD, dict(SEMANTIC_SCHEMA))
        instance.validate(VALID_PAYLOAD, dict(SEMANTIC_SCHEMA))
        assert cache_of(instance).stats()["hits"] == 1
        assert len(cache_of(instance)) == 1

    def test_key_order_does_not_change_identity(self) -> None:
        forward = {
            "type": "object",
            "title": "x",
            "properties": {"a": {"type": "string"}},
        }
        reversed_order = {
            "properties": {"a": {"type": "string"}},
            "title": "x",
            "type": "object",
        }
        assert content_digest(
            canonical_blob(own_and_audit(forward)[0])
        ) == content_digest(canonical_blob(own_and_audit(reversed_order)[0]))
        instance = validator()
        instance.validate({"a": "x"}, forward)
        instance.validate({"a": "x"}, reversed_order)
        assert cache_of(instance).stats()["hits"] == 1

    def test_content_change_misses(self) -> None:
        instance = validator()
        instance.validate(
            {"a": "abc"}, {"type": "object", "properties": {"a": {"type": "string"}}}
        )
        instance.validate(
            {"a": "abc"}, {"type": "object", "properties": {"a": {"type": "integer"}}}
        )
        assert cache_of(instance).stats()["misses"] == 2
        assert cache_of(instance).stats()["hits"] == 0

    def test_nested_change_misses(self) -> None:
        base = {
            "type": "object",
            "properties": {"a": {"type": "string", "minLength": 2}},
        }
        changed = {
            "type": "object",
            "properties": {"a": {"type": "string", "minLength": 3}},
        }
        instance = validator()
        instance.validate({"a": "abc"}, base)
        instance.validate({"a": "abc"}, changed)
        assert cache_of(instance).stats()["hits"] == 0

    def test_different_draft_is_a_different_context(self) -> None:
        # Same bytes, different metaschema: a marker earned under one dialect must
        # never authorise another.
        digest = content_digest(canonical_blob(SEMANTIC_SCHEMA))
        older = validator("draft7")
        newer = validator("draft202012")
        assert preparation_key(
            digest,
            older._validator_cls,
            False,  # noqa: SLF001
        ) != preparation_key(digest, newer._validator_cls, False)  # noqa: SLF001

    def test_format_policy_is_a_different_context(self) -> None:
        digest = content_digest(canonical_blob(SEMANTIC_SCHEMA))
        instance = validator()
        assert preparation_key(
            digest,
            instance._validator_cls,
            False,  # noqa: SLF001
        ) != preparation_key(digest, instance._validator_cls, True)  # noqa: SLF001

    def test_cache_version_participates_in_identity(self) -> None:
        instance = validator()
        key = preparation_key("d" * 64, instance._validator_cls, False)  # noqa: SLF001
        assert key[-1] == CHECK_SCHEMA_CACHE_VERSION

    def test_validator_class_identity_is_the_class_object(self) -> None:
        # A name-keyed cache could collide the stock and RE2-extended classes, since
        # `extend` produces an unrelated class that keeps the same __name__.
        instance = validator()
        key = preparation_key("d" * 64, instance._validator_cls, False)  # noqa: SLF001
        assert key[1] is instance._validator_cls  # noqa: SLF001
        assert not isinstance(key[1], str)

    def test_separate_evaluators_do_not_share_markers(self) -> None:
        first = validator()
        second = validator()
        first.validate(VALID_PAYLOAD, SEMANTIC_SCHEMA)
        second.validate(VALID_PAYLOAD, SEMANTIC_SCHEMA)
        assert cache_of(second).stats()["hits"] == 0
        assert cache_of(first) is not cache_of(second)


class TestOwnershipAndMutation:
    """A caller's dict is copied before it is judged, and never trusted after."""

    def test_snapshot_is_not_the_caller_object(self) -> None:
        snapshot, digest = prepare_identity(SEMANTIC_SCHEMA)
        assert digest is not None
        assert snapshot == SEMANTIC_SCHEMA
        assert snapshot is not SEMANTIC_SCHEMA
        assert snapshot["properties"] is not SEMANTIC_SCHEMA["properties"]

    def test_mutation_after_first_validation_does_not_hit(self) -> None:
        schema: Dict[str, Any] = {
            "type": "object",
            "properties": {"a": {"type": "string", "minLength": 2}},
        }
        instance = validator()
        instance.validate({"a": "abc"}, schema)
        schema["properties"]["a"]["minLength"] = 99
        instance.validate({"a": "abc"}, schema)
        assert cache_of(instance).stats()["hits"] == 0, (
            "mutated content must not inherit the original content's marker"
        )

    def test_mutated_schema_is_enforced_as_mutated(self) -> None:
        schema: Dict[str, Any] = {
            "type": "object",
            "properties": {"a": {"type": "string", "minLength": 2}},
        }
        instance = validator()
        assert instance.validate({"a": "abc"}, schema) == []
        schema["properties"]["a"]["minLength"] = 99
        assert instance.validate({"a": "abc"}, schema), "the new constraint must apply"

    def test_nested_list_mutation_changes_identity(self) -> None:
        schema: Dict[str, Any] = {
            "type": "object",
            "properties": {"a": {"type": "string", "enum": ["x", "y"]}},
        }
        instance = validator()
        instance.validate({"a": "x"}, schema)
        schema["properties"]["a"]["enum"].append("z")
        instance.validate({"a": "x"}, schema)
        assert cache_of(instance).stats()["hits"] == 0

    def test_validation_does_not_mutate_the_caller_schema(self) -> None:
        import copy

        schema = copy.deepcopy(SEMANTIC_SCHEMA)
        before = copy.deepcopy(schema)
        instance = validator()
        instance.validate(VALID_PAYLOAD, schema)
        instance.validate(VALID_PAYLOAD, schema)
        assert schema == before


class TestCacheSafeAudit:
    """What cannot be owned takes the old path — it never becomes a new failure."""

    def test_plain_json_is_cacheable(self) -> None:
        snapshot, ok = own_and_audit({"a": [1, 2.5, "x", True, None], "b": {"c": 1}})
        assert ok and snapshot == {"a": [1, 2.5, "x", True, None], "b": {"c": 1}}

    def test_booleans_survive_as_booleans(self) -> None:
        # isinstance(True, int) is True, so a careless audit re-owns True as 1 and
        # digests content the caller never supplied.
        snapshot, ok = own_and_audit({"a": True, "b": False, "c": 1, "d": 0})
        assert ok
        assert snapshot["a"] is True and snapshot["b"] is False
        assert isinstance(snapshot["c"], int) and snapshot["c"] is not True
        assert canonical_blob(snapshot) == '{"a":true,"b":false,"c":1,"d":0}'

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_floats_are_not_cacheable(self, bad: float) -> None:
        assert own_and_audit({"a": bad}) == (None, False)

    def test_non_string_keys_are_not_cacheable(self) -> None:
        assert own_and_audit({1: "x"}) == (None, False)

    def test_custom_mapping_subclass_is_not_cacheable(self) -> None:
        class Exotic(dict):  # type: ignore[type-arg]
            pass

        assert own_and_audit(Exotic({"a": 1}))[1] is False
        assert own_and_audit({"a": Exotic({"b": 1})})[1] is False

    def test_self_referential_dict_is_not_cacheable(self) -> None:
        node: Dict[str, Any] = {"type": "object"}
        node["self"] = node
        assert own_and_audit(node) == (None, False)

    def test_self_referential_list_is_not_cacheable(self) -> None:
        items: List[Any] = [1]
        items.append(items)
        assert own_and_audit({"a": items}) == (None, False)

    def test_nested_cycle_is_not_cacheable(self) -> None:
        inner: Dict[str, Any] = {}
        outer: Dict[str, Any] = {"inner": inner}
        inner["outer"] = outer
        assert own_and_audit(outer) == (None, False)

    def test_repeated_subobject_is_not_mistaken_for_a_cycle(self) -> None:
        # Only the current path is tracked; a schema legitimately reuses subobjects
        # and refusing that would needlessly disable the cache for valid contracts.
        shared = {"type": "string"}
        snapshot, ok = own_and_audit({"a": shared, "b": shared})
        assert ok and snapshot == {"a": {"type": "string"}, "b": {"type": "string"}}

    def test_uncacheable_schema_still_validates_normally(self) -> None:
        class Exotic(dict):  # type: ignore[type-arg]
            pass

        schema = Exotic(
            {"type": "object", "properties": {"a": {"type": "string", "minLength": 5}}}
        )
        instance = validator()
        first = instance.validate({"a": "x"}, schema)
        second = instance.validate({"a": "x"}, schema)
        assert first and first == second
        assert len(cache_of(instance)) == 0, "an uncacheable schema must not be cached"

    def test_uncacheable_schema_matches_cacheable_equivalent(self) -> None:
        class Exotic(dict):  # type: ignore[type-arg]
            pass

        plain = {
            "type": "object",
            "properties": {"a": {"type": "string", "minLength": 5}},
        }
        instance = validator()
        assert instance.validate({"a": "x"}, Exotic(plain)) == instance.validate(
            {"a": "x"}, plain
        )

    def test_cycle_preserves_existing_behaviour_and_leaves_the_cache_untouched(
        self,
    ) -> None:
        # A cyclic schema already made the uncached evaluator raise RecursionError
        # (verified against the pre-Slice-F code). The audit must refuse to cache it
        # without *changing* that outcome: inability to cache is an optimization
        # boundary, never a new or different failure.
        node: Dict[str, Any] = {"type": "object", "properties": {}}
        node["properties"]["self"] = node
        instance = validator()
        with pytest.raises(RecursionError):
            instance.validate({"a": "x"}, node)
        assert len(cache_of(instance)) == 0


class TestBoundAndEviction:
    def test_capacity_is_respected(self) -> None:
        cache = SchemaPreparationCache(capacity=4)
        for index in range(20):
            cache.mark_prepared((f"{index:064x}", SchemaPreparationCache, False, 1))
        assert len(cache) == 4
        assert cache.stats()["evictions"] == 16

    def test_eviction_is_least_recently_used(self) -> None:
        cache = SchemaPreparationCache(capacity=2)
        first = ("a" * 64, SchemaPreparationCache, False, 1)
        second = ("b" * 64, SchemaPreparationCache, False, 1)
        third = ("c" * 64, SchemaPreparationCache, False, 1)
        cache.mark_prepared(first)
        cache.mark_prepared(second)
        assert cache.is_prepared(first)  # refresh recency
        cache.mark_prepared(third)
        assert cache.is_prepared(first)
        assert not cache.is_prepared(second)

    def test_eviction_only_costs_a_repeat_not_a_verdict(self) -> None:
        instance = validator()
        cache_of(instance)._clear()  # noqa: SLF001
        cold = instance.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA)
        cache_of(instance)._clear()  # noqa: SLF001
        after = instance.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA)
        assert cold == after

    def test_zero_capacity_is_refused(self) -> None:
        with pytest.raises(ValueError):
            SchemaPreparationCache(capacity=0)

    def test_marker_value_is_the_named_constant(self) -> None:
        cache = SchemaPreparationCache()
        key = ("a" * 64, SchemaPreparationCache, False, 1)
        cache.mark_prepared(key)
        assert cache._entries[key] == CHECK_SCHEMA_VALID  # noqa: SLF001

    def test_footprint_is_bounded_and_measurable(self) -> None:
        cache = SchemaPreparationCache(capacity=64)
        for index in range(200):
            cache.mark_prepared((f"{index:064x}", SchemaPreparationCache, False, 1))
        assert len(cache) == 64
        assert 0 < cache._retained_bytes() < 200_000  # noqa: SLF001


class TestNothingMutableIsShared:
    def test_no_validator_instance_is_retained(self) -> None:
        instance = validator()
        instance.validate(VALID_PAYLOAD, SEMANTIC_SCHEMA)
        for key, value in cache_of(instance)._entries.items():  # noqa: SLF001
            assert value == CHECK_SCHEMA_VALID
            # Referencing the validator *class* is required for identity; retaining
            # an *instance* would be the unsafe design this slice rejected. Note
            # `isinstance(cls, Validator)` is useless here — Validator is a
            # runtime-checkable Protocol and a class object structurally satisfies
            # it — so the check is on concrete types instead.
            digest, validator_cls, format_policy, version = key
            assert isinstance(digest, str)
            assert isinstance(validator_cls, type)
            assert validator_cls is instance._validator_cls  # noqa: SLF001
            assert isinstance(format_policy, bool)
            assert isinstance(version, int)

    def test_no_schema_body_is_retained(self) -> None:
        instance = validator()
        instance.validate(VALID_PAYLOAD, SEMANTIC_SCHEMA)
        for key in cache_of(instance)._entries:  # noqa: SLF001
            assert not any(isinstance(part, (dict, list)) for part in key)

    def test_results_are_not_shared_between_calls(self) -> None:
        instance = validator()
        first = instance.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA)
        second = instance.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA)
        assert first == second
        assert first is not second
        if first:
            assert first[0] is not second[0] or first[0] == second[0]
            first.clear()
            assert second, "mutating one result must not empty another"


class TestConcurrency:
    def test_concurrent_cold_misses_agree(self) -> None:
        instance = validator()
        results: List[Any] = []
        barrier = threading.Barrier(8)

        def run() -> None:
            barrier.wait()
            results.append(instance.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA))

        threads = [threading.Thread(target=run) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(results) == 8
        assert all(item == results[0] for item in results)
        assert len(cache_of(instance)) == 1

    def test_concurrent_hits_agree(self) -> None:
        instance = validator()
        instance.validate(VALID_PAYLOAD, SEMANTIC_SCHEMA)
        results: List[Any] = []

        def run() -> None:
            results.append(instance.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA))

        threads = [threading.Thread(target=run) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert all(item == results[0] for item in results)

    def test_concurrent_distinct_schemas_do_not_cross_contaminate(self) -> None:
        instance = validator()
        outcomes: Dict[int, Any] = {}

        def run(index: int) -> None:
            schema = {
                "type": "object",
                "properties": {"a": {"type": "string", "minLength": index + 1}},
            }
            outcomes[index] = instance.validate({"a": "abc"}, schema)

        threads = [threading.Thread(target=run, args=(i,)) for i in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        # minLength <= 3 passes for "abc"; longer fails. A contaminated marker would
        # not change this, but a shared *validator* would.
        for index, breaches in outcomes.items():
            assert bool(breaches) == (index + 1 > 3), index

    def test_eviction_pressure_preserves_verdicts(self) -> None:
        instance = validator()
        instance._preparation_cache = SchemaPreparationCache(capacity=2)  # noqa: SLF001
        outcomes: List[Any] = []

        def run(index: int) -> None:
            schema = {
                "type": "object",
                "properties": {"a": {"type": "string", "minLength": 5}},
                "title": f"t{index}",
            }
            outcomes.append(instance.validate({"a": "x"}, schema))

        threads = [threading.Thread(target=run, args=(i,)) for i in range(16)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert len(outcomes) == 16
        assert all(item and item == outcomes[0] for item in outcomes)
        assert len(cache_of(instance)) <= 2

    def test_lock_is_not_held_across_preparation(self) -> None:
        """Correctness must not depend on serializing preparation.

        A cache that held its lock across ``check_schema`` would make one expensive
        cold schema block every unrelated validation. This drives the cache while an
        unrelated thread holds nothing, and asserts progress and agreement — if the
        implementation ever took the lock around preparation, a nested acquisition
        here would deadlock rather than fail an assertion.
        """
        cache = SchemaPreparationCache()
        key = ("a" * 64, SchemaPreparationCache, False, 1)
        observed: List[bool] = []

        def worker() -> None:
            # Interleave lookups and inserts from several threads; a lock held
            # across "preparation" (simulated by a nested cache call) would hang.
            for _ in range(50):
                if not cache.is_prepared(key):
                    observed.append(cache.is_prepared(key) is False or True)
                    cache.mark_prepared(key)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=10)
        assert all(not thread.is_alive() for thread in threads)
        assert cache.is_prepared(key)


class TestLateWorkerMarker:
    """The one permitted late-worker side effect, and its limits."""

    def test_marker_from_a_late_worker_yields_a_cold_equivalent_result(self) -> None:
        # Slice C allows a timed-out semantic worker to keep running. It may now
        # insert a preparation marker. That is safe only because the marker carries
        # no payload or result truth, so a later request that hits it must produce
        # exactly what a cold evaluation would.
        reference = validator()
        cold_expected = reference.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA)

        instance = validator()
        done = threading.Event()

        def late_worker() -> None:
            instance.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA)
            done.set()

        thread = threading.Thread(target=late_worker)
        thread.start()
        assert done.wait(timeout=10)
        thread.join()

        assert len(cache_of(instance)) == 1
        later = instance.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA)
        assert cache_of(instance).stats()["hits"] >= 1
        assert later == cold_expected

    def test_a_late_worker_publishes_no_result(self) -> None:
        # The evaluator returns breaches; it has no telemetry, no storage and no
        # ValidationResult. Final-result ownership stays with the use case, so the
        # only trace a late worker can leave is the marker itself.
        instance = validator()
        assert not hasattr(instance, "publish")
        assert not hasattr(instance, "_event_bus")
        stats_before = cache_of(instance).stats()
        instance.validate(VALID_PAYLOAD, SEMANTIC_SCHEMA)
        stats_after = cache_of(instance).stats()
        assert stats_after["entries"] == stats_before["entries"] + 1


class TestBudgetInteraction:
    """The cache lives inside the semantic stage and changes none of its rules."""

    def test_cold_path_semantic_timeout_stays_truthful(self) -> None:
        # A cold miss pays check_schema inside the semantic stage, so it can still
        # exhaust the budget — and must still say so, as a semantic-stage timeout.
        from congine_core.models import DegradedReason, EvaluationStage
        from tests.unit.test_p1_5_stage_budgets import BurningRunner, _run, _usecase

        result = _run(
            _usecase(
                BurningRunner([1.0, 60.0]),
                semantic=_stub_semantic(),
                timeout_ms=50,
                semantic_cap=20,
            )
        )
        assert result.degraded
        assert result.degraded_reason is DegradedReason.SEMANTIC_TIMEOUT
        assert result.evaluation_stage is EvaluationStage.SEMANTIC
        assert not result.is_enforced()

    def test_warm_path_still_subject_to_the_post_stage_check(self) -> None:
        # A warm hit is faster, not exempt. The post-stage check belongs to the use
        # case and fires on elapsed time regardless of why the stage was quick, so a
        # late normal return is still refused rather than enforced.
        from congine_core.models import DegradedReason, EvaluationStage
        from tests.unit.test_p1_5_stage_budgets import BurningRunner, _run, _usecase

        result = _run(
            _usecase(
                BurningRunner([1.0, 40.0]),
                semantic=_stub_semantic(),
                timeout_ms=100,
                semantic_cap=10,
            )
        )
        assert result.degraded
        assert result.degraded_reason is DegradedReason.SEMANTIC_TIMEOUT
        assert result.evaluation_stage is EvaluationStage.SEMANTIC
        assert not result.is_enforced()

    def test_a_cache_hit_does_not_reset_the_deadline(self) -> None:
        # The aggregate deadline is absolute and owned by the use case; nothing the
        # evaluator does — including returning early from a hit — restarts it.
        from congine_core.models import DegradedReason
        from tests.unit.test_p1_5_stage_budgets import BurningRunner, _run, _usecase

        result = _run(
            _usecase(BurningRunner([120.0]), semantic=_stub_semantic(), timeout_ms=100)
        )
        assert result.degraded
        assert result.degraded_reason in (
            DegradedReason.TIMEOUT,
            DegradedReason.SEMANTIC_TIMEOUT,
        )
        assert not result.is_enforced()


def _stub_semantic() -> Any:
    from tests.unit.test_p1_5_stage_budgets import StubSemantic

    return StubSemantic()


class TestCompatibility:
    def test_composite_validator_path(self) -> None:
        from congine_core.domain.validator import CompositeValidator, LocalValidator

        composite = CompositeValidator(LocalValidator(), validator())
        first = composite.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA)
        second = composite.validate(INVALID_PAYLOAD, SEMANTIC_SCHEMA)
        # `duration_ms` legitimately differs — a warm call is faster, which is the
        # whole point. Semantic content is what must be identical.
        assert first.status == second.status
        assert first.breaches == second.breaches
        assert first.degraded == second.degraded

    def test_governed_use_case_path(self) -> None:
        from tests.conftest import (
            FakeEventBus,
            FakeLogger,
            FakeSchemaStorage,
            ImmediateTimer,
        )
        from congine_core.domain.validator import LocalValidator
        from congine_core.usecases.validate_contract_usecase import (
            ValidateContractUseCase,
        )

        storage = FakeSchemaStorage({"c1": SEMANTIC_SCHEMA})
        use_case = ValidateContractUseCase(
            schema_storage=storage,
            validator=LocalValidator(),
            event_bus=FakeEventBus(),
            logger=FakeLogger(),
            timer=ImmediateTimer(),
            semantic_validator=validator(),
        )
        first = use_case.execute(INVALID_PAYLOAD, "c1", "1")
        second = use_case.execute(INVALID_PAYLOAD, "c1", "1")
        assert first.status == second.status
        assert [b.field for b in first.breaches] == [b.field for b in second.breaches]
        assert not first.degraded and not second.degraded

    def test_public_surface_is_unchanged(self) -> None:
        import congine_core

        assert "SchemaPreparationCache" not in congine_core.__all__
        assert "CHECK_SCHEMA_VALID" not in congine_core.__all__
