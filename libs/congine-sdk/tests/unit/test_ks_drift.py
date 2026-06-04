"""Unit tests for :mod:`congine_core.infrastructure.ks_drift`."""

from __future__ import annotations

import pytest

from congine_core.domain.models import DriftResult
from congine_core.infrastructure import ks_drift
from congine_core.infrastructure.ks_drift import KSDriftEngine

# numpy is required for detect(); skip the math tests if the extra is absent.
_HAS_NUMPY = True
try:  # pragma: no cover - environment dependent
    import numpy  # noqa: F401
except ImportError:  # pragma: no cover
    _HAS_NUMPY = False

needs_numpy = pytest.mark.skipif(not _HAS_NUMPY, reason="numpy extra not installed")


# --------------------------------------------------------------------------- #
# Reference-window bound (no numpy needed)
# --------------------------------------------------------------------------- #


def test_sample_limit_boundary_499_vs_500() -> None:
    engine = KSDriftEngine(max_samples=500)
    engine.add_reference_samples(range(499))
    assert engine.sample_count == 499
    assert engine.is_full is False

    engine.add_reference(499)
    assert engine.sample_count == 500
    assert engine.is_full is True


def test_sample_limit_strictly_capped() -> None:
    engine = KSDriftEngine(max_samples=500)
    engine.add_reference_samples(range(750))  # 250 over the cap
    assert engine.sample_count == 500  # never exceeds the limit
    assert engine.is_full is True


def test_non_positive_max_samples_rejected() -> None:
    with pytest.raises(ValueError):
        KSDriftEngine(max_samples=0)


def test_reset_clears_window() -> None:
    engine = KSDriftEngine()
    engine.add_reference_samples(range(10))
    engine.reset()
    assert engine.sample_count == 0


# --------------------------------------------------------------------------- #
# Optional-dependency handling (minimal runner without numpy)
# --------------------------------------------------------------------------- #


def test_detect_without_numpy_raises_clear_import_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _no_numpy():
        raise ImportError("No module named 'numpy'")

    monkeypatch.setattr(ks_drift, "_import_numpy", _no_numpy)

    engine = KSDriftEngine()
    engine.add_reference_samples(range(10))  # building state needs no numpy
    with pytest.raises(ImportError) as exc:
        engine.detect([1, 2, 3])
    assert "congine-sdk[stats]" in str(exc.value)


# --------------------------------------------------------------------------- #
# Drift detection (requires numpy)
# --------------------------------------------------------------------------- #


@needs_numpy
def test_no_drift_for_identical_distributions() -> None:
    engine = KSDriftEngine(threshold=0.2)
    engine.add_reference_samples(range(100))
    result = engine.detect(list(range(100)))
    assert isinstance(result, DriftResult)
    assert result.statistic == 0.0
    assert result.drift_detected is False
    assert result.p_value == 1.0
    assert result.n_reference == 100
    assert result.n_sample == 100


@needs_numpy
def test_drift_for_disjoint_distributions() -> None:
    engine = KSDriftEngine(threshold=0.2)
    engine.add_reference_samples(range(100))
    result = engine.detect(list(range(1000, 1100)))
    assert result.statistic == pytest.approx(1.0)
    assert result.drift_detected is True
    assert result.p_value < 0.05


@needs_numpy
def test_empty_reference_raises() -> None:
    engine = KSDriftEngine()
    with pytest.raises(ValueError):
        engine.detect([1, 2, 3])


@needs_numpy
def test_empty_current_raises() -> None:
    engine = KSDriftEngine()
    engine.add_reference_samples(range(10))
    with pytest.raises(ValueError):
        engine.detect([])
