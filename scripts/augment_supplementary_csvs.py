"""Append the new baselines and dispersion tables onto existing CSVs.

This is a one-off helper that lets us land the audit fixes without rerunning
the full Convex Adaptive search (which would otherwise take ~30+ minutes
for the 36-candidate improvement loop). It computes the following from
the existing cached return series:

* Equal Weight and 60/40 Benchmark rows for
  ``results/tables/convex_adaptive_performance_summary.csv``.
* ``results/tables/cscv_candidate_grid.csv`` from
  ``scripts.run_convex_adaptive_rrp.candidate_configurations``.
* ``results/tables/robustness_subperiod_dispersion.csv`` from the existing
  ``robustness_subperiod_summary.csv``.
* ``results/tables/transaction_cost_breakeven.csv`` from the existing
  ``robustness_transaction_cost_summary.csv``.

Run ``scripts/run_vol_aligned_comparison.py`` and
``scripts/generate_thesis_numbers.py`` after this to refresh the LaTeX
macros. The full pipeline (``scripts/run_all.py``) supersedes this helper
once a fresh run is available.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.run_convex_adaptive_rrp import candidate_configurations, summarize_result
from scripts.run_robustness_tests import (
    subperiod_dispersion_summary,
    transaction_cost_breakeven,
)
from src.benchmarks import run_benchmark_backtest
from src.data_loader import load_data
from src.public_labels import public_model_label
from src.utils import get_config, resolve_path


logger = logging.getLogger("augment_supplementary_csvs")


def _augment_summary(returns: pd.DataFrame, config: dict, eval_start: str) -> None:
    summary_path = Path(resolve_path("results/tables/convex_adaptive_performance_summary.csv"))
    summary = pd.read_csv(summary_path)
    existing = set(summary["model"].astype(str))
    targets = [
        ("Equal Weight Benchmark", "Equal Weight"),
        ("60/40 Benchmark", "60/40 Benchmark"),
    ]
    appended: list[dict] = []
    for benchmark_name, public_label in targets:
        if public_label in existing:
            logger.info("summary already contains %s; skipping", public_label)
            continue
        logger.info("backtesting %s ...", benchmark_name)
        result = run_benchmark_backtest(
            returns, benchmark_name, transaction_cost_bps=config["transaction_cost_bps"]
        )
        row = summarize_result(benchmark_name, result, eval_start, config)
        row["model"] = public_model_label(benchmark_name)
        appended.append(row)

    if not appended:
        return
    new_rows = pd.DataFrame(appended)
    merged = pd.concat([summary, new_rows], ignore_index=True)
    merged.to_csv(summary_path, index=False)
    logger.info("appended %d benchmark rows -> %s", len(appended), summary_path)


def _write_candidate_grid(config: dict) -> None:
    rows = []
    for candidate_id, cfg in candidate_configurations(config["transaction_cost_bps"]):
        rows.append(
            {
                "candidate_id": candidate_id,
                "lookback_days": cfg.lookback_days,
                "covariance_method": cfg.covariance_method,
                "max_weight": cfg.max_weight,
                "turnover_cap": cfg.turnover_cap if cfg.turnover_cap is not None else "无上限",
                "turnover_penalty": cfg.turnover_penalty,
                "budget_penalty": cfg.budget_penalty,
                "cvar_penalty": cfg.cvar_penalty,
                "cvar_beta": cfg.cvar_beta,
                "return_reward": cfg.return_reward,
                "vol_target_enabled": cfg.vol_target_enabled,
                "vol_target": cfg.vol_target,
                "portfolio_vol_cap_enabled": cfg.portfolio_vol_cap_enabled,
                "portfolio_vol_cap": cfg.portfolio_vol_cap,
            }
        )
    grid_path = Path(resolve_path("results/tables/cscv_candidate_grid.csv"))
    pd.DataFrame(rows).to_csv(grid_path, index=False)
    logger.info("wrote %d candidate rows -> %s", len(rows), grid_path)


def _write_subperiod_dispersion() -> None:
    sub_path = Path(resolve_path("results/tables/robustness_subperiod_summary.csv"))
    if not sub_path.exists():
        logger.warning("subperiod summary missing at %s; skipping", sub_path)
        return
    sub = pd.read_csv(sub_path)
    dispersion = subperiod_dispersion_summary(sub)
    out_path = Path(resolve_path("results/tables/robustness_subperiod_dispersion.csv"))
    dispersion.to_csv(out_path, index=False)
    logger.info("wrote %d dispersion rows -> %s", len(dispersion), out_path)


def _write_transaction_cost_breakeven() -> None:
    costs_path = Path(resolve_path("results/tables/robustness_transaction_cost_summary.csv"))
    if not costs_path.exists():
        logger.warning("transaction-cost summary missing at %s; skipping", costs_path)
        return
    costs = pd.read_csv(costs_path)
    breakeven = transaction_cost_breakeven(costs)
    out_path = Path(resolve_path("results/tables/transaction_cost_breakeven.csv"))
    breakeven.to_csv(out_path, index=False)
    logger.info("wrote %d breakeven rows -> %s", len(breakeven), out_path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})
    eval_start = config.get("plot_start_date", "2019-01-01")
    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    _augment_summary(returns, config, eval_start)
    _write_candidate_grid(config)
    _write_subperiod_dispersion()
    _write_transaction_cost_breakeven()


if __name__ == "__main__":
    main()
