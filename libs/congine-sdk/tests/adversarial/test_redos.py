"""Adversarial tests for the ReDoS guard (audit H3)."""

from __future__ import annotations

import time

import pytest

from congine_core.domain import validator as validator_mod
from congine_core.domain.validator import (
    _MAX_PATTERN_LENGTH,
    _MAX_REGEX_VALUE_LENGTH,
    RuleEngine,
)


def test_oversized_pattern_is_rejected_not_run() -> None:
    pmap = {"x": {"pattern": "a" * (_MAX_PATTERN_LENGTH + 1)}}
    breaches = RuleEngine.REGEX_PATTERN({"x": "aaa"}, pmap)
    assert len(breaches) == 1
    assert "length budget" in (breaches[0].message or "")


def test_oversized_value_is_rejected_not_run() -> None:
    pmap = {"x": {"pattern": "a+"}}
    value = "a" * (_MAX_REGEX_VALUE_LENGTH + 1)
    breaches = RuleEngine.REGEX_PATTERN({"x": value}, pmap)
    assert len(breaches) == 1
    assert "too long" in (breaches[0].message or "")


def test_invalid_pattern_becomes_breach() -> None:
    breaches = RuleEngine.REGEX_PATTERN({"x": "abc"}, {"x": {"pattern": "("}})
    assert len(breaches) == 1
    assert "Invalid regex" in (breaches[0].message or "")


def test_compiled_pattern_is_cached() -> None:
    validator_mod._compiled_pattern.cache_clear()
    RuleEngine.REGEX_PATTERN({"x": "abc"}, {"x": {"pattern": "[a-z]+"}})
    RuleEngine.REGEX_PATTERN({"x": "xyz"}, {"x": {"pattern": "[a-z]+"}})
    info = validator_mod._compiled_pattern.cache_info()
    assert info.hits >= 1  # second use hit the compiled-pattern cache


def test_evil_pattern_is_bounded_with_re2() -> None:
    pattern = "(a+)+$"
    value = "a" * 60 + "X"  # explodes under backtracking engines
    start = time.perf_counter()
    RuleEngine.REGEX_PATTERN({"x": value}, {"x": {"pattern": pattern}})
    assert time.perf_counter() - start < 1.0
