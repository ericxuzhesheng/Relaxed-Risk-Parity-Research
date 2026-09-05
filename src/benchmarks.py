from __future__ import annotations

import numpy as np
import pandas as pd
import cvxpy as cp

from src.convex_adaptive_rrp import drift_weights, rebalance_dates_for_frequency
from src.covariance_estimators import estimate_covariance
from src.hierarchical_risk_parity import solve_herc, solve_hrp
from src.investable import expand_weights, investable_columns, portfolio_return_for_available
from src.risk_parity import solve_standard_rp
from src.utils import get_config, infer_asset_class


def clean_weights(weights: np.ndarray, n_assets: int | None = None) -> np.ndarray:
    weights = np.asarray(weights, dtype=float)
    weights = np.nan_to_num(weights, nan=0.0, posinf=0.0, neginf=0.0)
    weights = np.clip(weights, 0.0, None)
    if n_assets is None:
        n_assets = len(weights)
    total = float(weights.sum())
    if total <= 0.0:
        return np.ones(n_assets) / n_assets
    return weights / total


def equal_weight(returns_window: pd.DataFrame) -> pd.Series:
    n_assets = len(returns_window.columns)
    return pd.Series(np.ones(n_assets) / n_assets, index=returns_window.columns)


def minimum_variance(returns_window: pd.DataFrame) -> pd.Series:
    n_assets = len(returns_window.columns)
    cov = estimate_covariance(returns_window, method="sample").values
    weights = cp.Variable(n_assets)
    problem = cp.Problem(
        cp.Minimize(cp.quad_form(weights, cp.psd_wrap(cov))),
        [weights >= 0.0, cp.sum(weights) == 1.0],
    )
    if not problem.is_dcp():
        raise RuntimeError("minimum-variance benchmark is not DCP compliant")
    problem.solve(solver="CLARABEL", verbose=False)
    if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE} or weights.value is None:
        raise RuntimeError(f"minimum-variance benchmark failed with status={problem.status}")
    return pd.Series(clean_weights(weights.value), index=returns_window.columns)


def maximum_diversification(returns_window: pd.DataFrame) -> pd.Series:
    cov = estimate_covariance(returns_window, method="sample").values
    vols = np.sqrt(np.clip(np.diag(cov), 1e-12, None))
    n_assets = len(returns_window.columns)
    scaled = cp.Variable(n_assets)
    problem = cp.Problem(
        cp.Minimize(cp.quad_form(scaled, cp.psd_wrap(cov))),
        [scaled >= 0.0, vols @ scaled == 1.0],
    )
    if not problem.is_dcp():
        raise RuntimeError("maximum-diversification benchmark is not DCP compliant")
    problem.solve(solver="CLARABEL", verbose=False)
    if problem.status not in {cp.OPTIMAL, cp.OPTIMAL_INACCURATE} or scaled.value is None:
        raise RuntimeError(f"maximum-diversification benchmark failed with status={problem.status}")
    return pd.Series(clean_weights(scaled.value), index=returns_window.columns)


def classical_risk_parity(returns_window: pd.DataFrame) -> pd.Series:
    cov = estimate_covariance(
        returns_window, method="sample", trading_days=243, annualize=True
    ).values
    weights = solve_standard_rp(cov, len(returns_window.columns), config=get_config({"optim_maxiter": 500}))
    return pd.Series(clean_weights(weights), index=returns_window.columns)


def sixty_forty(returns_window: pd.DataFrame) -> pd.Series | None:
    equity = [col for col in returns_window.columns if infer_asset_class(col) == "equity"]
    bonds = [col for col in returns_window.columns if infer_asset_class(col) == "bond"]
    if not equity or not bonds:
        return None
    weights = pd.Series(0.0, index=returns_window.columns)
    weights.loc[equity] = 0.60 / len(equity)
    weights.loc[bonds] = 0.40 / len(bonds)
    return weights


BENCHMARK_BUILDERS = {
    "Equal Weight Benchmark": equal_weight,
    "Minimum Variance Benchmark": minimum_variance,
    "Maximum Diversification Benchmark": maximum_diversification,
    "Classical Risk Parity Benchmark": classical_risk_parity,
    "60/40 Benchmark": sixty_forty,
    "HRP Benchmark": solve_hrp,
    "HERC Benchmark": solve_herc,
}


def monthly_rebalance_dates(returns: pd.DataFrame) -> set[pd.Timestamp]:
    return set(returns.groupby(returns.index.to_period("M")).tail(1).index)


def run_benchmark_backtest(
    returns: pd.DataFrame,
    name: str,
    lookback_days: int = 240,
    transaction_cost_bps: float = 3.0,
    rebalance_frequency: str = "M",
) -> pd.DataFrame:
    if name not in BENCHMARK_BUILDERS:
        raise ValueError(f"Unknown benchmark: {name}")
    builder = BENCHMARK_BUILDERS[name]
    returns = returns.copy()
    returns.index = pd.to_datetime(returns.index)
    dates = returns.index
    rebalance_dates = rebalance_dates_for_frequency(returns, rebalance_frequency)
    n_assets = len(returns.columns)
    weights = np.zeros(n_assets)
    rows = []
    cost_rate = transaction_cost_bps / 10000.0
    skipped = False
    skip_reason = ""
    for date in dates:
        turnover = 0.0
        if date in rebalance_dates:
            window_full = returns[returns.index < date].iloc[-lookback_days:]
            active_cols = investable_columns(window_full, min_observations=min(60, lookback_days))
            window = window_full[active_cols]
            if len(window) >= 30 and len(active_cols) > 1:
                previous = weights.copy()
                candidate = builder(window)
                if candidate is None:
                    skipped = True
                    skip_reason = "Skipped because both equity and bond groups were not identifiable from infer_asset_class."
                else:
                    active_weights = clean_weights(candidate.reindex(active_cols).fillna(0.0).values, len(active_cols))
                    weights = expand_weights(active_weights, active_cols, returns.columns)
                    turnover = float(np.abs(weights - previous).sum())
        gross = portfolio_return_for_available(returns.loc[date], weights)
        net = gross - cost_rate * turnover
        row = {
            "date": date,
            "is_rebalance_day": date in rebalance_dates,
            "portfolio_return": net,
            "gross_return": gross,
            "net_return": net,
            "turnover": turnover,
            "benchmark_status": "skipped" if skipped else "ok",
            "skip_reason": skip_reason,
        }
        for i, asset in enumerate(returns.columns):
            row[f"weight_{asset}"] = weights[i]
        rows.append(row)
        weights = drift_weights(weights, returns.loc[date])
    return pd.DataFrame(rows)
