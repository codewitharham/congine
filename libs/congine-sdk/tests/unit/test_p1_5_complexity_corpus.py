"""Determinism and admission-validity guards for the Slice-E complexity corpus.

Slice E's conclusions rest on three claims that are cheap to assert and expensive
to discover broken later:

1. **The corpus is reproducible.** A recorded observation cites a corpus hash; if
   generation drifts, the hash must change loudly rather than the comparison
   quietly becoming invalid.
2. **Every predictor fixture is genuinely admissible.** Slice E measures the cost
   of *supported, admitted* contracts. A fixture CONGINE would refuse is not a
   cheap-or-expensive contract, it is a non-contract, and measuring it would bias
   the corpus toward whatever admission happens to allow today.
3. **Statistics degrade truthfully.** An undefined correlation reported as ``0.0``
   reads as "measured, and unrelated" — a different and false claim.

Nothing here asserts a timing. These tests are deterministic by construction and
cannot flake on a loaded machine.
"""

from __future__ import annotations

import math

import pytest

from congine_core.security_limits import DEFAULT_MAX_SCHEMA_BYTES
from tools.p1_5_evidence import analysis, complexity, complexity_corpus, features


@pytest.fixture(scope="module")
def supported_formats() -> "frozenset[str]":
    return complexity_corpus.supported_formats()


@pytest.fixture(scope="module")
def cases(supported_formats: "frozenset[str]") -> tuple:
    return tuple(complexity_corpus.build(supported_formats))


@pytest.fixture(scope="module")
def report(cases: tuple) -> complexity_corpus.CorpusReport:
    return complexity_corpus.validate_corpus(list(cases))


class TestCorpusDeterminism:
    def test_two_builds_produce_the_same_hash(
        self, supported_formats: "frozenset[str]"
    ) -> None:
        first = complexity_corpus.build(supported_formats)
        second = complexity_corpus.build(supported_formats)
        assert complexity_corpus.corpus_hash(first) == complexity_corpus.corpus_hash(
            second
        )

    def test_case_order_is_stable(self, supported_formats: "frozenset[str]") -> None:
        first = [c.name for c in complexity_corpus.build(supported_formats)]
        second = [c.name for c in complexity_corpus.build(supported_formats)]
        assert first == second

    def test_case_names_are_unique(self, cases: tuple) -> None:
        names = [c.name for c in cases]
        assert len(names) == len(set(names))

    def test_hash_covers_payloads_not_just_schemas(self, cases: tuple) -> None:
        # A payload change must invalidate the corpus identity: Slice E draws
        # conclusions about payload sensitivity, so payloads are part of what a
        # recorded observation measured.
        mutated = list(cases)
        original = mutated[0]
        mutated[0] = complexity_corpus.CorpusCase(
            family=original.family,
            name=original.name,
            parameters=original.parameters,
            schema=original.schema,
            payloads={**original.payloads, "extra": {"f0": "zzz"}},
            kind=original.kind,
            draft=original.draft,
            format_checking=original.format_checking,
        )
        assert complexity_corpus.corpus_hash(mutated) != complexity_corpus.corpus_hash(
            list(cases)
        )

    def test_digest_ignores_key_order(self) -> None:
        a = complexity_corpus.CorpusCase(
            family="t",
            name="a",
            parameters={},
            schema={"type": "object", "title": "x"},
            payloads={},
        )
        b = complexity_corpus.CorpusCase(
            family="t",
            name="b",
            parameters={},
            schema={"title": "x", "type": "object"},
            payloads={},
        )
        assert a.digest == b.digest


