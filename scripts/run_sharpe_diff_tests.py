"""Run pairwise block-bootstrap Sharpe difference tests for the headline
model comparison.

Loads or recomputes the daily net return series for the four headline
models and the Equal Weight benchmark, then runs
``sharpe_difference_block_bootstrap`` for every pair. Output is written to
``results/tables/sharpe_difference_tests.csv``.

The published Improved Convex Adaptive RRP return series is loaded from
the cached CSV; Global RRP and Defensive Dynamic RRP are recomputed via
the standard backtest paths (cheap, default ~30 seconds) so the test uses
exactly the same return convention as the rest of the pipeline.
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
from src.dynamic_selection import run_dynamic_rrp_selection
from src.statistical_tests import pairwise_sharpe_difference_table
from src.utils import get_config, resolve_path


logger = logging.getLogger("sharpe_diff_tests")


def _equal_weight_returns(returns: pd.DataFrame) -> pd.Series:
    """Equal-weight portfolio return: daily mean of available assets."""
    return returns.mean(axis=1, skipna=True)


def _load_improved_returns() -> pd.Series:
    path = resolve_path("results/tables/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv")
    if not Path(path).exists():
        return pd.Series(dtype=float)
    df = pd.read_csv(path, parse_dates=["date"])
    col = "net_return" if "net_return" in df.columns else "portfolio_return"
    return df.set_index("date")[col].astype(float).rename("Improved Convex Adaptive Global RRP")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-start", default="2019-01-01")
    parser.add_argument("--n-resamples", type=int, default=2000)
    parser.add_argument("--block-size", type=int, default=21)
    parser.add_argument("--seed", type=int, default=20260511)
    parser.add_argument("--trading-days", type=int, default=243)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out_dir = Path(resolve_path("results/tables"))
    out_dir.mkdir(parents=True, exist_ok=True)
    eval_start = pd.Timestamp(args.eval_start)

    logger.info("Loading returns")
    returns = load_data(source="tushare", force_update=False).dropna(how="all")

    config = get_config({"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060})

    logger.info("Running Global RRP static backtest")
    global_rrp = run_static_backtest(returns, model_type="relaxed", config_overrides=config)
    global_series = (
        global_rrp.set_index("date")["portfolio_return"].astype(float)
        .rename("Global RRP")
    )

    logger.info("Running Defensive Dynamic RRP")
    dynamic = run_dynamic_rrp_selection(
        returns,
        [
            {"lambda_pen": 0.10, "m": 1.9, "bond_leverage_upper": 1.4},
            {"lambda_pen": 1.90, "m": 3.0, "bond_leverage_upper": 1.8},
        ],
        train_window_months=24,
        selection_metric="utility",
        top_k=2,
        config_base=config,
    )
    dynamic_series = (
        dynamic.set_index("date")["portfolio_return"].astype(float)
        .rename("Defensive Dynamic RRP")
    )

    logger.info("Loading Improved Convex Adaptive RRP return series from cache")
    improved_series = _load_improved_returns()
    if improved_series.empty:
        logger.warning(
            "improved_convex_adaptive_global_relaxed_risk_parity_returns.csv is missing; "
            "skipping Improved Convex tests. Run scripts/run_convex_adaptive_rrp.py first."
        )

    logger.info("Building equal-weight benchmark series")
    equal_weight = _equal_weight_returns(returns).rename("Equal Weight")

    series_map: dict[str, pd.Series] = {
        "Global RRP": global_series,
        "Defensive Dynamic RRP": dynamic_series,
        "Equal Weight": equal_weight,
    }
    if not improved_series.empty:
        series_map["Improved Convex Adaptive Global RRP"] = improved_series

    # Trim every series to the evaluation window.
    series_map = {
        name: s.loc[pd.to_datetime(s.index) >= eval_start].astype(float)
        for name, s in series_map.items()
    }

    # Headline thesis comparisons (ordered so observed_difference reflects
    # the named "a − b" direction): a is the proposed / improved model, b
    # is the comparison anchor.
    pairs = []
    if "Improved Convex Adaptive Global RRP" in series_map:
        pairs.extend(
            [
                ("Improved Convex Adaptive Global RRP", "Global RRP"),
                ("Improved Convex Adaptive Global RRP", "Defensive Dynamic RRP"),
                ("Improved Convex Adaptive Global RRP", "Equal Weight"),
            ]
        )
    pairs.extend(
        [
            ("Global RRP", "Equal Weight"),
            ("Defensive Dynamic RRP", "Equal Weight"),
        ]
    )

    logger.info(
        "Running %d pairwise tests with n_resamples=%d block_size=%d",
        len(pairs),
        args.n_resamples,
        args.block_size,
    )
    table = pairwise_sharpe_difference_table(
        series_map,
        pairs=pairs,
        n_resamples=args.n_resamples,
        block_size=args.block_size,
        risk_free_rate=config.get("risk_free_rate", 0.0182),
        trading_days=args.trading_days,
        seed=args.seed,
    )
    out_path = out_dir / "sharpe_difference_tests.csv"
    table.to_csv(out_path, index=False)
    logger.info("Wrote %d test rows -> %s", len(table), out_path)

    display_cols = [
        "model_a",
        "model_b",
        "n_observations",
        "sharpe_a",
        "sharpe_b",
        "observed_difference",
        "ci_low",
        "ci_high",
        "p_value_two_sided",
        "significant_at_95pct",
    ]
    pd.options.display.float_format = "{:.4f}".format
    print(table[display_cols].to_string(index=False))


if __name__ == "__main__":
    main()
