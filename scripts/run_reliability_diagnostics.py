"""Generate solver / covariance / investable-universe diagnostics CSVs.

This script runs the static backtest with the diagnostics channel enabled and
writes three artifacts under ``results/tables/``:

* ``static_backtest_solver_diagnostics.csv`` — per rebalance SLSQP solver
  status / message / fallback flag for the Global RRP path.
* ``static_backtest_covariance_diagnostics.csv`` — per rebalance n_obs,
  n_assets, condition number, PSD repair flags, and low-sample/ill-conditioned
  warning flags.
* ``static_backtest_universe_diagnostics.csv`` — per rebalance investable
  universe (included assets, excluded assets, exclusion reason, count).

A short aggregate summary is also written to
``results/tables/reliability_summary.csv``.

The script is intentionally minimal so it can be run as a smoke test:

    python scripts/run_reliability_diagnostics.py

It does not change the headline performance numbers; it only surfaces the
reliability information that previously lived inside the solver but was not
recorded.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.backtest import run_static_backtest
from src.data_loader import load_data
from src.utils import resolve_path


logger = logging.getLogger("reliability_diagnostics")


def _aggregate_summary(diagnostics: dict) -> pd.DataFrame:
    solver = diagnostics.get("solver", pd.DataFrame())
    cov = diagnostics.get("covariance", pd.DataFrame())
    universe = diagnostics.get("universe", pd.DataFrame())

    total_rebalance = int(len(solver)) if not solver.empty else 0
    if not solver.empty:
        success = int(solver["solver_success"].fillna(False).sum())
        fallback = int(solver["fallback_used"].fillna(False).sum())
    else:
        success = 0
        fallback = 0

    if not cov.empty:
        low_sample = int(cov["low_sample_warning"].fillna(False).sum())
        ill_conditioned = int(cov["ill_conditioned_warning"].fillna(False).sum())
        ratio_min = float(cov["n_obs_to_n_assets_ratio"].min())
        ratio_median = float(cov["n_obs_to_n_assets_ratio"].median())
        psd_repaired = int(cov.get("covariance_psd_repaired", pd.Series(dtype=bool)).fillna(False).sum())
    else:
        low_sample = ill_conditioned = psd_repaired = 0
        ratio_min = ratio_median = float("nan")

    if not universe.empty:
        avg_assets = float(universe["asset_count"].mean())
        min_assets = int(universe["asset_count"].min())
        max_assets = int(universe["asset_count"].max())
    else:
        avg_assets = float("nan")
        min_assets = max_assets = 0

    return pd.DataFrame(
        [
            {
                "metric": "total_rebalance_dates",
                "value": total_rebalance,
                "note": "Number of rebalance dates with optimizer calls (model_type=relaxed).",
            },
            {
                "metric": "solver_success_count",
                "value": success,
                "note": "Rebalance dates where SLSQP converged with success=True.",
            },
            {
                "metric": "solver_fallback_count",
                "value": fallback,
                "note": "Rebalance dates where the solver fell back (equal weights or standard RP).",
            },
            {
                "metric": "solver_fallback_rate",
                "value": (fallback / total_rebalance) if total_rebalance else 0.0,
                "note": "Fraction of rebalance dates that used the fallback weights.",
            },
            {
                "metric": "covariance_low_sample_warning_count",
                "value": low_sample,
                "note": "Rebalance dates with n_obs/n_assets < 3.",
            },
            {
                "metric": "covariance_ill_conditioned_warning_count",
                "value": ill_conditioned,
                "note": "Rebalance dates with condition number > 1e8 after PSD repair.",
            },
            {
                "metric": "covariance_psd_repaired_count",
                "value": psd_repaired,
                "note": "Rebalance dates where eigenvalue flooring was triggered.",
            },
            {
                "metric": "covariance_obs_to_assets_ratio_min",
                "value": ratio_min,
                "note": "Minimum n_obs/n_assets ratio across rebalance dates.",
            },
            {
                "metric": "covariance_obs_to_assets_ratio_median",
                "value": ratio_median,
                "note": "Median n_obs/n_assets ratio across rebalance dates.",
            },
            {
                "metric": "investable_universe_size_min",
                "value": min_assets,
                "note": "Smallest investable universe across rebalance dates.",
            },
            {
                "metric": "investable_universe_size_max",
                "value": max_assets,
                "note": "Largest investable universe across rebalance dates.",
            },
            {
                "metric": "investable_universe_size_avg",
                "value": avg_assets,
                "note": "Average investable universe size across rebalance dates.",
            },
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model-type",
        default="relaxed",
        choices=["standard", "relaxed"],
        help="Backtest model_type to diagnose (default: relaxed = Global RRP).",
    )
    parser.add_argument(
        "--source",
        default="tushare",
        help="Return data source for src.data_loader.load_data.",
    )
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Force a remote data refresh before running.",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

    out_dir = Path(resolve_path("results/tables"))
    out_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Loading returns (source=%s, force_update=%s)", args.source, args.force_update)
    returns = load_data(source=args.source, force_update=args.force_update).dropna(how="all")

    diagnostics: dict = {}
    logger.info("Running static backtest with diagnostics enabled (model_type=%s)", args.model_type)
    result = run_static_backtest(returns, model_type=args.model_type, diagnostics_out=diagnostics)

    solver_path = out_dir / "static_backtest_solver_diagnostics.csv"
    cov_path = out_dir / "static_backtest_covariance_diagnostics.csv"
    universe_path = out_dir / "static_backtest_universe_diagnostics.csv"
    summary_path = out_dir / "reliability_summary.csv"

    diagnostics["solver"].to_csv(solver_path, index=False)
    diagnostics["covariance"].to_csv(cov_path, index=False)
    diagnostics["universe"].to_csv(universe_path, index=False)
    summary = _aggregate_summary(diagnostics)
    summary.to_csv(summary_path, index=False)

    logger.info("Wrote %s rows -> %s", len(diagnostics["solver"]), solver_path)
    logger.info("Wrote %s rows -> %s", len(diagnostics["covariance"]), cov_path)
    logger.info("Wrote %s rows -> %s", len(diagnostics["universe"]), universe_path)
    logger.info("Wrote summary -> %s", summary_path)

    print(summary.to_string(index=False))
    print(f"Backtest produced {len(result)} daily rows; headline numbers unchanged.")


if __name__ == "__main__":
    main()