class TestAdmissionValidity:
    """The E.8 gate: predictors admitted, controls refused, nothing oversize."""

    def test_corpus_validation_passes(
        self, report: complexity_corpus.CorpusReport
    ) -> None:
        assert report.failures == ()
        assert report.oversize == ()
        assert report.ok

    def test_every_predictor_is_admitted(
        self, cases: tuple, report: complexity_corpus.CorpusReport
    ) -> None:
        predictors = complexity_corpus.predictors(list(cases))
        assert len(report.admitted) == len(predictors)
        for case in predictors:
            assert report.witnesses[case.name]["admitted"] is True, case.name

    def test_every_refusal_control_is_refused(
        self, cases: tuple, report: complexity_corpus.CorpusReport
    ) -> None:
        controls = complexity_corpus.controls(list(cases))
        assert controls, "the corpus must keep refusal controls"
        assert len(report.refused_controls) == len(controls)
        for case in controls:
            assert report.witnesses[case.name]["admitted"] is False, case.name

    def test_predictors_stay_under_the_schema_preflight(self, cases: tuple) -> None:
        for case in complexity_corpus.predictors(list(cases)):
            assert case.canonical_bytes < DEFAULT_MAX_SCHEMA_BYTES, case.name

    def test_oversize_predictor_fails_validation(self) -> None:
        # The preflight guard must be mechanical, not a claim in a docstring.
        case = complexity_corpus.CorpusCase(
            family="t",
            name="huge",
            parameters={},
            schema={"type": "object", "title": "x" * 5_000},
            payloads={"valid": {}},
        )
        result = complexity_corpus.validate_corpus([case], max_schema_bytes=1_000)
        assert result.oversize
        assert not result.ok

    def test_refused_predictor_fails_validation(self) -> None:
        # A predictor CONGINE refuses must stop the experiment, never be dropped.
        case = complexity_corpus.CorpusCase(
            family="t",
            name="external-ref-as-predictor",
            parameters={},
            schema={
                "type": "object",
                "properties": {"f0": {"$ref": "http://example.invalid/s.json"}},
            },
            payloads={"valid": {}},
        )
        result = complexity_corpus.validate_corpus([case])
        assert any("REFUSED" in failure for failure in result.failures)
        assert not result.ok

    def test_dialect_family_covers_every_supported_draft(self, cases: tuple) -> None:
        drafts = {c.draft for c in cases if c.family == "dialect"}
        assert drafts == set(complexity_corpus.ALL_DRAFTS)

    def test_format_family_only_uses_assertable_names(
        self, cases: tuple, supported_formats: "frozenset[str]"
    ) -> None:
        for case in cases:
            if case.family != "format":
                continue
            assert case.format_checking is True
            assert case.parameters["format"] in supported_formats


class TestMeasurementContextIdentity:
    """Preparation identity spans the evaluator context, not schema bytes alone."""

    def test_same_bytes_different_draft_are_different_contexts(self) -> None:
        schema = {"type": "object", "properties": {"f0": {"type": "string"}}}
        common = dict(family="t", parameters={}, schema=schema, payloads={})
        older = complexity_corpus.CorpusCase(name="a", draft="draft7", **common)
        newer = complexity_corpus.CorpusCase(name="b", draft="draft202012", **common)
        assert older.digest == newer.digest
        assert older.context_key("cap-a") != newer.context_key("cap-a")

    def test_same_bytes_different_capability_are_different_contexts(self) -> None:
        schema = {"type": "object", "properties": {"f0": {"type": "string"}}}
        case = complexity_corpus.CorpusCase(
            family="t", name="a", parameters={}, schema=schema, payloads={}
        )
        assert case.context_key("cap-a") != case.context_key("cap-b")

    def test_identical_contexts_collapse_to_one_observation(self, cases: tuple) -> None:
        contexts = complexity.contexts(list(cases))
        ids = [c.context_id for c in contexts]
        assert len(ids) == len(set(ids))
        # Aliases are recorded rather than dropped, so the collapse is visible.
        aliased = sum(len(c.aliases) for c in contexts)
        assert len(contexts) + aliased == len(complexity_corpus.predictors(list(cases)))

    def test_capability_identity_reflects_format_policy(self) -> None:
        off = complexity_corpus.evaluator("draft202012", False).capability
        on = complexity_corpus.evaluator("draft202012", True).capability
        assert complexity_corpus.capability_identity(
            off
        ) != complexity_corpus.capability_identity(on)


