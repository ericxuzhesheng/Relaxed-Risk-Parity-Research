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
    selection_metric: str = "utility",
    top_k: int = 3,  # 取表现最好的前K组参数进行平滑
    config_base: dict = None
) -> pd.DataFrame:
    """
    Enhanced Dynamic Parameter Selection using Top-K ensemble and Utility Score.
    """
    dates = returns.index
    rebalance_dates = pd.date_range(start=dates[0], end=dates[-1], freq=rebalance_frequency)
    rebalance_dates = [d for d in rebalance_dates if d in dates]
    
    results = []
    
    def get_bond_indices(df_window):
        keywords = config_base["bond_keywords"]
        return [i for i, col in enumerate(df_window.columns) if any(k in col for k in keywords)]

    def evaluate_params(df_train, params, config_base):
        mu = df_train.mean() * config_base["trading_days_per_year"]
        Sigma = df_train.cov() * config_base["trading_days_per_year"]
        Theta = np.diag(np.diag(Sigma))
        n_assets = len(df_train.columns)
        bond_indices = get_bond_indices(df_train)
        
        cfg = config_base.copy()
        cfg.update(params)
        
        try:
            R_base = mu.mean()
            if bond_indices:
                w_train, lev = optimize_with_leverage(Sigma.values, n_assets, bond_indices, mu.values, Theta, R_base, is_relaxed=True, config=cfg)
                w_train = w_train * lev
            else:
                w_train = solve_relaxed_rp(Sigma.values, mu.values, Theta, n_assets, R_base, cfg)
            
            port_ret = df_train.fillna(0) @ w_train
            nav = (1 + port_ret).cumprod()
            m = calculate_metrics(nav, trading_days=config_base["trading_days_per_year"])
            
            # 效用函数：收益 - 2.0 * 波动 (更保守，追求夏普比率)
            if selection_metric == "utility":
                return m["annualized_return"] - 2.0 * m["annualized_volatility"]
            return m.get(selection_metric, -999)
        except:
            return -999

    print(f"Starting Enhanced Dynamic Selection (Top-{top_k} Ensemble)...")
    for i in range(len(rebalance_dates)):
        curr_date = rebalance_dates[i]
        if i < 1: continue
        
        train_start = curr_date - pd.DateOffset(months=train_window_months)
        df_train = returns[(returns.index >= train_start) & (returns.index < curr_date)]
        if len(df_train) < 20: continue
        
        # Grid Search: 记录所有参数得分
        scores = []
        for params in param_grid:
            score = evaluate_params(df_train, params, config_base)
            scores.append((score, params))
        
        # 排序并取 Top-K
        scores.sort(key=lambda x: x[0], reverse=True)
        top_params = [s[1] for s in scores[:top_k]]
        
        # 计算 Top-K 的平均权重 (集成学习思想)
        n_assets = len(df_train.columns)
        bond_indices = get_bond_indices(df_train)
        mu_curr = df_train.mean() * config_base["trading_days_per_year"]
        Sigma_curr = df_train.cov() * config_base["trading_days_per_year"]
        Theta_curr = np.diag(np.diag(Sigma_curr))
        R_base = mu_curr.mean()
        
        ensemble_weights = np.zeros(n_assets)
        for p in top_params:
            cfg_p = config_base.copy()
            cfg_p.update(p)
            if bond_indices:
                w_p, lev_p = optimize_with_leverage(Sigma_curr.values, n_assets, bond_indices, mu_curr.values, Theta_curr, R_base, is_relaxed=True, config=cfg_p)
                ensemble_weights += (w_p * lev_p) / top_k
            else:
                w_p = solve_relaxed_rp(Sigma_curr.values, mu_curr.values, Theta_curr, n_assets, R_base, cfg_p)
                ensemble_weights += w_p / top_k

        # 样本外测试
        test_end = rebalance_dates[i+1] if i+1 < len(rebalance_dates) else dates[-1]
        df_test = returns[(returns.index >= curr_date) & (returns.index < test_end)]
        if df_test.empty: continue
        
        for d in df_test.index:
            res = {
                "date": d,
                "portfolio_return": np.dot(df_test.fillna(0).loc[d], ensemble_weights),
                "avg_selected_lambda": np.mean([p.get("lambda_pen", 0) for p in top_params]),
                "avg_selected_m": np.mean([p.get("m", 0) for p in top_params]),
                "selection_score": scores[0][0]
            }
            for j, asset in enumerate(returns.columns):
                res[f"weight_{asset}"] = ensemble_weights[j]
            results.append(res)

    return pd.DataFrame(results)
