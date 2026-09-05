"""Export every weekly decision and reconcile calendar-week and holding-period P&L."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.asset_universe import ETF_UNIVERSE


def build_weekly_tables(daily, solver):
    daily = daily.sort_values("date").reset_index(drop=True)
    if daily.date.duplicated().any():
        raise ValueError("Duplicate daily dates")
    decisions = daily[daily.is_rebalance_day].copy()
    names = [a.new_name for a in ETF_UNIVERSE]
    cols = ["weight_" + name for name in names]
    np.testing.assert_allclose(decisions[cols].sum(axis=1), 1, atol=5e-5)
    calendar = {str(k): g for k, g in daily.groupby(daily.date.dt.to_period("W"))}
    solver = solver.copy()
    solver["date"] = pd.to_datetime(solver.date)
    solver = solver.set_index("date")
    summary, holdings = [], []
    positions = list(decisions.index)
    for n, (pos, row) in enumerate(decisions.iterrows()):
        next_pos = positions[n + 1] if n + 1 < len(positions) else len(daily)
        holding = daily.iloc[pos:next_pos]
        week = row.date.to_period("W")
        actual = calendar[str(week)]
        if row.date != actual.date.max():
            raise ValueError("Rebalance is not the last actual trading day of its week")
        cutoff = pd.Timestamp(solver.loc[row.date, "information_cutoff"])
        if cutoff >= row.date:
            raise ValueError("Future information at rebalance")
        delta = np.array([row["weight_"+x] - row["previous_weight_"+x] for x in names])
        np.testing.assert_allclose(np.abs(delta).sum(), row.turnover, atol=5e-5)
        np.testing.assert_allclose(row.transaction_cost, row.turnover * .0003, atol=1e-12)
        record = {
            "week_start": week.start_time.date().isoformat(),
            "week_end": week.end_time.date().isoformat(),
            "actual_week_start": actual.date.min().date().isoformat(),
            "rebalance_date": row.date.date().isoformat(),
            "information_cutoff": cutoff.date().isoformat(),
            "trading_days": len(actual),
            "calendar_week_gross_return": float((1+actual.gross_return).prod()-1),
            "calendar_week_net_return": float((1+actual.net_return).prod()-1),
            "turnover": float(row.turnover),
            "transaction_cost": float(row.transaction_cost),
            "holding_period_end": holding.date.max().date().isoformat(),
            "holding_period_days": len(holding),
            "holding_period_net_return": float((1+holding.net_return).prod()-1),
            "holding_period_truncated": n == len(positions)-1,
            "calendar_week_at_sample_end": n == len(positions)-1,
            "cash_target_weight": float(row["weight_日利ETF"]),
            "max_target_weight": float(row[cols].max()),
        }
        summary.append(record)
        for a in ETF_UNIVERSE:
            before = float(row["previous_weight_"+a.new_name])
            target = float(row["weight_"+a.new_name])
            holdings.append({"rebalance_date": record["rebalance_date"], "information_cutoff": record["information_cutoff"],
                "holding_period_end": record["holding_period_end"], "ticker": a.ticker, "asset": a.new_name,
                "asset_class": a.asset_class, "pretrade_weight": before, "target_weight": target,
                "weight_change": target-before, "absolute_trade_weight": abs(target-before),
                "transaction_cost": abs(target-before)*.0003})
    summary, holdings = pd.DataFrame(summary), pd.DataFrame(holdings)
    if len(summary) != len(calendar):
        raise ValueError("A calendar week is missing from the decision export")
    np.testing.assert_allclose((1+summary.calendar_week_net_return).prod(), (1+daily.net_return).prod(), atol=1e-10)
    np.testing.assert_allclose(summary.transaction_cost.sum(), daily.transaction_cost.sum(), atol=1e-10)
    if not np.isfinite(holdings.select_dtypes("number")).all().all():
        raise ValueError("Nonfinite holdings")
    return summary, holdings


def main():
    tables = ROOT / "results/tables"
    daily = pd.read_csv(tables / "improved_convex_adaptive_global_relaxed_risk_parity_returns.csv", parse_dates=["date"])
    solver = pd.read_csv(tables / "convex_adaptive_solver_diagnostics.csv")
    solver = solver[solver.model.eq("Improved Convex Adaptive Global RRP")]
    weekly, holdings = build_weekly_tables(daily, solver)
    wide = holdings.pivot(index="rebalance_date", columns="asset", values="target_weight")
    wide = wide[[a.new_name for a in ETF_UNIVERSE]]
    weekly.to_csv(tables / "primary_weekly_summary.csv", index=False, encoding="utf-8-sig")
    holdings.to_csv(tables / "primary_weekly_holdings.csv", index=False, encoding="utf-8-sig")
    wide.to_csv(tables / "primary_weekly_weights.csv", encoding="utf-8-sig")
    print(f"Validated {len(weekly)} weeks, {len(holdings)} asset rows, 30 assets per week")


if __name__ == "__main__":
    main()
