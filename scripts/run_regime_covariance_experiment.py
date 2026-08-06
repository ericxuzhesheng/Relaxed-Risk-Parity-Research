from __future__ import annotations

"""Regime-conditional covariance A/B experiment with a state-prior sweep.

Motivation
----------
Classic risk parity estimates a single *unconditional* covariance from a
trailing window, pooling calm and crisis days into one distribution. This
under-weights the tail co-movement that only appears in stress regimes. The
``regime_conditional`` estimator (see ``src/covariance_estimators.py``) instead
splits the window into calm/stress buckets, estimates a within-regime
covariance for each, and recombines them with a state-frequency prior that
over-weights the stress regime.

This script feeds that estimator into the Convex Adaptive RRP and the *exact*
Improved Convex Adaptive RRP configuration used for the headline performance
table (reconstructed from the selected improvement candidate, so the
volatility-target overlay is preserved and absolute numbers align with the
README dashboard). It then:

1. A/B tests the standard EWMA covariance against the regime-conditional
   estimator at its default prior, over the full 2019-01-01..end window plus
   three China-market stress sub-periods; and
2. sweeps the state-frequency prior (``regime_crisis_prior`` x
   ``regime_prior_weight``) to check whether a stronger stress tilt changes
   the picture.

It is an additive research diagnostic: it does not change any headline model or
the primary performance summary.
"""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_convex_adaptive_rrp import candidate_configurations, cvar, summarize_result
from src.convex_adaptive_rrp import ConvexRRPConfig, run_convex_adaptive_backtest
from src.data_loader import load_data
from src.utils import get_config, resolve_path


# China-market stress windows inside the 2019-01-01.. evaluation period.
STRESS_PERIODS: dict[str, tuple[str, str]] = {
    "covid_2020Q1": ("2020-01-20", "2020-04-30"),
    "selloff_2022": ("2022-01-01", "2022-10-31"),
    "ashare_bottom_2024": ("2024-01-01", "2024-02-09"),
}

# State-frequency prior grid for the sweep (crisis_prior, prior_weight).
PRIOR_GRID: list[tuple[float, float]] = [
    (0.40, 0.50),  # default (mild tilt: empirical ~0.33 -> ~0.365)
    (0.50, 0.50),
    (0.50, 0.75),
    (0.60, 0.75),
    (0.67, 1.00),  # aggressive: ignore empirical, force two-thirds stress weight
]


def subperiod_metrics(result: pd.DataFrame, start: str, end: str, trading_days: int) -> dict:
    data = result.copy()
    data["date"] = pd.to_datetime(data["date"])
    return_col = "net_return" if "net_return" in data else "portfolio_return"
    window = data[(data["date"] >= pd.Timestamp(start)) & (data["date"] <= pd.Timestamp(end))]
    if window.empty:
        return {"cumulative_return": np.nan, "max_drawdown": np.nan, "annualized_volatility": np.nan, "cvar_95_daily_loss": np.nan}
    rets = window[return_col].fillna(0.0)
    nav = (1.0 + rets).cumprod()
    drawdown = float((nav / nav.cummax() - 1.0).min())
    return {
        "cumulative_return": float(nav.iloc[-1] - 1.0),
        "max_drawdown": drawdown,
        "annualized_volatility": float(rets.std() * np.sqrt(trading_days)),
        "cvar_95_daily_loss": cvar(rets, 0.95),
    }


def selected_full_improved_config(transaction_cost_bps: float) -> ConvexRRPConfig:
    """Reconstruct the *exact* headline Improved config (vol-target preserved).

    ``selected_improved_config`` in run_robustness_tests rebuilds a partial
    config from the candidates CSV and drops the volatility-target overlay,
    which detaches its absolute numbers from the README dashboard. Here we
    instead match the selected candidate id back to ``candidate_configurations``
    so the full ConvexRRPConfig (including vol_target_enabled/vol_target) is
    used, keeping the A/B anchored to the published 1.43-Sharpe model.
    """
    candidates_path = ROOT_DIR / "results" / "tables" / "convex_adaptive_improvement_candidates.csv"
    candidates = pd.read_csv(candidates_path)
    selected = candidates[candidates["selected"].astype(str).str.lower().eq("true")]
    if selected.empty:
        raise ValueError(f"No selected improved row found in {candidates_path}")
    selected_name = str(selected.iloc[0]["candidate_name"])
    for name, cfg in candidate_configurations(transaction_cost_bps):
        if name == selected_name:
            return cfg
    raise ValueError(f"Selected candidate {selected_name} not found in candidate_configurations")


def model_configs(transaction_cost_bps: float, smoke: bool) -> list[tuple[str, ConvexRRPConfig]]:
    base = ConvexRRPConfig(transaction_cost_bps=transaction_cost_bps, budget_penalty=0.55)
    if smoke:
        base.lookback_days = min(base.lookback_days, 80)
        base.max_weight = max(base.max_weight, 0.60)
        improved = replace(base)
        return [("Convex Adaptive Global RRP", base), ("Improved Convex Adaptive Global RRP", improved)]
    improved = selected_full_improved_config(transaction_cost_bps)
    return [("Convex Adaptive Global RRP", base), ("Improved Convex Adaptive Global RRP", improved)]


def with_overrides(cfg: ConvexRRPConfig, **overrides) -> ConvexRRPConfig:
    params = {**cfg.__dict__, **overrides, "covariance_allow_fallback": True}
    return ConvexRRPConfig(**params)


