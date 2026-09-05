"""Publish the designated rolling-calibration Global RRP and four comparisons."""
from pathlib import Path
import json
import logging
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.generate_thesis_numbers import _asset_stats_table, _etf_pool_table
from scripts.run_convex_adaptive_rrp import run_hrp_like, slice_and_rebase_result, summarize_result
from src.benchmarks import run_benchmark_backtest
from src.data_loader import load_data
from src.public_labels import validate_publication_models
from src.utils import get_config


PRIMARY_FOLDER = ROOT / "results/global_rrp_rolling_252"
PRIMARY_SPECIFICATION = "annual_prior_only_penalty_calibration_252"


def tex_table(headers, rows, align):
    return "\n".join([
        r"\begin{tabular}{" + align + "}",
        r"\toprule",
        " & ".join(headers) + r"\\\midrule",
        *[" & ".join(row) + r"\\" for row in rows],
        r"\bottomrule",
        r"\end{tabular}",
    ])


def pct(value):
    return f"{value * 100:.2f}" + r"\%"


def main():
    logging.getLogger().setLevel(logging.ERROR)
    tables = ROOT / "results/tables"
    thesis = ROOT / "report/thesis_latex"
    source_summary = json.loads((PRIMARY_FOLDER / "summary.json").read_text(encoding="utf-8"))
    source_audit = json.loads((PRIMARY_FOLDER / "audit.json").read_text(encoding="utf-8"))
    if source_summary["status"] != "passed" or source_audit["status"] != "passed":
        raise ValueError("The designated rolling Global RRP path has not passed verification")

    source_config = json.loads(
        (PRIMARY_FOLDER / "configuration.json").read_text(encoding="utf-8")
    )
    cfg = get_config(source_config)
    if cfg["trading_days_per_year"] != 252 or cfg["lookback_days"] != 252:
        raise ValueError("The designated primary path must use both 252-day conventions")

    primary = pd.read_csv(PRIMARY_FOLDER / "daily_returns.csv", parse_dates=["date"])
    solver = pd.read_csv(
        PRIMARY_FOLDER / "solver.csv", parse_dates=["date", "information_cutoff"]
    )
    solver = solver[solver.date.between(cfg["evaluation_start_date"], cfg["evaluation_end_date"])]
    covariance = pd.read_csv(PRIMARY_FOLDER / "covariance.csv", parse_dates=["date"])
    covariance = covariance[
        covariance.date.between(cfg["evaluation_start_date"], cfg["evaluation_end_date"])
    ]
    usage = pd.read_csv(PRIMARY_FOLDER / "asset_participation.csv")
    schedule = pd.read_csv(PRIMARY_FOLDER / "selected_schedule.csv")
    candidates = pd.read_csv(PRIMARY_FOLDER / "validation_candidates.csv")
    protocol = json.loads((PRIMARY_FOLDER / "protocol.json").read_text(encoding="utf-8"))

    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    models = {"Global RRP": primary}
    for name, key in [("HRP Benchmark", "hrp"), ("HERC Benchmark", "herc")]:
        print("Running", name, flush=True)
        models[name] = run_hrp_like(returns, key, 3.0)
    for name in ["Equal Weight", "60/40 Benchmark"]:
        benchmark_name = "Equal Weight Benchmark" if name == "Equal Weight" else name
        models[name] = run_benchmark_backtest(
            returns, benchmark_name, transaction_cost_bps=3.0
        )

    summaries = []
    daily = {}
    for name, result in models.items():
        net = result.net_return if "net_return" in result else result.portfolio_return
        gross = (
            result.gross_return
            if "gross_return" in result
            else net + result.turnover.fillna(0.0) * 0.0003
        )
        result = slice_and_rebase_result(
            result.assign(net_return=net, gross_return=gross), cfg["evaluation_start_date"]
        )
        result = result[pd.to_datetime(result.date) <= pd.Timestamp(cfg["evaluation_end_date"])]
        result = result.reset_index(drop=True)
        pd.testing.assert_series_equal(result.date, primary.date, check_names=False)
        if not np.isfinite(result.net_return).all():
            raise ValueError(f"Nonfinite returns in {name}")
        daily[name] = result
        summaries.append(summarize_result(name, result, cfg["evaluation_start_date"], cfg))

    summary = pd.DataFrame(summaries)
    validate_publication_models(summary.model)
    summary["role"] = np.where(summary.model.eq("Global RRP"), "primary", "comparison")
    summary["risk_free_rate"] = 0.0
    summary["rebalance_frequency"] = np.where(summary.role.eq("primary"), "W", "M")
    row = summary.iloc[0]
    for field in [
        "net_annual_return", "annualized_volatility", "sharpe_ratio", "max_drawdown"
    ]:
        if not np.isclose(row[field], source_summary[field], atol=1e-12, rtol=0.0):
            raise ValueError(f"Published primary metric does not match saved source: {field}")

    for name, result in daily.items():
        slug = name.lower().replace("/", "_").replace(" ", "_")
        result.to_csv(tables / f"comparison_{slug}_returns.csv", index=False)
    for filename in [
        "model_performance_summary.csv",
        "convex_adaptive_performance_summary.csv",
        "hrp_comparison.csv",
    ]:
        summary.to_csv(tables / filename, index=False)
    solver.to_csv(tables / "global_rrp_solver_diagnostics.csv", index=False)
    covariance.to_csv(tables / "global_rrp_covariance_diagnostics.csv", index=False)
    usage.to_csv(tables / "primary_asset_participation.csv", index=False)
    schedule.to_csv(tables / "primary_parameter_schedule.csv", index=False)
    schedule.to_csv(tables / "primary_constraint_comparison.csv", index=False)
    candidates.to_csv(tables / "primary_calibration_candidates.csv", index=False)

    annual = pd.DataFrame([
        {
            "year": int(year),
            **summarize_result(
                "Global RRP", frame, str(pd.to_datetime(frame.date).min().date()), cfg
            ),
        }
        for year, frame in primary.groupby(primary.date.dt.year)
    ])
    annual.to_csv(tables / "primary_annual_summary.csv", index=False)

    audit = {
        "status": "passed",
        "model": "Global RRP",
        "problem_is_dcp": bool(solver.problem_is_dcp.all()),
        "solver_success": bool(solver.solver_success.all()),
        "covariance_fallback_count": int(covariance.covariance_fallback_used.sum()),
        "max_constraint_violation": float(solver.max_constraint_violation.max()),
        "future_information_count": int((solver.information_cutoff >= solver.date).sum()),
        "sharpe_target": 1.0,
        "sharpe_target_met": bool(row.sharpe_ratio >= 1.0),
        "preferred_net_return_target": 0.10,
        "preferred_net_return_target_met": bool(row.net_annual_return >= 0.10),
        "acceptable_net_return_floor": 0.08,
        "acceptable_net_return_floor_met": bool(row.net_annual_return >= 0.08),
        "max_drawdown_guardrail": -0.08,
        "max_drawdown_guardrail_met": bool(row.max_drawdown >= -0.08),
        "target_met": bool(
            row.sharpe_ratio >= 1.0
            and row.net_annual_return >= 0.08
            and row.max_drawdown >= -0.08
        ),
        "parameter_selection_informative_years": int(
            (schedule.within_one_standard_error_count < schedule.candidate_count).sum()
        ),
        "parameter_selection_years": int(len(schedule)),
        "all_eligible_assets_ever_used": bool(
            usage.loc[usage.eligible_weeks.gt(0), "ever_used"].all()
        ),
        "daily_observations": int(len(primary)),
        "rebalance_count": int(primary.is_rebalance_day.sum()),
        "risk_free_rate": 0.0,
        "annualization_days": 252,
        "estimation_window_days": 252,
        "selection_is_exploratory": True,
        "source_audit": source_audit,
    }
    if (
        not audit["problem_is_dcp"]
        or not audit["solver_success"]
        or audit["covariance_fallback_count"]
        or audit["future_information_count"]
    ):
        raise ValueError("Primary publication audit failed")
    (tables / "primary_publication_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )

    configuration_record = {
        "model": "Global RRP",
        "selected_specification": PRIMARY_SPECIFICATION,
        "configuration": source_config,
        "calibration_protocol": protocol,
        "selection": (
            "Annual penalties use strictly earlier calibration and validation blocks. "
            "All nine candidates were within one Sharpe standard error in every year, "
            "so the data do not identify unique coefficients. Primary status records "
            "the designated research specification."
        ),
    }
    (tables / "primary_model_configuration.json").write_text(
        json.dumps(configuration_record, indent=2), encoding="utf-8"
    )

    cash_mean = float(primary["weight_日利ETF"].mean())
    cash_max = float(primary["weight_日利ETF"].max())
    defensive_names = ["日利ETF", "5年国债ETF", "10年国债ETF", "信用债ETF"]
    defensive_mean = float(
        primary[[f"weight_{name}" for name in defensive_names]].sum(axis=1).mean()
    )
    macros = {
        "evalStartDate": cfg["evaluation_start_date"],
        "evalEndDate": cfg["evaluation_end_date"],
        "etfCount": "30",
        "txCostBps": "3",
        "annualizationDays": "252",
        "lookbackDays": "252",
        "primaryRebalances": str(audit["rebalance_count"]),
        "primaryObservations": str(len(primary)),
        "primaryCashMean": pct(cash_mean),
        "primaryCashMax": pct(cash_max),
        "primaryDefensiveMean": pct(defensive_mean),
        "primaryAssetsUsed": str(int(usage.ever_used.sum())),
        "primarySelectionInformativeYears": str(audit["parameter_selection_informative_years"]),
        "primaryParameterYears": str(audit["parameter_selection_years"]),
        "primaryReturnTargetDef": (
            r"$R_t=\mu_t^\mathsf{T}q_t$，即当期可行风险预算参考的预测收益"
        ),
    }
    for suffix, field in [
        ("GrossReturn", "gross_annual_return"),
        ("NetReturn", "net_annual_return"),
        ("Volatility", "annualized_volatility"),
        ("MaxDD", "max_drawdown"),
        ("MonthlyTurnover", "avg_monthly_turnover"),
        ("CostDrag", "transaction_cost_drag"),
        ("CVaR", "cvar_95_daily_loss"),
    ]:
        macros["global" + suffix] = pct(row[field])
    for suffix, field in [
        ("Sharpe", "sharpe_ratio"),
        ("Sortino", "sortino_ratio"),
        ("Calmar", "calmar_ratio"),
    ]:
        macros["global" + suffix] = f"{row[field]:.3f}"
    (thesis / "generated_numbers.tex").write_text(
        "\n".join(f"\\newcommand{{\\{key}}}{{{value}}}" for key, value in macros.items())
        + "\n",
        encoding="utf-8",
    )

    performance_rows = [
        [
            r.model,
            pct(r.net_annual_return),
            pct(r.annualized_volatility),
            f"{r.sharpe_ratio:.3f}",
            pct(r.max_drawdown),
            pct(r.avg_monthly_turnover),
        ]
        for r in summary.itertuples()
    ]
    (thesis / "generated_global_performance.tex").write_text(
        tex_table(
            ["模型", "净年化收益", "年化波动", "夏普", "最大回撤", "月均换手"],
            performance_rows,
            "lrrrrr",
        ),
        encoding="utf-8",
    )
    annual_rows = [
        [
            str(r.year),
            pct(r.net_annual_return),
            pct(r.annualized_volatility),
            f"{r.sharpe_ratio:.3f}",
            pct(r.max_drawdown),
        ]
        for r in annual.itertuples()
    ]
    (thesis / "generated_primary_annual.tex").write_text(
        tex_table(
            ["年份", "净年化收益", "年化波动", "夏普", "最大回撤"],
            annual_rows,
            "lrrrr",
        ),
        encoding="utf-8",
    )
    schedule_rows = [
        [
            str(pd.Timestamp(r.effective_date).year),
            f"{r.rrp_variance_penalty:.4g}",
            f"{r.lambda_pen:.4g}",
            f"{r.validation_net_sharpe:.3f}",
            f"{int(r.within_one_standard_error_count)}/{int(r.candidate_count)}",
        ]
        for r in schedule.itertuples()
    ]
    (thesis / "generated_primary_constraints.tex").write_text(
        tex_table(
            ["生效年", "$\\lambda_{v,t}$", "$\\lambda_{r,t}$", "验证夏普", "标准误集合"],
            schedule_rows,
            "lrrrr",
        ),
        encoding="utf-8",
    )
    _etf_pool_table(thesis)
    _asset_stats_table(pd.read_csv(tables / "asset_descriptive_statistics.csv"), thesis)
    print(json.dumps(audit), flush=True)


if __name__ == "__main__":
    main()
