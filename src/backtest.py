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
    portfolio_navs = [1.0]
    high_water_mark = 1.0
    
    for i, d in enumerate(dates):
        # 计算当前回撤
        current_nav = portfolio_navs[-1]
        high_water_mark = max(high_water_mark, current_nav)
        drawdown = (current_nav / high_water_mark) - 1
        
        if d in rebalance_dates:
            # Recompute weights
            lookback = config["lookback_weeks"] * 5
            df_window = returns[returns.index < d].iloc[-lookback:]
            if len(df_window) > 20:
                mu = df_window.mean() * config["trading_days_per_year"]
                Sigma = df_window.cov() * config["trading_days_per_year"]
                Theta = np.diag(np.diag(Sigma))
                
                # --- Killer 2: Momentum Filter (60-day) ---
                # 如果过去60天累计收益为负，将其预期收益设为极低，抑制其在Relaxed RRP中的权重
                mom_lookback = 60
                recent_ret = (1 + df_window.iloc[-mom_lookback:]).prod() - 1
                mu_filtered = mu.copy()
                mu_filtered[recent_ret < 0] = -0.1 
                # ------------------------------------------

                R_base = mu.mean()
                
                if model_type == "standard":
                    if bond_indices:
                        w, lev = optimize_with_leverage(Sigma.values, n_assets, bond_indices, config=config)
                        current_weights = w * lev
                    else:
                        current_weights = solve_standard_rp(Sigma.values, n_assets, config)
                else: # relaxed
                    if bond_indices:
                        w, lev = optimize_with_leverage(Sigma.values, n_assets, bond_indices, mu_filtered.values, Theta, R_base, is_relaxed=True, config=config)
                        current_weights = w * lev
                    else:
                        current_weights = solve_relaxed_rp(Sigma.values, mu_filtered.values, Theta, n_assets, R_base, config)
                
                # --- Volatility Targeting & Killer 1: Risk Budget Overlay ---
                expected_vol = np.sqrt(current_weights @ Sigma.values @ current_weights)
                base_target_vol = config.get("target_vol", 0.025)
                
                # 如果当前回撤超过 1.5%，触发防御模式，目标波动率减半
                current_target_vol = base_target_vol
                if abs(drawdown) > 0.015:
                    current_target_vol = base_target_vol * 0.5
                
                if expected_vol > current_target_vol:
                    scaling_factor = current_target_vol / expected_vol
                    current_weights = current_weights * scaling_factor
                # ------------------------------------------------------------

        ret = np.dot(returns.fillna(0).loc[d], current_weights)
        portfolio_navs.append(portfolio_navs[-1] * (1 + ret))
        res = {"date": d, "portfolio_return": ret}
        for j, asset in enumerate(returns.columns):
            res[f"weight_{asset}"] = current_weights[j]
        results.append(res)
        
    return pd.DataFrame(results)
