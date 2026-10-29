"""Reconcile risk contributions and document the two covariance scales."""
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd
from sklearn.covariance import LedoitWolf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.data_loader import load_data
from src.investable import investable_columns
from src.covariance_estimators import estimate_covariance
from src.asset_universe import ETF_UNIVERSE
from scripts.analyze_primary_attribution import GROUPS
from scripts.publish_global_rrp import tex_table, pct
from scripts.render_publication_figures import style, save


def tracking_risk_diagnostic(detail, thesis, tables):
    """Describe weight distance and risk-budget deviation without changing targets."""
    import matplotlib.pyplot as plt

    distance = detail.tracking_distance
    error = detail.max_relative_risk_budget_error
    threshold = distance.quantile(.25)
    small = detail.loc[distance <= threshold]
    example = small.loc[small.max_relative_risk_budget_error.idxmax()]
    summary = {
        "decisions": len(detail),
        "distance_median": distance.median(),
        "distance_p95": distance.quantile(.95),
        "risk_error_median_pp": error.median()*100,
        "risk_error_p95_pp": error.quantile(.95)*100,
        "spearman_correlation": distance.corr(error, method="spearman"),
        "low_distance_threshold": threshold,
        "low_distance_count": len(small),
        "low_distance_max_error_date": str(example.date.date()),
        "low_distance_example_distance": example.tracking_distance,
        "low_distance_max_error_pp": example.max_relative_risk_budget_error*100,
        "example_largest_deviation_asset": example.largest_deviation_asset,
    }
    pd.DataFrame([summary]).to_csv(tables / "primary_tracking_risk_summary.csv", index=False)
    detail[["date", "information_cutoff", "assets", "tracking_distance",
            "max_relative_risk_budget_error", "reference_risk_budget_error",
            "largest_deviation_asset", "primary_lw_volatility"]].to_csv(
        tables / "primary_tracking_risk.csv", index=False)
    (thesis / "generated_tracking_risk_table.tex").write_text(tex_table(
        ["统计量", "数值"],
        [["周度决策数", str(len(detail))],
         ["资本距离中位数 / 95\%分位数", f'{distance.median():.4f} / {distance.quantile(.95):.4f}'],
         ["风险偏离中位数 / 95\%分位数（百分点）", f'{error.median()*100:.2f} / {error.quantile(.95)*100:.2f}'],
         ["距离与风险偏离的秩相关", f'{summary["spearman_correlation"]:.3f}'],
         ["距离下四分位组的最大风险偏离（百分点）", f'{summary["low_distance_max_error_pp"]:.2f}']],
        "lr"), encoding="utf-8")
    macros = {
        "trackingRiskCorrelation": f'{summary["spearman_correlation"]:.3f}',
        "trackingLowThreshold": f'{threshold:.4f}',
        "trackingExampleDate": summary["low_distance_max_error_date"],
        "trackingExampleDistance": f'{example.tracking_distance:.4f}',
        "trackingExampleError": f'{summary["low_distance_max_error_pp"]:.2f}',
        "trackingExampleAsset": summary["example_largest_deviation_asset"],
    }
    (thesis / "generated_tracking_risk_numbers.tex").write_text("\n".join(
        "\\newcommand{\\"+key+"}{"+value+"}" for key,value in macros.items())+"\n", encoding="utf-8")
    style()
    fig, ax = plt.subplots(figsize=(8.2, 4.8))
    ax.scatter(distance, error*100, color="#194F7D", s=19, alpha=.55, label="Weekly decisions")
    ax.axvline(threshold, color="#B53B4A", linestyle="--", linewidth=1, label="Distance 25th percentile")
    ax.scatter([example.tracking_distance], [example.max_relative_risk_budget_error*100],
               color="#B53B4A", s=65, marker="D", zorder=4,
               label="Largest risk deviation in lower distance quartile")
    ax.set(xlabel="Capital-weight distance (L2)", ylabel="Maximum risk-budget deviation (percentage points)")
    ax.grid(alpha=.5)
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    save(fig, "primary_tracking_risk")
    return summary


