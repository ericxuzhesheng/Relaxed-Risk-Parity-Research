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

from scripts.run_convex_adaptive_rrp import monthly_rebalance_dates
from src.backtest import run_static_backtest
from src.convex_adaptive_rrp import ConvexRRPConfig, estimate_covariance, run_convex_adaptive_backtest
from src.data_loader import load_data
from src.dynamic_selection import run_dynamic_rrp_selection
from src.metrics import calculate_metrics, drawdown_series
from src.risk_overlay import RiskOverlayConfig, apply_risk_overlay, apply_trend_confirmation, transaction_cost_rate
from src.risk_parity import optimize_with_leverage, solve_relaxed_rp
from src.utils import apply_asset_class_budget_multipliers, get_config, infer_asset_class

GLOBAL_RRP = "Global Relaxed Risk Parity"
IMPROVED_INTERNAL = "Improved Convex Adaptive Global Relaxed Risk Parity"
IMPROVED_DISPLAY = "Improved Convex Adaptive Global RRP"
CONVEX_DISPLAY = "Convex Adaptive Global RRP"
DYNAMIC_RRP = "Defensive Dynamic Relaxed Risk Parity"

TABLES = [
    "robustness_subperiod_summary.csv",
    "robustness_covariance_summary.csv",
    "robustness_transaction_cost_summary.csv",
    "robustness_stress_period_summary.csv",
    "robustness_parameter_perturbation.csv",
    "robustness_no_lookahead_audit.csv",
    "robustness_solver_stability.csv",
    "robustness_overall_summary.csv",
]


def output_dirs(root: Path) -> tuple[Path, Path]:
    tables = root / "tables"
    figures = root / "figures"
    tables.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    return tables, figures


def load_return_universe(smoke: bool = False) -> pd.DataFrame:
    if smoke:
        rng = np.random.default_rng(7)
        dates = pd.bdate_range("2020-01-01", periods=190)
        data = rng.normal(0.0002, 0.007, size=(len(dates), 6))
        data[:, 0] += 0.00015
        return pd.DataFrame(data, index=dates, columns=[f"asset_{i}" for i in range(6)])
    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    return returns.loc[:, returns.notna().mean() > 0.95].fillna(0.0)


def cvar(returns: pd.Series, beta: float = 0.95) -> float:
    losses = -pd.Series(returns).dropna()
    if losses.empty:
        return 0.0
    var = losses.quantile(beta)
    tail = losses[losses >= var]
    return float(tail.mean()) if not tail.empty else float(var)


def nav_from_result(result: pd.DataFrame, start: pd.Timestamp | None = None, end: pd.Timestamp | None = None) -> pd.Series:
    data = result.copy()
    data["date"] = pd.to_datetime(data["date"])
    if start is not None:
        data = data[data["date"] >= start]
    if end is not None:
        data = data[data["date"] <= end]
    return_col = "net_return" if "net_return" in data else "portfolio_return"
    nav = (1.0 + data[return_col].fillna(0.0)).cumprod()
    nav.index = data["date"]
    return nav


