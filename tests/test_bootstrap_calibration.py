"""Calibration test for the block-bootstrap Sharpe-difference test.

When two independent return series are drawn from the same distribution, the
null hypothesis ``Sharpe(a) - Sharpe(b) = 0`` is true. The 95% confidence
interval produced by ``sharpe_difference_block_bootstrap`` should therefore
contain zero in approximately 95% of repetitions. This test draws many such
pairs and asserts that the empirical coverage is within a reasonable
tolerance of the nominal level.

The check guards against silent regressions in the bootstrap implementation
(wrong block resampling, off-by-one in the percentile, broken centering of
the p-value, etc.).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.statistical_tests import sharpe_difference_block_bootstrap


def _independent_normal_series(rng: np.random.Generator, n: int) -> tuple[pd.Series, pd.Series]:
    index = pd.date_range("2019-01-01", periods=n, freq="B")
    a = pd.Series(rng.normal(loc=0.0005, scale=0.01, size=n), index=index)
    b = pd.Series(rng.normal(loc=0.0005, scale=0.01, size=n), index=index)
    return a, b


@pytest.mark.unit
def test_block_bootstrap_ci_covers_zero_under_the_null() -> None:
    """95% CI should contain zero in ≈95% of independent null replications."""
    rng = np.random.default_rng(2026)
    n_replications = 60
    n_observations = 504  # two years of business days
    covered = 0
    for trial in range(n_replications):
        a, b = _independent_normal_series(rng, n_observations)
        result = sharpe_difference_block_bootstrap(
            a,
            b,
            n_resamples=200,
            block_size=21,
            seed=int(rng.integers(0, 2**32 - 1)),
            confidence_level=0.95,
        )
        if result.ci_low <= 0.0 <= result.ci_high:
            covered += 1

    empirical_coverage = covered / n_replications
    # 60 trials at nominal 0.95 → 95% binomial CI ≈ [0.86, 1.00];
    # use a permissive ±0.12 tolerance so the test does not become flaky.
    assert 0.83 <= empirical_coverage <= 1.0, (
        f"Empirical 95% CI coverage was {empirical_coverage:.3f} over {n_replications} "
        "null trials; expected ≈ 0.95. This indicates the block bootstrap is mis-calibrated."
    )


@pytest.mark.unit
def test_block_bootstrap_p_value_uniform_under_null() -> None:
    """Under the null the two-sided p-value should rarely be tiny."""
    rng = np.random.default_rng(7)
    p_values = []
    for _ in range(30):
        a, b = _independent_normal_series(rng, 504)
        result = sharpe_difference_block_bootstrap(
            a, b, n_resamples=200, block_size=21, seed=int(rng.integers(0, 2**32 - 1))
        )
        p_values.append(result.p_value_two_sided)

    p_array = np.asarray(p_values)
    # Under a well-calibrated test, ≤ 10% of trials should hit p < 0.05.
    # 30 trials → allow up to 4 to be conservative.
    false_rejection_rate = float(np.mean(p_array < 0.05))
    assert false_rejection_rate <= 4 / 30 + 1e-9, (
        f"Block bootstrap rejected the null in {false_rejection_rate:.2%} of trials; "
        "expected ≤ 13% with this sample size."
    )
