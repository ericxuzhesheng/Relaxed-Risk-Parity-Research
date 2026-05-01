import numpy as np
import pandas as pd

from src.hierarchical_risk_parity import solve_herc, solve_hrp
from src.risk_parity import optimize_with_leverage, solve_relaxed_rp, solve_standard_rp
from src.utils import get_config


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
    transaction_cost_rate = config.get("transaction_cost_bps", 0.0) / 10000.0

    results = []
    current_weights = np.ones(n_assets) / n_assets
    portfolio_navs = [1.0]
    high_water_mark = 1.0

    for d in dates:
        current_nav = portfolio_navs[-1]
        high_water_mark = max(high_water_mark, current_nav)
        drawdown = (current_nav / high_water_mark) - 1.0
        turnover = 0.0

        if d in rebalance_dates:
            lookback = config["lookback_weeks"] * 5
            df_window = returns[returns.index < d].iloc[-lookback:]
            if len(df_window) > 20:
                previous_weights = current_weights.copy()

                if model_type == "hrp":
                    current_weights = solve_hrp(df_window).values
                elif model_type == "herc":
                    current_weights = solve_herc(df_window).values
                else:
                    mu = df_window.mean() * config["trading_days_per_year"]
                    sigma = df_window.cov() * config["trading_days_per_year"]
                    theta = np.diag(np.diag(sigma))

                    mom_lookback = 60
                    recent_ret = (1.0 + df_window.iloc[-mom_lookback:]).prod() - 1.0
                    mu_filtered = mu.copy()
                    mu_filtered[recent_ret < 0] = -0.1
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

                    expected_vol = np.sqrt(current_weights @ sigma.values @ current_weights)
                    target_vol = config.get("target_vol", 0.025)
                    if abs(drawdown) > 0.035:
                        target_vol *= 0.5
                    if expected_vol > target_vol:
                        current_weights = current_weights * (target_vol / expected_vol)

                turnover = float(np.abs(current_weights - previous_weights).sum())

        ret = float(np.dot(returns.fillna(0.0).loc[d], current_weights))
        if turnover > 0.0 and transaction_cost_rate > 0.0:
            ret -= transaction_cost_rate * turnover

        portfolio_navs.append(portfolio_navs[-1] * (1.0 + ret))
        res = {"date": d, "portfolio_return": ret, "turnover": turnover}
        for j, asset in enumerate(returns.columns):
            res[f"weight_{asset}"] = current_weights[j]
        results.append(res)

    return pd.DataFrame(results)
