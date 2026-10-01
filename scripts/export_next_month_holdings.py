"""Forecast the next month's initial Global RRP allocation from observed history."""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.asset_universe import ETF_UNIVERSE
from src.backtest import run_static_backtest
from src.data_loader import load_data


def build_next_month_holdings(returns, config, rebalance_date):
    """Use a zero-return placeholder only to invoke the existing forecast solver.

    The placeholder's return never enters estimation. Its simulated P&L is
    discarded; only target weights and strictly prior diagnostics are exported.
    """
    cutoff = pd.Timestamp(returns.index.max())
    decision = pd.Timestamp(rebalance_date)
    month = (cutoff + pd.offsets.MonthBegin(1)).to_period("M")
    if decision.to_period("M") != month:
        raise ValueError("Rebalance date must be in the month after the information cutoff")
    names = [asset.new_name for asset in ETF_UNIVERSE]
    if list(returns.columns) != names:
        raise ValueError("Returns must match the active ETF universe")
    if config["rebalance_frequency"] != "W" or config["lookback_days"] != 252:
        raise ValueError("Forecast requires the designated weekly 252-day specification")
    history = returns.sort_index().tail(config["lookback_days"])
    if len(history) < config["lookback_days"]:
        raise ValueError("Insufficient history for the forecast")
    future_row = pd.DataFrame(0.0, index=[decision], columns=names)
    diagnostics = {}
    result = run_static_backtest(
        pd.concat([history, future_row]), "relaxed", config, diagnostics
    )
    solver = diagnostics["solver"].set_index("date").loc[decision]
    covariance = diagnostics["covariance"].set_index("date").loc[decision]
    if (not solver.solver_success or not solver.problem_is_dcp
            or solver.fallback_used or covariance.covariance_fallback_used
            or pd.Timestamp(solver.information_cutoff) != cutoff):
        raise ValueError("Next-month forecast failed solver or information-timing checks")
    latest = result.loc[result.date.eq(decision)].iloc[0]
    weights = np.array([latest["weight_" + name] for name in names], dtype=float)
    if not np.isfinite(weights).all() or weights.min() < -1e-8:
        raise ValueError("Invalid next-month weights")
    np.testing.assert_allclose(weights.sum(), 1.0, atol=1e-8)
    holdings = pd.DataFrame([
        {"holding_month": str(month), "as_of_date": cutoff.date().isoformat(),
         "rebalance_date": decision.date().isoformat(), "model": "Global RRP",
         "allocation_type": "initial_forecast_update_weekly",
         "etf": asset.new_name, "ticker": asset.ticker,
         "asset_class": asset.asset_class, "weight": weight, "weight_pct": weight * 100}
        for asset, weight in zip(ETF_UNIVERSE, weights)
    ]).sort_values(["weight", "ticker"], ascending=[False, True]).reset_index(drop=True)
    audit = {
        "status": "passed", "model": "Global RRP", "holding_month": str(month),
        "information_cutoff": cutoff.date().isoformat(),
        "rebalance_date": decision.date().isoformat(),
        "forecast_only": True, "future_realized_returns_used": False,
        "refresh_at_next_weekly_rebalance": True,
        "estimation_observations": len(history), "asset_count": len(holdings),
        "weight_sum": float(weights.sum()),
        "selected_variance_penalty": float(solver.selected_variance_penalty),
        "selected_shortfall_penalty": float(solver.selected_shortfall_penalty),
        "max_constraint_violation": float(solver.max_constraint_violation),
        "solver_success": bool(solver.solver_success),
        "problem_is_dcp": bool(solver.problem_is_dcp),
    }
    return holdings, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebalance-date", required=True,
                        help="Next month's first weekly trading decision, YYYY-MM-DD")
    args = parser.parse_args()
    logging.getLogger().setLevel(logging.ERROR)
    tables = ROOT / "results/tables"
    record = json.loads((tables / "primary_model_configuration.json").read_text(encoding="utf-8"))
    config = record["configuration"]
    returns = load_data(source="tushare", force_update=False)
    if pd.Timestamp(returns.index.max()) != pd.Timestamp(config["evaluation_end_date"]):
        raise ValueError("Latest data and published configuration do not agree")
    holdings, audit = build_next_month_holdings(returns, config, args.rebalance_date)
    output = tables / "next_month_holdings.csv"
    holdings.to_csv(output, index=False, encoding="utf-8-sig", float_format="%.10f")
    (tables / "next_month_holdings_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(f"Wrote {audit['holding_month']} Global RRP forecast: {len(holdings)} ETFs, "
          f"information through {audit['information_cutoff']}; {output}")


if __name__ == "__main__":
    main()
