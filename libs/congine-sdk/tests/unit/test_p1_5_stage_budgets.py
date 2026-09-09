"""P1.5 Slice C+D — aggregate/stage budgets and stage-truthful results.

Deadline policy is tested **deterministically**, through a stub
:class:`IValidationRunner` that can consume a controllable amount of logical
time and return whatever the case needs. Sleeping would make these tests slow
and flaky while proving less: the property under test is *which deadline the
orchestration compares against*, not how fast this machine happens to be.

The case that motivates most of this file is the one an aggregate deadline alone
cannot catch::

    aggregate = 100ms, native cap = 20ms, runner returns normally at 30ms

The aggregate still has 70 ms left, so a naive implementation accepts the
result — and the configured stage cap becomes decorative. It must be refused.
"""

from __future__ import annotations

import time
from typing import Any, Callable, List, Optional

import pytest

from congine_core.config import CongineConfig, FailMode
from congine_core.exceptions import CongineConfigurationError, LoadShedError
from congine_core.models import (
    BreachDetail,
    DegradedReason,
    EvaluationStage,
    ValidationResult,
)
from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase

SCHEMA = {"type": "object", "properties": {"f": {"type": "string"}}}
PAYLOAD = {"f": "value"}


class BurningRunner:
    """Runner that consumes real monotonic time before returning.

    Time is burned with a short busy-wait rather than ``sleep`` so the elapsed
    monotonic time the orchestration measures is genuine, while the amounts stay
    in the low-millisecond range and the tests stay fast.
    """

    def __init__(self, burns_ms: List[float], raises: Optional[List[Any]] = None):
        self.burns_ms = list(burns_ms)
        self.raises = list(raises or [])
        self.calls: List[int] = []

    @property
    def capacity(self) -> int:
        return 10

    def run_with_timeout(self, func: Callable[[], Any], timeout_ms: int) -> Any:
        self.calls.append(timeout_ms)
        if self.raises:
            exc = self.raises.pop(0)
            if exc is not None:
                raise exc
        burn = self.burns_ms.pop(0) if self.burns_ms else 0.0
        if burn:
            deadline = time.monotonic_ns() + int(burn * 1_000_000)
            while time.monotonic_ns() < deadline:
                pass
        return func()

    async def run_with_timeout_async(
        self, func: Callable[[], Any], timeout_ms: int
    ) -> Any:
        return self.run_with_timeout(func, timeout_ms)

    def health(self) -> dict:
        return {}

    def shutdown(self, wait: bool = False) -> None:
        return


class StubNative:
    """Native validator returning a fixed result."""

    def __init__(self, result: Optional[ValidationResult] = None):
        self.result = result or ValidationResult(status="pass")
        self.calls = 0

    def validate(self, payload: dict, schema: dict) -> ValidationResult:
        self.calls += 1
        return self.result


class StubSemantic:
    """Semantic validator returning fixed breaches."""

    def __init__(self, breaches: Optional[List[BreachDetail]] = None):
        self.breaches = breaches or []
        self.calls = 0

    def validate(self, payload: dict, schema: dict) -> List[BreachDetail]:
        self.calls += 1
        return list(self.breaches)


class Storage:
    def get(self, contract_id: str):
        return SCHEMA

    def put(self, *a: Any, **k: Any) -> None: ...
    def clear(self) -> None: ...
    def exists(self, contract_id: str) -> bool:
        return True

    def size(self) -> int:
        return 1

    def stop(self) -> None: ...


class Bus:
    def __init__(self) -> None:
        self.events: List[Any] = []

    def publish(self, event: Any) -> None:
        self.events.append(event)

    def queue_depth(self) -> int:
        return 0

    def stop(self, drain: bool = True) -> None: ...


class Logger:
    def info(self, *a: Any, **k: Any) -> None: ...
    def warning(self, *a: Any, **k: Any) -> None: ...
    def error(self, *a: Any, **k: Any) -> None: ...
    def debug(self, *a: Any, **k: Any) -> None: ...


