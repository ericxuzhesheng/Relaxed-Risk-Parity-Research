"""Publish current primary-model diagnostics from validated daily paths.

Historical ablations are repriced at rf=0, without changing their decisions.
Their input snapshot must match today's adjusted-price return data exactly.
"""
from pathlib import Path
import sys
import json

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_weekly_constraint_research import result_summary, check_result, VARIANTS
from src.data_loader import load_data
from src.utils import get_config

LABELS = dict(zip(VARIANTS, ["月度集中度约束对照", "周频集中度约束对照", "仅取消现金上限", "仅取消单资产上限", "主模型：取消两项集中度上限", "取消换手硬上限", "Ledoit--Wolf", "相对 CVaR", "Ledoit--Wolf 与相对 CVaR"]))


def tex_table(headers, rows, align):
    return "\n".join([r"\begin{tabular}{" + align + "}", r"\toprule", " & ".join(headers) + r" \\", r"\midrule", *[" & ".join(row) + r" \\" for row in rows], r"\bottomrule", r"\end{tabular}"])


def main():
    config = get_config()
    assert config["risk_free_rate"] == 0.0
    tables = ROOT / "results/tables"
    thesis = ROOT / "report/thesis_latex"
    returns = load_data(source="tushare").dropna(how="all")
    snapshot = pd.read_csv(ROOT / "results/weekly_constraint_research/unfiltered_input_returns.csv", index_col=0, parse_dates=True)
    pd.testing.assert_frame_equal(returns, snapshot, check_freq=False, check_names=False, atol=1e-12, rtol=1e-12)
    rows = []
    for variant in VARIANTS:
        folder = ROOT / "results/weekly_constraint_research" / variant
        result = pd.read_csv(folder / "daily_returns.csv", parse_dates=["date"])
        row = result_summary(variant, result, config)
        row["sharpe_chinabond"] = result_summary(variant, result, {**config, "risk_free_rate": None})["sharpe_ratio"]
        rows.append(row)
    experiments = pd.DataFrame(rows)
    experiments.to_csv(tables / "primary_constraint_comparison.csv", index=False)
    result = pd.read_csv(tables / "improved_convex_adaptive_global_relaxed_risk_parity_returns.csv", parse_dates=["date"])
    solver = pd.read_csv(tables / "convex_adaptive_solver_diagnostics.csv")
    solver = solver[solver.model.eq("Improved Convex Adaptive Global RRP")].copy()
    check_result(result, solver, returns.loc[config["evaluation_start_date"]:])
    saved = pd.read_csv(ROOT / "results/weekly_constraint_research_rf0/no_concentration_caps/daily_returns.csv")
    cols = ["net_return", "turnover"] + list(result.filter(regex="^weight_").columns)
    np.testing.assert_allclose(result[cols], saved[cols], atol=5e-5, rtol=0)
    main_row = result_summary("primary", result, config)
    annual = pd.DataFrame([{"year": year, **result_summary("primary", group, config)} for year, group in result.groupby(result.date.dt.year)])
    annual.to_csv(tables / "primary_annual_summary.csv", index=False)
    audit = {"status": "passed", "daily_observations": len(result), "rebalance_count": int(result.is_rebalance_day.sum()), "max_constraint_violation": float(solver.max_constraint_violation.max()), "future_information_count": int((pd.to_datetime(solver.information_cutoff) >= pd.to_datetime(solver.date)).sum()), "research_reproduction_atol": 5e-5, "risk_free_rate": 0.0, "selection_is_exploratory": True}
    (tables / "primary_publication_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")
    macros = {"primaryCashMean": f"{main_row['mean_cash_weight']:.2%}".replace("%", r"\%"), "primaryCashMax": f"{main_row['max_cash_weight']:.2%}".replace("%", r"\%"), "primaryChinaBondSharpe": f"{experiments.set_index('variant').loc['no_concentration_caps','sharpe_chinabond']:.3f}", "primaryRebalances": str(audit['rebalance_count']), "primaryObservations": str(len(result))}
    (thesis / "generated_primary_numbers.tex").write_text("\n".join("\\newcommand{\\" + k + "}{" + v + "}" for k,v in macros.items()) + "\n", encoding="utf-8")
    exp_rows = [[LABELS[r.variant], f"{r.net_annual_return:.2%}".replace("%",r"\%"), f"{r.sharpe_ratio:.3f}", f"{r.sharpe_chinabond:.3f}", f"{r.mean_cash_weight:.2%}".replace("%",r"\%")] for r in experiments.itertuples()]
    (thesis / "generated_primary_constraints.tex").write_text(tex_table(["配置", "净年化收益", "$r_f=0$ 夏普", "中债夏普", "平均现金权重"], exp_rows, "lrrrr"), encoding="utf-8")
    yr_rows = [[str(r.year), f"{r.net_annual_return:.2%}".replace("%",r"\%"), f"{r.annualized_volatility:.2%}".replace("%",r"\%"), f"{r.sharpe_ratio:.3f}", f"{r.max_drawdown:.2%}".replace("%",r"\%")] for r in annual.itertuples()]
    (thesis / "generated_primary_annual.tex").write_text(tex_table(["年份", "净年化收益", "年化波动", "夏普", "最大回撤"], yr_rows, "lrrrr"), encoding="utf-8")
    weights = result.set_index("date").filter(regex="^weight_")
    top = weights.mean().nlargest(6).index
    chart = weights[top].rename(columns=lambda c: c.removeprefix("weight_"))
    chart["其他"] = 1 - chart.sum(axis=1)
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "DejaVu Sans"]
    chart.plot.area(figsize=(12,5), linewidth=0, ylim=(0,1), title="主模型持仓结构（周频）")
    plt.ylabel("权重")
    plt.legend(loc="upper center", bbox_to_anchor=(.5,-.12), ncol=4)
    plt.tight_layout()
    plt.savefig(ROOT / "results/figures/primary_weights.png", dpi=180, bbox_inches="tight")
    plt.close()
    print(json.dumps(audit))


if __name__ == "__main__":
    main()
