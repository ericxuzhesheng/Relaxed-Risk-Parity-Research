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
    parser.add_argument("--update-wind", action="store_true")
    parser.add_argument("--train-window-months", type=int, default=24)
    parser.add_argument("--selection-metric", type=str, default="utility")
    parser.add_argument("--top-k", type=int, default=3)
    parser.add_argument("--fast-mode", action="store_true")
    args = parser.parse_args()

    config = get_config()
    
    if args.update_wind:
        update_data_from_wind()

    # Load data
    returns = load_data("资产数据.xlsx")
    
    # Define Asset Groups (V1/V2 and V3)
    assets_v1 = ["黄金ETF", "有色ETF大成", "恒生科技指数ETF", "恒生ETF", "沪深300ETF华泰柏瑞", "上证指数ETF", "中证1000ETF", "科创50ETF", "红利ETF", "0-5中高信用票", "CFFEX10年期国债期货", "CFFEX2年期国债期货", "CFFEX30年期国债期货"]
    assets_v3 = assets_v1 + ["纳指ETF", "标普500ETF", "日经225ETF", "CBOT10年美债连续"]
    
    # Ensure columns exist
    assets_v1 = [c for c in assets_v1 if c in returns.columns]
    assets_v3 = [c for c in assets_v3 if c in returns.columns]

    all_summaries = []

    # 1. Static Baselines
    if args.mode in ["static", "full"]:
        print("Running Static Baselines...")
        for name, assets, m_type in [("V1_Standard", assets_v1, "standard"), ("V2_Relaxed", assets_v1, "relaxed"), ("V3_Global", assets_v3, "relaxed")]:
            print(f"  Processing {name}...")
            df_ret = returns[assets]
            res = run_static_backtest(df_ret, model_type=m_type)
            res['nav'] = (1 + res['portfolio_return']).cumprod()
            
            # Save weights
            weight_cols = [c for c in res.columns if c.startswith("weight_")]
            res[['date'] + weight_cols].to_csv(resolve_path(f"results/tables/static_{name.lower()}_weights.csv"), index=False)
            
            metrics = calculate_metrics(res['nav'], risk_free_rate=config["risk_free_rate"])
            metrics['model'] = name
            metrics['turnover'] = calculate_turnover(res[weight_cols])
            all_summaries.append(metrics)
            
            plot_weights(res[['date'] + weight_cols].set_index('date'), f"{name} Weights", resolve_path(f"results/figures/static_{name.lower()}_weights.png"))

    # 2. Dynamic Selection
    if args.mode in ["dynamic", "full"]:
        print(f"Running Dynamic Selection with metric={args.selection_metric}, top_k={args.top_k}...")
        if args.fast_mode:
            param_grid = [{"lambda_pen": l, "m": m} for l in [0.5, 1.0, 1.9, 3.0] for m in [1.0, 1.5, 1.9, 2.5]]
        else:
            param_grid = [
                {"lambda_pen": l, "m": m, "bond_leverage_upper": lev} 
                for l in [0.1, 0.5, 1.0, 1.9, 5.0] 
                for m in [1.0, 1.3, 1.6, 1.9, 2.2, 2.5]
                for lev in [1.0, 1.2, 1.4]
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
        
        res_dyn['nav'] = (1 + res_dyn['portfolio_return']).cumprod()
        
        # Metrics
        metrics_dyn = calculate_metrics(res_dyn['nav'], risk_free_rate=config["risk_free_rate"])
        metrics_dyn['model'] = "Dynamic_RRP"
        weight_cols = [c for c in res_dyn.columns if c.startswith("weight_")]
        metrics_dyn['turnover'] = calculate_turnover(res_dyn[weight_cols])
        all_summaries.append(metrics_dyn)
        
        # Save results
        res_dyn.to_csv(resolve_path("results/tables/dynamic_rrp_full.csv"), index=False)
        
        # Stability Audit
        res_dyn['selected_lambda'] = res_dyn['avg_selected_lambda']
        res_dyn['selected_m'] = res_dyn['avg_selected_m']
        
        stability = {
            "parameter_switch_count": (res_dyn['selected_lambda'].diff() != 0).sum(),
            "avg_lambda": res_dyn['selected_lambda'].mean(),
            "avg_m": res_dyn['selected_m'].mean()
        }
        pd.DataFrame([stability]).to_csv(resolve_path("results/tables/rrp_parameter_stability.csv"), index=False)
        
        # Plots
        plot_weights(res_dyn[['date'] + weight_cols].set_index('date'), "Dynamic RRP Weights", resolve_path("results/figures/dynamic_rrp_weights.png"))
        plot_param_timeline(res_dyn, 'selected_lambda', "Selected Lambda over Time", resolve_path("results/figures/lambda_selection_timeline.png"))
        plot_param_timeline(res_dyn, 'selected_m', "Selected M over Time", resolve_path("results/figures/m_selection_timeline.png"))

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
                # Compute NAV from weights and returns
                common_dates = returns.index.intersection(w_df.index)
                port_ret = (returns.loc[common_dates] * w_df.loc[common_dates]).sum(axis=1)
                nav_dict[name] = (1 + port_ret).cumprod()
    
    if args.mode in ["dynamic", "full"]:
        res_dyn_file = resolve_path("results/tables/dynamic_rrp_full.csv")
        if os.path.exists(res_dyn_file):
            res_dyn_loaded = pd.read_csv(res_dyn_file, index_col='date', parse_dates=True)
            nav_dict["Dynamic_RRP"] = (1 + res_dyn_loaded['portfolio_return']).cumprod()
            
    if nav_dict:
        plot_nav_comparison(nav_dict, "NAV Comparison: Static vs Dynamic RRP", resolve_path("results/figures/static_vs_dynamic_nav.png"))

    print("\nSummary Results:")
    print(summary_df)
    print("Pipeline completed successfully.")

if __name__ == "__main__":
    main()
