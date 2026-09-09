"""Kolmogorov-Smirnov drift engine (Layer 4).

:class:`KSDriftEngine` maintains a bounded reference window of observations and
runs a two-sample Kolmogorov-Smirnov test against a current sample to detect
distribution drift.

Optional math extension: ``numpy`` is imported **lazily** inside
:meth:`KSDriftEngine.detect`. Constructing the engine, adding samples, and
importing this module never require ``numpy`` — so a minimal runner without the
math extension does not crash at import. Only invoking :meth:`detect` requires
it, and a clear :class:`ImportError` is raised if it is absent (install
``congine-sdk[stats]``).

Reference-window bound: the window is a :class:`collections.deque` with
``maxlen=max_samples`` (default 500), so it is strictly capped — the 501st
observation evicts the oldest and the window length never exceeds the limit.
"""

from __future__ import annotations

import math
from collections import deque
from typing import Any, Iterable, Sequence

from congine_core.models import DriftResult

#: Default strict upper bound on the reference window size.
DEFAULT_MAX_SAMPLES = 500


def _import_numpy() -> Any:
    """Import and return ``numpy`` (indirected so tests can simulate absence)."""
    import numpy as np

    return np


def _require_numpy() -> Any:
    """Return ``numpy`` or raise a clear, actionable :class:`ImportError`."""
    try:
        return _import_numpy()
    except ImportError as exc:  # pragma: no cover - exercised via monkeypatch
        raise ImportError(
            "KSDriftEngine.detect requires the 'numpy' math extension. "
            "Install it with: pip install congine-sdk[stats]"
        ) from exc


class KSDriftEngine:
    """Two-sample KS drift detector with a strictly bounded reference window."""

    def __init__(
        self, threshold: float = 0.1, max_samples: int = DEFAULT_MAX_SAMPLES
    ) -> None:
        """Args:
        threshold: KS D-statistic above which drift is flagged.
        max_samples: Strict cap on the reference window (default 500).

        Raises:
            ValueError: If ``max_samples`` is not positive.
        """
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self.threshold = threshold
        self.max_samples = max_samples
        self._reference: "deque[float]" = deque(maxlen=max_samples)

    # ------------------------------------------------------------------ #
    # Reference-window management (no numpy needed)
    # ------------------------------------------------------------------ #
    def add_reference(self, value: float) -> None:
        """Append one observation to the reference window (oldest evicted at cap)."""
        self._reference.append(float(value))

    def add_reference_samples(self, values: Iterable[float]) -> None:
        """Append many observations, honouring the strict ``max_samples`` cap."""
        for value in values:
            self._reference.append(float(value))

    @property
    def sample_count(self) -> int:
        """Number of observations currently in the reference window."""
        return len(self._reference)

    @property
    def is_full(self) -> bool:
        """``True`` once the reference window has reached ``max_samples``."""
        return len(self._reference) >= self.max_samples

    def reset(self) -> None:
        """Clear the reference window."""
        self._reference.clear()

    # ------------------------------------------------------------------ #
    # Drift detection (requires numpy)
    # ------------------------------------------------------------------ #
    def detect(self, current: Sequence[float]) -> DriftResult:
        """Run the two-sample KS test between the reference window and *current*.

        Args:
            current: The current-window observations to compare.

        Returns:
            A :class:`DriftResult` with the KS statistic, p-value, and a
            ``drift_detected`` flag (statistic > ``threshold``).

        Raises:
            ImportError: If the ``numpy`` extension is not installed.
            ValueError: If the reference window or *current* sample is empty.
        """
        np = _require_numpy()

        reference = list(self._reference)
        if not reference:
            raise ValueError("reference window is empty")
        sample = [float(x) for x in current]
        if not sample:
            raise ValueError("current sample is empty")

        ref = np.sort(np.asarray(reference, dtype=float))
        cur = np.sort(np.asarray(sample, dtype=float))
        merged = np.concatenate([ref, cur])
        cdf_ref = np.searchsorted(ref, merged, side="right") / ref.size
        cdf_cur = np.searchsorted(cur, merged, side="right") / cur.size
        statistic = float(np.max(np.abs(cdf_ref - cdf_cur)))

        p_value = _ks_p_value(statistic, ref.size, cur.size)
        return DriftResult(
            statistic=statistic,
            p_value=p_value,
            drift_detected=statistic > self.threshold,
            n_reference=int(ref.size),
            n_sample=int(cur.size),
        )


def _ks_p_value(statistic: float, n1: int, n2: int) -> float:
    """Asymptotic two-sample KS p-value (Numerical Recipes ``probks``).

    Pure-Python (no numpy): a small alternating series in the effective sample
    size. Returns a value clamped to ``[0.0, 1.0]``.
    """
    en = math.sqrt(n1 * n2 / (n1 + n2))
    t = (en + 0.12 + 0.11 / en) * statistic
    if t <= 0.0:
        return 1.0

    total = 0.0
    sign = 1.0
    for k in range(1, 101):
        term = 2.0 * sign * math.exp(-2.0 * k * k * t * t)
        total += term
        if abs(term) <= 1e-10:
            break
        sign = -sign
    return max(0.0, min(1.0, total))
