import argparse
import os
import pandas as pd
import numpy as np
from src.data_loader import load_data, update_data_from_wind
from src.backtest import run_static_backtest
from src.dynamic_selection import run_dynamic_rrp_selection
from src.metrics import calculate_metrics, calculate_turnover
from src.visualization import plot_nav_comparison, plot_weights, plot_param_timeline
from src.utils import get_config, resolve_path

def main():
    parser = argparse.ArgumentParser(description="Relaxed Risk Parity Pipeline")
    parser.add_argument("--mode", type=str, choices=["static", "dynamic", "full"], default="full")
    parser.add_argument("--source", type=str, choices=["excel", "tushare"], default="tushare")
    parser.add_argument("--force-update", action="store_true", help="强制从Tushare同步数据")
    parser.add_argument("--update-wind", action="store_true")
    parser.add_argument("--train-window-months", type=int, default=24)
    parser.add_argument("--selection-metric", type=str, default="sharpe")
    parser.add_argument("--top-k", type=int, default=1)
    parser.add_argument("--fast-mode", action="store_true")
    args = parser.parse_args()

    config = get_config()
    
    if args.update_wind:
        update_data_from_wind()

    # Load data
    returns = load_data(source=args.source, force_update=args.force_update)
    
    # Define Asset Groups
    # V1/V2: Domestic Core (Balanced)
    assets_v1 = [
        "红利ETF", "上证指数ETF", "沪深300ETF", "中证1000ETF", "恒生ETF", "恒生科技ETF", "科创50ETF",
        "0-5中高信用票", "中证转债", "CFFEX2年期国债期货", "CFFEX10年期国债期货", "CFFEX30年期国债期货", "黄金ETF"
    ]
    
    # V3 Global: Core Diversified (Domestic + Int'l + FX + Commodity)
    assets_v3 = list(returns.columns)
    
    # Ensure columns exist
    assets_v1 = [c for c in assets_v1 if c in returns.columns]
    assets_v3 = [c for c in assets_v3 if c in returns.columns]

    all_summaries = []
    eval_start_date = "2021-01-01"

    # 1. Static Baselines
    if args.mode in ["static", "full"]:
        print("Running Static Baselines...")
        for name, assets, m_type in [("V1_Standard", assets_v1, "standard"), ("V2_Relaxed", assets_v1, "relaxed"), ("V3_Global", assets_v3, "relaxed")]:
            print(f"  Processing {name}...")
            df_ret = returns[assets]
            res = run_static_backtest(df_ret, model_type=m_type)
            
            # Slice results from eval_start_date
            res_eval = res[res['date'] >= eval_start_date].copy()
            if not res_eval.empty:
                res_eval['nav'] = (1 + res_eval['portfolio_return']).cumprod()
                
                # Save weights
                weight_cols = [c for c in res.columns if c.startswith("weight_")]
                res[['date'] + weight_cols].to_csv(resolve_path(f"results/tables/static_{name.lower()}_weights.csv"), index=False)
                
                metrics = calculate_metrics(res_eval['nav'], risk_free_rate=config["risk_free_rate"])
                metrics['model'] = name
                metrics['turnover'] = calculate_turnover(res[weight_cols])
                all_summaries.append(metrics)
                
                plot_weights(res[['date'] + weight_cols].set_index('date'), f"{name} Weights", resolve_path(f"results/figures/static_{name.lower()}_weights.png"))

    # 2. Dynamic Selection
    if args.mode in ["dynamic", "full"]:
        print(f"Running Dynamic Selection with metric={args.selection_metric}, top_k={args.top_k}...")
        if args.fast_mode:
            # 快速模式也提升至 100+ 组合
            param_grid = [{"lambda_pen": l, "m": m} for l in [0.001, 0.01, 0.1, 0.5, 1.0, 1.9, 3.0, 5.0, 10.0] for m in [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]]
        else:
            # 全量模式提升至 1000 组合：10 (lambda) * 10 (m) * 10 (lev) = 1000
            param_grid = [
                {"lambda_pen": l, "m": m, "bond_leverage_upper": lev}
                for l in [0.001, 0.01, 0.05, 0.1, 0.5, 1.0, 1.5, 2.0, 5.0, 10.0]
                for m in [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 6.0]
                for lev in [1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0]
            ]
            
        # Use V3 assets for dynamic
        df_ret_dyn = returns[assets_v3]
        res_dyn = run_dynamic_rrp_selection(
            df_ret_dyn, 
            param_grid, 
            train_window_months=args.train_window_months,
            selection_metric=args.selection_metric,
            top_k=args.top_k,
            config_base=config
        )
        
        # Slice results from eval_start_date
        res_dyn_eval = res_dyn[res_dyn['date'] >= eval_start_date].copy()
        if not res_dyn_eval.empty:
            res_dyn_eval['nav'] = (1 + res_dyn_eval['portfolio_return']).cumprod()
            
            # Metrics
            metrics_dyn = calculate_metrics(res_dyn_eval['nav'], risk_free_rate=config["risk_free_rate"])
            metrics_dyn['model'] = "Dynamic_RRP"
            weight_cols = [c for c in res_dyn.columns if c.startswith("weight_")]
            metrics_dyn['turnover'] = calculate_turnover(res_dyn[weight_cols])
            all_summaries.append(metrics_dyn)
            
            # Save results
            res_dyn.to_csv(resolve_path("results/tables/dynamic_rrp_full.csv"), index=False)
            
            # Stability Audit
            res_dyn_audit = res_dyn[res_dyn['date'] >= eval_start_date]
            stability = {
                "parameter_switch_count": (res_dyn_audit['avg_selected_lambda'].diff() != 0).sum(),
                "avg_lambda": res_dyn_audit['avg_selected_lambda'].mean(),
                "avg_m": res_dyn_audit['avg_selected_m'].mean()
            }
            pd.DataFrame([stability]).to_csv(resolve_path("results/tables/rrp_parameter_stability.csv"), index=False)
            
            # Plots
            plot_weights(res_dyn[['date'] + weight_cols].set_index('date'), "Dynamic RRP Weights", resolve_path("results/figures/dynamic_rrp_weights.png"))
            plot_param_timeline(res_dyn_audit, 'avg_selected_lambda', "Selected Lambda over Time", resolve_path("results/figures/lambda_selection_timeline.png"))
            plot_param_timeline(res_dyn_audit, 'avg_selected_m', "Selected M over Time", resolve_path("results/figures/m_selection_timeline.png"))

    # Summary Table
    summary_df = pd.DataFrame(all_summaries)
    summary_df.to_csv(resolve_path("results/tables/static_vs_dynamic_rrp_comparison.csv"), index=False)
    
    # Final NAV Plot Comparison
    nav_dict = {}
    if args.mode in ["static", "full"]:
        for name in ["V1_Standard", "V2_Relaxed", "V3_Global"]:
            w_file = resolve_path(f"results/tables/static_{name.lower()}_weights.csv")
            if os.path.exists(w_file):
                w_df = pd.read_csv(w_file, index_col='date', parse_dates=True)
                common_dates = returns.index.intersection(w_df.index)
                common_dates = [d for d in common_dates if d >= pd.to_datetime(eval_start_date)]
                if common_dates:
                    port_ret = (returns.loc[common_dates] * w_df.loc[common_dates]).sum(axis=1)
                    nav_dict[name] = (1 + port_ret).cumprod()
    
    if args.mode in ["dynamic", "full"]:
        res_dyn_file = resolve_path("results/tables/dynamic_rrp_full.csv")
        if os.path.exists(res_dyn_file):
            res_dyn_loaded = pd.read_csv(res_dyn_file, index_col='date', parse_dates=True)
            res_dyn_loaded = res_dyn_loaded[res_dyn_loaded.index >= eval_start_date]
            nav_dict["Dynamic_RRP"] = (1 + res_dyn_loaded['portfolio_return']).cumprod()
            
    if nav_dict:
        plot_nav_comparison(nav_dict, f"NAV Comparison since {eval_start_date}", resolve_path("results/figures/static_vs_dynamic_nav.png"))

    print("\nSummary Results (Evaluation from 2021-01-01):")
    print(summary_df)
    print("Pipeline completed successfully.")

if __name__ == "__main__":
    main()
