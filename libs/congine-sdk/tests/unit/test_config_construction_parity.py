"""Construction-path parity for ``CongineConfig`` (P0 closeout).

One property, stated once:

    A configuration value means the same thing regardless of whether it came
    from ``from_env()``, direct Python construction, a test, or a future
    CLI/API adapter.

Two defects made that untrue, and both were silent.

**Enum fields accepted raw strings.** Every enum here is ``str``-backed, so a raw
wire string compared *equal* to the member while failing the ``is`` identity
checks the code actually branches on. Consequences ranged from cosmetic
(``region``) to severe: a directly constructed ``fail_mode="strict"`` **degraded
instead of raising**, and ``deployment_mode="multi_tenant"`` bypassed the
multi-tenant guard.

**Validation ran on one path only.** ``validate()`` was invoked solely by
``from_env()``, so direct construction skipped the credential and HTTPS policy
entirely.

Both are now handled by ``CongineConfig.__post_init__``: normalize, then
validate.
"""

from __future__ import annotations

import pytest

from congine_core.config import (
    CongineConfig,
    ContractAdmissionMode,
    ContractSource,
    DeploymentMode,
    FailMode,
    Region,
)
from congine_core.exceptions import CongineConfigurationError, CongineValidationError

# A minimal, valid, local base config. Loopback so `validate()` is exempt and
# each test can vary exactly one thing.
_BASE = dict(
    base_url="http://localhost:8080",
    api_key=None,
    project_id=None,
    tenant_id=None,
    region=Region.US,
)


def _cfg(**kw) -> CongineConfig:
    return CongineConfig(**{**_BASE, **kw})


# --------------------------------------------------------------------------- #
# Enum normalization — direct construction must equal env construction
# --------------------------------------------------------------------------- #
_ENUM_CASES = [
    ("region", "eu", Region.EU),
    ("fail_mode", "strict", FailMode.STRICT),
    ("contract_source", "file", ContractSource.FILE),
    ("deployment_mode", "multi_tenant", DeploymentMode.MULTI_TENANT),
    ("contract_admission", "warn", ContractAdmissionMode.WARN),
]


@pytest.mark.parametrize("field,wire,member", _ENUM_CASES)
def test_enum_member_is_preserved(field, wire, member) -> None:
    assert getattr(_cfg(**{field: member}), field) is member


@pytest.mark.parametrize("field,wire,member", _ENUM_CASES)
def test_wire_string_is_canonicalized_to_the_member(field, wire, member) -> None:
    """``is`` matters: production code branches on identity, not equality."""
    assert getattr(_cfg(**{field: wire}), field) is member


@pytest.mark.parametrize("field,wire,member", _ENUM_CASES)
def test_case_and_whitespace_are_normalized(field, wire, member) -> None:
    assert getattr(_cfg(**{field: f"  {wire.upper()} "}), field) is member


@pytest.mark.parametrize("field,wire,member", _ENUM_CASES)
def test_direct_and_env_construction_agree(field, wire, member, monkeypatch) -> None:
    """The whole point: identical input, identical canonical result, either path."""
    env_var = {
        "region": "CONGINE_REGION",
        "fail_mode": "CONGINE_FAIL_MODE",
        "contract_source": "CONGINE_CONTRACT_SOURCE",
        "deployment_mode": "CONGINE_DEPLOYMENT_MODE",
        "contract_admission": "CONGINE_CONTRACT_ADMISSION",
    }[field]
    monkeypatch.setenv("CONGINE_BASE_URL", "http://localhost:8080")
    monkeypatch.setenv(env_var, wire)
    assert getattr(CongineConfig.from_env(), field) is member
    assert getattr(_cfg(**{field: wire}), field) is member


@pytest.mark.parametrize(
    "field,bad",
    [
        ("contract_source", "files"),
        ("contract_source", "FILE_REPOSITORY"),
        ("contract_admission", "lenient"),
        ("fail_mode", "bogus"),
        ("region", "antarctica"),
        ("deployment_mode", "single"),
        ("fail_mode", ""),
        ("region", "   "),
        ("contract_source", 42),
        ("contract_admission", None),
        ("deployment_mode", object()),
    ],
)
def test_invalid_enum_values_fail_loudly(field, bad) -> None:
    """Never a silent fallback — that is how a typo used to switch topology."""
    with pytest.raises(CongineConfigurationError, match=field):
        _cfg(**{field: bad})


# --------------------------------------------------------------------------- #
# The two severe pre-existing divergences, asserted as behaviour
# --------------------------------------------------------------------------- #
def test_raw_string_strict_mode_now_actually_enforces() -> None:
    """``fail_mode="strict"`` used to degrade silently instead of raising.

    The identity check ``self.fail_mode is FailMode.STRICT`` never matched a raw
    string, so the use case fell through to the degrade branch — enforcement
    quietly lost on a config that looked correct.
    """
    from congine_core.domain.validator import LocalValidator
    from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase
    from tests.conftest import (
        FakeEventBus,
        FakeLogger,
        FakeSchemaStorage,
        ImmediateTimer,
    )

    schema = {"type": "object", "properties": {"a": {"type": "string", "enum": ["ok"]}}}
    use_case = ValidateContractUseCase(
        schema_storage=FakeSchemaStorage({"k": schema}),
        validator=LocalValidator(),
        event_bus=FakeEventBus(),
        logger=FakeLogger(),
        timer=ImmediateTimer(),
        fail_mode=_cfg(fail_mode="strict").fail_mode,
    )
    with pytest.raises(CongineValidationError):
        use_case.execute({"a": "nope"}, "k", "1.0")