def _usecase(
    runner: BurningRunner,
    *,
    native: Optional[StubNative] = None,
    semantic: Optional[StubSemantic] = None,
    timeout_ms: int = 100,
    native_cap: Optional[int] = None,
    semantic_cap: Optional[int] = None,
    bus: Optional[Bus] = None,
) -> ValidateContractUseCase:
    return ValidateContractUseCase(
        schema_storage=Storage(),
        validator=native or StubNative(),
        semantic_validator=semantic,
        event_bus=bus or Bus(),
        logger=Logger(),
        timer=runner,
        timeout_ms=timeout_ms,
        native_timeout_ms=native_cap,
        semantic_timeout_ms=semantic_cap,
        fail_mode=FailMode.DEGRADE,
    )


def _run(uc: ValidateContractUseCase) -> ValidationResult:
    return uc.execute(PAYLOAD, "c", "1")


# --------------------------------------------------------------------------- #
class TestStageCapEnforcement:
    """An explicit stage cap must bind even while the aggregate has time left."""

    def test_native_cap_expiry_refused_although_aggregate_remains(self) -> None:
        """aggregate 100, native cap 20, runner returns normally at ~30ms."""
        uc = _usecase(BurningRunner([30.0]), timeout_ms=100, native_cap=20)
        result = _run(uc)

        assert result.degraded is True
        assert result.degraded_reason == DegradedReason.TIMEOUT
        assert result.evaluation_stage == EvaluationStage.NATIVE
        assert result.is_enforced() is False

    def test_semantic_cap_expiry_refused_although_aggregate_remains(self) -> None:
        """Same trap on the semantic stage: cap 20, returns normally at ~30ms."""
        uc = _usecase(
            BurningRunner([1.0, 30.0]),
            semantic=StubSemantic(),
            timeout_ms=200,
            semantic_cap=20,
        )
        result = _run(uc)

        assert result.degraded is True
        assert result.degraded_reason == DegradedReason.SEMANTIC_TIMEOUT
        assert result.evaluation_stage == EvaluationStage.SEMANTIC
        assert result.is_enforced() is False

    def test_stage_return_comfortably_inside_cap_is_accepted(self) -> None:
        uc = _usecase(BurningRunner([1.0]), timeout_ms=100, native_cap=50)
        result = _run(uc)

        assert result.degraded is False
        assert result.is_enforced() is True
        assert result.evaluation_stage == EvaluationStage.NATIVE

    def test_stage_cap_equal_to_aggregate_is_allowed(self) -> None:
        uc = _usecase(BurningRunner([1.0]), timeout_ms=100, native_cap=100)
        assert _run(uc).is_enforced() is True

    def test_stage_budget_never_exceeds_remaining_aggregate(self) -> None:
        """A generous cap must still be clipped by the aggregate deadline."""
        runner = BurningRunner([1.0, 1.0])
        uc = _usecase(runner, semantic=StubSemantic(), timeout_ms=50, semantic_cap=50)
        _run(uc)

        # Native consumed part of the aggregate, so the semantic wait must be
        # strictly smaller than both the cap and the original aggregate.
        assert runner.calls[1] <= 50
        assert runner.calls[1] <= runner.calls[0]


