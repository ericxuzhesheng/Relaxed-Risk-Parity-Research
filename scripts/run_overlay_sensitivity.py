"""Risk-overlay parameter sensitivity sweep.

Sweep the drawdown-scaling thresholds and the momentum lookback parameters
used by ``src.risk_overlay.apply_risk_overlay``; for each variant run the
static backtest and record the realised performance and turnover so the
sensitivity of Global RRP / Defensive Dynamic RRP to these "magic numbers"
becomes empirically visible.

The sweep is intentionally narrow — one parameter at a time around the
defaults — to keep runtime modest. Use it as a disclosure layer (the
"how much does the result depend on these thresholds" question) rather
than as a tuning loop. The script never alters the default
``RiskOverlayConfig`` and never writes back into the published headline
summary.

Output: ``results/tables/overlay_sensitivity.csv`` with one row per
variant and the official ``baseline`` row at the top for comparison.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.backtest import run_static_backtest
from src.data_loader import load_data
from src.metrics import calculate_metrics
from src.utils import resolve_path


logger = logging.getLogger("overlay_sensitivity")


# Sweep cells: (variant_label, config_overrides). Each row varies one
# parameter at a time. The defaults match RiskOverlayConfig.
SWEEP: list[tuple[str, dict]] = [
    ("baseline", {}),
    # Drawdown thresholds
    ("dd_low_0.015", {"drawdown_low": 0.015, "drawdown_mild": 0.015}),
    ("dd_low_0.035", {"drawdown_low": 0.035, "drawdown_mild": 0.035}),
    ("dd_high_0.030", {"drawdown_high": 0.030, "drawdown_medium": 0.030}),
    ("dd_high_0.050", {"drawdown_high": 0.050, "drawdown_medium": 0.050}),
    ("dd_severe_0.060", {"drawdown_severe": 0.060}),
    ("dd_severe_0.100", {"drawdown_severe": 0.100}),
    # Drawdown scaling intensities
    ("dd_scale_aggressive", {"drawdown_medium_scale": 0.60, "drawdown_severe_scale": 0.35}),
    ("dd_scale_lenient", {"drawdown_medium_scale": 0.85, "drawdown_severe_scale": 0.65}),
    # Trend / momentum lookbacks
    ("mom_lookback_40", {"momentum_lookback": 40}),
    ("mom_lookback_120", {"momentum_lookback": 120}),
    ("mom_confirm_10", {"momentum_confirm_lookback": 10}),
    ("mom_confirm_40", {"momentum_confirm_lookback": 40}),
]


def _summarize(result: pd.DataFrame, eval_start: pd.Timestamp, trading_days: int) -> dict:
    eval_result = result[pd.to_datetime(result["date"]) >= eval_start].copy()
    net_return = eval_result["portfolio_return"].fillna(0.0)
    nav = (1.0 + net_return).cumprod()
    nav.index = pd.to_datetime(eval_result["date"])
    metrics = calculate_metrics(nav, risk_free_rate=0.0182, trading_days=trading_days)
    months = pd.to_datetime(eval_result["date"]).dt.to_period("M").nunique()
    avg_monthly_turnover = float(eval_result["turnover"].fillna(0.0).sum() / max(months, 1))
    return {
        "net_annual_return": metrics["annualized_return"],
        "annualized_volatility": metrics["annualized_volatility"],
        "sharpe_ratio": metrics["sharpe_ratio"],
        "sortino_ratio": metrics["sortino_ratio"],
        "max_drawdown": metrics["max_drawdown"],
        "calmar_ratio": metrics["calmar_ratio"],
        "avg_monthly_turnover": avg_monthly_turnover,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="tushare")
    parser.add_argument("--force-update", action="store_true")
    parser.add_argument("--eval-start", default="2019-01-01")
    parser.add_argument("--trading-days", type=int, default=243)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    out_dir = Path(resolve_path("results/tables"))
    out_dir.mkdir(parents=True, exist_ok=True)
    eval_start = pd.Timestamp(args.eval_start)

    logger.info("Loading returns (source=%s, force_update=%s)", args.source, args.force_update)
    returns = load_data(source=args.source, force_update=args.force_update).dropna(how="all")

    rows: list[dict] = []
    base_config: dict = {"transaction_cost_bps": 3.0, "turnover_cap": 0.25, "target_vol": 0.060}
    for label, overrides in SWEEP:
        logger.info("Running variant %s with overrides=%s", label, overrides)
        cfg = {**base_config, **overrides}
        result = run_static_backtest(returns, model_type="relaxed", config_overrides=cfg)
        summary = _summarize(result, eval_start, args.trading_days)
        rows.append({"variant": label, **overrides, **summary})

    df = pd.DataFrame(rows)
    out_path = out_dir / "overlay_sensitivity.csv"
    df.to_csv(out_path, index=False)
    logger.info("wrote %d variants -> %s", len(df), out_path)

    cols_to_show = [
        "variant",
        "net_annual_return",
        "annualized_volatility",
        "sharpe_ratio",
        "max_drawdown",
        "calmar_ratio",
        "avg_monthly_turnover",
    ]
    pd.options.display.float_format = "{:.4f}".format
    print(df[cols_to_show].to_string(index=False))


if __name__ == "__main__":
    main()
