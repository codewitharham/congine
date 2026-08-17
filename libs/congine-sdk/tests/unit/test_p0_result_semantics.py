"""Result semantics, typed degradation and strict configuration (audit P0-02/05/06/07).

The property under test throughout:

    "the policy was violated" and "the policy was never evaluated" must be
    distinguishable without parsing prose.

Every degraded path below carries **zero breaches**: an inability to evaluate
must never fabricate a verdict.
"""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from congine_core.config import (
    DEFAULT_VALIDATION_TIMEOUT_MS,
    CongineConfig,
    ContractAdmissionMode,
    ContractSource,
    FailMode,
    Region,
)
from congine_core.domain.models import DegradedReason, ValidationResult
from congine_core.exceptions import (
    CongineConfigurationError,
    CongineContractNotFoundError,
    CongineValidationError,
    LoadShedError,
)
from congine_core.infrastructure.bounded_executor import BoundedValidationExecutor
from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase
from tests.conftest import FakeEventBus, FakeLogger, FakeSchemaStorage, ImmediateTimer

_SCHEMA = {
    "type": "object",
    "required": ["label"],
    "properties": {"label": {"type": "string", "enum": ["ok"]}},
}


def _usecase(*, fail_mode=FailMode.DEGRADE, timer=None, storage=None):
    return ValidateContractUseCase(
        schema_storage=storage or FakeSchemaStorage({"k": _SCHEMA}),
        validator=__import__(
            "congine_core.domain.validator", fromlist=["LocalValidator"]
        ).LocalValidator(),
        event_bus=FakeEventBus(),
        logger=FakeLogger(),
        timer=timer or ImmediateTimer(),
        fail_mode=fail_mode,
    )


# --------------------------------------------------------------------------- #
# P0-05 — is_enforced()
# --------------------------------------------------------------------------- #
def test_three_states_are_distinguishable() -> None:
    evaluated_pass = ValidationResult(status="pass")
    evaluated_fail = ValidationResult(status="fail")
    not_evaluated = ValidationResult(
        status="fail", degraded=True, degraded_reason=DegradedReason.TIMEOUT
    )

    assert (evaluated_pass.is_enforced(), evaluated_pass.is_pass()) == (True, True)
    assert (evaluated_fail.is_enforced(), evaluated_fail.is_pass()) == (True, False)
    assert (not_evaluated.is_enforced(), not_evaluated.is_pass()) == (False, False)


def test_is_pass_alone_cannot_distinguish_violation_from_non_evaluation() -> None:
    """The reason ``is_enforced()`` had to exist."""
    violated = ValidationResult(status="fail")
    never_ran = ValidationResult(
        status="fail", degraded=True, degraded_reason=DegradedReason.LOAD_SHED
    )
    assert violated.is_pass() == never_ran.is_pass()  # indistinguishable...
    assert violated.is_enforced() != never_ran.is_enforced()  # ...until now


def test_real_breach_is_enforced() -> None:
    result = _usecase().execute({"label": "nope"}, "k", "1.0")
    assert result.is_enforced() and not result.is_pass()
    assert result.degraded_reason is None
    assert len(result.breaches) == 1


# --------------------------------------------------------------------------- #
# P0-06 — load shed vs deadline
# --------------------------------------------------------------------------- #
def test_load_shed_error_subclasses_timeout_for_backward_compatibility() -> None:
    assert issubclass(LoadShedError, TimeoutError)
    try:
        raise LoadShedError("saturated")
    except TimeoutError:
        pass  # existing broad handlers keep working
    else:  # pragma: no cover
        pytest.fail("LoadShedError must be catchable as TimeoutError")


def test_saturated_executor_raises_load_shed_not_plain_timeout() -> None:
    import threading

    executor = BoundedValidationExecutor(
        max_workers=1, max_pending=0, register_atexit=False
    )
    block = threading.Event()
    try:
        threading.Thread(
            target=lambda: executor.run_with_timeout(lambda: block.wait(10), 10_000),
            daemon=True,
        ).start()
        # Wait until the single permit is genuinely taken.
        for _ in range(200):
            if executor.in_flight == 1:
                break
            block.wait(0.01)
        with pytest.raises(LoadShedError):
            executor.run_with_timeout(lambda: 1, 5_000)
    finally:
        block.set()
        executor.shutdown(wait=False)


def test_deadline_overrun_raises_timeout_but_not_load_shed() -> None:
    import time

    executor = BoundedValidationExecutor(
        max_workers=2, max_pending=2, register_atexit=False
    )
    try:
        with pytest.raises(TimeoutError) as exc:
            executor.run_with_timeout(lambda: time.sleep(0.5), 10)
        assert not isinstance(exc.value, LoadShedError)
    finally:
        executor.shutdown(wait=False)


