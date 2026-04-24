import pandas as pd
import numpy as np
from src.risk_parity import solve_standard_rp, solve_relaxed_rp, optimize_with_leverage
from src.utils import get_config

def run_static_backtest(returns: pd.DataFrame, model_type: str = "relaxed", config_overrides: dict = None) -> pd.DataFrame:
    config = get_config(config_overrides)
    n_assets = len(returns.columns)
    dates = returns.index
    
    # Identify bond indices
    keywords = config["bond_keywords"]
    bond_indices = [i for i, col in enumerate(returns.columns) if any(k in col for k in keywords)]
    
    results = []
    
    # We rebalance monthly
    rebalance_dates = pd.date_range(start=dates[0], end=dates[-1], freq="M")
    rebalance_dates = [d for d in rebalance_dates if d in dates]
    
    current_weights = np.ones(n_assets) / n_assets
    
    for i, d in enumerate(dates):
        if d in rebalance_dates:
            # Recompute weights
            lookback = config["lookback_weeks"] * 5
            df_window = returns[returns.index < d].iloc[-lookback:]
            if len(df_window) > 20:
                mu = df_window.mean() * config["trading_days_per_year"]
                Sigma = df_window.cov() * config["trading_days_per_year"]
                Theta = np.diag(np.diag(Sigma))
                R_base = mu.mean()
                
                if model_type == "standard":
                    if bond_indices:
                        w, lev = optimize_with_leverage(Sigma.values, n_assets, bond_indices, config=config)
                        current_weights = w * lev
                    else:
                        current_weights = solve_standard_rp(Sigma.values, n_assets, config)
                else: # relaxed
                    if bond_indices:
                        w, lev = optimize_with_leverage(Sigma.values, n_assets, bond_indices, mu.values, Theta, R_base, is_relaxed=True, config=config)
                        current_weights = w * lev
                    else:
                        current_weights = solve_relaxed_rp(Sigma.values, mu.values, Theta, n_assets, R_base, config)
        
        ret = np.dot(returns.fillna(0).loc[d], current_weights)
        res = {"date": d, "portfolio_return": ret}
        for j, asset in enumerate(returns.columns):
            res[f"weight_{asset}"] = current_weights[j]
        results.append(res)
        
    return pd.DataFrame(results)
