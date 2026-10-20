"""Holdings-based Brinson-Fachler attribution and prior-market position analysis.

Attribution reports arithmetic mean daily effects (bps), not compounded effects.
It uses the saved return-generating weights, including drift on nontrade days.
"""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.asset_universe import ETF_UNIVERSE
from src.data_loader import load_data
from scripts.publish_global_rrp import pct, tex_table

TABLES = ROOT / "results/tables"
THESIS = ROOT / "report/thesis_latex"
GROUPS = {
    "money market": "货币",
    "government bond": "国债",
    "credit bond": "信用债",
    "convertible bond": "可转债",
    "hong kong equity": "境外权益",
    "global equity": "境外权益",
    "commodity": "商品相关",
}


def brinson_fachler(wp, wb, rp, rb):
    """Single-period category effects, with categories in columns."""
    benchmark = (wb * rb).sum(axis=1)
    allocation = (wp - wb) * (rb - benchmark[:, None])
    selection = wb * (rp - rb)
    interaction = (wp - wb) * (rp - rb)
    return allocation, selection, interaction


def main():
    returns = load_data(source="tushare", force_update=False)
    assets = [item.new_name for item in ETF_UNIVERSE]
    groups = {
        name: [item.new_name for item in ETF_UNIVERSE
               if GROUPS.get(item.asset_class, "境内权益") == name]
        for name in ["货币", "国债", "信用债", "可转债", "境内权益", "境外权益", "商品相关"]
    }

    def read(path):
        frame = pd.read_csv(path, parse_dates=["date"]).set_index("date")
        frame["transaction_cost"] = frame.gross_return - frame.net_return
        return frame

    primary = read(TABLES / "comparison_global_rrp_returns.csv")
    equal = read(TABLES / "comparison_equal_weight_returns.csv")
    matched = read(ROOT / "results/primary_diagnostics/matched_equal_daily.csv")
    index = primary.index
    assert equal.index.equals(index) and matched.index.equals(index)
    raw = returns.loc[index, assets]
    # Match the published dot-product convention: an unavailable quote adds zero.
    daily = raw.fillna(0)
    state = raw["沪深300ETF"].lt(0)
    assert raw["沪深300ETF"].notna().all()
    reconstructed_errors = []
    missing_held_counts = {}

    def aggregate(frame, fallback=None):
        weights = frame[["weight_" + a for a in assets]].copy()
        weights.columns = assets
        np.testing.assert_allclose(weights.sum(axis=1), 1, atol=1e-8)
        reconstructed_errors.append(float(
            ((weights * daily).sum(axis=1) - frame.gross_return).abs().max()))
        wg = pd.DataFrame({g: weights[a].sum(axis=1) for g, a in groups.items()})
        cg = pd.DataFrame({g: (weights[a] * daily[a]).sum(axis=1) for g, a in groups.items()})
        rg = cg.div(wg.where(wg != 0))
        if fallback is not None:
            rg = rg.fillna(fallback)
        return wg, rg.fillna(0), int(((weights.abs() > 1e-10) & raw.isna()).sum().sum())

    we, re, missing_held_counts["equal"] = aggregate(equal)
    wp, rp, missing_held_counts["primary"] = aggregate(primary, re)
    details, summaries, category_rows = [], [], []
    max_identity_error = 0.0
    for key, baseline in [("equal", equal), ("matched_equal", matched)]:
        wb, rb, missing_held_counts[key] = aggregate(baseline, re)
        allocation, selection, interaction = brinson_fachler(
            wp.to_numpy(), wb.to_numpy(), rp.to_numpy(), rb.to_numpy())
        effects = pd.DataFrame({
            "allocation": allocation.sum(axis=1),
            "selection": selection.sum(axis=1),
            "interaction": interaction.sum(axis=1),
            "cost": baseline.transaction_cost - primary.transaction_cost,
            "net_active": primary.net_return - baseline.net_return,
        }, index=index)
        error = effects.iloc[:, :4].sum(axis=1) - effects.net_active
        max_identity_error = max(max_identity_error, float(error.abs().max()))
        for j, group in enumerate(groups):
            detail = pd.DataFrame({
                "date": index, "benchmark": key, "group": group,
                "portfolio_weight": wp[group].values, "benchmark_weight": wb[group].values,
                "portfolio_group_return": rp[group].values, "benchmark_group_return": rb[group].values,
                "allocation": allocation[:, j], "selection": selection[:, j],
                "interaction": interaction[:, j], "market_down_day": state.values,
            })
            details.append(detail)
        for label, mask in [("all", np.ones(len(index), dtype=bool)), ("market_down", state.values)]:
            summaries.append({
                "benchmark": key, "sample": label, "days": int(mask.sum()),
                **{col + "_bps": effects.loc[mask, col].mean() * 10000 for col in effects},
            })
            for j, group in enumerate(groups):
                category_rows.append({
                    "benchmark": key, "sample": label, "group": group,
                    "allocation_bps": allocation[mask, j].mean() * 10000,
                    "selection_bps": selection[mask, j].mean() * 10000,
                    "interaction_bps": interaction[mask, j].mean() * 10000,
                })
        effects.assign(benchmark=key, market_down_day=state).to_csv(
            TABLES / f"primary_brinson_{key}_daily.csv", index_label="date")

    assert max(reconstructed_errors) < 1e-10
    assert max_identity_error < 1e-10
    pd.concat(details, ignore_index=True).to_csv(TABLES / "primary_brinson_group_daily.csv", index=False)
    summary = pd.DataFrame(summaries)
    summary.to_csv(TABLES / "primary_brinson_summary.csv", index=False)
    category = pd.DataFrame(category_rows)
    category.to_csv(TABLES / "primary_brinson_categories.csv", index=False)
    row_labels = ["Equal Weight：全样本", "Equal Weight：下跌日",
                  "风险匹配等权：全样本", "风险匹配等权：下跌日"]
    (THESIS / "generated_brinson_summary.tex").write_text(tex_table(
        ["比较基准与样本", "配置", "组内选择", "交互", "成本差", "净差异"],
        [[label] + [f"{row[k + '_bps']:.2f}" for k in
          ["allocation", "selection", "interaction", "cost", "net_active"]]
         for label, (_, row) in zip(row_labels, summary.iterrows())], "lrrrrr"), encoding="utf-8")
    table_rows = []
    for group in groups:
        values = [category.query("benchmark == @key and sample == @sample and group == @group").iloc[0].allocation_bps
                  for key, sample in [("equal", "all"), ("equal", "market_down"),
                                      ("matched_equal", "all"), ("matched_equal", "market_down")]]
        table_rows.append([group] + [f"{v:.2f}" for v in values])
    (THESIS / "generated_brinson_allocation.tex").write_text(tex_table(
        ["归因组", "等权全样本", "等权下跌日", "匹配全样本", "匹配下跌日"],
        table_rows, "lrrrr"), encoding="utf-8")
    macros = {"attrDays": str(len(index)), "attrDownDays": str(int(state.sum()))}
    for key, prefix in [("equal", "Equal"), ("matched_equal", "Matched")]:
        for sample, suffix in [("all", "All"), ("market_down", "Down")]:
            result = summary.query("benchmark == @key and sample == @sample").iloc[0]
            macros[f"attr{prefix}Net{suffix}"] = f"{result.net_active_bps:.2f}"
        cash = category.query("benchmark == @key and sample == 'market_down' and group == '货币'").iloc[0]
        macros[f"attr{prefix}CashDown"] = f"{cash.allocation_bps:.2f}"
    (THESIS / "generated_attribution_numbers.tex").write_text("\n".join(
        rf"\newcommand{{\{key}}}{{{value}}}" for key, value in macros.items()) + "\n", encoding="utf-8")

    prior = (1 + returns["沪深300ETF"]).rolling(63).apply(np.prod, raw=True).sub(1).shift(1)
    dates = index[primary.is_rebalance_day]
    records = []
    for start, end in zip(dates[:-1], dates[1:]):
        assert pd.notna(prior.loc[start])
        records.append({
            "date": start, "next_rebalance": end, "prior_63_return": prior.loc[start],
            "prior_down": bool(prior.loc[start] < 0),
            "cash_weight": primary.loc[start, "weight_日利ETF"],
            "cash_bond_weight": primary.loc[start, [
                "weight_日利ETF", "weight_5年国债ETF", "weight_10年国债ETF", "weight_信用债ETF"]].sum(),
        })
    positions = pd.DataFrame(records)
    positions.to_csv(TABLES / "primary_position_market_states.csv", index=False)
    position_summary = positions.groupby("prior_down").agg(
        weeks=("date", "size"), cash_weight=("cash_weight", "mean"),
        cash_bond_weight=("cash_bond_weight", "mean"))
    position_summary.to_csv(TABLES / "primary_position_summary.csv")
    (THESIS / "generated_position_states.tex").write_text(tex_table(
        ["调仓前63日市场收益", "完整周区间数", "货币权重", "货币及三只债券权重"],
        [[("小于零" if down else "大于等于零"), str(int(row.weeks)), pct(row.cash_weight), pct(row.cash_bond_weight)]
         for down, row in position_summary.iterrows()], "lrrr"), encoding="utf-8")
    audit = {
        "status": "passed", "daily_reconstruction_max_error": max(reconstructed_errors),
        "daily_attribution_identity_max_error": max_identity_error,
        "days": len(index), "market_down_days": int(state.sum()),
        "complete_weekly_intervals": len(positions),
        "missing_held_return_counts": missing_held_counts,
        "units": "arithmetic mean daily basis points; not compounded or annualized",
        "groups": groups,
        "zero_weight_convention": "empty portfolio groups use unscaled Equal Weight group return; empty benchmark groups use the same fallback",
        "market_state": "daily attribution: contemporaneous CSI300 ETF negative return, ex-post descriptive; weekly positions: strictly prior 63-day return",
    }
    (TABLES / "primary_attribution_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary.to_string(index=False))
    print(position_summary.to_string())
    print("Maximum daily reconciliation error:", max_identity_error)


if __name__ == "__main__":
    main()
