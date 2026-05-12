"""Vol-aligned comparison between Improved Convex and HRP/HERC.

HRP's headline Sharpe is driven almost entirely by its very low realized
volatility (≈0.17%). To make the Sharpe comparison meaningful, this script
rescales the Improved Convex Adaptive Global RRP return series by a constant
factor so its annualized volatility matches HRP (and separately HERC), then
recomputes net annual return, Sharpe, and max drawdown. The output answers
"what would the main model look like at the same risk level as the
hierarchical benchmarks?".

Output: ``results/tables/vol_aligned_comparison.csv`` with one row per
target benchmark. The ``slug`` column drives the LaTeX macros emitted by
``scripts/generate_thesis_numbers.py``.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.metrics import calculate_metrics
from src.utils import RISK_FREE_RATE_ANNUAL, get_config, resolve_path


logger = logging.getLogger("run_vol_aligned_comparison")


def _load_returns(path: Path, return_col_candidates: tuple[str, ...]) -> pd.Series:
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    for col in return_col_candidates:
        if col in df.columns:
            return df.set_index("date")[col].fillna(0.0)
    raise KeyError(
        f"none of {return_col_candidates} found in {path}; "
        "available columns: " + ",".join(df.columns)
    )


def _vol_aligned_metrics(
    improved_returns: pd.Series,
    target_vol: float,
    trading_days: int,
    risk_free: float,
) -> dict[str, float]:
    realized_vol = float(improved_returns.std() * np.sqrt(trading_days))
    if realized_vol <= 0.0:
        scale = 1.0
    else:
        scale = target_vol / realized_vol
    scaled = improved_returns * scale
    nav = (1.0 + scaled).cumprod()
    metrics = calculate_metrics(nav, risk_free, trading_days)
    metrics["scale_factor"] = scale
    metrics["target_vol"] = target_vol
    return metrics


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    config = get_config({"transaction_cost_bps": 3.0})
    trading_days = int(config["trading_days_per_year"])

    improved_path = Path(
        resolve_path("results/tables/improved_convex_adaptive_global_relaxed_risk_parity_returns.csv")
    )
    summary_path = Path(resolve_path("results/tables/convex_adaptive_performance_summary.csv"))
    if not improved_path.exists() or not summary_path.exists():
        raise FileNotFoundError(
            "Run scripts/run_convex_adaptive_rrp.py before scripts/run_vol_aligned_comparison.py."
        )

    improved_returns = _load_returns(improved_path, ("net_return", "portfolio_return"))
    summary = pd.read_csv(summary_path).set_index("model")
    targets = [
        ("improvedVolAlignedHrp", "HRP Benchmark"),
        ("improvedVolAlignedHerc", "HERC Benchmark"),
    ]
    rows = []
    for slug, target_model in targets:
        if target_model not in summary.index:
            logger.warning("target model %s not in performance summary; skipping", target_model)
            continue
        target_vol = float(summary.loc[target_model, "annualized_volatility"])
        metrics = _vol_aligned_metrics(
            improved_returns, target_vol, trading_days, RISK_FREE_RATE_ANNUAL
        )
        rows.append(
            {
                "slug": slug,
                "target_model": target_model,
                "target_annualized_volatility": target_vol,
                "scale_factor": metrics["scale_factor"],
                "net_annual_return": metrics["annualized_return"],
                "annualized_volatility": metrics["annualized_volatility"],
                "sharpe_ratio": metrics["sharpe_ratio"],
                "sortino_ratio": metrics["sortino_ratio"],
                "max_drawdown": metrics["max_drawdown"],
                "calmar_ratio": metrics["calmar_ratio"],
            }
        )
    output_path = Path(resolve_path("results/tables/vol_aligned_comparison.csv"))
    pd.DataFrame(rows).to_csv(output_path, index=False)
    logger.info("wrote %d vol-aligned comparison rows -> %s", len(rows), output_path)


if __name__ == "__main__":
    main()
