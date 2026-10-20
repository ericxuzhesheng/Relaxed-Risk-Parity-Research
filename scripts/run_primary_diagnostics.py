"""Ablations, ex-ante risk matching and robustness for the published Global RRP.

All variants are diagnostic experiments, never candidates for replacing the
primary specification. Run after publish_global_rrp.py; --render-only rebuilds
the figures and TeX from the saved diagnostic CSVs.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict
import json
import logging
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.publish_global_rrp import pct, tex_table
from scripts.render_publication_figures import save, style
from scripts.run_convex_adaptive_rrp import slice_and_rebase_result, summarize_result
from src.backtest import run_static_backtest
from src.benchmarks import run_benchmark_backtest
from src.convex_adaptive_rrp import drift_weights
from src.covariance_estimators import estimate_covariance
from src.data_loader import load_data
from src.investable import investable_columns, portfolio_return_for_available
from src.statistical_tests import sharpe_difference_block_bootstrap

TABLES = ROOT / "results/tables"
OUTPUT = ROOT / "results/primary_diagnostics"
THESIS = ROOT / "report/thesis_latex"
LABELS = {
    "primary": "Global RRP",
    "reference": "仅风险预算参考",
    "no_shortfall": "收益短缺惩罚置零",
    "no_variance": "方差惩罚置零",
    "frozen": "冻结评价首年参数",
    "matched_equal": "Equal Weight（风险匹配）",
    "matched_60_40": "60/40 Benchmark（风险匹配）",
    "half_life_10": "均值半衰期10日",
    "half_life_40": "均值半衰期40日",
    "delay_1": "延后一交易日执行",
}
ABLATIONS = ["primary", "reference", "no_shortfall", "no_variance", "frozen"]
MATCHED = ["primary", "matched_equal", "matched_60_40"]
PAIRS = ["reference", "no_shortfall", "frozen", "matched_equal", "matched_60_40"]
PERIODS = [
    ("2018--2020", "2018-01-02", "2020-12-31"),
    ("2021--2023", "2021-01-01", "2023-12-31"),
    ("2024--2026", "2024-01-01", "2026-10-16"),
]


def risk_matched_weights(base, cash, covariance, target_variance):
    """Largest unlevered base fraction meeting an ex-ante variance ceiling.

    If the ceiling is below the attainable minimum, return the minimum-variance
    mixture and flag it. If the whole base already meets it, retain that base.
    """
    base, cash = np.asarray(base), np.asarray(cash)
    delta = base - cash
    a = float(delta @ covariance @ delta)
    b = float(2 * cash @ covariance @ delta)
    c = float(cash @ covariance @ cash)
    if a <= 1e-16:
        fraction = 1.0
    elif a + b + c <= target_variance:
        fraction = 1.0
    else:
        minimum = float(np.clip(-b / (2 * a), 0, 1))
        if a * minimum**2 + b * minimum + c > target_variance:
            fraction = minimum
        else:
            root = (-b + np.sqrt(max(b*b - 4*a*(c-target_variance), 0))) / (2*a)
            fraction = float(np.clip(root, 0, 1))
    weights = cash + fraction * delta
    variance = float(weights @ covariance @ weights)
    return weights, fraction, variance <= target_variance + 1e-12


def replay_targets(returns, targets, *, delay=0, cost_bps=3.0):
    """Trade saved decision weights, then drift; delay shifts execution only."""
    if delay < 0:
        raise ValueError("delay must be nonnegative")
    execution = {}
    for date, row in targets.iterrows():
        position = returns.index.get_indexer([date])[0]
        if position < 0:
            raise ValueError("target date is outside the return calendar")
        if position + delay < len(returns):
            execution[returns.index[position + delay]] = row.to_numpy(float)
    weights = np.zeros(returns.shape[1])
    rows = []
    for date, row in returns.iterrows():
        previous = weights.copy()
        traded = date in execution
        if traded:
            weights = execution[date].copy()
        turnover = float(np.abs(weights-previous).sum()) if traded else 0.0
        if row[weights > 1e-8].isna().any():
            raise ValueError(f"Missing held return at {date}")
        gross = portfolio_return_for_available(row, weights)
        cost = turnover * cost_bps / 10000
        rows.append({
            "date": date, "gross_return": gross, "net_return": gross-cost,
            "transaction_cost": cost, "turnover": turnover,
            "is_rebalance_day": traded,
            **{f"weight_{name}": weights[i] for i, name in enumerate(returns.columns)},
        })
        weights = drift_weights(weights, row)
    return pd.DataFrame(rows)


def experiment_config(config, key):
    result = deepcopy(config)
    schedule = result["rrp_parameter_schedule"]
    if key in {"no_shortfall", "no_variance"}:
        field = "lambda_pen" if key == "no_shortfall" else "rrp_variance_penalty"
        result[field] = 0.0
        for row in schedule:
            row[field] = 0.0
    elif key == "frozen":
        prior = [r for r in schedule if r["effective_date"] <= config["evaluation_start_date"]]
        fixed = prior[-1]
        if fixed["information_end"] >= config["evaluation_start_date"]:
            raise ValueError("Fixed coefficients must be known before evaluation")
        for row in schedule:
            if row["effective_date"] >= fixed["effective_date"]:
                for field in ("rrp_variance_penalty", "lambda_pen"):
                    row[field] = fixed[field]
    elif key.startswith("half_life_"):
        result["mean_ewma_halflife"] = float(key.rsplit("_", 1)[1])
    return result


def validate_path(result, config):
    public = slice_and_rebase_result(result, config["evaluation_start_date"])
    public = public[public.date <= config["evaluation_end_date"]].reset_index(drop=True)
    weights = public.filter(regex="^weight_").to_numpy(float)
    np.testing.assert_allclose(weights.sum(axis=1), 1, atol=1e-6)
    if weights.min() < -1e-8 or not np.isfinite(public.net_return).all():
        raise ValueError("Invalid diagnostic path")
    np.testing.assert_allclose(
        public.gross_return-public.net_return,
        public.turnover*config["transaction_cost_bps"]/10000, atol=1e-12,
    )
    return public


def run_experiments(*, reuse_solver_paths=False):
    logging.getLogger().setLevel(logging.ERROR)
    config = json.loads((TABLES / "primary_model_configuration.json").read_text("utf-8"))["configuration"]
    returns = load_data(source="tushare", force_update=False).dropna(how="all")
    # 504 warm-up observations give the last pre-evaluation decision its full
    # 252-day estimation history. Public-path parity is asserted below.
    start = returns.index.searchsorted(config["evaluation_start_date"])
    returns = returns.iloc[max(0, start-504):]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    if reuse_solver_paths:
        prior = json.loads((OUTPUT / "protocol.json").read_text("utf-8"))
        if prior["primary_configuration"] != config:
            raise ValueError("Saved solver paths use a different primary configuration")
    protocol = {
        "evaluation_start": config["evaluation_start_date"],
        "evaluation_end": config["evaluation_end_date"],
        "primary_configuration": config,
        "experiments": LABELS,
        "cost_bps": [0, 3, 10, 20],
        "subperiods": PERIODS,
        "bootstrap": {"resamples": 2000, "block_sizes": [5, 21, 63], "seed": 20261020,
                      "confidence": .95, "pairs": PAIRS},
        "role": "historical diagnostic experiments; no primary model selection",
        "frozen_parameters": "last schedule entry effective before evaluation; retained throughout evaluation",
        "ablation_parameters": "retain the primary annual schedule for the remaining objective terms",
        "mean_sensitivity": "retain primary annual penalties; change only the EWMA half-life",
        "risk_matching": "largest base fraction in [0,1] with prior sample covariance variance <= contemporaneous primary; LW feasibility recorded separately",
        "execution_delay": "trade the original targets one observed trading day later; recompute drift and costs",
    }
    (OUTPUT / "protocol.json").write_text(json.dumps(protocol, indent=2, ensure_ascii=False), "utf-8")
    paths, full, solvers = {}, {}, {}
    for key in ABLATIONS + ["half_life_10", "half_life_40"]:
        print(f"Running diagnostic: {key}", flush=True)
        if reuse_solver_paths:
            paths[key] = validate_path(pd.read_csv(OUTPUT / f"{key}_daily.csv", parse_dates=["date"]), config)
            solvers[key] = pd.read_csv(OUTPUT / f"{key}_solver.csv", parse_dates=["date"])
            continue
        diagnostics = {}
        cfg = experiment_config(config, key)
        result = run_static_backtest(returns, "standard" if key == "reference" else "relaxed", cfg, diagnostics)
        public = validate_path(result, cfg)
        solver = diagnostics["solver"]
        solver = solver[pd.to_datetime(solver.date) >= config["evaluation_start_date"]]
        if not solver.solver_success.all() or not solver.problem_is_dcp.all():
            raise ValueError(f"Solver failure in {key}")
        if (pd.to_datetime(solver.information_cutoff) >= pd.to_datetime(solver.date)).any():
            raise ValueError(f"Future input in {key}")
        paths[key], full[key], solvers[key] = public, result, solver
        public.to_csv(OUTPUT / f"{key}_daily.csv", index=False)
        solver.to_csv(OUTPUT / f"{key}_solver.csv", index=False)
    if reuse_solver_paths:
        from src.incremental_backtest import _restore_frame
        checkpoint = json.loads((ROOT / "results/backtest_checkpoints/global_rrp.json").read_text("utf-8"))
        full["primary"] = _restore_frame(checkpoint["result"])
        cached_public = validate_path(full["primary"], config)
        pd.testing.assert_series_equal(cached_public.date, paths["primary"].date)
        np.testing.assert_allclose(cached_public.net_return, paths["primary"].net_return, atol=1e-12, rtol=0)
    published = pd.read_csv(TABLES / "comparison_global_rrp_returns.csv", parse_dates=["date"])
    pd.testing.assert_series_equal(paths["primary"].date, published.date)
    parity_error = float(np.max(np.abs(paths["primary"].net_return-published.net_return)))
    np.testing.assert_allclose(paths["primary"].net_return, published.net_return, atol=1e-8, rtol=0)

    print("Running ex-ante risk matching and execution replay", flush=True)
    columns = [f"weight_{c}" for c in returns.columns]
    primary_full = full["primary"].set_index("date")
    targets = primary_full.loc[primary_full.is_rebalance_day, columns]
    targets = targets[targets.sum(axis=1) > .99].copy()
    targets = targets.loc[targets.index >= returns.index[252]]
    targets.columns = returns.columns
    contexts = {}
    for date in targets.index:
        window = returns.loc[returns.index < date].iloc[-252:]
        active = investable_columns(window, min_observations=60)
        sigma = estimate_covariance(window[active], method="sample", trading_days=252,
                                    annualize=True, allow_fallback=False).to_numpy()
        lw = estimate_covariance(window[active], method="ledoit_wolf", trading_days=252,
                                 annualize=True, allow_fallback=False).to_numpy()
        contexts[date] = (active, sigma, lw, window.index.max())
    matching_rows = []
    for key, name in [("matched_equal", "Equal Weight Benchmark"), ("matched_60_40", "60/40 Benchmark")]:
        benchmark = run_benchmark_backtest(returns, name, transaction_cost_bps=3, rebalance_frequency="W").set_index("date")
        matched = []
        for date, target in targets.iterrows():
            active, sigma, lw, cutoff = contexts[date]
            base = benchmark.loc[date, [f"weight_{c}" for c in active]].to_numpy(float)
            np.testing.assert_allclose(base.sum(), 1, atol=1e-6)
            if "日利ETF" not in active:
                raise ValueError("Risk matching requires an eligible money-market ETF")
            cash = np.zeros(len(active))
            cash[active.index("日利ETF")] = 1
            primary = target[active].to_numpy(float)
            target_var = float(primary @ sigma @ primary)
            mixed, fraction, feasible = risk_matched_weights(base, cash, sigma, target_var)
            lw_target = float(primary @ lw @ primary)
            lw_mixed, lw_fraction, lw_feasible = risk_matched_weights(base, cash, lw, lw_target)
            weights = pd.Series(0.0, index=returns.columns)
            weights.loc[active] = mixed
            matched.append(weights)
            matching_rows.append({
                "experiment": key, "date": date, "information_cutoff": cutoff,
                "base_fraction": fraction, "target_volatility": np.sqrt(target_var),
                "matched_volatility": np.sqrt(float(mixed @ sigma @ mixed)),
                "ceiling_feasible": feasible,
                "risk_gap": np.sqrt(float(mixed @ sigma @ mixed))-np.sqrt(target_var),
                "lw_base_fraction": lw_fraction, "lw_ceiling_feasible": lw_feasible,
                "lw_risk_gap": np.sqrt(float(lw_mixed @ lw @ lw_mixed))-np.sqrt(lw_target),
                "cash_sample_volatility": np.sqrt(float(cash @ sigma @ cash)),
                "cash_lw_volatility": np.sqrt(float(cash @ lw @ cash)),
            })
        frame = pd.DataFrame(matched, index=targets.index)
        full[key] = replay_targets(returns, frame)
        paths[key] = validate_path(full[key], config)
    replay = validate_path(replay_targets(returns, targets), config)
    np.testing.assert_allclose(replay.net_return, paths["primary"].net_return, atol=1e-12, rtol=0)
    paths["delay_1"] = validate_path(replay_targets(returns, targets, delay=1), config)
    for key in ["matched_equal", "matched_60_40", "delay_1"]:
        paths[key].to_csv(OUTPUT / f"{key}_daily.csv", index=False)
    match = pd.DataFrame(matching_rows)
    match = match[match.date >= config["evaluation_start_date"]]
    match.to_csv(TABLES / "primary_risk_matching.csv", index=False)

    summaries = []
    for key, result in paths.items():
        row = {"experiment": key, **summarize_result("Global RRP" if key not in MATCHED[1:] else
                ("Equal Weight" if key == "matched_equal" else "60/40 Benchmark"),
                result, config["evaluation_start_date"], config)}
        row["mean_cash_weight"] = result["weight_日利ETF"].mean()
        if key in solvers:
            solver = solvers[key]
            field = "final_max_risk_budget_error" if "final_max_risk_budget_error" in solver else "max_risk_budget_error"
            row["mean_max_risk_budget_error"] = solver[field].mean()
            row["mean_tracking_squared"] = solver.get("objective_tracking", pd.Series([0.0])).mean()
        summaries.append(row)
    summary = pd.DataFrame(summaries)
    summary.to_csv(TABLES / "primary_diagnostic_summary.csv", index=False)

    robustness = []
    for bps in [0, 3, 10, 20]:
        result = paths["primary"].copy()
        result["net_return"] = result.gross_return-result.turnover*bps/10000
        robustness.append({"experiment": f"cost_{bps}", "group": "cost", "cost_bps": bps,
                           **summarize_result("Global RRP", result, config["evaluation_start_date"], config)})
    for key in ["half_life_10", "half_life_40", "delay_1"]:
        robustness.append({"experiment": key, "group": "implementation",
                           **summarize_result("Global RRP", paths[key], config["evaluation_start_date"], config)})
    pd.DataFrame(robustness).to_csv(TABLES / "primary_robustness.csv", index=False)
    subperiods = []
    for label, start_date, end_date in PERIODS:
        for key in MATCHED:
            result = paths[key]
            result = result[result.date.between(start_date, end_date)]
            subperiods.append({"period": label, "experiment": key, "observations": len(result),
                              **summarize_result("Global RRP" if key == "primary" else
                                ("Equal Weight" if key == "matched_equal" else "60/40 Benchmark"),
                                result, start_date, config)})
    pd.DataFrame(subperiods).to_csv(TABLES / "primary_subperiods.csv", index=False)

    bootstrap = []
    # Drop the baseline NAV date to match the publication Sharpe convention.
    primary_returns = paths["primary"].set_index("date").net_return.iloc[1:]
    for block in [5, 21, 63]:
        for key in PAIRS:
            print(f"Paired bootstrap: {key}, block={block}", flush=True)
            pair = sharpe_difference_block_bootstrap(
                primary_returns, paths[key].set_index("date").net_return.iloc[1:],
                model_a="Global RRP", model_b=key, n_resamples=2000, block_size=block,
                trading_days=252, risk_free_rate=0.0, seed=20261020,
            )
            bootstrap.append(asdict(pair))
    pd.DataFrame(bootstrap).to_csv(TABLES / "primary_paired_bootstrap.csv", index=False)
    audit = {
        "status": "passed", "experiment_count": len(paths),
        "primary_return_parity_max_error": parity_error,
        "replay_parity": True, "long_only_fully_invested": True,
        "prior_only_solver_inputs": True, "cost_identity": True,
        "risk_matching_decisions": len(match),
        "risk_matching_infeasible_count": int((~match.ceiling_feasible).sum()),
        "risk_matching_max_abs_gap": float(match.risk_gap.abs().max()),
        "risk_matching_covariance": "prior 252-day sample covariance with PSD floor",
        "lw_risk_matching_infeasible_count": int((~match.lw_ceiling_feasible).sum()),
        "paired_bootstrap_rows": len(bootstrap),
        "confidence_intervals": "pointwise percentile intervals conditional on historical specification; no multiple-selection correction",
    }
    (TABLES / "primary_diagnostics_audit.json").write_text(json.dumps(audit, indent=2), "utf-8")
    print(json.dumps(audit), flush=True)


def render_artifacts():
    import matplotlib.pyplot as plt
    from matplotlib.ticker import PercentFormatter

    summary = pd.read_csv(TABLES / "primary_diagnostic_summary.csv").set_index("experiment")
    robust = pd.read_csv(TABLES / "primary_robustness.csv")
    periods = pd.read_csv(TABLES / "primary_subperiods.csv")
    bootstrap = pd.read_csv(TABLES / "primary_paired_bootstrap.csv")
    match = pd.read_csv(TABLES / "primary_risk_matching.csv")
    for name, keys in [("ablation", ABLATIONS), ("matched", MATCHED)]:
        rows = [[LABELS[key], pct(summary.loc[key, "net_annual_return"]),
                 pct(summary.loc[key, "annualized_volatility"]),
                 f'{summary.loc[key, "sharpe_ratio"]:.3f}',
                 pct(summary.loc[key, "max_drawdown"]),
                 pct(summary.loc[key, "avg_monthly_turnover"])] for key in keys]
        (THESIS / f"generated_diagnostic_{name}.tex").write_text(tex_table(
            ["实验设定", "净年化收益", "年化波动", "夏普", "最大回撤", "月均换手"],
            rows, "lrrrrr"), "utf-8")
    rows = [[LABELS[key], f'{summary.loc[key, "mean_tracking_squared"]:.5f}',
             pct(summary.loc[key, "mean_max_risk_budget_error"]),
             pct(summary.loc[key, "mean_cash_weight"])] for key in ABLATIONS]
    (THESIS / "generated_diagnostic_mechanism.tex").write_text(tex_table(
        ["实验设定", "平均权重距离平方", "平均最大风险预算偏离", "平均货币权重"],
        rows, "lrrr"), "utf-8")
    rows = []
    for row in robust.itertuples():
        label = f"单边成本{int(row.cost_bps)} bps" if row.group == "cost" else LABELS[row.experiment]
        rows.append([label, pct(row.net_annual_return), pct(row.annualized_volatility),
                     f"{row.sharpe_ratio:.3f}", pct(row.max_drawdown)])
    (THESIS / "generated_diagnostic_robustness.tex").write_text(tex_table(
        ["检验设定", "净年化收益", "年化波动", "夏普", "最大回撤"], rows, "lrrrr"), "utf-8")
    rows = [[row.period, LABELS[row.experiment], pct(row.net_annual_return),
             f"{row.sharpe_ratio:.3f}", pct(row.max_drawdown)] for row in periods.itertuples()]
    (THESIS / "generated_diagnostic_subperiods.tex").write_text(tex_table(
        ["子区间", "配置", "净年化收益", "夏普", "最大回撤"], rows, "llrrr"), "utf-8")
    selected = bootstrap[bootstrap.block_size == 21]
    rows = [[LABELS[row.model_b], f"{row.observed_difference:.3f}",
             f"[{row.ci_low:.3f}, {row.ci_high:.3f}]"] for row in selected.itertuples()]
    (THESIS / "generated_diagnostic_bootstrap.tex").write_text(tex_table(
        ["比较对象", "主模型减比较对象的夏普差", "95\\%区间"], rows, "lrr"), "utf-8")
    macros = {}
    for prefix, key in [("diagReference", "reference"), ("diagNoShortfall", "no_shortfall"),
                        ("diagFrozen", "frozen"), ("diagMatchedEW", "matched_equal"),
                        ("diagMatchedSB", "matched_60_40"), ("diagDelay", "delay_1")]:
        for suffix, field in [("Return", "net_annual_return"), ("Vol", "annualized_volatility"),
                              ("DD", "max_drawdown"), ("Turnover", "avg_monthly_turnover")]:
            macros[prefix+suffix] = pct(summary.loc[key, field])
        macros[prefix+"Sharpe"] = f'{summary.loc[key, "sharpe_ratio"]:.3f}'
    macros["diagCostTwentyReturn"] = pct(robust.set_index("experiment").loc["cost_20", "net_annual_return"])
    macros["diagMatchDecisions"] = str(len(match))
    macros["diagMatchFeasible"] = str(int(match.ceiling_feasible.sum()))
    macros["diagLWMatchInfeasible"] = str(int((~match.lw_ceiling_feasible).sum()))
    macros["diagPrimaryRCError"] = pct(summary.loc["primary", "mean_max_risk_budget_error"])
    macros["diagReferenceRCError"] = pct(summary.loc["reference", "mean_max_risk_budget_error"])
    (THESIS / "generated_diagnostic_numbers.tex").write_text("\n".join(
        "\\newcommand{\\"+key+"}{"+value+"}" for key, value in macros.items())+"\n", "utf-8")

    style()
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "Arial"]
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    colors = ["#B51F35", "#123F70", "#176DA3", "#7C1735", "#476B94"]
    for ax, field, title in zip(axes, ["net_annual_return", "mean_max_risk_budget_error"],
                               ["净年化收益", "平均最大风险预算偏离"]):
        ax.barh([LABELS[k] for k in ABLATIONS], summary.loc[ABLATIONS, field], color=colors)
        ax.invert_yaxis()
        ax.xaxis.set_major_formatter(PercentFormatter(1))
        ax.set_title(title)
        ax.grid(axis="x", alpha=.4)
    fig.tight_layout()
    save(fig, "primary_diagnostic_ablation")
    fig, ax = plt.subplots(figsize=(10, 4.3))
    for key, color, line in zip(MATCHED, colors, ["-", "--", "-."]):
        path = pd.read_csv(OUTPUT / f"{key}_daily.csv", parse_dates=["date"])
        nav = (1+path.net_return).cumprod()
        ax.plot(path.date, nav/nav.iloc[0], label=LABELS[key], color=color, linestyle=line)
    ax.set_ylabel("净值（首日为1）")
    ax.legend()
    ax.grid(alpha=.4)
    fig.tight_layout()
    save(fig, "primary_diagnostic_risk_matched")
    fig, ax = plt.subplots(figsize=(10, 4))
    x = np.arange(len(PAIRS))
    for block, offset, color in zip([5, 21, 63], [-.2, 0, .2], colors):
        rows = bootstrap[bootstrap.block_size == block].set_index("model_b").loc[PAIRS]
        # Draw interval endpoints directly: percentile intervals need not
        # contain the original point estimate.
        ax.vlines(x+offset, rows.ci_low, rows.ci_high, colors=color, linewidth=2)
        ax.scatter(x+offset, rows.observed_difference, color=color, s=22, label=f"区块长度{block}日")
    ax.axhline(0, color="#777777", linewidth=.8)
    ax.set_xticks(x, [LABELS[k] for k in PAIRS], fontsize=9)
    ax.set_ylabel("主模型减比较对象的夏普差")
    ax.legend(ncol=3)
    ax.grid(axis="y", alpha=.4)
    fig.tight_layout()
    save(fig, "primary_diagnostic_bootstrap")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-only", action="store_true")
    parser.add_argument("--reuse-solver-paths", action="store_true",
                        help="Rebuild matching/replay/statistics from validated saved solver paths")
    args = parser.parse_args()
    if not args.render_only:
        run_experiments(reuse_solver_paths=args.reuse_solver_paths)
    render_artifacts()