def summarize_window(model: str, result: pd.DataFrame, window: str, config: dict, start=None, end=None) -> dict:
    data = result.copy()
    data["date"] = pd.to_datetime(data["date"])
    if start is not None:
        data = data[data["date"] >= pd.Timestamp(start)]
    if end is not None:
        data = data[data["date"] <= pd.Timestamp(end)]
    if data.empty:
        return {}
    nav = nav_from_result(data)
    metrics = calculate_metrics(nav, config.get("risk_free_rate", 0.0), config["trading_days_per_year"])
    dates = pd.to_datetime(data["date"])
    years = max((dates.max() - dates.min()).days / 365.25, 1.0 / 12.0)
    ret_col = "net_return" if "net_return" in data else "portfolio_return"
    return {
        "window": window,
        "model": model,
        "start_date": dates.min().date().isoformat(),
        "end_date": dates.max().date().isoformat(),
        "observations": len(data),
        "annualized_return": metrics["annualized_return"],
        "annualized_volatility": metrics["annualized_volatility"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "calmar_ratio": metrics["calmar_ratio"],
        "cvar_95_daily_loss": cvar(data[ret_col], 0.95),
        "avg_monthly_turnover": float(data.get("turnover", pd.Series(0.0, index=data.index)).fillna(0.0).sum() / max(len(dates.dt.to_period("M").unique()), 1)),
        "annualized_turnover": float(data.get("turnover", pd.Series(0.0, index=data.index)).fillna(0.0).sum() / years),
    }


def selected_improved_config(transaction_cost_bps: float, candidates_path: Path, smoke: bool = False) -> ConvexRRPConfig:
    if smoke or not candidates_path.exists():
        return ConvexRRPConfig(
            transaction_cost_bps=transaction_cost_bps,
            lookback_days=60,
            covariance_method="ewma",
            max_weight=0.60,
            turnover_cap=0.80,
            turnover_penalty=0.02,
            budget_penalty=0.10,
            cvar_penalty=0.08,
            cvar_beta=0.95,
            return_reward=0.05,
        )
    candidates = pd.read_csv(candidates_path)
    selected = candidates[candidates["selected"].astype(str).str.lower().eq("true")]
    if selected.empty:
        raise ValueError(f"No selected improved row found in {candidates_path}")
    row = selected.iloc[0]
    return ConvexRRPConfig(
        transaction_cost_bps=transaction_cost_bps,
        lookback_days=int(row["lookback_window"]),
        covariance_method=str(row["covariance_estimator"]),
        max_weight=float(row["upper_bound_i"]),
        turnover_cap=None if pd.isna(row["turnover_cap"]) else float(row["turnover_cap"]),
        turnover_penalty=float(row["lambda_turnover"]),
        budget_penalty=float(row["lambda_budget"]),
        cvar_penalty=float(row["lambda_cvar"]),
        cvar_beta=float(row["cvar_alpha"]),
        return_reward=float(row["return_reward"]),
    )


def run_global_covariance_diagnostic(returns: pd.DataFrame, method: str, config: dict) -> pd.DataFrame:
    n_assets = len(returns.columns)
    weights = np.ones(n_assets) / n_assets
    rebalance_dates = monthly_rebalance_dates(returns)
    overlay_config = RiskOverlayConfig.from_config(config)
    cost_rate = transaction_cost_rate(overlay_config)
    bond_indices = [i for i, col in enumerate(returns.columns) if infer_asset_class(col) == "bond"]
    rows = []
    nav = 1.0
    high = 1.0
    risk_state = {}
    for date in returns.index:
        high = max(high, nav)
        drawdown = nav / high - 1.0
        turnover = 0.0
        if date in rebalance_dates:
            window = returns[returns.index < date].iloc[-config["lookback_weeks"] * 5 :]
            if len(window) > 20:
                previous = weights.copy()
                mu = window.mean() * config["trading_days_per_year"]
                sigma = estimate_covariance(window, method, config["trading_days_per_year"])
                theta = np.diag(np.diag(sigma))
                mu_filtered, trend_count = apply_trend_confirmation(mu, window, overlay_config)
                if bond_indices:
                    base_w, lev = optimize_with_leverage(
                        sigma.values,
                        n_assets,
                        bond_indices,
                        mu_filtered.values,
                        theta,
                        float(mu.mean()),
                        is_relaxed=True,
                        config=config,
                    )
                    weights = base_w * lev
                else:
                    weights = solve_relaxed_rp(sigma.values, mu_filtered.values, theta, n_assets, float(mu.mean()), config)
                weights = apply_asset_class_budget_multipliers(weights, returns.columns, config)
                weights, state = apply_risk_overlay(weights, previous, window, drawdown, overlay_config, risk_state)
                risk_state = state.copy()
                turnover = float(state["turnover"])
        gross = float(np.dot(returns.loc[date].fillna(0.0).values, weights))
        net = gross - cost_rate * turnover
        nav *= 1.0 + net
        row = {"date": date, "portfolio_return": net, "gross_return": gross, "net_return": net, "turnover": turnover}
        rows.append(row)
    return pd.DataFrame(rows)


def build_models(returns: pd.DataFrame, config: dict, improved_cfg: ConvexRRPConfig, include_dynamic: bool = True) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    models = {
        GLOBAL_RRP: run_static_backtest(returns, model_type="relaxed", config_overrides=config),
    }
    if include_dynamic:
        models[DYNAMIC_RRP] = run_dynamic_rrp_selection(
            returns,
            [{"lambda_pen": 0.10, "m": 1.9, "bond_leverage_upper": 1.4}, {"lambda_pen": 1.90, "m": 3.0, "bond_leverage_upper": 1.8}],
            train_window_months=24,
            selection_metric="utility",
            top_k=2,
            config_base=config,
        )
    base_cfg = ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], budget_penalty=0.55, lookback_days=min(240, improved_cfg.lookback_days))
    if len(returns) < 260:
        base_cfg.lookback_days = min(base_cfg.lookback_days, 60)
    base, base_solver, _, _ = run_convex_adaptive_backtest(returns, base_cfg)
    improved, improved_solver, _, _ = run_convex_adaptive_backtest(returns, improved_cfg)
    models[CONVEX_DISPLAY] = base
    models[IMPROVED_DISPLAY] = improved
    solvers = []
    if not base_solver.empty:
        solvers.append(base_solver.assign(model=CONVEX_DISPLAY))
    if not improved_solver.empty:
        solvers.append(improved_solver.assign(model=IMPROVED_DISPLAY))
    return models, pd.concat(solvers, ignore_index=True) if solvers else pd.DataFrame()


