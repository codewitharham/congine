"""Runtime conformance checks at constructor-injection boundaries (P1-02)."""

from __future__ import annotations

from typing import Any

import pytest

from congine_core.domain.models import BreachDetail
from congine_core.domain.validator import CompositeValidator, LocalValidator
from congine_core.exceptions import CongineConfigurationError
from congine_core.usecases.sync_contracts_usecase import SyncContractsUseCase
from congine_core.usecases.validate_contract_usecase import ValidateContractUseCase
from tests.conftest import (
    FakeContractRepository,
    FakeEventBus,
    FakeLogger,
    FakeSchemaStorage,
    ImmediateTimer,
)


class _SemanticValidator:
    def validate(
        self, payload: dict[str, Any], schema: dict[str, Any]
    ) -> list[BreachDetail]:
        return []


class _CircuitBreaker:
    state = "CLOSED"

    def allow(self) -> bool:
        return True

    def record_success(self) -> None:
        pass

    def record_failure(self) -> None:
        pass


def _validate_dependencies() -> dict[str, object]:
    return {
        "schema_storage": FakeSchemaStorage(),
        "validator": LocalValidator(),
        "event_bus": FakeEventBus(),
        "logger": FakeLogger(),
        "timer": ImmediateTimer(),
    }


@pytest.mark.parametrize(
    ("injection_key", "role", "protocol"),
    [
        ("schema_storage", "schema_storage", "ISchemaStorage"),
        ("validator", "validator", "IValidator"),
        ("event_bus", "event_bus", "IEventBus"),
        ("logger", "logger", "ILogger"),
        ("timer", "validation_runner", "IValidationRunner"),
    ],
)
def test_validate_usecase_rejects_nonconforming_roles(
    injection_key: str, role: str, protocol: str
) -> None:
    dependencies = _validate_dependencies()
    dependencies[injection_key] = object()

    with pytest.raises(CongineConfigurationError) as exc_info:
        ValidateContractUseCase(**dependencies)  # type: ignore[arg-type]

    message = str(exc_info.value)
    assert role in message
    assert protocol in message


@pytest.mark.parametrize(
    ("role", "protocol"),
    [
        ("schema_storage", "ISchemaStorage"),
        ("contract_repository", "IContractRepository"),
        ("logger", "ILogger"),
    ],
)
def test_sync_usecase_rejects_nonconforming_required_roles(
    role: str, protocol: str
) -> None:
    dependencies: dict[str, object] = {
        "schema_storage": FakeSchemaStorage(),
        "contract_repository": FakeContractRepository(),
        "logger": FakeLogger(),
    }
    dependencies[role] = object()

    with pytest.raises(CongineConfigurationError) as exc_info:
        SyncContractsUseCase(**dependencies)  # type: ignore[arg-type]

    message = str(exc_info.value)
    assert role in message
    assert protocol in message


def test_sync_usecase_allows_absent_optional_breaker() -> None:
    SyncContractsUseCase(
        schema_storage=FakeSchemaStorage(),
        contract_repository=FakeContractRepository(),
        logger=FakeLogger(),
        circuit_breaker=None,
    )


def test_sync_usecase_validates_optional_breaker_when_supplied() -> None:
    valid = dict(
        schema_storage=FakeSchemaStorage(),
        contract_repository=FakeContractRepository(),
        logger=FakeLogger(),
    )
    SyncContractsUseCase(**valid, circuit_breaker=_CircuitBreaker())

    with pytest.raises(CongineConfigurationError) as exc_info:
        SyncContractsUseCase(**valid, circuit_breaker=object())  # type: ignore[arg-type]

    assert "circuit_breaker" in str(exc_info.value)
    assert "ICircuitBreaker" in str(exc_info.value)


@pytest.mark.parametrize(
    ("role", "rule_validator", "semantic_validator", "protocol"),
    [
        ("rule_validator", object(), _SemanticValidator(), "IValidator"),
        ("semantic_validator", LocalValidator(), object(), "ISemanticValidator"),
    ],
)
def test_composite_validator_rejects_nonconforming_roles(
    role: str,
    rule_validator: object,
    semantic_validator: object,
    protocol: str,
) -> None:
    with pytest.raises(CongineConfigurationError) as exc_info:
        CompositeValidator(
            rule_validator=rule_validator,  # type: ignore[arg-type]
            semantic_validator=semantic_validator,  # type: ignore[arg-type]
        )

    message = str(exc_info.value)
    assert role in message
    assert protocol in message