def test_use_case_maps_the_two_conditions_to_distinct_reasons() -> None:
    class Shedding:
        def run_with_timeout(self, func, timeout_ms):
            raise LoadShedError("saturated")

    class Slow:
        def run_with_timeout(self, func, timeout_ms):
            raise TimeoutError("deadline")

    shed = _usecase(timer=Shedding()).execute({"label": "ok"}, "k", "1.0")
    slow = _usecase(timer=Slow()).execute({"label": "ok"}, "k", "1.0")

    assert shed.degraded_reason == DegradedReason.LOAD_SHED == "load_shed"
    assert slow.degraded_reason == DegradedReason.TIMEOUT == "timeout"
    for result in (shed, slow):
        assert not result.is_enforced()
        assert result.breaches == ()  # never fabricate a verdict


# --------------------------------------------------------------------------- #
# P0-02 — unmeasurable input fails closed
# --------------------------------------------------------------------------- #
def _circular():
    d: dict = {}
    d["self"] = d
    return d


class _ReprRaises:
    def __repr__(self):
        raise RuntimeError("boom")


@pytest.mark.parametrize(
    "name,payload",
    [
        ("circular reference", _circular()),
        ("non-string mapping key", {(1, 2): "x"}),
        ("__repr__ raises", {"a": _ReprRaises()}),
    ],
)
def test_unmeasurable_payload_degrades_and_never_bypasses_the_bound(name, payload):
    result = _usecase().execute(payload, "k", "1.0")
    assert not result.is_enforced(), name
    assert result.degraded_reason == DegradedReason.INVALID_PAYLOAD
    assert result.breaches == ()  # "could not measure" is not "violated"


def test_unmeasurable_schema_degrades_with_invalid_contract() -> None:
    storage = FakeSchemaStorage({"k": {"bad": _ReprRaises()}})
    result = _usecase(storage=storage).execute({"label": "ok"}, "k", "1.0")
    assert result.degraded_reason == DegradedReason.INVALID_CONTRACT
    assert not result.is_enforced()


def test_measurable_oversize_remains_a_real_breach_not_a_degradation() -> None:
    """The distinction P0-02 turns on: measured-and-exceeded is a genuine verdict."""
    uc = ValidateContractUseCase(
        schema_storage=FakeSchemaStorage({"k": _SCHEMA}),
        validator=__import__(
            "congine_core.domain.validator", fromlist=["LocalValidator"]
        ).LocalValidator(),
        event_bus=FakeEventBus(),
        logger=FakeLogger(),
        timer=ImmediateTimer(),
        max_payload_bytes=50,
    )
    result = uc.execute({"label": "x" * 500}, "k", "1.0")
    assert result.is_enforced()  # we DID measure it
    assert [b.rule for b in result.breaches] == ["INPUT_BOUNDS"]


def test_missing_contract_still_fails_closed_in_every_mode() -> None:
    for mode in (FailMode.SILENT, FailMode.DEGRADE, FailMode.STRICT):
        with pytest.raises(CongineContractNotFoundError):
            _usecase(fail_mode=mode).execute({"label": "ok"}, "absent", "1.0")


def test_strict_mode_still_raises_on_a_real_breach() -> None:
    with pytest.raises(CongineValidationError):
        _usecase(fail_mode=FailMode.STRICT).execute({"label": "nope"}, "k", "1.0")


# --------------------------------------------------------------------------- #
# Machine-facing serialization (the enum trap)
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("reason", list(DegradedReason))
def test_degraded_reason_serializes_as_its_wire_value(reason) -> None:
    """Must hold on *every* path: a mixin enum leaks ``X.MEMBER`` under ``str()``."""
    assert json.dumps({"r": reason}) == f'{{"r": "{reason.value}"}}'
    assert json.dumps({"r": reason}, default=str) == f'{{"r": "{reason.value}"}}'
    assert str(reason) == reason.value
    assert f"{reason}" == reason.value
    assert "%s" % reason == reason.value
    assert reason == reason.value


def test_degraded_reason_survives_the_structured_logger(capsys) -> None:
    from congine_core.infrastructure.logger import StructuredLogger

    StructuredLogger("t").warning("x", degraded_reason=DegradedReason.LOAD_SHED)
    emitted = json.loads(capsys.readouterr().out.strip())
    assert emitted["degraded_reason"] == "load_shed"


def test_degraded_reason_survives_telemetry_serialization() -> None:
    from congine_core.domain.models import TelemetryEvent
    from congine_core.infrastructure.queue_event_bus import QueueEventBus

    event = TelemetryEvent(
        contract_id="c",
        contract_version="1",
        status="fail",
        duration_ms=1.0,
        breach_details=[{"reason": DegradedReason.LOAD_SHED}],
    )
    wire = json.dumps(QueueEventBus._serialize(event))
    assert '"load_shed"' in wire
    assert "DegradedReason" not in wire


# --------------------------------------------------------------------------- #
# P0-07 — strict configuration
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "raw", ["1", "true", "TRUE", " yes ", "on", "0", "false", "off"]
)
def test_accepted_booleans_parse(monkeypatch, raw) -> None:
    monkeypatch.setenv("CONGINE_TELEMETRY_ENABLED", raw)
    assert isinstance(CongineConfig.from_env().telemetry_enabled, bool)