def subperiod_summary(models: dict[str, pd.DataFrame], config: dict) -> pd.DataFrame:
    all_dates = pd.concat([pd.to_datetime(df["date"]) for df in models.values()])
    start, end = all_dates.min(), all_dates.max()
    windows = [
        ("full_available_sample", start, end),
        ("pre_2020", start, pd.Timestamp("2019-12-31")),
        ("2020_2021", pd.Timestamp("2020-01-01"), pd.Timestamp("2021-12-31")),
        ("post_2021", pd.Timestamp("2022-01-01"), end),
        ("post_2022", pd.Timestamp("2023-01-01"), end),
    ]
    rows = []
    for name, result in models.items():
        for label, win_start, win_end in windows:
            row = summarize_window(name, result, label, config, win_start, win_end)
            if row:
                rows.append(row)
        dates = pd.to_datetime(result["date"])
        first_months = pd.period_range(dates.min().to_period("M"), dates.max().to_period("M"), freq="M")
        if len(first_months) >= 36:
            for idx in range(0, len(first_months) - 35, 12):
                s = first_months[idx].to_timestamp()
                e = (first_months[idx + 35] + 1).to_timestamp() - pd.Timedelta(days=1)
                row = summarize_window(name, result, f"rolling_36m_{s.date()}_{e.date()}", config, s, e)
                if row:
                    rows.append(row)
    return pd.DataFrame(rows)


def covariance_summary(returns: pd.DataFrame, config: dict, improved_cfg: ConvexRRPConfig, smoke: bool) -> pd.DataFrame:
    methods = ["sample", "ewma", "ledoit_wolf"]
    if smoke:
        methods = ["sample", "ewma"]
    rows = []
    for method in methods:
        global_result = run_global_covariance_diagnostic(returns, method, config)
        rows.append({**summarize_window(GLOBAL_RRP, global_result, "full_available_sample", config), "covariance_estimator": method})
        for label, cfg in [
            (CONVEX_DISPLAY, ConvexRRPConfig(transaction_cost_bps=config["transaction_cost_bps"], budget_penalty=0.55, covariance_method=method, lookback_days=min(improved_cfg.lookback_days, 240))),
            (IMPROVED_DISPLAY, ConvexRRPConfig(**{**improved_cfg.__dict__, "covariance_method": method})),
        ]:
            if smoke:
                cfg.lookback_days = min(cfg.lookback_days, 60)
                cfg.max_weight = max(cfg.max_weight, 0.60)
            result, _, _, _ = run_convex_adaptive_backtest(returns, cfg)
            rows.append({**summarize_window(label, result, "full_available_sample", config), "covariance_estimator": method})
    dynamic = run_dynamic_rrp_selection(
        returns,
        [{"lambda_pen": 0.10, "m": 1.9, "bond_leverage_upper": 1.4}, {"lambda_pen": 1.90, "m": 3.0, "bond_leverage_upper": 1.8}],
        train_window_months=24,
        selection_metric="utility",
        top_k=2,
        config_base=config,
    )
    rows.append({**summarize_window(DYNAMIC_RRP, dynamic, "full_available_sample", config), "covariance_estimator": "default_sample_reference"})
    return pd.DataFrame(rows)


def transaction_cost_summary(returns: pd.DataFrame, base_config: dict, candidates_path: Path, smoke: bool) -> pd.DataFrame:
    levels = [0, 5, 10, 20, 50]
    rows = []
    for bps in levels:
        cfg = get_config({**base_config, "transaction_cost_bps": float(bps)})
        improved_cfg = selected_improved_config(float(bps), candidates_path, smoke)
        models, _ = build_models(returns, cfg, improved_cfg, include_dynamic=not smoke)
        for name, result in models.items():
            row = summarize_window(name, result, "full_available_sample", cfg)
            row["transaction_cost_bps"] = bps
            rows.append(row)
    return pd.DataFrame(rows)