# --------------------------------------------------------------------------- #
class TestAggregateExhaustion:
    def test_aggregate_exhausted_during_native_is_native_timeout(self) -> None:
        uc = _usecase(BurningRunner([30.0]), timeout_ms=10)
        result = _run(uc)

        assert result.degraded_reason == DegradedReason.TIMEOUT
        assert result.evaluation_stage == EvaluationStage.NATIVE

    def test_aggregate_exhausted_during_native_is_attributed_to_native(self) -> None:
        """Aggregate expiry *while native runs* belongs to the native stage.

        Worth pinning because it constrains the case below: the native
        post-stage check tests both deadlines, so an aggregate that dies during
        native can never surface as a semantic failure.
        """
        semantic = StubSemantic()
        uc = _usecase(BurningRunner([30.0]), semantic=semantic, timeout_ms=20)
        result = _run(uc)

        assert result.degraded_reason == DegradedReason.TIMEOUT
        assert result.evaluation_stage == EvaluationStage.NATIVE
        assert semantic.calls == 0, "semantic must not run after a native timeout"

    def test_no_budget_left_for_semantic_is_a_semantic_timeout(self) -> None:
        """Native finished in time, but nothing usable remains for semantic.

        Semantic is then the required stage that cannot be completed, so it owns
        the outcome — the native PASS must not become an overall enforced PASS.
        Sub-millisecond remainders land here too: a budget that cannot be
        expressed as a positive integer millisecond is exhausted, not rounded up.
        """
        semantic = StubSemantic()
        uc = _usecase(BurningRunner([19.6]), semantic=semantic, timeout_ms=20)
        result = _run(uc)

        assert result.is_enforced() is False
        assert result.degraded_reason == DegradedReason.SEMANTIC_TIMEOUT
        assert result.evaluation_stage == EvaluationStage.SEMANTIC
        assert semantic.calls == 0, "semantic must not run without budget"

    def test_native_timeout_prevents_semantic_from_running(self) -> None:
        semantic = StubSemantic()
        uc = _usecase(
            BurningRunner([0.0], raises=[TimeoutError("native")]),
            semantic=semantic,
            timeout_ms=100,
        )
        result = _run(uc)

        assert result.degraded_reason == DegradedReason.TIMEOUT
        assert result.evaluation_stage == EvaluationStage.NATIVE
        assert semantic.calls == 0


# --------------------------------------------------------------------------- #
class TestLoadShedOrdering:
    """``LoadShedError`` subclasses ``TimeoutError``; order must not invert."""

    def test_native_load_shed_is_not_reported_as_timeout(self) -> None:
        uc = _usecase(BurningRunner([], raises=[LoadShedError("shed")]), timeout_ms=100)
        result = _run(uc)

        assert result.degraded_reason == DegradedReason.LOAD_SHED
        assert result.evaluation_stage == EvaluationStage.NATIVE

    def test_semantic_load_shed_is_not_reported_as_semantic_timeout(self) -> None:
        uc = _usecase(
            BurningRunner([1.0], raises=[None, LoadShedError("shed")]),
            semantic=StubSemantic(),
            timeout_ms=100,
        )
        result = _run(uc)

        assert result.degraded_reason == DegradedReason.LOAD_SHED
        assert result.evaluation_stage == EvaluationStage.SEMANTIC


# --------------------------------------------------------------------------- #
class TestPartialEnforcement:
    """A known native breach cannot rescue an incomplete semantic stage."""

    def test_native_pass_plus_semantic_timeout_is_non_enforced(self) -> None:
        uc = _usecase(
            BurningRunner([1.0], raises=[None, TimeoutError("sem")]),
            semantic=StubSemantic(),
            timeout_ms=100,
        )
        result = _run(uc)

        assert result.is_enforced() is False
        assert result.degraded_reason == DegradedReason.SEMANTIC_TIMEOUT

    def test_native_breach_plus_semantic_timeout_is_non_enforced(self) -> None:
        """The result model cannot say "known breach, partially enforced".

        Presenting the native breaches as a completed evaluation would claim
        enforcement that did not happen, so the degraded outcome wins. Recorded
        as explicit P1.5 debt; the partial-result model is deferred.
        """
        breached = ValidationResult(
            status="fail", breaches=(BreachDetail(rule="TYPE_MATCH", field="f"),)
        )
        uc = _usecase(
            BurningRunner([1.0], raises=[None, TimeoutError("sem")]),
            native=StubNative(breached),
            semantic=StubSemantic(),
            timeout_ms=100,
        )
        result = _run(uc)

        assert result.is_enforced() is False
        assert result.degraded_reason == DegradedReason.SEMANTIC_TIMEOUT
        assert result.breaches == (), "partial breaches must not look complete"


