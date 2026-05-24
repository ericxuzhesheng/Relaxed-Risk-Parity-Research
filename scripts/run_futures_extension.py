"""Futures extension experiment — Bridgewater-style comparison.

Runs three scenarios and saves a comparison table + NAV chart:
  Scenario 0 (ETF Baseline): loads the pre-computed improved convex returns CSV.
  Scenario 1 (Futures Substitution): replaces bond/commodity ETFs with futures
              continuous contracts, same Improved Convex config, no leverage.
  Scenario 2 (Futures + 1.5x Leverage): scales Scenario 1 portfolio returns by
              1.5 and deducts borrowing cost at 2.5% p.a. on the 0.5x excess.

Usage
-----
    python scripts/run_futures_extension.py [--force-update] [--eval-start 2019-01-01]

Output
------
    results/tables/futures_extension_comparison.csv
    results/figures/futures_extension_nav.png
    results/figures/futures_extension_weights.png
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.convex_adaptive_rrp import ConvexRRPConfig, run_convex_adaptive_backtest
from src.data_loader import load_data
from src.futures_data import FUTURES_UNIVERSE, load_futures_returns
from src.metrics import calculate_metrics
from src.utils import get_config, resolve_path
from src.visualization import plot_nav_comparison

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ETFs replaced by futures in the mixed universe (new_name column values).
# Tushare (CFX/DCE/INE/GFEX): T, TF, M, SC + new I, C, Y, SI, LC, LH
# akshare Sina (SFE/CZCE):    AU, AG, CU, RB, SR, CF, OI
# ZC (thermal coal, CZCE) not available via Sina — 煤炭ETF kept as ETF.
REPLACED_ETFS = {
    "国债ETF",    # → 国债期货T   (CFX, Tushare)
    "信用债ETF",  # → 国债期货TF  (CFX, Tushare)
    "豆粕ETF",    # → 豆粕期货M   (DCE, Tushare)
    "原油ETF",    # → 原油期货SC  (INE, Tushare)
    "黄金ETF",    # → 黄金期货AU  (SFE, akshare)
    "白银LOF",    # → 白银期货AG  (SFE, akshare)
    "有色ETF",    # → 铜期货CU    (SFE, akshare)
}

# candidate_09 configuration (the "improved" model's winning parameters)
IMPROVED_CFG_PARAMS = dict(
    lookback_days=180,
    covariance_method="ewma",
    max_weight=0.45,
    turnover_cap=0.80,
    turnover_penalty=0.010,
    budget_penalty=0.100,
    cvar_penalty=0.080,
    cvar_beta=0.95,
    return_reward=0.050,
)

LEVERAGE_MULTIPLE = 1.5
BORROW_RATE_PA = 0.025  # 2.5% annual borrowing cost on excess notional


def load_scenario0_returns(eval_start: str, config: dict) -> dict:
    """Load pre-computed improved convex returns from CSV."""
    path = resolve_path("results/tables/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv")
    if not Path(path).exists():
        logger.warning("Scenario 0 CSV not found at %s — run run_convex_adaptive_rrp.py first.", path)
        return {}
    df = pd.read_csv(path, parse_dates=["date"])
    eval_df = df[df["date"] >= eval_start].copy()
    nav = (1.0 + eval_df["portfolio_return"].fillna(0.0)).cumprod()
    nav.index = pd.to_datetime(eval_df["date"])
    metrics = calculate_metrics(nav, config.get("risk_free_rate", 0.0), config["trading_days_per_year"])
    metrics["model"] = "Scenario 0: ETF Baseline (Improved Convex)"
    avg_turnover = float(eval_df["turnover"].fillna(0.0).mean())
    metrics["avg_monthly_turnover"] = avg_turnover
    return {"metrics": metrics, "nav": nav, "returns": eval_df["portfolio_return"].values}


def build_futures_universe(
    etf_returns: pd.DataFrame,
    futures_returns: pd.DataFrame,
) -> pd.DataFrame:
    """Remove replaced ETFs and join futures returns into a unified DataFrame."""
    keep_etfs = [c for c in etf_returns.columns if c not in REPLACED_ETFS]
    logger.info("Keeping %d ETFs (dropped %d replaced)", len(keep_etfs),
                len([c for c in etf_returns.columns if c in REPLACED_ETFS]))
    available_futures = [c for c in FUTURES_UNIVERSE if c in futures_returns.columns]
    logger.info("Available futures: %s", available_futures)
    combined = pd.concat([etf_returns[keep_etfs], futures_returns[available_futures]], axis=1)
    combined = combined.dropna(how="all")
    return combined


def run_scenario1(combined_returns: pd.DataFrame, config: dict, eval_start: str) -> dict:
    """Futures substitution, no leverage — same Improved Convex config."""
    cfg = ConvexRRPConfig(
        transaction_cost_bps=config.get("transaction_cost_bps", 5.0),
        **IMPROVED_CFG_PARAMS,
    )
    logger.info("Running Scenario 1: Futures Substitution (no leverage)...")
    result, solver_diag, _, _ = run_convex_adaptive_backtest(combined_returns, cfg)
    eval_df = result[pd.to_datetime(result["date"]) >= pd.Timestamp(eval_start)].copy()
    nav = (1.0 + eval_df["portfolio_return"].fillna(0.0)).cumprod()
    nav.index = pd.to_datetime(eval_df["date"])
    metrics = calculate_metrics(nav, config.get("risk_free_rate", 0.0), config["trading_days_per_year"])
    metrics["model"] = "Scenario 1: Futures Substitution (No Leverage)"
    metrics["avg_monthly_turnover"] = float(eval_df["turnover"].fillna(0.0).mean())
    fallback_rate = float(solver_diag["fallback_used"].mean()) if not solver_diag.empty else float("nan")
    metrics["solver_fallback_rate"] = fallback_rate
    return {"metrics": metrics, "nav": nav, "result": result}


def apply_leverage(
    base_returns: pd.Series,
    leverage: float = LEVERAGE_MULTIPLE,
    borrow_rate_pa: float = BORROW_RATE_PA,
    trading_days: int = 243,
) -> pd.Series:
    """Scale portfolio returns by leverage and deduct daily borrowing cost."""
    excess = leverage - 1.0
    daily_borrow_cost = excess * borrow_rate_pa / trading_days
    return base_returns * leverage - daily_borrow_cost


def run_leveraged_scenario(
    scenario1_result: pd.DataFrame,
    config: dict,
    eval_start: str,
    leverage: float,
    scenario_idx: int,
) -> dict:
    """Apply a given leverage multiplier to Scenario 1 portfolio returns."""
    eval_df = scenario1_result[pd.to_datetime(scenario1_result["date"]) >= pd.Timestamp(eval_start)].copy()
    leveraged_returns = apply_leverage(
        eval_df["portfolio_return"].fillna(0.0),
        leverage=leverage,
        borrow_rate_pa=BORROW_RATE_PA,
        trading_days=config["trading_days_per_year"],
    )
    nav = (1.0 + leveraged_returns).cumprod()
    nav.index = pd.to_datetime(eval_df["date"])
    metrics = calculate_metrics(nav, config.get("risk_free_rate", 0.0), config["trading_days_per_year"])
    metrics["model"] = (
        f"Scenario {scenario_idx}: Futures + {leverage}x Leverage "
        f"({BORROW_RATE_PA*100:.1f}% borrow)"
    )
    metrics["avg_monthly_turnover"] = float(eval_df["turnover"].fillna(0.0).mean())
    return {"metrics": metrics, "nav": nav}


def run_scenario2(scenario1_result: pd.DataFrame, config: dict, eval_start: str) -> dict:
    return run_leveraged_scenario(scenario1_result, config, eval_start, leverage=1.5, scenario_idx=2)


def run_scenario3(scenario1_result: pd.DataFrame, config: dict, eval_start: str) -> dict:
    return run_leveraged_scenario(scenario1_result, config, eval_start, leverage=2.0, scenario_idx=3)


def save_comparison_table(all_metrics: list[dict]) -> None:
    df = pd.DataFrame(all_metrics)
    cols_order = ["model", "annualized_return", "annualized_volatility", "sharpe_ratio",
                  "max_drawdown", "calmar_ratio", "avg_monthly_turnover"]
    cols = [c for c in cols_order if c in df.columns] + [c for c in df.columns if c not in cols_order]
    df = df[cols]
    out = resolve_path("results/tables/futures_extension_comparison.csv")
    df.to_csv(out, index=False)
    logger.info("Saved comparison table → %s", out)
    print("\nFutures Extension Comparison:")
    print(df.to_string(index=False))


def save_nav_chart(nav_dict: dict[str, pd.Series]) -> None:
    out = resolve_path("results/figures/futures_extension_nav.png")
    plot_nav_comparison(nav_dict, "Futures Extension: ETF vs Futures vs Leveraged", out)
    logger.info("Saved NAV chart → %s", out)


def save_weights_chart(scenario1_result: pd.DataFrame, eval_start: str) -> None:
    weight_cols = [c for c in scenario1_result.columns if c.startswith("weight_")]
    if not weight_cols:
        return
    eval_df = scenario1_result[pd.to_datetime(scenario1_result["date"]) >= pd.Timestamp(eval_start)].copy()
    wdf = eval_df.set_index(pd.to_datetime(eval_df["date"]))[weight_cols]
    wdf.columns = [c.replace("weight_", "") for c in wdf.columns]
    # Keep only top-10 by mean allocation for readability
    top_cols = wdf.mean().nlargest(10).index.tolist()
    wdf_plot = wdf[top_cols]
    fig, ax = plt.subplots(figsize=(14, 5))
    wdf_plot.plot.area(ax=ax, alpha=0.75)
    ax.set_title("Scenario 1: Futures Substitution — Top-10 Asset Weights")
    ax.set_ylabel("Weight")
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    plt.tight_layout()
    out = resolve_path("results/figures/futures_extension_weights.png")
    plt.savefig(out, dpi=120)
    plt.close()
    logger.info("Saved weights chart → %s", out)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force-update", action="store_true", help="Re-fetch futures data from Tushare")
    parser.add_argument("--eval-start", type=str, default="2019-01-01")
    args = parser.parse_args()

    config = get_config({
        "transaction_cost_bps": 5.0,  # slightly higher for futures
        "risk_free_rate": 0.0182,
        "trading_days_per_year": 243,
    })
    eval_start = args.eval_start

    # ── Load data ────────────────────────────────────────────────────────────
    logger.info("Loading ETF returns...")
    etf_returns = load_data(source="tushare").dropna(how="all")

    logger.info("Loading futures returns...")
    futures_returns = load_futures_returns(force_update=args.force_update)

    # ── Build combined universe ───────────────────────────────────────────────
    combined_returns = build_futures_universe(etf_returns, futures_returns)
    logger.info("Combined universe: %d assets, %d trading days", combined_returns.shape[1], len(combined_returns))

    # ── Run scenarios ────────────────────────────────────────────────────────
    all_metrics: list[dict] = []
    nav_dict: dict[str, pd.Series] = {}

    s0 = load_scenario0_returns(eval_start, config)
    if s0:
        all_metrics.append(s0["metrics"])
        nav_dict["ETF Baseline"] = s0["nav"]

    s1 = run_scenario1(combined_returns, config, eval_start)
    all_metrics.append(s1["metrics"])
    nav_dict["Futures (No Leverage)"] = s1["nav"]

    s2 = run_scenario2(s1["result"], config, eval_start)
    all_metrics.append(s2["metrics"])
    nav_dict["Futures + 1.5x Leverage"] = s2["nav"]

    s3 = run_scenario3(s1["result"], config, eval_start)
    all_metrics.append(s3["metrics"])
    nav_dict["Futures + 2.0x Leverage"] = s3["nav"]

    # ── Output ───────────────────────────────────────────────────────────────
    save_comparison_table(all_metrics)
    save_nav_chart(nav_dict)
    save_weights_chart(s1["result"], eval_start)
    logger.info("Futures extension experiment complete.")


if __name__ == "__main__":
    main()