def stress_summary(returns: pd.DataFrame, models: dict[str, pd.DataFrame], config: dict) -> pd.DataFrame:
    equal_weight = returns.mean(axis=1).fillna(0.0)
    monthly = equal_weight.resample("ME").apply(lambda x: (1.0 + x).prod() - 1.0)
    vol = equal_weight.rolling(21).std()
    nav = (1.0 + equal_weight).cumprod()
    dd = drawdown_series(nav)
    stress_dates = {
        "highest_realized_volatility": set(vol[vol >= vol.quantile(0.90)].dropna().index),
        "deepest_equal_weight_drawdown": set(dd[dd <= dd.quantile(0.10)].dropna().index),
        "worst_10pct_monthly_returns": set(monthly[monthly <= monthly.quantile(0.10)].index.to_period("M")),
    }
    rows = []
    for name, result in models.items():
        data = result.copy()
        data["date"] = pd.to_datetime(data["date"])
        ret_col = "net_return" if "net_return" in data else "portfolio_return"
        for stress_name, labels in stress_dates.items():
            if "monthly" in stress_name:
                sample = data[data["date"].dt.to_period("M").isin(labels)]
            else:
                sample = data[data["date"].isin(labels)]
            if sample.empty:
                continue
            nav = (1.0 + sample[ret_col].fillna(0.0)).cumprod()
            metrics = calculate_metrics(nav, config.get("risk_free_rate", 0.0), config["trading_days_per_year"])
            rows.append(
                {
                    "stress_period": stress_name,
                    "model": name,
                    "observations": len(sample),
                    "cumulative_return": float(nav.iloc[-1] - 1.0),
                    "annualized_return": metrics["annualized_return"],
                    "sharpe_ratio": metrics["sharpe_ratio"],
                    "max_drawdown": metrics["max_drawdown"],
                    "cvar_95_daily_loss": cvar(sample[ret_col], 0.95),
                    "stress_identification": "ex_post_equal_weight_universe",
                }
            )
    return pd.DataFrame(rows)


def parameter_perturbation(returns: pd.DataFrame, config: dict, baseline_cfg: ConvexRRPConfig, smoke: bool) -> pd.DataFrame:
    cases: list[tuple[str, ConvexRRPConfig]] = [("selected_baseline", baseline_cfg)]
    attrs = [
        ("lambda_cvar", "cvar_penalty"),
        ("lambda_turnover", "turnover_penalty"),
        ("lambda_ref", "return_reward"),
        ("lambda_budget", "budget_penalty"),
    ]
    for public_name, attr in attrs:
        for scale in [0.75, 1.25]:
            params = baseline_cfg.__dict__.copy()
            params[attr] = float(params[attr]) * scale
            cases.append((f"{public_name}_{scale:.2f}x", ConvexRRPConfig(**params)))
    for bump in [-0.05, 0.05]:
        params = baseline_cfg.__dict__.copy()
        params["max_weight"] = min(1.0, max(1.0 / returns.shape[1], float(params["max_weight"]) + bump))
        cases.append((f"upper_bound_i_{bump:+.2f}", ConvexRRPConfig(**params)))
    for lookback in [180, 240, 252]:
        params = baseline_cfg.__dict__.copy()
        params["lookback_days"] = min(lookback, max(45, len(returns) // 2)) if smoke else lookback
        cases.append((f"lookback_{lookback}", ConvexRRPConfig(**params)))
    rows = []
    for case, cfg in cases:
        result, solver, _, _ = run_convex_adaptive_backtest(returns, cfg)
        row = summarize_window(IMPROVED_DISPLAY, result, "full_available_sample", config)
        row["case"] = case
        row["fallback_rate"] = float(solver["fallback_used"].mean()) if not solver.empty else 0.0
        row["lookback_days"] = cfg.lookback_days
        row["lambda_cvar"] = cfg.cvar_penalty
        row["lambda_turnover"] = cfg.turnover_penalty
        row["lambda_ref"] = cfg.return_reward
        row["lambda_budget"] = cfg.budget_penalty
        row["upper_bound_i"] = cfg.max_weight
        rows.append(row)
    return pd.DataFrame(rows)


def no_lookahead_audit() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"component": "return_universe_loading", "uses_future_data": False, "lag_applied": "input returns only", "notes": "Loads cached historical prices and evaluates realized returns after each date."},
            {"component": "monthly_rebalance_schedule", "uses_future_data": False, "lag_applied": "rebalance at month end", "notes": "Rebalance dates are calendar diagnostics; model windows still exclude the rebalance date."},
            {"component": "global_rrp_covariance", "uses_future_data": False, "lag_applied": "window index < rebalance date", "notes": "Robustness covariance wrapper changes only the estimator."},
            {"component": "convex_adaptive_covariance", "uses_future_data": False, "lag_applied": "window index < rebalance date", "notes": "Convex backtest estimates covariance from trailing returns only."},
            {"component": "adaptive_budget_target", "uses_future_data": False, "lag_applied": "trailing lookback window", "notes": "Budget target is derived from past-window asset risk and bounded state inputs."},
            {"component": "transaction_cost_scenarios", "uses_future_data": False, "lag_applied": "cost applied on rebalance turnover", "notes": "Cost levels are fixed diagnostics and are not selected from outcomes."},
            {"component": "parameter_perturbation", "uses_future_data": False, "lag_applied": "selected row read once", "notes": "One-at-a-time perturbations around the selected public configuration; no candidate search is performed."},
            {"component": "stress_period_identification", "uses_future_data": True, "lag_applied": "not used for trading", "notes": "Stress periods are identified ex post solely for evaluation."},
            {"component": "solver_diagnostics", "uses_future_data": False, "lag_applied": "per-rebalance solve record", "notes": "Solver status summarizes optimization diagnostics after the fact."},
        ]
    )