@pytest.mark.parametrize("raw", ["TRUE!", "yes please", "maybe", "enabled", "", "  "])
def test_malformed_boolean_raises_instead_of_silently_disabling(monkeypatch, raw):
    """It used to return False, silently switching off telemetry or background services."""
    monkeypatch.setenv("CONGINE_TELEMETRY_ENABLED", raw)
    with pytest.raises(CongineConfigurationError, match="CONGINE_TELEMETRY_ENABLED"):
        CongineConfig.from_env()


def test_invalid_contract_source_raises_instead_of_meaning_http(monkeypatch) -> None:
    monkeypatch.setenv("CONGINE_CONTRACT_SOURCE", "files")
    with pytest.raises(CongineConfigurationError, match="CONGINE_CONTRACT_SOURCE"):
        CongineConfig.from_env()


def test_valid_contract_source_parses(monkeypatch) -> None:
    monkeypatch.setenv("CONGINE_CONTRACT_SOURCE", "FILE")
    assert CongineConfig.from_env().contract_source is ContractSource.FILE


@pytest.mark.parametrize(
    "var", ["CONGINE_LOCAL_CONTRACTS_DIR", "CONGINE_CONTRACTS_DIR"]
)
@pytest.mark.parametrize("raw", ["", "   "])
def test_empty_contract_dir_raises(monkeypatch, var, raw) -> None:
    """``VAR=""`` is the shell idiom for "unset"; it used to select a broken mode."""
    monkeypatch.setenv(var, raw)
    with pytest.raises(CongineConfigurationError, match=var):
        CongineConfig.from_env()


def test_unset_contract_dir_is_simply_not_selected(monkeypatch) -> None:
    monkeypatch.delenv("CONGINE_LOCAL_CONTRACTS_DIR", raising=False)
    assert CongineConfig.from_env().local_contracts_dir is None


def test_invalid_admission_mode_raises(monkeypatch) -> None:
    monkeypatch.setenv("CONGINE_CONTRACT_ADMISSION", "lenient")
    with pytest.raises(CongineConfigurationError, match="CONGINE_CONTRACT_ADMISSION"):
        CongineConfig.from_env()


def test_admission_defaults_to_strict(monkeypatch) -> None:
    monkeypatch.delenv("CONGINE_CONTRACT_ADMISSION", raising=False)
    assert CongineConfig.from_env().contract_admission is ContractAdmissionMode.STRICT


def test_timeout_default_has_one_source_of_truth(monkeypatch) -> None:
    """Config and direct construction previously disagreed: 100 vs 15."""
    monkeypatch.delenv("CONGINE_TIMEOUT_MS", raising=False)
    import inspect

    constructor_default = (
        inspect.signature(ValidateContractUseCase.__init__)
        .parameters["timeout_ms"]
        .default
    )
    assert constructor_default == DEFAULT_VALIDATION_TIMEOUT_MS
    assert (
        CongineConfig.from_env().validation_timeout_ms == DEFAULT_VALIDATION_TIMEOUT_MS
    )


# --------------------------------------------------------------------------- #
# P0-08 — region never infers a destination
# --------------------------------------------------------------------------- #
def test_region_without_base_url_raises(monkeypatch) -> None:
    """It used to resolve to an unverified placeholder host — with the API key."""
    monkeypatch.setenv("CONGINE_REGION", "eu")
    monkeypatch.delenv("CONGINE_BASE_URL", raising=False)
    with pytest.raises(CongineConfigurationError, match="CONGINE_BASE_URL"):
        CongineConfig.from_env()


def test_explicit_base_url_wins_over_region(monkeypatch) -> None:
    monkeypatch.setenv("CONGINE_REGION", "eu")
    monkeypatch.setenv("CONGINE_BASE_URL", "https://cp.example.com")
    monkeypatch.setenv("CONGINE_API_KEY", "k")
    monkeypatch.setenv("CONGINE_PROJECT_ID", "p")
    monkeypatch.setenv("CONGINE_TENANT_ID", "t")
    cfg = CongineConfig.from_env()
    assert cfg.base_url == "https://cp.example.com"
    assert cfg.region is Region.EU  # retained as metadata


def test_local_development_needs_neither(monkeypatch) -> None:
    monkeypatch.delenv("CONGINE_REGION", raising=False)
    monkeypatch.delenv("CONGINE_BASE_URL", raising=False)
    assert CongineConfig.from_env().base_url == "http://localhost:8080"


def test_no_placeholder_regional_hostname_remains_in_config() -> None:
    """Guard against the mapping being reintroduced."""
    from pathlib import Path

    import congine_core.config as config_module

    source = Path(config_module.__file__).read_text(encoding="utf-8")
    assert "api.eu.congine.dev" not in source
    assert "_REGION_BASE_URLS" not in source
    assert not hasattr(Region.EU, "default_base_url")


def test_replace_keeps_config_usable() -> None:
    """``dataclasses.replace`` is how hosts build variants; it must still work."""
    cfg = replace(
        CongineConfig(
            base_url="http://localhost:8080",
            api_key=None,
            project_id=None,
            tenant_id=None,
            region=Region.US,
        ),
        contract_admission=ContractAdmissionMode.WARN,
    )
    assert cfg.contract_admission is ContractAdmissionMode.WARN
