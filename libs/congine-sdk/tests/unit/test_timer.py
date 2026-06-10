"""Unit tests for :mod:`congine_core.infrastructure.timer`."""

from __future__ import annotations

import time

import pytest

from congine_core.infrastructure.timer import ValidationTimer
from congine_core.infrastructure.bounded_executor import BoundedValidationExecutor

def test_returns_result_under_budget() -> None:
    timer = BoundedValidationExecutor()
    try:
        assert timer.run_with_timeout(lambda: 6 * 7, 1000) == 42
    finally:
        timer.shutdown()


def test_raises_timeout_on_overrun() -> None:
    timer = BoundedValidationExecutor()
    try:
        with pytest.raises(TimeoutError):
            timer.run_with_timeout(lambda: time.sleep(0.5), 10)
    finally:
        timer.shutdown()


def test_propagates_function_exception() -> None:
    timer = BoundedValidationExecutor()

    def boom() -> None:
        raise ValueError("kaboom")

    try:
        with pytest.raises(ValueError):
            timer.run_with_timeout(boom, 1000)
    finally:
        timer.shutdown()


def test_shutdown_idempotent() -> None:
    timer = BoundedValidationExecutor()
    timer.shutdown()
    timer.shutdown()  # must not raise