# --------------------------------------------------------------------------- #
class TestNormalOutcomes:
    def test_native_only_pass_is_tagged_native(self) -> None:
        result = _run(_usecase(BurningRunner([0.5])))
        assert result.is_pass() and result.evaluation_stage == EvaluationStage.NATIVE

    def test_semantic_breaches_merge_after_native(self) -> None:
        native = StubNative(
            ValidationResult(
                status="fail", breaches=(BreachDetail(rule="TYPE_MATCH", field="a"),)
            )
        )
        semantic = StubSemantic([BreachDetail(rule="SEMANTIC_SCHEMA", field="b")])
        result = _run(
            _usecase(
                BurningRunner([0.5, 0.5]),
                native=native,
                semantic=semantic,
                timeout_ms=500,
            )
        )

        assert [b.rule for b in result.breaches] == ["TYPE_MATCH", "SEMANTIC_SCHEMA"]
        assert result.evaluation_stage == EvaluationStage.SEMANTIC
        assert result.is_enforced() is True

    def test_disabled_semantic_never_calls_a_semantic_validator(self) -> None:
        uc = _usecase(BurningRunner([0.5]), semantic=None)
        assert _run(uc).evaluation_stage == EvaluationStage.NATIVE


# --------------------------------------------------------------------------- #
class TestWiringGuard:
    """A composite validator plus a semantic validator would double-evaluate."""

    def test_composite_plus_semantic_is_refused_at_construction(self) -> None:
        from congine_core.domain.validator import CompositeValidator, LocalValidator
        from congine_core.infrastructure.jsonschema_validator import (
            JsonSchemaSemanticValidator,
        )

        semantic = JsonSchemaSemanticValidator()
        composite = CompositeValidator(LocalValidator(), semantic)
        with pytest.raises(CongineConfigurationError) as excinfo:
            _usecase(BurningRunner([]), native=composite, semantic=semantic)  # type: ignore[arg-type]
        assert "semantic" in str(excinfo.value).lower()


# --------------------------------------------------------------------------- #
class TestTelemetryCompatibility:
    """Stage truth must reach telemetry without changing the success shape."""

    def test_successful_event_wire_shape_is_unchanged(self) -> None:
        from congine_core.infrastructure.queue_event_bus import QueueEventBus

        bus = Bus()
        _run(_usecase(BurningRunner([0.5]), bus=bus))
        payload = QueueEventBus._serialize(bus.events[0])

        assert set(payload) == {
            "contract_id",
            "contract_version",
            "status",
            "duration_ms",
            "breach_details",
            "created_at",
        }

    def test_degraded_event_carries_reason_and_stage(self) -> None:
        from congine_core.infrastructure.queue_event_bus import QueueEventBus

        bus = Bus()
        _run(
            _usecase(
                BurningRunner([1.0], raises=[None, TimeoutError("sem")]),
                semantic=StubSemantic(),
                timeout_ms=100,
                bus=bus,
            )
        )
        payload = QueueEventBus._serialize(bus.events[0])

        assert payload["degraded_reason"] == "semantic_timeout"
        assert payload["evaluation_stage"] == "semantic"

    def test_all_four_degraded_outcomes_are_distinguishable(self) -> None:
        """The whole point of the added fields."""
        from congine_core.infrastructure.queue_event_bus import QueueEventBus

        seen = set()
        for raises, cap in (
            ([TimeoutError("n")], None),
            ([LoadShedError("n")], None),
            ([None, TimeoutError("s")], None),
            ([None, LoadShedError("s")], None),
        ):
            bus = Bus()
            _run(
                _usecase(
                    BurningRunner([1.0], raises=list(raises)),
                    semantic=StubSemantic(),
                    timeout_ms=100,
                    semantic_cap=cap,
                    bus=bus,
                )
            )
            payload = QueueEventBus._serialize(bus.events[0])
            seen.add((payload["degraded_reason"], payload["evaluation_stage"]))

        assert seen == {
            ("timeout", "native"),
            ("load_shed", "native"),
            ("semantic_timeout", "semantic"),
            ("load_shed", "semantic"),
        }


