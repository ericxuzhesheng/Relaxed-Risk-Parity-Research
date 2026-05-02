from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

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
    clean = returns_window.dropna(how="any")
    cov = (clean if not clean.empty else returns_window.fillna(0.0)).cov().values
    n_assets = len(returns_window.columns)

    def objective(w: np.ndarray) -> float:
        return float(w @ cov @ w)

    result = minimize(
        objective,
        np.ones(n_assets) / n_assets,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n_assets,
        constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}],
        options={"maxiter": 500, "ftol": 1e-10},
    )
    weights = result.x if result.success else np.ones(n_assets) / n_assets
    return pd.Series(clean_weights(weights), index=returns_window.columns)


def maximum_diversification(returns_window: pd.DataFrame) -> pd.Series:
    clean = returns_window.dropna(how="any")
    cov = (clean if not clean.empty else returns_window.fillna(0.0)).cov().values
    vols = np.sqrt(np.clip(np.diag(cov), 1e-12, None))
    n_assets = len(returns_window.columns)

    def objective(w: np.ndarray) -> float:
        port_vol = np.sqrt(max(float(w @ cov @ w), 1e-12))
        weighted_vol = float(w @ vols)
        return -weighted_vol / port_vol

    result = minimize(
        objective,
        np.ones(n_assets) / n_assets,
        method="SLSQP",
        bounds=[(0.0, 1.0)] * n_assets,
        constraints=[{"type": "eq", "fun": lambda w: np.sum(w) - 1.0}],
        options={"maxiter": 500, "ftol": 1e-10},
    )
    weights = result.x if result.success else np.ones(n_assets) / n_assets
    return pd.Series(clean_weights(weights), index=returns_window.columns)


def classical_risk_parity(returns_window: pd.DataFrame) -> pd.Series:
    clean = returns_window.dropna(how="any")
    cov = (clean if not clean.empty else returns_window.fillna(0.0)).cov().values * 243
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
) -> pd.DataFrame:
    if name not in BENCHMARK_BUILDERS:
        raise ValueError(f"Unknown benchmark: {name}")
    builder = BENCHMARK_BUILDERS[name]
    returns = returns.copy()
    returns.index = pd.to_datetime(returns.index)
    dates = returns.index
    n_assets = len(returns.columns)
    weights = np.zeros(n_assets)
    rows = []
    cost_rate = transaction_cost_bps / 10000.0
    skipped = False
    skip_reason = ""
    for date in dates:
        turnover = 0.0
        if date in monthly_rebalance_dates(returns):
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
    return pd.DataFrame(rows)
