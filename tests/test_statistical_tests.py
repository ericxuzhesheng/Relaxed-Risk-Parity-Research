"""Tests for src.statistical_tests: block-bootstrap Sharpe difference.

Lightweight, deterministic. The bootstrap is exercised on small synthetic
series with controlled signal so the assertions are robust to seed but
non-trivial.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.statistical_tests import (
    SharpeDifferenceResult,
    annualized_sharpe,
    pairwise_sharpe_difference_table,
    sharpe_difference_block_bootstrap,
)


def _make_series(mean: float, vol: float, n: int, seed: int) -> pd.Series:
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n)
    return pd.Series(rng.normal(mean, vol, size=n), index=dates)


def test_annualized_sharpe_matches_metrics_convention() -> None:
    rng = np.random.default_rng(0)
    series = pd.Series(rng.normal(0.0008, 0.01, size=600))
    sharpe = annualized_sharpe(series, risk_free_rate=0.0, trading_days=252)
    # With mean ~ 0.0008 per day and vol ~ 0.01, annualised Sharpe ~ sqrt(252) * 0.08 ≈ 1.27.
    assert 0.5 < sharpe < 2.5


def test_block_bootstrap_returns_result_with_sane_fields() -> None:
    a = _make_series(mean=0.0008, vol=0.01, n=500, seed=1)
    b = _make_series(mean=0.0002, vol=0.01, n=500, seed=2)
    result = sharpe_difference_block_bootstrap(
        a,
        b,
        model_a="A",
        model_b="B",
        n_resamples=300,
        block_size=10,
        trading_days=252,
        seed=42,
    )
    assert isinstance(result, SharpeDifferenceResult)
    assert result.model_a == "A"
    assert result.model_b == "B"
    assert result.n_observations == 500
    assert result.n_resamples == 300
    assert result.block_size == 10
    # Confidence interval bounds the observed difference loosely.
    assert result.ci_low <= result.observed_difference <= result.ci_high or \
        result.ci_low - 0.1 <= result.observed_difference <= result.ci_high + 0.1
    assert 0.0 <= result.p_value_two_sided <= 1.0


def test_block_bootstrap_detects_strong_signal() -> None:
    """When series A has a much higher mean than B, the CI should be
    strictly positive (significant at 95%)."""
    a = _make_series(mean=0.0020, vol=0.008, n=600, seed=11)
    b = _make_series(mean=-0.0005, vol=0.008, n=600, seed=12)
    result = sharpe_difference_block_bootstrap(
        a, b, n_resamples=600, block_size=21, trading_days=252, seed=7,
    )
    assert result.observed_difference > 0.0
    assert result.ci_low > 0.0
    assert result.p_value_two_sided < 0.05


def test_block_bootstrap_handles_identical_series() -> None:
    """When the two series are identical the observed difference is zero
    and the test must not crash on the degenerate case."""
    a = _make_series(mean=0.0005, vol=0.01, n=300, seed=21)
    result = sharpe_difference_block_bootstrap(
        a, a.copy(), n_resamples=200, block_size=10, trading_days=252, seed=0,
    )
    assert result.observed_difference == pytest.approx(0.0, abs=1e-12)


def test_pairwise_table_runs_default_pairs() -> None:
    series = {
        "X": _make_series(0.0010, 0.008, 400, seed=31),
        "Y": _make_series(0.0005, 0.008, 400, seed=32),
        "Z": _make_series(0.0001, 0.008, 400, seed=33),
    }
    table = pairwise_sharpe_difference_table(
        series, n_resamples=200, block_size=10, seed=9,
    )
    # 3 series => 3 ordered pairs.
    assert len(table) == 3
    required = {
        "model_a", "model_b", "sharpe_a", "sharpe_b",
        "observed_difference", "ci_low", "ci_high",
        "p_value_two_sided", "significant_at_95pct",
    }
    assert required.issubset(table.columns)


def test_block_bootstrap_validates_inputs() -> None:
    a = _make_series(0.0, 0.01, 50, seed=1)
    b = _make_series(0.0, 0.01, 50, seed=2)
    with pytest.raises(ValueError):
        sharpe_difference_block_bootstrap(a, b, n_resamples=0, block_size=5)
    with pytest.raises(ValueError):
        sharpe_difference_block_bootstrap(a, b, n_resamples=10, block_size=0)
    with pytest.raises(ValueError):
        sharpe_difference_block_bootstrap(a, b, n_resamples=10, block_size=10, confidence_level=1.5)
    with pytest.raises(ValueError):
        # block_size must be < series length
        sharpe_difference_block_bootstrap(a, b, n_resamples=10, block_size=100)