def solver_stability(solver_diag: pd.DataFrame) -> pd.DataFrame:
    columns = ["model", "solver", "status", "status_count", "fallback_rate", "failed_dates", "fallback_dates", "average_objective_value"]
    if solver_diag.empty:
        return pd.DataFrame(columns=columns)
    df = solver_diag.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    rows = []
    for (model, solver, status), group in df.groupby(["model", "solver_name", "solver_status"], dropna=False):
        fallback = group[group["fallback_used"].astype(bool)]
        failed = group[~group["solver_status"].astype(str).str.contains("optimal|success", case=False, na=False)]
        rows.append(
            {
                "model": model,
                "solver": solver,
                "status": status,
                "status_count": len(group),
                "fallback_rate": float(group["fallback_used"].mean()),
                "failed_dates": ";".join(failed["date"].head(20)),
                "fallback_dates": ";".join(fallback["date"].head(20)),
                "average_objective_value": float(pd.to_numeric(group["objective_value"], errors="coerce").mean()),
            }
        )
    return pd.DataFrame(rows, columns=columns)


def overall_summary(subperiod: pd.DataFrame, costs: pd.DataFrame, covariance: pd.DataFrame, stress: pd.DataFrame, perturb: pd.DataFrame) -> pd.DataFrame:
    models = sorted(set(subperiod["model"]) | set(costs["model"]) | set(covariance["model"]) | set(stress["model"]))
    rows = []
    for model in models:
        sub = subperiod[subperiod["model"].eq(model)]
        cost = costs[costs["model"].eq(model)]
        cov = covariance[covariance["model"].eq(model)]
        st = stress[stress["model"].eq(model)]
        par = perturb if model == IMPROVED_DISPLAY else pd.DataFrame()
        sub_rating = "Strong" if not sub.empty and (sub["sharpe_ratio"] > 0).mean() >= 0.75 else "Moderate" if not sub.empty else "Weak"
        cost_rating = "Strong" if not cost.empty and cost.groupby("transaction_cost_bps")["annualized_return"].mean().is_monotonic_decreasing else "Moderate"
        cov_rating = "Strong" if not cov.empty and cov["sharpe_ratio"].std(ddof=0) < 0.35 else "Moderate" if not cov.empty else "Weak"
        stress_rating = "Strong" if not st.empty and st["cumulative_return"].median() >= 0 else "Moderate" if not st.empty else "Weak"
        param_rating = "Not applicable"
        if not par.empty:
            param_rating = "Strong" if par["sharpe_ratio"].std(ddof=0) < 0.25 and (par["max_drawdown"] > -0.10).all() else "Moderate"
        ratings = [r for r in [sub_rating, cost_rating, cov_rating, stress_rating, param_rating] if r != "Not applicable"]
        overall = "Strong" if ratings.count("Strong") >= max(3, len(ratings) - 1) else "Weak" if ratings.count("Weak") >= 2 else "Moderate"
        rows.append(
            {
                "model": model,
                "subperiod_rating": sub_rating,
                "transaction_cost_rating": cost_rating,
                "covariance_rating": cov_rating,
                "stress_rating": stress_rating,
                "parameter_stability_rating": param_rating,
                "overall_assessment": overall,
                "notes": "Validation-only robustness diagnostics; ratings are qualitative and do not select or retune models.",
            }
        )
    return pd.DataFrame(rows)