def load_returns(quick: bool, cutoff: str) -> pd.DataFrame:
    if quick:
        rng = np.random.default_rng(7)
        dates = pd.bdate_range("2019-01-01", periods=320)
        base = rng.normal(0.0003, 0.006, size=(len(dates), 6))
        base[120:150] += rng.normal(0.0, 0.02, size=(30, 6))
        return pd.DataFrame(base, index=dates, columns=[f"asset_{i}" for i in range(6)])
    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    return returns[pd.to_datetime(returns.index) <= pd.Timestamp(cutoff)]


def evaluate(model_name: str, setting: str, result: pd.DataFrame, eval_start: str, config: dict) -> tuple[dict, list[dict]]:
    metrics = summarize_result(model_name, result, eval_start, config)
    summary = {"model": model_name, "covariance_setting": setting, **{k: v for k, v in metrics.items() if k != "model"}}
    stress = []
    for period_name, (start, end) in STRESS_PERIODS.items():
        sub = subperiod_metrics(result, start, end, config["trading_days_per_year"])
        stress.append({"model": model_name, "covariance_setting": setting, "period": period_name, "start": start, "end": end, **sub})
    return summary, stress


def main() -> None:
    parser = argparse.ArgumentParser(description="Regime-conditional covariance A/B + prior sweep.")
    parser.add_argument("--quick", action="store_true", help="Use a synthetic short sample for smoke testing.")
    parser.add_argument("--cutoff", default="2026-07-31", help="Inclusive end date for the return sample.")
    parser.add_argument("--output-root", default="results", help="Output root containing tables/.")
    args = parser.parse_args()

    config = get_config({"transaction_cost_bps": 3.0})
    eval_start = config.get("plot_start_date", "2019-01-01")
    returns = load_returns(args.quick, args.cutoff)
    print(f"Sample: {returns.index.min().date()} .. {returns.index.max().date()} ({len(returns)} rows, {returns.shape[1]} assets)")

    summary_rows: list[dict] = []
    stress_rows: list[dict] = []
    sweep_rows: list[dict] = []

    for model_name, cfg in model_configs(config["transaction_cost_bps"], args.quick):
        baseline_method = cfg.covariance_method
        # Arm A: standard covariance (EWMA) — the published setting.
        print(f"Running {model_name} | baseline ({baseline_method})...")
        result, _, _, _ = run_convex_adaptive_backtest(returns, with_overrides(cfg, covariance_method=baseline_method))
        s, st = evaluate(model_name, "baseline_ewma", result, eval_start, config)
        summary_rows.append(s)
        stress_rows.extend(st)

        # Arm B: regime-conditional covariance at the default prior.
        print(f"Running {model_name} | regime_conditional (default prior)...")
        result, _, _, _ = run_convex_adaptive_backtest(returns, with_overrides(cfg, covariance_method="regime_conditional"))
        s, st = evaluate(model_name, "regime_conditional", result, eval_start, config)
        summary_rows.append(s)
        stress_rows.extend(st)

        # Sweep: state-frequency prior grid (regime_conditional only).
        for crisis_prior, prior_weight in PRIOR_GRID:
            print(f"Sweeping {model_name} | crisis_prior={crisis_prior} prior_weight={prior_weight}...")
            run_cfg = with_overrides(
                cfg,
                covariance_method="regime_conditional",
                regime_crisis_prior=crisis_prior,
                regime_prior_weight=prior_weight,
            )
            result, _, _, _ = run_convex_adaptive_backtest(returns, run_cfg)
            metrics = summarize_result(model_name, result, eval_start, config)
            covid = subperiod_metrics(result, *STRESS_PERIODS["covid_2020Q1"], config["trading_days_per_year"])
            selloff = subperiod_metrics(result, *STRESS_PERIODS["selloff_2022"], config["trading_days_per_year"])
            sweep_rows.append({
                "model": model_name,
                "crisis_prior": crisis_prior,
                "prior_weight": prior_weight,
                "net_annual_return": metrics["net_annual_return"],
                "annualized_volatility": metrics["annualized_volatility"],
                "sharpe_ratio": metrics["sharpe_ratio"],
                "max_drawdown": metrics["max_drawdown"],
                "calmar_ratio": metrics["calmar_ratio"],
                "avg_monthly_turnover": metrics["avg_monthly_turnover"],
                "cvar_95_daily_loss": metrics["cvar_95_daily_loss"],
                "covid_2020Q1_max_drawdown": covid["max_drawdown"],
                "selloff_2022_max_drawdown": selloff["max_drawdown"],
            })

    summary = pd.DataFrame(summary_rows)
    stress = pd.DataFrame(stress_rows)
    sweep = pd.DataFrame(sweep_rows)
    tables = Path(args.output_root) / "tables"
    tables.mkdir(parents=True, exist_ok=True)
    summary.to_csv(tables / "regime_covariance_experiment_summary.csv", index=False)
    stress.to_csv(tables / "regime_covariance_experiment_stress.csv", index=False)
    sweep.to_csv(tables / "regime_covariance_experiment_sweep.csv", index=False)

    show_cols = ["model", "covariance_setting", "net_annual_return", "annualized_volatility", "sharpe_ratio", "max_drawdown", "calmar_ratio", "avg_monthly_turnover", "cvar_95_daily_loss"]
    print("\n=== Full-period A/B (eval start {}) ===".format(eval_start))
    print(summary[show_cols].to_string(index=False))
    print("\n=== Stress sub-period max drawdown ===")
    print(stress.pivot_table(index=["model", "period"], columns="covariance_setting", values="max_drawdown").to_string())
    print("\n=== State-frequency prior sweep ===")
    sweep_cols = ["model", "crisis_prior", "prior_weight", "sharpe_ratio", "max_drawdown", "covid_2020Q1_max_drawdown", "selloff_2022_max_drawdown", "avg_monthly_turnover"]
    print(sweep[sweep_cols].to_string(index=False))
    print("\nOutputs written to", tables)


if __name__ == "__main__":
    main()
