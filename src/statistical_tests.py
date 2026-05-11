"""Statistical tests for pairwise Sharpe-ratio differences.

The thesis claims Improved Convex Adaptive RRP delivers Sharpe 1.326 versus
0.693 for Global RRP. Single-path Sharpe estimates have non-trivial sampling
error, especially on serially dependent daily return series, so this module
implements a block-bootstrap test for the null hypothesis that the *paired*
Sharpe difference equals zero.

The block bootstrap (Politis & Romano 1994) handles serial correlation by
resampling contiguous return blocks with replacement. With ``block_size``
roughly equal to the autocorrelation horizon (≈21 daily for typical asset
return series) the resampled paths approximately preserve the dependence
structure.

The primary entry point is :func:`sharpe_difference_block_bootstrap`. It
returns the observed Sharpe difference, a percentile confidence interval,
and a two-sided p-value derived from the bootstrap distribution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class SharpeDifferenceResult:
    model_a: str
    model_b: str
    sharpe_a: float
    sharpe_b: float
    observed_difference: float
    ci_low: float
    ci_high: float
    p_value_two_sided: float
    n_resamples: int
    block_size: int
    confidence_level: float
    n_observations: int


def annualized_sharpe(
    returns: pd.Series,
    risk_free_rate: float = 0.0,
    trading_days: int = 243,
) -> float:
    """Annualized Sharpe ratio from a daily return series.

    Matches the convention used in ``src.metrics.calculate_metrics``:
    annualized return computed from the cumulative product, annualized
    volatility computed from the daily standard deviation times the square
    root of trading days. Returns 0.0 when the realized volatility is
    non-positive so callers can safely skip degenerate windows.
    """
    series = pd.Series(returns).astype(float).dropna()
    if len(series) < 2:
        return 0.0
    nav = (1.0 + series).cumprod()
    total_return = float(nav.iloc[-1] / nav.iloc[0] - 1.0)
    annualized_return = (1.0 + total_return) ** (trading_days / len(nav)) - 1.0
    annualized_vol = float(series.std() * np.sqrt(trading_days))
    if annualized_vol <= 0.0:
        return 0.0
    return float((annualized_return - risk_free_rate) / annualized_vol)


def _aligned_pair(
    returns_a: pd.Series,
    returns_b: pd.Series,
) -> tuple[np.ndarray, np.ndarray, pd.DatetimeIndex]:
    df = pd.concat(
        [
            pd.Series(returns_a).rename("a").astype(float),
            pd.Series(returns_b).rename("b").astype(float),
        ],
        axis=1,
    ).dropna(how="any")
    if df.empty:
        raise ValueError("Aligned return series is empty; cannot run Sharpe-diff bootstrap.")
    df = df.sort_index()
    return df["a"].values, df["b"].values, pd.DatetimeIndex(df.index)


def sharpe_difference_block_bootstrap(
    returns_a: pd.Series,
    returns_b: pd.Series,
    *,
    model_a: str = "model_a",
    model_b: str = "model_b",
    n_resamples: int = 2000,
    block_size: int = 21,
    risk_free_rate: float = 0.0,
    trading_days: int = 243,
    confidence_level: float = 0.95,
    seed: int = 0,
) -> SharpeDifferenceResult:
    """Block-bootstrap test for ``Sharpe(a) - Sharpe(b) = 0``.

    The two series are aligned on their common date index. Returns the
    observed Sharpe difference, a percentile confidence interval, and a
    two-sided p-value computed as
    ``2 · min( P(diff*<=0), P(diff*>=0) )`` over the bootstrap distribution.
    """
    if n_resamples < 1:
        raise ValueError("n_resamples must be >= 1")
    if block_size < 1:
        raise ValueError("block_size must be >= 1")
    if not (0.0 < confidence_level < 1.0):
        raise ValueError("confidence_level must be in (0, 1)")

    a, b, index = _aligned_pair(returns_a, returns_b)
    n = len(a)
    if n <= block_size:
        raise ValueError(
            f"Aligned series length {n} must exceed block_size {block_size}."
        )

    rng = np.random.default_rng(seed)
    sharpe_a_obs = annualized_sharpe(pd.Series(a, index=index), risk_free_rate, trading_days)
    sharpe_b_obs = annualized_sharpe(pd.Series(b, index=index), risk_free_rate, trading_days)
    diff_obs = float(sharpe_a_obs - sharpe_b_obs)

    n_blocks = int(np.ceil(n / block_size))
    diffs = np.empty(n_resamples)
    for r in range(n_resamples):
        starts = rng.integers(0, n - block_size + 1, size=n_blocks)
        idx = np.concatenate([np.arange(s, s + block_size) for s in starts])[:n]
        a_star = a[idx]
        b_star = b[idx]
        ts = pd.DatetimeIndex(index)  # original date index for cumprod
        sharpe_a_star = annualized_sharpe(pd.Series(a_star, index=ts), risk_free_rate, trading_days)
        sharpe_b_star = annualized_sharpe(pd.Series(b_star, index=ts), risk_free_rate, trading_days)
        diffs[r] = sharpe_a_star - sharpe_b_star

    alpha = 1.0 - confidence_level
    ci_low = float(np.quantile(diffs, alpha / 2.0))
    ci_high = float(np.quantile(diffs, 1.0 - alpha / 2.0))

    # Two-sided p-value: how often does the bootstrap distribution
    # contradict the observed direction? We use the empirical CDF of the
    # *centered* bootstrap distribution evaluated at the observed shift.
    centered = diffs - float(np.mean(diffs))
    p_left = float(np.mean(centered <= -abs(diff_obs)))
    p_right = float(np.mean(centered >= abs(diff_obs)))
    p_value = float(min(1.0, p_left + p_right))

    return SharpeDifferenceResult(
        model_a=model_a,
        model_b=model_b,
        sharpe_a=sharpe_a_obs,
        sharpe_b=sharpe_b_obs,
        observed_difference=diff_obs,
        ci_low=ci_low,
        ci_high=ci_high,
        p_value_two_sided=p_value,
        n_resamples=n_resamples,
        block_size=block_size,
        confidence_level=confidence_level,
        n_observations=n,
    )


def pairwise_sharpe_difference_table(
    return_series: dict[str, pd.Series],
    pairs: Iterable[tuple[str, str]] | None = None,
    **kwargs,
) -> pd.DataFrame:
    """Run :func:`sharpe_difference_block_bootstrap` across multiple pairs.

    ``return_series`` is a mapping ``{model_name: daily_returns_series}``.
    When ``pairs`` is None every ordered (a, b) pair is tested. Returns a
    long-form DataFrame, one row per pair.
    """
    names = list(return_series.keys())
    if pairs is None:
        pairs = [(a, b) for i, a in enumerate(names) for b in names[i + 1:]]
    rows = []
    for a_name, b_name in pairs:
        result = sharpe_difference_block_bootstrap(
            return_series[a_name],
            return_series[b_name],
            model_a=a_name,
            model_b=b_name,
            **kwargs,
        )
        rows.append(
            {
                "model_a": result.model_a,
                "model_b": result.model_b,
                "n_observations": result.n_observations,
                "sharpe_a": result.sharpe_a,
                "sharpe_b": result.sharpe_b,
                "observed_difference": result.observed_difference,
                "ci_low": result.ci_low,
                "ci_high": result.ci_high,
                "confidence_level": result.confidence_level,
                "p_value_two_sided": result.p_value_two_sided,
                "block_size": result.block_size,
                "n_resamples": result.n_resamples,
                "significant_at_95pct": bool(
                    result.ci_low > 0.0 or result.ci_high < 0.0
                ),
            }
        )
    return pd.DataFrame(rows)