def main():
    tables = ROOT / "results/tables"
    thesis = ROOT / "report/thesis_latex"
    returns = load_data(source="tushare", force_update=False)
    primary = pd.read_csv(tables / "comparison_global_rrp_returns.csv", parse_dates=["date"]).set_index("date")
    reference = pd.read_csv(ROOT / "results/primary_diagnostics/reference_daily.csv", parse_dates=["date"]).set_index("date")
    solver = pd.read_csv(tables / "global_rrp_solver_diagnostics.csv", parse_dates=["date"]).set_index("date")
    matching = pd.read_csv(tables / "primary_risk_matching.csv", parse_dates=["date"])
    dates = primary.index[primary.is_rebalance_day]
    assert set(dates) == set(matching.date)
    assert set(dates) == set(solver.index)
    assert primary.index.equals(reference.index)
    group_map = {a.new_name: GROUPS.get(a.asset_class, "境内权益") for a in ETF_UNIVERSE}
    rows, contributions = [], []
    max_euler_error = max_lw_error = 0.0
    for date in dates:
        window = returns.loc[returns.index < date].iloc[-252:]
        active = investable_columns(window, min_observations=60)
        complete = window[active].dropna(how="any")
        x = complete.to_numpy()
        x = x - x.mean(axis=0)
        empirical = x.T @ x / len(x)
        estimator = LedoitWolf().fit(complete.to_numpy())
        delta = estimator.shrinkage_
        target = np.trace(empirical) / len(active)
        formula = (1-delta)*empirical + delta*target*np.eye(len(active))
        max_lw_error = max(max_lw_error, float(np.max(np.abs(formula-estimator.covariance_))))
        sigma = estimate_covariance(window[active], method="ledoit_wolf", trading_days=252, annualize=True, allow_fallback=False).to_numpy()
        sample = estimate_covariance(window[active], method="sample", trading_days=252, annualize=True, allow_fallback=False).to_numpy()
        w = primary.loc[date, ["weight_"+a for a in active]].to_numpy(float)
        q = reference.loc[date, ["weight_"+a for a in active]].to_numpy(float)
        tracking = float(np.linalg.norm(w-q))
        np.testing.assert_allclose(tracking**2, solver.loc[date, "objective_tracking"], atol=1e-7, rtol=0)
        reference_rrc = q*(sigma@q)/float(q@sigma@q)
        variance, sample_variance = float(w @ sigma @ w), float(w @ sample @ w)
        rc = w * (sigma @ w) / np.sqrt(variance)
        rrc, sample_rrc = rc / np.sqrt(variance), w * (sample @ w) / sample_variance
        max_euler_error = max(max_euler_error, abs(rc.sum()-np.sqrt(variance)), abs(rrc.sum()-1), abs(sample_rrc.sum()-1))
        cash = active.index("日利ETF")
        rows.append({
            "date": date, "information_cutoff": complete.index.max(), "observations": len(x),
            "assets": len(active), "shrinkage": delta,
            "sample_cash_volatility": np.sqrt(sample[cash,cash]),
            "lw_cash_volatility": np.sqrt(sigma[cash,cash]),
            "primary_lw_volatility": np.sqrt(variance),
            "primary_sample_volatility": np.sqrt(sample_variance),
            "max_relative_risk_budget_error": np.max(np.abs(rrc-1/len(active))),
            "tracking_distance": tracking,
            "reference_risk_budget_error": np.max(np.abs(reference_rrc-1/len(active))),
            "largest_deviation_asset": active[int(np.argmax(np.abs(rrc-1/len(active))))],
        })
        for i, asset in enumerate(active):
            contributions.append({"date": date, "asset": asset, "group": group_map[asset],
                                  "weight": w[i], "rrc_lw": rrc[i], "rrc_sample": sample_rrc[i]})
    detail = pd.DataFrame(rows)
    np.testing.assert_allclose(detail.max_relative_risk_budget_error, solver.loc[dates, "final_max_risk_budget_error"], atol=1e-8, rtol=0)
    np.testing.assert_allclose(detail.reference_risk_budget_error, solver.loc[dates, "reference_max_risk_budget_error"], atol=1e-5, rtol=0)
    assert max_lw_error < 1e-12 and max_euler_error < 1e-10
    published = pd.read_csv(tables / "primary_diagnostic_summary.csv").set_index("experiment")
    np.testing.assert_allclose(detail.max_relative_risk_budget_error.mean(),
                               published.loc["primary", "mean_max_risk_budget_error"], atol=1e-8, rtol=0)
    daily = pd.DataFrame(contributions)
    group_daily = daily.groupby(["date", "group"])[["weight","rrc_lw","rrc_sample"]].sum()
    group_daily = group_daily.reindex(pd.MultiIndex.from_product(
        [dates, list(dict.fromkeys(group_map.values()))], names=["date","group"]), fill_value=0)
    grouped = group_daily.groupby("group").mean().reindex(
        ["货币","国债","信用债","可转债","境内权益","境外权益","商品相关"])
    np.testing.assert_allclose(grouped.sum(), 1, atol=1e-10)
    detail.to_csv(tables / "primary_covariance_interpretation.csv", index=False)
    daily.to_csv(tables / "primary_risk_contribution_by_asset.csv", index=False)
    grouped.to_csv(tables / "primary_group_risk_contribution.csv")
    (thesis / "generated_group_risk_contribution.tex").write_text(tex_table(
        ["资产组", "平均资本权重", "LW风险贡献份额", "样本风险贡献份额"],
        [[g]+[pct(v) for v in row] for g,row in grouped.iterrows()], "lrrr"), encoding="utf-8")
    (thesis / "generated_covariance_interpretation.tex").write_text(tex_table(
        ["统计量", "最小值", "中位数", "最大值"],
        [[label]+[(f"{v:.0f}" if field=="observations" else pct(v))
          for v in [detail[field].min(), detail[field].median(), detail[field].max()]]
         for field,label in [("observations","共同完整观察数"),
                             ("shrinkage","收缩强度"),
                             ("sample_cash_volatility","货币ETF样本估计年化波动"),
                             ("lw_cash_volatility","货币ETF收缩估计年化波动")]], "lrrr"), encoding="utf-8")
    tracking_summary = tracking_risk_diagnostic(detail, thesis, tables)
    audit = {"status":"passed", "decisions":len(dates), "lw_formula_max_error":max_lw_error,
             "tracking_risk_diagnostic": tracking_summary,
             "tracking_and_risk_errors_reconciled_with_solver": True,
             "euler_identity_max_error":max_euler_error, "mean_risk_budget_error_matches_saved_solver":True,
             "risk_contribution_scope":"decision-date target weights; common eligible set; each matrix separately",
             "sample_covariance":"unbiased M-1 denominator plus PSD floor",
             "lw_covariance":"centered M denominator, isotropic Ledoit-Wolf shrinkage, annualization and PSD floor"}
    (tables / "primary_defense_consistency_audit.json").write_text(json.dumps(audit,indent=2),encoding="utf-8")
    print(json.dumps(audit))
    print(grouped.to_string())
    print(detail[["observations","shrinkage","sample_cash_volatility","lw_cash_volatility"]].describe().to_string())


if __name__ == "__main__":
    main()