class TestRotation:
    def test_rotation_is_a_deterministic_permutation(self) -> None:
        items = list(range(10))
        for index in range(complexity.OFFICIAL_RUNS):
            rotated = complexity.rotate(items, index, complexity.OFFICIAL_RUNS)
            assert sorted(rotated) == items
            assert rotated == complexity.rotate(items, index, complexity.OFFICIAL_RUNS)

    def test_workers_do_not_all_share_one_order(self) -> None:
        items = list(range(10))
        orders = {
            tuple(complexity.rotate(items, index, complexity.OFFICIAL_RUNS))
            for index in range(complexity.OFFICIAL_RUNS)
        }
        assert len(orders) > 1

    def test_empty_input_is_handled(self) -> None:
        assert complexity.rotate([], 3, 5) == []


class TestQuantileFloors:
    """Frozen nearest-rank policy: p50/max always, p95 n>=20, p99 n>=100."""

    def test_small_sample_reports_neither_p95_nor_p99(self) -> None:
        timing = complexity.ComplexityTiming.of([float(i) for i in range(12)], warmup=3)
        assert timing.n == 12
        assert timing.p95 is None
        assert timing.p99 is None
        assert "p95 requires n>=20" in (timing.not_reported_reason or "")
        assert "p99 requires n>=100" in (timing.not_reported_reason or "")

    def test_medium_sample_reports_p95_but_not_p99(self) -> None:
        timing = complexity.ComplexityTiming.of([float(i) for i in range(20)], warmup=5)
        assert timing.p95 is not None
        assert timing.p99 is None
        assert "p95" not in (timing.not_reported_reason or "")

    def test_large_sample_reports_every_quantile(self) -> None:
        timing = complexity.ComplexityTiming.of(
            [float(i) for i in range(120)], warmup=5
        )
        assert timing.p95 is not None
        assert timing.p99 is not None
        assert timing.not_reported_reason is None

    def test_reported_values_were_actually_measured(self) -> None:
        # Nearest-rank, never interpolation: a quoted quantile is an observation.
        samples = [float(i) for i in range(100)]
        timing = complexity.ComplexityTiming.of(samples, warmup=5)
        for value in (timing.p50, timing.p95, timing.p99, timing.max):
            assert value in samples

    def test_single_sample_still_yields_p50_and_max(self) -> None:
        timing = complexity.ComplexityTiming.of([4.0], warmup=0)
        assert timing.p50 == 4.0
        assert timing.max == 4.0
        assert timing.p95 is None

    def test_empty_sample_is_refused(self) -> None:
        with pytest.raises(ValueError):
            complexity.ComplexityTiming.of([], warmup=0)

    def test_tier_schedule_is_total_and_ordered(self) -> None:
        for size in (0, 1_999, 2_000, 19_999, 20_000, 10_000_000):
            tier, iterations, warmup = complexity.tier_for(size)
            assert tier in {"small", "medium", "large"}
            assert iterations >= 3 and warmup >= 1