def test_raw_string_multi_tenant_still_triggers_the_guard() -> None:
    """``deployment_mode="multi_tenant"`` used to slip past the identity check."""
    assert _cfg(deployment_mode="multi_tenant").deployment_mode is (
        DeploymentMode.MULTI_TENANT
    )


# --------------------------------------------------------------------------- #
# Non-enum validation parity — construction alone must enforce it
# --------------------------------------------------------------------------- #
def test_direct_construction_enforces_credential_requirement() -> None:
    """Existing invariant, previously reachable only via an explicit validate()."""
    with pytest.raises(CongineConfigurationError, match="missing"):
        CongineConfig(
            base_url="https://cp.example.com",
            api_key=None,
            project_id=None,
            tenant_id=None,
            region=Region.US,
        )


def test_env_construction_enforces_credential_requirement(monkeypatch) -> None:
    monkeypatch.setenv("CONGINE_BASE_URL", "https://cp.example.com")
    for var in ("CONGINE_API_KEY", "CONGINE_PROJECT_ID", "CONGINE_TENANT_ID"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(CongineConfigurationError, match="missing"):
        CongineConfig.from_env()


def test_direct_construction_enforces_https_policy() -> None:
    with pytest.raises(CongineConfigurationError, match="https"):
        CongineConfig(
            base_url="http://cp.example.com",
            api_key="k",
            project_id="p",
            tenant_id="t",
            region=Region.US,
        )


def test_env_construction_enforces_https_policy(monkeypatch) -> None:
    monkeypatch.setenv("CONGINE_BASE_URL", "http://cp.example.com")
    monkeypatch.setenv("CONGINE_API_KEY", "k")
    monkeypatch.setenv("CONGINE_PROJECT_ID", "p")
    monkeypatch.setenv("CONGINE_TENANT_ID", "t")
    monkeypatch.delenv("CONGINE_ALLOW_CLEARTEXT", raising=False)
    with pytest.raises(CongineConfigurationError, match="https"):
        CongineConfig.from_env()


def test_no_caller_must_remember_to_call_validate() -> None:
    """Construction alone rejects it — note there is no ``.validate()`` here."""
    with pytest.raises(CongineConfigurationError):
        CongineConfig(
            base_url="http://cp.example.com",
            api_key="k",
            project_id="p",
            tenant_id="t",
            region=Region.US,
        )


def test_equivalent_valid_config_matches_across_both_paths(monkeypatch) -> None:
    monkeypatch.setenv("CONGINE_BASE_URL", "https://cp.example.com")
    monkeypatch.setenv("CONGINE_API_KEY", "k")
    monkeypatch.setenv("CONGINE_PROJECT_ID", "p")
    monkeypatch.setenv("CONGINE_TENANT_ID", "t")
    monkeypatch.setenv("CONGINE_FAIL_MODE", "strict")
    monkeypatch.setenv("CONGINE_CONTRACT_SOURCE", "file")

    from_env = CongineConfig.from_env()
    direct = CongineConfig(
        base_url="https://cp.example.com",
        api_key="k",
        project_id="p",
        tenant_id="t",
        region=Region.US,
        fail_mode="strict",
        contract_source="file",
    )
    for field in ("base_url", "api_key", "fail_mode", "contract_source", "region"):
        assert getattr(from_env, field) == getattr(direct, field)
    assert from_env.fail_mode is direct.fail_mode is FailMode.STRICT
    assert from_env.contract_source is direct.contract_source is ContractSource.FILE


def test_validation_is_not_duplicated_across_paths() -> None:
    """One owner: ``from_env`` must not re-invoke ``validate()`` after construction.

    Checked by AST rather than substring, so a comment mentioning ``validate()``
    does not masquerade as a call.
    """
    import ast
    import inspect
    import textwrap

    def _calls_validate(func) -> bool:
        tree = ast.parse(textwrap.dedent(inspect.getsource(func)))
        return any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "validate"
            for node in ast.walk(tree)
        )

    assert _calls_validate(CongineConfig.__post_init__), "the one owner must validate"
    assert not _calls_validate(CongineConfig.from_env), (
        "from_env must not validate again — construction already did"
    )


# --------------------------------------------------------------------------- #
# Runtime branch, not just the config value
# --------------------------------------------------------------------------- #
def test_raw_string_contract_source_selects_the_file_repository(tmp_path) -> None:
    """The defect that motivated the closeout, proven at the runtime branch.

    ``ServiceContainer`` compares ``config.contract_source is ContractSource.FILE``;
    an un-normalized string silently fell through to the HTTP repository.
    """
    from congine_core.adapters.dependency_injection import ServiceContainer
    from congine_core.infrastructure.file_contract_repository import (
        FileContractRepository,
    )

    container = ServiceContainer(
        _cfg(
            contract_source="file",
            contracts_dir=str(tmp_path),
            telemetry_enabled=False,
            start_background_services=False,
        )
    )
    try:
        assert isinstance(container.contract_repository, FileContractRepository)
    finally:
        container.close()


def test_enum_config_values_serialize_as_wire_strings() -> None:
    """Machine-facing surfaces must never leak ``Class.MEMBER``."""
    import json

    cfg = _cfg(contract_source="file", contract_admission="warn")
    assert json.dumps({"s": cfg.contract_source}) == '{"s": "file"}'
    assert json.dumps({"a": cfg.contract_admission}) == '{"a": "strict"}'.replace(
        "strict", "warn"
    )
    assert f"{cfg.contract_source}" == "file"
    assert f"{cfg.contract_admission}" == "warn"
