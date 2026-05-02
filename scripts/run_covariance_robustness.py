from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_convex_adaptive_rrp import cvar, monthly_rebalance_dates
from scripts.run_robustness_tests import selected_improved_config
from src.convex_adaptive_rrp import ConvexRRPConfig, run_convex_adaptive_backtest
from src.covariance_estimators import estimate_covariance
from src.data_loader import load_data
from src.investable import expand_weights, investable_columns, portfolio_return_for_available
from src.metrics import calculate_metrics
from src.risk_overlay import RiskOverlayConfig, apply_risk_overlay, apply_trend_confirmation, transaction_cost_rate
from src.risk_parity import optimize_with_leverage, solve_relaxed_rp
from src.utils import apply_asset_class_budget_multipliers, get_config, infer_asset_class


MODELS = [
    "Global RRP",
    "Convex Adaptive Global RRP",
    "Improved Convex Adaptive Global RRP",
]
METHODS = ["sample", "ledoit_wolf", "ewma_halflife_20", "ewma_halflife_60", "ewma_halflife_120"]


def output_dirs(root: Path) -> tuple[Path, Path]:
    tables = root / "tables"
    figures = root / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    return tables, figures


def load_returns(quick: bool) -> pd.DataFrame:
    if quick:
        rng = np.random.default_rng(11)
        dates = pd.bdate_range("2020-01-01", periods=190)
        factors = rng.normal(0.0, 0.004, size=(len(dates), 2))
        loadings = rng.normal(0.6, 0.2, size=(2, 6))
        noise = rng.normal(0.00015, 0.006, size=(len(dates), 6))
        return pd.DataFrame(factors @ loadings + noise, index=dates, columns=[f"asset_{i}" for i in range(6)])
    return load_data(source="tushare", force_update=False).dropna(how="all")


