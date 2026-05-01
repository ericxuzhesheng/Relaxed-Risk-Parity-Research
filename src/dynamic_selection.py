from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from src.metrics import calculate_metrics
from src.risk_overlay import (
    RiskOverlayConfig,
    apply_risk_overlay,
    apply_trend_confirmation,
    transaction_cost_rate,
)
from src.risk_parity import optimize_with_leverage, solve_relaxed_rp


def monthly_rebalance_dates(returns: pd.DataFrame) -> list[pd.Timestamp]:
    return list(returns.groupby(returns.index.to_period("M")).tail(1).index)


def _bond_indices(columns: pd.Index, config: dict) -> list[int]:
    keywords = config["bond_keywords"]
    return [i for i, col in enumerate(columns) if any(k in col for k in keywords)]


def solve_rrp_window_weights(
    df_window: pd.DataFrame,
    params: dict[str, Any],
    config_base: dict,
    overlay_config: RiskOverlayConfig | None = None,
) -> tuple[np.ndarray, dict]:
    cfg = config_base.copy()
    cfg.update(params)
    overlay = overlay_config or RiskOverlayConfig.from_config(cfg)
    n_assets = len(df_window.columns)
    mu = df_window.mean() * cfg["trading_days_per_year"]
    sigma = df_window.cov() * cfg["trading_days_per_year"]
    theta = np.diag(np.diag(sigma))
    mu_filtered, trend_positive_count = apply_trend_confirmation(mu, df_window, overlay)
    r_base = mu.mean()
    bond_indices = _bond_indices(df_window.columns, cfg)

    if bond_indices:
        weights, leverage = optimize_with_leverage(
            sigma.values,
            n_assets,
            bond_indices,
            mu_filtered.values,
            theta,
            r_base,
            is_relaxed=True,
            config=cfg,
        )
        weights = weights * leverage
    else:
        weights = solve_relaxed_rp(sigma.values, mu_filtered.values, theta, n_assets, r_base, cfg)

    state = {
        "selected_lambda": float(params.get("lambda_pen", cfg.get("lambda_pen", 0.0))),
        "selected_m": float(params.get("m", cfg.get("m", 0.0))),
        "selected_bond_leverage_upper": float(
            params.get("bond_leverage_upper", cfg.get("bond_leverage_upper", 0.0))
        ),
        "trend_positive_count": trend_positive_count,
    }
    return weights, state


def score_params(
    df_train: pd.DataFrame,
    params: dict[str, Any],
    config_base: dict,
    selection_metric: str = "utility",
) -> float:
    try:
        overlay = RiskOverlayConfig.from_config(config_base)
        weights, _ = solve_rrp_window_weights(df_train, params, config_base, overlay)
        port_ret = df_train.fillna(0.0) @ weights
        scalar = min(1.0, overlay.target_vol / (port_ret.std() * np.sqrt(overlay.trading_days_per_year) + 1e-12))
        port_ret = port_ret * scalar
        nav = (1.0 + port_ret).cumprod()
        metrics = calculate_metrics(
            nav,
            risk_free_rate=config_base.get("risk_free_rate", 0.0),
            trading_days=config_base["trading_days_per_year"],
        )
        diversification_bonus = 0.001 / (np.std(weights) + 1e-6)
        if selection_metric == "utility":
            return (
                metrics["annualized_return"]
                - 2.0 * abs(metrics["max_drawdown"])
                + 0.25 * metrics.get("sortino_ratio", 0.0)
                + diversification_bonus
            )
        return float(metrics.get(selection_metric, metrics.get("sharpe_ratio", -999.0))) + diversification_bonus
    except Exception:
        return -999.0


def run_dynamic_rrp_selection(
    returns: pd.DataFrame,
    param_grid: list[dict[str, Any]],
    train_window_months: int = 24,
    test_window_months: int = 1,
    rebalance_frequency: str = "M",
    selection_metric: str = "utility",
    top_k: int = 2,
    config_base: dict | None = None,
) -> pd.DataFrame:
    if config_base is None:
        raise ValueError("config_base is required")

    overlay = RiskOverlayConfig.from_config(config_base)
    cost_rate = transaction_cost_rate(overlay)
    rebalance_dates = monthly_rebalance_dates(returns)
    results = []
    n_assets = len(returns.columns)
    current_weights = np.ones(n_assets) / n_assets
    portfolio_navs = [1.0]
    high_water_mark = 1.0
    selected_state = {
        "avg_selected_lambda": np.nan,
        "avg_selected_m": np.nan,
        "avg_selected_bond_leverage_upper": np.nan,
        "selection_score": np.nan,
        "trend_positive_count": n_assets,
    }

    for i, curr_date in enumerate(rebalance_dates):
        train_start = curr_date - pd.DateOffset(months=train_window_months)
        df_train = returns[(returns.index >= train_start) & (returns.index < curr_date)]
        if len(df_train) < max(40, overlay.momentum_lookback):
            continue

        scores = [(score_params(df_train, params, config_base, selection_metric), params) for params in param_grid]
        scores.sort(key=lambda item: item[0], reverse=True)
        top = scores[: max(1, top_k)]
        top_params = [params for _, params in top]

        proposed = np.zeros(n_assets)
        trend_counts = []
        for params in top_params:
            weights, state = solve_rrp_window_weights(df_train, params, config_base, overlay)
            proposed += weights / len(top_params)
            trend_counts.append(state["trend_positive_count"])

        current_nav = portfolio_navs[-1]
        high_water_mark = max(high_water_mark, current_nav)
        drawdown = current_nav / high_water_mark - 1.0
        current_weights, overlay_state = apply_risk_overlay(
            proposed,
            current_weights,
            df_train,
            drawdown,
            overlay,
        )

        selected_state = {
            "avg_selected_lambda": float(np.mean([p.get("lambda_pen", config_base.get("lambda_pen", 0.0)) for p in top_params])),
            "avg_selected_m": float(np.mean([p.get("m", config_base.get("m", 0.0)) for p in top_params])),
            "avg_selected_bond_leverage_upper": float(
                np.mean([p.get("bond_leverage_upper", config_base.get("bond_leverage_upper", 0.0)) for p in top_params])
            ),
            "selection_score": float(top[0][0]),
            "trend_positive_count": int(np.mean(trend_counts)) if trend_counts else n_assets,
            **overlay_state,
        }

        test_end = curr_date + pd.DateOffset(months=test_window_months)
        if i + 1 < len(rebalance_dates):
            test_end = min(test_end, rebalance_dates[i + 1])
        df_test = returns[(returns.index >= curr_date) & (returns.index < test_end)]
        if df_test.empty:
            continue

        rebalance_turnover = selected_state["turnover"]
        for j, date in enumerate(df_test.index):
            turnover = rebalance_turnover if j == 0 else 0.0
            ret = float(np.dot(df_test.fillna(0.0).loc[date], current_weights))
            if turnover > 0.0 and cost_rate > 0.0:
                ret -= cost_rate * turnover
            portfolio_navs.append(portfolio_navs[-1] * (1.0 + ret))

            row = {
                "date": date,
                "portfolio_return": ret,
                **selected_state,
                "turnover": turnover,
            }
            for asset, weight in zip(returns.columns, current_weights):
                row[f"weight_{asset}"] = weight
            results.append(row)

    return pd.DataFrame(results)
