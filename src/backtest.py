import numpy as np
import pandas as pd

from src.hierarchical_risk_parity import solve_herc, solve_hrp
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
    current_weights = np.ones(n_assets) / n_assets
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
            df_window = returns[returns.index < d].iloc[-lookback:]
            if len(df_window) > 20:
                previous_weights = current_weights.copy()
                trend_positive_count = n_assets

                if model_type == "hrp":
                    current_weights = solve_hrp(df_window).values
                elif model_type == "herc":
                    current_weights = solve_herc(df_window).values
                else:
                    mu = df_window.mean() * config["trading_days_per_year"]
                    sigma = df_window.cov() * config["trading_days_per_year"]
                    theta = np.diag(np.diag(sigma))

                    mu_filtered, trend_positive_count = apply_trend_confirmation(
                        mu,
                        df_window,
                        overlay_config,
                    )
                    r_base = mu.mean()

                    if model_type == "standard":
                        if bond_indices:
                            w, lev = optimize_with_leverage(
                                sigma.values,
                                n_assets,
                                bond_indices,
                                config=config,
                            )
                            current_weights = w * lev
                        else:
                            current_weights = solve_standard_rp(sigma.values, n_assets, config)
                    else:
                        if bond_indices:
                            w, lev = optimize_with_leverage(
                                sigma.values,
                                n_assets,
                                bond_indices,
                                mu_filtered.values,
                                theta,
                                r_base,
                                is_relaxed=True,
                                config=config,
                            )
                            current_weights = w * lev
                        else:
                            current_weights = solve_relaxed_rp(
                                sigma.values,
                                mu_filtered.values,
                                theta,
                                n_assets,
                                r_base,
                                config,
                            )

                current_weights = apply_asset_class_budget_multipliers(current_weights, returns.columns, config)
                current_weights, overlay_state = apply_risk_overlay(
                    current_weights,
                    previous_weights,
                    df_window,
                    drawdown,
                    overlay_config,
                    risk_state,
                )
                risk_state = overlay_state.copy()
                overlay_state["trend_positive_count"] = trend_positive_count

                turnover = overlay_state["turnover"]

        ret = float(np.dot(returns.fillna(0.0).loc[d], current_weights))
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