def summarize(model: str, method: str, result: pd.DataFrame, config: dict) -> dict:
    data = result.copy()
    data["date"] = pd.to_datetime(data["date"])
    return_col = "net_return" if "net_return" in data else "portfolio_return"
    nav = (1.0 + data[return_col].fillna(0.0)).cumprod()
    nav.index = data["date"]
    metrics = calculate_metrics(nav, config.get("risk_free_rate", 0.0), trading_days=config["trading_days_per_year"])
    months = max(data["date"].dt.to_period("M").nunique(), 1)
    return {
        "model": model,
        "covariance_estimator": method,
        "start_date": data["date"].min().date().isoformat(),
        "end_date": data["date"].max().date().isoformat(),
        "observations": len(data),
        "annualized_return": metrics["annualized_return"],
        "annualized_volatility": metrics["annualized_volatility"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "calmar_ratio": metrics["calmar_ratio"],
        "cvar_95_daily_loss": cvar(data[return_col], 0.95),
        "avg_monthly_turnover": float(data.get("turnover", pd.Series(0.0, index=data.index)).fillna(0.0).sum() / months),
    }


def run_global_rrp(returns: pd.DataFrame, method: str, config: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    n_assets = len(returns.columns)
    weights = np.zeros(n_assets)
    rebalance_dates = monthly_rebalance_dates(returns)
    overlay_config = RiskOverlayConfig.from_config(config)
    cost_rate = transaction_cost_rate(overlay_config)
    rows: list[dict] = []
    diagnostics: list[dict] = []
    nav = 1.0
    high = 1.0
    risk_state = {}

    for date in returns.index:
        high = max(high, nav)
        drawdown = nav / high - 1.0
        turnover = 0.0
        if date in rebalance_dates:
            lookback = config["lookback_weeks"] * 5
            window_full = returns[returns.index < date].iloc[-lookback:]
            active_cols = investable_columns(window_full, min_observations=min(60, lookback))
            window = window_full[active_cols]
            if len(window) > 20 and len(active_cols) > 1:
                previous = weights.copy()
                cov_result = estimate_covariance(
                    window,
                    method=method,
                    trading_days=config["trading_days_per_year"],
                    annualize=True,
                    allow_fallback=True,
                    return_diagnostics=True,
                    point_in_time=True,
                )
                sigma = cov_result.covariance
                mu = window.mean() * config["trading_days_per_year"]
                theta = np.diag(np.diag(sigma))
                mu_filtered, _ = apply_trend_confirmation(mu, window, overlay_config)
                bond_indices = [i for i, col in enumerate(active_cols) if infer_asset_class(col) == "bond"]
                if bond_indices:
                    base_w, lev = optimize_with_leverage(
                        sigma.values,
                        len(active_cols),
                        bond_indices,
                        mu_filtered.values,
                        theta,
                        float(mu.mean()),
                        is_relaxed=True,
                        config=config,
                    )
                    active_weights = base_w * lev
                else:
                    active_weights = solve_relaxed_rp(sigma.values, mu_filtered.values, theta, len(active_cols), float(mu.mean()), config)
                active_weights = apply_asset_class_budget_multipliers(active_weights, active_cols, config)
                weights = expand_weights(active_weights, active_cols, returns.columns)
                weights, state = apply_risk_overlay(weights, previous, window_full, drawdown, overlay_config, risk_state)
                risk_state = state.copy()
                turnover = float(state["turnover"])
                diagnostics.append({"date": date, "model": "Global RRP", **cov_result.diagnostics})
        gross = portfolio_return_for_available(returns.loc[date], weights)
        net = gross - cost_rate * turnover
        nav *= 1.0 + net
        rows.append({"date": date, "portfolio_return": net, "gross_return": gross, "net_return": net, "turnover": turnover})
    return pd.DataFrame(rows), pd.DataFrame(diagnostics)


def convex_configs(config: dict, quick: bool) -> list[tuple[str, ConvexRRPConfig]]:
    candidates = ROOT_DIR / "results" / "tables" / "convex_adaptive_improvement_candidates.csv"
    improved_cfg = selected_improved_config(config["transaction_cost_bps"], candidates, smoke=quick)
    if quick:
        improved_cfg.lookback_days = min(improved_cfg.lookback_days, 60)
        improved_cfg.max_weight = max(improved_cfg.max_weight, 0.60)
    base_cfg = ConvexRRPConfig(
        transaction_cost_bps=config["transaction_cost_bps"],
        budget_penalty=0.55,
        lookback_days=min(improved_cfg.lookback_days, 240),
    )
    if quick:
        base_cfg.lookback_days = min(base_cfg.lookback_days, 60)
        base_cfg.max_weight = 0.60
    return [
        ("Convex Adaptive Global RRP", base_cfg),
        ("Improved Convex Adaptive Global RRP", improved_cfg),
    ]


def plot_metric(summary: pd.DataFrame, metric: str, ylabel: str, save_path: Path) -> None:
    plt.figure(figsize=(10, 5))
    for model in MODELS:
        data = summary[summary["model"].eq(model)]
        plt.plot(data["covariance_estimator"], data[metric], marker="o", label=model)
    plt.ylabel(ylabel)
    plt.xlabel("Covariance estimator")
    plt.grid(True, alpha=0.3)
    plt.xticks(rotation=20, ha="right")
    plt.legend()
    plt.tight_layout()
    plt.savefig(save_path)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run covariance-estimator robustness diagnostics.")
    parser.add_argument("--quick", action="store_true", help="Use a synthetic short sample for smoke testing.")
    parser.add_argument("--output-root", default="results", help="Output root containing tables/ and figures/.")
    args = parser.parse_args()

    output_root = Path(args.output_root)
    tables, figures = output_dirs(output_root)
    config = get_config({"transaction_cost_bps": 3.0})
    returns = load_returns(args.quick)

    summary_rows: list[dict] = []
    diagnostics: list[pd.DataFrame] = []
    for method in METHODS:
        print(f"Running covariance method: {method}")
        global_result, global_diag = run_global_rrp(returns, method, config)
        summary_rows.append(summarize("Global RRP", method, global_result, config))
        if not global_diag.empty:
            global_diag["covariance_estimator"] = method
            diagnostics.append(global_diag)

        for model, cfg in convex_configs(config, args.quick):
            cfg = ConvexRRPConfig(**{**cfg.__dict__, "covariance_method": method, "covariance_allow_fallback": True})
            result, solver_diag, _, _ = run_convex_adaptive_backtest(returns, cfg)
            summary_rows.append(summarize(model, method, result, config))
            if not solver_diag.empty:
                solver_diag = solver_diag.copy()
                solver_diag.insert(0, "model", model)
                solver_diag["covariance_estimator"] = method
                diagnostics.append(solver_diag)

    summary = pd.DataFrame(summary_rows)
    diag = pd.concat(diagnostics, ignore_index=True) if diagnostics else pd.DataFrame()
    summary.to_csv(tables / "covariance_robustness_summary.csv", index=False)
    diag.to_csv(tables / "covariance_estimator_diagnostics.csv", index=False)

    plot_metric(summary, "sharpe_ratio", "Sharpe ratio", figures / "covariance_robustness_sharpe.png")
    plot_metric(summary, "max_drawdown", "Max drawdown", figures / "covariance_robustness_drawdown.png")
    plot_metric(summary, "avg_monthly_turnover", "Average monthly turnover", figures / "covariance_robustness_turnover.png")

    print("Covariance robustness outputs written.")


if __name__ == "__main__":
    main()