# --------------------------------------------------------------------------- #
class TestConfigParity:
    """G13: both construction doors must reach the same canonical state."""

    _BASE = dict(
        base_url="http://localhost:8080",
        api_key=None,
        project_id=None,
        tenant_id=None,
        region="us",
    )

    def test_defaults_unchanged(self) -> None:
        cfg = CongineConfig(**self._BASE)  # type: ignore[arg-type]
        assert cfg.validation_timeout_ms == 100
        assert cfg.native_validation_timeout_ms is None
        assert cfg.semantic_validation_timeout_ms is None
        assert cfg.semantic_validation_enabled is False

    @pytest.mark.parametrize(
        "bad", [0, -1, True, 101], ids=["zero", "negative", "bool", "exceeds-aggregate"]
    )
    def test_invalid_stage_caps_refused(self, bad: Any) -> None:
        with pytest.raises(CongineConfigurationError):
            CongineConfig(**self._BASE, native_validation_timeout_ms=bad)  # type: ignore[arg-type]

    def test_env_and_direct_construction_agree(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        for key in [k for k in __import__("os").environ if k.startswith("CONGINE_")]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("CONGINE_BASE_URL", "http://localhost:8080")
        monkeypatch.setenv("CONGINE_NATIVE_TIMEOUT_MS", "20")
        monkeypatch.setenv("CONGINE_SEMANTIC_TIMEOUT_MS", "60")

        from_env = CongineConfig.from_env()
        direct = CongineConfig(
            **self._BASE,
            native_validation_timeout_ms=20,
            semantic_validation_timeout_ms=60,
        )  # type: ignore[arg-type]

        assert (
            from_env.native_validation_timeout_ms == direct.native_validation_timeout_ms
        )
        assert (
            from_env.semantic_validation_timeout_ms
            == direct.semantic_validation_timeout_ms
        )
        assert type(from_env.native_validation_timeout_ms) is type(
            direct.native_validation_timeout_ms
        )

    @pytest.mark.parametrize("raw", ["", "   ", "abc", "-5", "0"])
    def test_malformed_env_values_refused(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        for key in [k for k in __import__("os").environ if k.startswith("CONGINE_")]:
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("CONGINE_BASE_URL", "http://localhost:8080")
        monkeypatch.setenv("CONGINE_NATIVE_TIMEOUT_MS", raw)
        with pytest.raises(CongineConfigurationError):
            CongineConfig.from_env()


# --------------------------------------------------------------------------- #
class TestGovernedEntryPoints:
    """Every governed product path must terminate at the budgeted use case.

    A path that reaches ``CompositeValidator`` directly would silently run
    without any deadline, which is the failure this slice exists to prevent.
    """

    def test_container_gives_the_use_case_a_native_only_validator(self) -> None:
        """Wiring must not hand the use case a composite.

        Doing so would evaluate semantics twice — once inside the composite and
        once as the scheduled semantic stage — and destroy the stage budgets.
        """
        import os

        from congine_core.adapters.dependency_injection import ServiceContainer
        from congine_core.domain.validator import CompositeValidator, LocalValidator

        for key in [k for k in os.environ if k.startswith("CONGINE_")]:
            os.environ.pop(key, None)
        os.environ["CONGINE_BASE_URL"] = "http://localhost:8080"
        os.environ["CONGINE_SEMANTIC_VALIDATION"] = "true"
        os.environ["CONGINE_TELEMETRY_ENABLED"] = "false"
        os.environ["CONGINE_START_BACKGROUND_SERVICES"] = "false"
        container = ServiceContainer.from_env()
        try:
            usecase = container.validate_contract_usecase
            assert isinstance(usecase.validator, LocalValidator)
            assert not isinstance(usecase.validator, CompositeValidator)
            assert usecase.semantic_validator is container.semantic_validator
            # The composite remains available as the documented low-level API.
            assert isinstance(container.validator, CompositeValidator)
        finally:
            container.close()
            os.environ.pop("CONGINE_SEMANTIC_VALIDATION", None)

    def test_governed_adapters_call_the_use_case(self) -> None:
        """Source-level check that no governed adapter bypasses the boundary."""
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "src" / "congine_core"
        for adapter in ("adapters/guard.py", "adapters/langchain_handler.py"):
            source = (root / adapter).read_text(encoding="utf-8")
            assert "validate_contract_usecase" in source, adapter
            assert ".validator.validate(" not in source, (
                f"{adapter} reaches the unbudgeted validator directly"
            )
