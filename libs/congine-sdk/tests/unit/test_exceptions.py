"""Unit tests for :mod:`congine_core.exceptions`."""

from __future__ import annotations

import pytest

from congine_core.exceptions import (
    CongineBaseException,
    CongineCacheError,
    CongineConfigurationError,
    CongineContractNotFoundError,
    CongineSyncError,
    CongineTelemetryError,
    CongineValidationError,
    ContractBreachException,
    SchemaCacheMissException,
    TenantIsolationViolationException,
    ValidationTimeoutException,
)

_CANONICAL = [
    CongineValidationError,
    CongineContractNotFoundError,
    CongineConfigurationError,
    CongineSyncError,
    CongineCacheError,
    CongineTelemetryError,
]


@pytest.mark.parametrize("exc_cls", _CANONICAL)
def test_all_derive_from_base(exc_cls: type) -> None:
    assert issubclass(exc_cls, CongineBaseException)


def test_single_except_guards_whole_sdk() -> None:
    for exc_cls in _CANONICAL:
        with pytest.raises(CongineBaseException):
            raise exc_cls("boom")


def test_base_is_exception() -> None:
    assert issubclass(CongineBaseException, Exception)


def test_aliases_are_identity_bound() -> None:
    assert ContractBreachException is CongineValidationError
    assert SchemaCacheMissException is CongineContractNotFoundError
    assert ValidationTimeoutException is CongineValidationError
    assert TenantIsolationViolationException is CongineValidationError


def test_aliases_are_not_independent_subclasses() -> None:
    # An alias must BE the canonical class, not a fresh subclass of it.
    assert ContractBreachException.__name__ == "CongineValidationError"
