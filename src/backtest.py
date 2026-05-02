import numpy as np
import pandas as pd

from src.hierarchical_risk_parity import solve_herc, solve_hrp
from src.covariance_estimators import estimate_covariance
from src.investable import expand_weights, investable_columns, portfolio_return_for_available
from src.risk_parity import optimize_with_leverage, solve_relaxed_rp, solve_standard_rp
from src.risk_overlay import (
    RiskOverlayConfig,
    apply_risk_overlay,
    apply_trend_confirmation,
    transaction_cost_rate,
)
from src.utils import apply_asset_class_budget_multipliers, get_config


def _monthly_rebalance_dates(returns: pd.DataFrame) -> set[pd.Timestamp]:
    return set(returns.groupby(returns.index.to_period("M")).tail(1).index)


def run_static_backtest(
    returns: pd.DataFrame,
    model_type: str = "relaxed",
    config_overrides: dict = None,
) -> pd.DataFrame:
    config = get_config(config_overrides)
    n_assets = len(returns.columns)
    dates = returns.index
    model_type = model_type.lower()
    if model_type not in {"standard", "relaxed", "hrp", "herc"}:
        raise ValueError(f"Unsupported model_type: {model_type}")

    keywords = config["bond_keywords"]
    bond_indices = [i for i, col in enumerate(returns.columns) if any(k in col for k in keywords)]
    rebalance_dates = _monthly_rebalance_dates(returns)
    overlay_config = RiskOverlayConfig.from_config(config)
    cost_rate = transaction_cost_rate(overlay_config)

    results = []
    current_weights = np.zeros(n_assets)
    portfolio_navs = [1.0]
    high_water_mark = 1.0
    risk_state = {}

    for d in dates:
        current_nav = portfolio_navs[-1]
        high_water_mark = max(high_water_mark, current_nav)
        drawdown = (current_nav / high_water_mark) - 1.0
        turnover = 0.0
        overlay_state = {
            "target_vol_scalar": 1.0,
            "drawdown_scalar": 1.0,
            "trend_scalar": 1.0,
            "final_risk_scalar": 1.0,
            "turnover_cap_bound": False,
            "gross_exposure": float(np.abs(current_weights).sum()),
            "risky_exposure": float(np.abs(current_weights).sum()),
            "defensive_cash_proxy_exposure": float(max(0.0, 1.0 - np.abs(current_weights).sum())),
            "reentry_state": 1.0,
            "trend_positive_count": n_assets,
        }

        if d in rebalance_dates:
            lookback = config["lookback_weeks"] * 5
            df_window_full = returns[returns.index < d].iloc[-lookback:]
            active_cols = investable_columns(df_window_full, min_observations=min(60, lookback))
            df_window = df_window_full[active_cols]
            if len(df_window) >= 20 and len(active_cols) > 1:
                previous_weights = current_weights.copy()
                previous_active = pd.Series(previous_weights, index=returns.columns).reindex(active_cols).fillna(0.0).values
                trend_positive_count = len(active_cols)

                if model_type == "hrp":
                    active_weights = solve_hrp(df_window).values
                elif model_type == "herc":
                    active_weights = solve_herc(df_window).values
                else:
                    mu = df_window.mean() * config["trading_days_per_year"]
                    sigma = estimate_covariance(
                        df_window,
                        method=config.get("covariance_method", "sample"),
                        trading_days=config["trading_days_per_year"],
                        annualize=True,
                        allow_fallback=True,
                        point_in_time=True,
                    )
                    theta = np.diag(np.diag(sigma))
                    active_bond_indices = [i for i, col in enumerate(active_cols) if any(k in col for k in keywords)]

                    mu_filtered, trend_positive_count = apply_trend_confirmation(
                        mu,
                        df_window,
                        overlay_config,
                    )
                    r_base = mu.mean()

                    if model_type == "standard":
                        if active_bond_indices:
                            w, lev = optimize_with_leverage(
                                sigma.values,
                                len(active_cols),
                                active_bond_indices,
                                config=config,
                            )
                            active_weights = w * lev
                        else:
                            active_weights = solve_standard_rp(sigma.values, len(active_cols), config)
                    else:
                        if active_bond_indices:
                            w, lev = optimize_with_leverage(
                                sigma.values,
                                len(active_cols),
                                active_bond_indices,
                                mu_filtered.values,
                                theta,
                                r_base,
                                is_relaxed=True,
                                config=config,
                            )
                            active_weights = w * lev
                        else:
                            active_weights = solve_relaxed_rp(
                                sigma.values,
                                mu_filtered.values,
                                theta,
                                len(active_cols),
                                r_base,
                                config,
                            )

                active_weights = apply_asset_class_budget_multipliers(active_weights, active_cols, config)
                current_weights = expand_weights(active_weights, active_cols, returns.columns)
                if model_type in {"standard", "relaxed"}:
                    current_weights, overlay_state = apply_risk_overlay(
                        current_weights,
                        previous_weights,
                        df_window_full,
                        drawdown,
                        overlay_config,
                        risk_state,
                    )
                    risk_state = overlay_state.copy()
                    overlay_state["trend_positive_count"] = trend_positive_count
                    turnover = overlay_state["turnover"]
                else:
                    turnover = float(np.abs(current_weights - previous_weights).sum())
                    overlay_state["turnover"] = turnover

        ret = portfolio_return_for_available(returns.loc[d], current_weights)
        if turnover > 0.0 and cost_rate > 0.0:
            ret -= cost_rate * turnover

        portfolio_navs.append(portfolio_navs[-1] * (1.0 + ret))
        res = {
            "date": d,
            "portfolio_return": ret,
            "turnover": turnover,
            "target_vol_scalar": overlay_state["target_vol_scalar"],
            "drawdown_scalar": overlay_state["drawdown_scalar"],
            "trend_scalar": overlay_state["trend_scalar"],
            "final_risk_scalar": overlay_state["final_risk_scalar"],
            "turnover_cap_bound": overlay_state["turnover_cap_bound"],
            "gross_exposure": overlay_state["gross_exposure"],
            "risky_exposure": overlay_state["risky_exposure"],
            "defensive_cash_proxy_exposure": overlay_state["defensive_cash_proxy_exposure"],
            "reentry_state": overlay_state["reentry_state"],
            "trend_positive_count": overlay_state["trend_positive_count"],
        }
        for j, asset in enumerate(returns.columns):
            res[f"weight_{asset}"] = current_weights[j]
        results.append(res)

    return pd.DataFrame(results)