class TestDegenerateStatistics:
    """An uncomputable statistic is absent with a reason, never a misleading 0.0."""

    def test_constant_feature_has_no_correlation(self) -> None:
        stat = analysis.spearman([2.0, 2.0, 2.0, 2.0], [1.0, 5.0, 3.0, 9.0])
        assert stat.value is None
        assert stat.reason == analysis.CONSTANT_FEATURE

    def test_constant_cost_has_no_correlation(self) -> None:
        stat = analysis.spearman([1.0, 5.0, 3.0, 9.0], [2.0, 2.0, 2.0, 2.0])
        assert stat.value is None
        assert stat.reason == analysis.CONSTANT_COST

    def test_too_few_observations_is_reported(self) -> None:
        stat = analysis.spearman([1.0, 2.0], [3.0, 4.0])
        assert stat.value is None
        assert stat.reason == analysis.INSUFFICIENT

    def test_no_nan_ever_escapes(self) -> None:
        for xs, ys in (
            ([1.0, 1.0, 1.0], [1.0, 1.0, 1.0]),
            ([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]),
            ([1.0, 2.0, 3.0], [0.0, 0.0, 0.0]),
        ):
            for stat in (analysis.spearman(xs, ys), analysis.pearson(xs, ys)):
                assert stat.value is None or not math.isnan(stat.value)

    def test_perfect_monotonic_relation_scores_one(self) -> None:
        stat = analysis.spearman([1.0, 2.0, 3.0, 4.0], [10.0, 20.0, 30.0, 40.0])
        assert stat.value == 1.0

    def test_rank_correlation_tolerates_ties(self) -> None:
        # Real families hold a feature constant on purpose, so ties are normal
        # and must not be resolved into an ordering the data does not contain.
        stat = analysis.spearman([1.0, 1.0, 2.0, 3.0], [5.0, 5.0, 7.0, 9.0])
        assert stat.value is not None and stat.value > 0.9

    def test_monotonicity_needs_two_points(self) -> None:
        result = analysis.monotonicity([1.0], [2.0])
        assert result.fraction is None
        assert result.reason == analysis.INSUFFICIENT

    def test_monotonicity_counts_broken_steps(self) -> None:
        result = analysis.monotonicity([1.0, 2.0, 3.0], [1.0, 5.0, 4.0])
        assert result.pairs == 2
        assert result.non_decreasing == 1
        assert result.strict is False

    def test_rank_stability_reports_absence(self) -> None:
        result = analysis.rank_stability([[1.0, 1.0, 1.0], [2.0, 2.0, 2.0]])
        assert result["min"] is None
        assert result["reason"] == analysis.INSUFFICIENT


class TestConfusionAnalysis:
    def test_threshold_sweep_covers_adjacent_midpoints(self) -> None:
        assert analysis.candidate_thresholds([1.0, 1.0, 3.0, 5.0]) == (2.0, 4.0)

    def test_single_distinct_value_admits_no_threshold(self) -> None:
        assert analysis.candidate_thresholds([4.0, 4.0]) == ()
        assert (
            analysis.best_threshold("f", 10.0, [("a", 4.0, 1.0), ("b", 4.0, 90.0)])
            is None
        )

    def test_confusion_labels_both_error_directions(self) -> None:
        rows = [
            ("cheap-but-big", 100.0, 1.0),
            ("expensive-but-small", 1.0, 500.0),
            ("expensive-and-big", 100.0, 500.0),
            ("cheap-and-small", 1.0, 1.0),
        ]
        result = analysis.confusion("nodes", 50.0, 100.0, rows)
        assert result.false_positive == 1
        assert result.false_negative == 1
        assert "cheap-but-big" in result.false_positive_examples[0]
        assert "expensive-but-small" in result.false_negative_examples[0]


