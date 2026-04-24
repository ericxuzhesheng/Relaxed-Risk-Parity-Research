import pandas as pd
import numpy as np
from typing import List, Dict, Any
from src.risk_parity import solve_relaxed_rp, optimize_with_leverage
from src.metrics import calculate_metrics
from tqdm import tqdm

def run_dynamic_rrp_selection(
    returns: pd.DataFrame,
    param_grid: List[Dict[str, Any]],
    train_window_months: int = 24,
    test_window_months: int = 1,
    rebalance_frequency: str = "M",
    selection_metric: str = "sharpe_ratio",
    transaction_cost: float = 0.0,
    config_base: dict = None
) -> pd.DataFrame:
    """
    Rolling window dynamic parameter selection for RRP.
    """
    dates = returns.index
    rebalance_dates = pd.date_range(start=dates[0], end=dates[-1], freq=rebalance_frequency)
    rebalance_dates = [d for d in rebalance_dates if d in dates]
    
    if not rebalance_dates:
        rebalance_dates = [dates[0]] # Fallback
        
    results = []
    current_weights = None
    
    # Identify bond indices (dynamic)
    def get_bond_indices(df_window):
        keywords = config_base["bond_keywords"]
        return [i for i, col in enumerate(df_window.columns) if any(k in col for k in keywords)]

    # Grid search helper
    def evaluate_params(df_train, params, config_base):
        mu = df_train.mean() * config_base["trading_days_per_year"]
        Sigma = df_train.cov() * config_base["trading_days_per_year"]
        Theta = np.diag(np.diag(Sigma))
        n_assets = len(df_train.columns)
        bond_indices = get_bond_indices(df_train)
        
        cfg = config_base.copy()
        cfg.update(params)
        
        # Simple backtest in train window to get metric
        # For efficiency, we just solve once at the end of train window and use that weight
        # OR we could do a mini-backtest. Let's do a simple one-step solve for speed.
        try:
            R_base = mu.mean() # Simplified baseline return
            if bond_indices:
                w_train, _ = optimize_with_leverage(Sigma.values, n_assets, bond_indices, mu.values, Theta, R_base, is_relaxed=True, config=cfg)
            else:
                w_train = solve_relaxed_rp(Sigma.values, mu.values, Theta, n_assets, R_base, cfg)
            
            # Calculate score on train window (last month or whole window)
            # To be robust, let's use the whole train window with these weights
            port_ret = df_train.fillna(0) @ w_train
            nav = (1 + port_ret).cumprod()
            metrics = calculate_metrics(nav, trading_days=config_base["trading_days_per_year"])
            return metrics.get(selection_metric, -999)
        except:
            return -999

    print("Starting walk-forward parameter selection...")
    # Walk-forward loop
    for i in range(len(rebalance_dates)):
        curr_date = rebalance_dates[i]
        if i < 1: continue # Need at least one window
        
        # Training window
        train_start = curr_date - pd.DateOffset(months=train_window_months)
        df_train = returns[(returns.index >= train_start) & (returns.index < curr_date)]
        
        if len(df_train) < 20: continue # Not enough data
        
        # Grid Search
        best_score = -np.inf
        best_params = param_grid[0]
        
        for params in param_grid:
            score = evaluate_params(df_train, params, config_base)
            if score > best_score:
                best_score = score
                best_params = params
        
        # Apply best params to next period
        mu_curr = df_train.mean() * config_base["trading_days_per_year"]
        Sigma_curr = df_train.cov() * config_base["trading_days_per_year"]
        Theta_curr = np.diag(np.diag(Sigma_curr))
        n_assets = len(df_train.columns)
        bond_indices = get_bond_indices(df_train)
        
        cfg_best = config_base.copy()
        cfg_best.update(best_params)
        
        R_base = mu_curr.mean()
        if bond_indices:
            w_best, lev_best = optimize_with_leverage(Sigma_curr.values, n_assets, bond_indices, mu_curr.values, Theta_curr, R_base, is_relaxed=True, config=cfg_best)
            w_best = w_best * lev_best # Apply leverage
        else:
            w_best = solve_relaxed_rp(Sigma_curr.values, mu_curr.values, Theta_curr, n_assets, R_base, cfg_best)

        # Test window (until next rebalance)
        test_end = rebalance_dates[i+1] if i+1 < len(rebalance_dates) else dates[-1]
        df_test = returns[(returns.index >= curr_date) & (returns.index < test_end)]
        
        if df_test.empty: continue
        
        for d in df_test.index:
            res = {
                "date": d,
                "portfolio_return": np.dot(df_test.fillna(0).loc[d], w_best),
                "selected_lambda": best_params.get("lambda_pen"),
                "selected_m": best_params.get("m"),
                "selected_bond_leverage_cap": best_params.get("bond_leverage_upper"),
                "selection_score": best_score
            }
            # Add weights
            for j, asset in enumerate(returns.columns):
                res[f"weight_{asset}"] = w_best[j]
            results.append(res)

    return pd.DataFrame(results)