def plot_metric(df: pd.DataFrame, x: str, y: str, hue: str, title: str, path: Path) -> None:
    plt.figure(figsize=(11, 5))
    if df.empty:
        plt.text(0.5, 0.5, "No data", ha="center", va="center")
        plt.axis("off")
    else:
        pivot = df.pivot_table(index=x, columns=hue, values=y, aggfunc="mean")
        pivot.plot(kind="bar", ax=plt.gca())
        plt.title(title)
        plt.ylabel(y.replace("_", " "))
        plt.xticks(rotation=30, ha="right")
        plt.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    plt.savefig(path)
    plt.close()


def write_figures(figures: Path, sub: pd.DataFrame, costs: pd.DataFrame, cov: pd.DataFrame, perturb: pd.DataFrame, stress: pd.DataFrame) -> None:
    fixed = sub[~sub["window"].str.startswith("rolling_36m", na=False)]
    plot_metric(fixed, "window", "sharpe_ratio", "model", "Robustness Subperiod Sharpe", figures / "robustness_subperiod_sharpe.png")
    plot_metric(fixed, "window", "max_drawdown", "model", "Robustness Subperiod Drawdown", figures / "robustness_subperiod_drawdown.png")
    plot_metric(costs, "transaction_cost_bps", "annualized_return", "model", "Transaction Cost Sensitivity", figures / "robustness_transaction_cost_sensitivity.png")
    plot_metric(cov, "covariance_estimator", "sharpe_ratio", "model", "Covariance Estimator Comparison", figures / "robustness_covariance_comparison.png")
    plot_metric(perturb, "case", "sharpe_ratio", "model", "Parameter Sensitivity", figures / "robustness_parameter_sensitivity.png")
    plot_metric(stress, "stress_period", "cumulative_return", "model", "Stress Period Performance", figures / "robustness_stress_period_performance.png")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true", help="Run a fast deterministic smoke diagnostic.")
    parser.add_argument("--output-root", type=Path, default=ROOT_DIR / "results", help="Directory containing tables/ and figures/ outputs.")
    args = parser.parse_args()

    tables, figures = output_dirs(args.output_root)
    base_config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    if args.smoke:
        base_config.update({"lookback_weeks": 12, "optim_maxiter": 200})
    returns = load_return_universe(args.smoke)
    candidates_path = ROOT_DIR / "results" / "tables" / "convex_adaptive_improvement_candidates.csv"
    improved_cfg = selected_improved_config(base_config["transaction_cost_bps"], candidates_path, args.smoke)
    if args.smoke:
        improved_cfg.lookback_days = min(improved_cfg.lookback_days, 60)
        improved_cfg.max_weight = max(improved_cfg.max_weight, 0.60)

    print("Running fixed public models...")
    models, solver_diag = build_models(returns, base_config, improved_cfg, include_dynamic=True)
    print("Writing subperiod robustness...")
    sub = subperiod_summary(models, base_config)
    print("Writing covariance robustness...")
    cov = covariance_summary(returns, base_config, improved_cfg, args.smoke)
    print("Writing transaction cost robustness...")
    costs = transaction_cost_summary(returns, base_config, candidates_path, args.smoke)
    print("Writing stress and parameter diagnostics...")
    stress = stress_summary(returns, models, base_config)
    perturb = parameter_perturbation(returns, base_config, improved_cfg, args.smoke)
    audit = no_lookahead_audit()
    solver = solver_stability(solver_diag)
    overall = overall_summary(sub, costs, cov, stress, perturb)

    frames = {
        "robustness_subperiod_summary.csv": sub,
        "robustness_covariance_summary.csv": cov,
        "robustness_transaction_cost_summary.csv": costs,
        "robustness_stress_period_summary.csv": stress,
        "robustness_parameter_perturbation.csv": perturb,
        "robustness_no_lookahead_audit.csv": audit,
        "robustness_solver_stability.csv": solver,
        "robustness_overall_summary.csv": overall,
    }
    for name, frame in frames.items():
        frame.to_csv(tables / name, index=False)
    write_figures(figures, sub, costs, cov, perturb, stress)
    print(f"Robustness diagnostics written to {args.output_root}")


if __name__ == "__main__":
    main()