class TestFeatureExtractor:
    def test_features_ignore_key_order(self) -> None:
        a = {"type": "object", "properties": {"f0": {"minLength": 1, "type": "string"}}}
        b = {"properties": {"f0": {"type": "string", "minLength": 1}}, "type": "object"}
        assert features.extract(a) == features.extract(b)

    def test_every_declared_feature_is_produced(self) -> None:
        extracted = features.extract({"type": "object"})
        assert set(extracted) == set(features.FEATURE_DEFINITIONS)

    def test_depth_and_properties(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "object", "properties": {"b": {"type": "string"}}}
            },
        }
        extracted = features.extract(schema)
        assert extracted["properties"] == 2
        assert extracted["max_depth"] == 4

    def test_combinator_breadth_and_product(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "a": {"anyOf": [{"const": 1}, {"const": 2}, {"const": 3}]},
                "b": {"oneOf": [{"const": 1}, {"const": 2}]},
            },
        }
        extracted = features.extract(schema)
        assert extracted["combinators"] == 2
        assert extracted["max_combinator_breadth"] == 3
        assert extracted["combinator_product"] == 6

    def test_combinator_product_is_capped(self) -> None:
        node = {"anyOf": [{"const": i} for i in range(30)]}
        schema = {"allOf": [node for _ in range(10)]}
        assert features.extract(schema)["combinator_product"] == 10**9

    def test_nested_combinator_depth(self) -> None:
        schema = {"allOf": [{"anyOf": [{"oneOf": [{"const": 1}, {"const": 2}]}]}]}
        assert features.extract(schema)["max_combinator_depth"] == 3

    def test_enum_cardinality_is_max_not_sum(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "a": {"enum": [1, 2, 3]},
                "b": {"enum": [1, 2, 3, 4, 5]},
            },
        }
        extracted = features.extract(schema)
        assert extracted["enum_values"] == 8
        assert extracted["enum_max_cardinality"] == 5

    def test_reference_reuse_is_distinguished_from_reference_count(self) -> None:
        schema = {
            "$defs": {"S": {"type": "string"}, "T": {"type": "integer"}},
            "properties": {
                "a": {"$ref": "#/$defs/S"},
                "b": {"$ref": "#/$defs/S"},
                "c": {"$ref": "#/$defs/T"},
            },
        }
        extracted = features.extract(schema)
        assert extracted["refs"] == 3
        assert extracted["distinct_ref_targets"] == 2
        assert extracted["repeated_refs"] == 1
        assert extracted["defs_count"] == 2

    def test_reference_chain_depth(self) -> None:
        schema = {
            "$defs": {
                "L0": {"type": "string"},
                "L1": {"$ref": "#/$defs/L0"},
                "L2": {"$ref": "#/$defs/L1"},
            },
            "properties": {"a": {"$ref": "#/$defs/L2"}},
        }
        assert features.extract(schema)["ref_graph_depth"] == 3

    def test_dangling_reference_does_not_crash_the_extractor(self) -> None:
        schema = {"properties": {"a": {"$ref": "#/$defs/Missing"}}}
        assert features.extract(schema)["refs"] == 1

    def test_cyclic_reference_terminates(self) -> None:
        # Admission refuses cycles, but the extractor also runs over refusal
        # controls, so it must not depend on that guarantee.
        schema = {
            "$defs": {"A": {"$ref": "#/$defs/B"}, "B": {"$ref": "#/$defs/A"}},
            "properties": {"a": {"$ref": "#/$defs/A"}},
        }
        assert features.extract(schema)["ref_graph_depth"] >= 1

    def test_regex_and_array_features(self) -> None:
        schema = {
            "type": "object",
            "properties": {
                "a": {"type": "string", "pattern": "^abc$"},
                "b": {
                    "type": "array",
                    "prefixItems": [{"type": "string"}, {"type": "integer"}],
                    "contains": {"const": 1},
                    "minItems": 1,
                },
            },
        }
        extracted = features.extract(schema)
        assert extracted["regexes"] == 1
        assert extracted["max_regex_chars"] == len("^abc$")
        assert extracted["prefix_items"] == 2
        assert extracted["contains_count"] == 1
        assert extracted["array_constraints"] >= 3


class TestPilotIsNotEvidence:
    def test_assemble_refuses_pilot_runs(self) -> None:
        pilot = {
            "evidence": False,
            "corpus_hash": "x",
            "methodology_version": complexity.METHODOLOGY_VERSION,
        }
        with pytest.raises(RuntimeError, match="pilot"):
            complexity.assemble([pilot])

    def test_assemble_refuses_mismatched_corpora(self) -> None:
        def run(corpus_hash: str) -> dict:
            return {
                "evidence": True,
                "corpus_hash": corpus_hash,
                "methodology_version": complexity.METHODOLOGY_VERSION,
            }

        with pytest.raises(RuntimeError, match="disagree"):
            complexity.assemble([run("a"), run("b")])
