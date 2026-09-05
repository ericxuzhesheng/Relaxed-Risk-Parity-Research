"""Synchronize publication prose with the designated rolling Global RRP results."""
from pathlib import Path
import json

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]


def performance_table(data: pd.DataFrame, english: bool = False) -> str:
    rows = "\n".join(
        f"| {row.model} | {row.net_annual_return:.2%} | {row.annualized_volatility:.2%} | "
        f"{row.sharpe_ratio:.3f} | {row.sortino_ratio:.3f} | {row.max_drawdown:.2%} | "
        f"{row.avg_monthly_turnover:.2%} |"
        for row in data.itertuples()
    )
    if english:
        header = (
            "| Model | Net annual return | Volatility | Sharpe | Sortino | "
            "Max drawdown | Monthly turnover |\n"
        )
    else:
        header = "| 模型 | 净年化收益 | 年化波动 | 夏普 | Sortino | 最大回撤 | 月均换手 |\n"
    return header + "|---|---:|---:|---:|---:|---:|---:|\n" + rows


def main():
    tables = ROOT / "results/tables"
    data = pd.read_csv(tables / "model_performance_summary.csv")
    daily = pd.read_csv(tables / "comparison_global_rrp_returns.csv")
    usage = pd.read_csv(tables / "primary_asset_participation.csv")
    audit = json.loads((tables / "primary_publication_audit.json").read_text(encoding="utf-8"))
    zh_table = performance_table(data)
    en_table = performance_table(data, english=True)
    cash_mean = daily["weight_日利ETF"].mean()
    cash_max = daily["weight_日利ETF"].max()
    defensive = daily[[
        "weight_日利ETF", "weight_5年国债ETF", "weight_10年国债ETF", "weight_信用债ETF"
    ]].sum(axis=1).mean()
    primary = data.iloc[0]

    readme = f'''# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

[中文](#中文) · [English](#english) · [论文](report/thesis_latex/main.pdf) · [答辩](report/ppt/rrp_defense.pdf)

## 中文

### 模型与方法

**Global RRP** 是周频主模型。HRP Benchmark、HERC Benchmark、Equal Weight 和 60/40 Benchmark 是月频对照。正式结果只包含这五个模型。

主模型先求凸风险预算参考 $q_t$，再平衡参考跟踪、归一化方差和预测收益短缺。收益软目标取当期参考组合的预测收益。

$$
R_t = μ_tᵀq_t
$$

历史窗口和年化口径均为252个交易日。协方差采用 Ledoit-Wolf 收缩估计，收益均值采用20日半衰期指数加权估计。组合保持多头、满仓和无杠杆。

方差及收益短缺惩罚每年更新一次。每次更新先用较早的252日校准目标项尺度，再用随后252日净收益验证候选，所选参数在下一年冻结。全部步骤只读取参数生效日前的数据。

### 历史结果

评价区间为 **2018-01-02 至 2026-08-31**。收益保留极端观察，主指标采用 **rf=0、252日年化和单边3 bps约定成本**。

{zh_table}

Global RRP 的净年化收益为 **{primary.net_annual_return:.2%}**，夏普为 **{primary.sharpe_ratio:.3f}**，最大回撤为 **{primary.max_drawdown:.2%}**。主模型定位来自当前研究选择，不代表各项指标均优于对照。

日利ETF的平均权重为 **{cash_mean:.2%}**，最高权重为 **{cash_max:.2%}**。日利ETF、5年国债ETF、10年国债ETF和信用债ETF的平均合计权重为 **{defensive:.2%}**，这一结构解释了较低波动和有限收益。30只ETF均曾在合格期间形成实质持仓，优化器仍允许单期零权重。

年度验证中，每年9组候选都进入一倍夏普标准误集合，能够区分参数的年度为 **{audit['parameter_selection_informative_years']}/{audit['parameter_selection_years']}**。滚动规则可以复现，现有样本没有识别出唯一惩罚系数。

### 图表

![累计净值](results/figures/global_rrp_nav_comparison.png)

五个模型使用相同评价日期。主模型按周调仓，对照按月调仓。

![历史回撤](results/figures/global_rrp_drawdown_comparison.png)

回撤表示净值相对历史高点的跌幅。

![月均换手](results/figures/global_rrp_turnover_comparison.png)

换手按买入和卖出绝对权重变化之和计算，并按自然月汇总。

![历史尾部损失](results/figures/global_rrp_cvar_comparison.png)

95% CVaR 是实现收益的事后描述，主模型没有启用 CVaR 约束。

![周度持仓](results/figures/primary_weights.png)

### 数据与复现

资产池包含30只ETF和8类资产，另有6只候选资产不参与本次回测。缓存覆盖2007-01-18至2026-08-31。资产至少需要60个有效历史观察及正方差，上市前价格不回填。

配置 `TUSHARE_TOKEN` 后运行 `python scripts/run_primary_publication_pipeline.py`。入口刷新ETF数据，复跑年度滚动校准及四个对照，随后生成表格、红蓝配色图和两份PDF。无风险利率固定为零，不调用中债利率接口。

| 内容 | 文件 |
|---|---|
| 主模型配置 | [配置记录](results/tables/primary_model_configuration.json) |
| 发布审计 | [审计记录](results/tables/primary_publication_audit.json) |
| 年度参数 | [参数表](results/tables/primary_parameter_schedule.csv) |
| 候选验证 | [验证表](results/tables/primary_calibration_candidates.csv) |
| 自然年结果 | [年度绩效](results/tables/primary_annual_summary.csv) |
| 每周结果 | [持仓](results/tables/primary_weekly_holdings.csv) · [权重](results/tables/primary_weekly_weights.csv) · [周收益](results/tables/primary_weekly_summary.csv) |
| 资产池 | [资产定义](src/asset_universe.py) |
| 研究边界 | [模型治理](docs/MODEL_GOVERNANCE.md) |

逐周持仓只保存在仓库CSV中，论文和答辩展示持仓结构。图表同时提供矢量PDF和300 dpi PNG。

## English

### Models and method

**Global RRP** is the weekly primary model. HRP Benchmark, HERC Benchmark, Equal Weight and 60/40 Benchmark are monthly comparisons. These are the five models in the publication results.

The primary model first solves for a convex risk-budget reference. A second convex problem balances reference tracking, normalized variance and expected-return shortfall. Its feasible return target equals the predicted return of the contemporaneous reference portfolio.

$$
R_t = μ_tᵀq_t
$$

The lookback and annualization conventions both use 252 trading days. Covariance uses Ledoit-Wolf shrinkage, while expected returns use a 20-day half-life. The portfolio remains long-only, fully invested and unlevered.

Variance and shortfall penalties update annually. An earlier 252-day block calibrates objective scales, the following 252-day block evaluates candidates after costs, and the selected coefficients remain fixed for the next year. Every update uses information available before its effective date.

### Historical results

The common period is **2018-01-02 to 2026-08-31**. Results retain extreme returns and use a zero risk-free rate, 252-day annualization and assumed 3-bp one-way costs.

{en_table}

Global RRP records **{primary.net_annual_return:.2%}** net annual return, a **{primary.sharpe_ratio:.3f}** Sharpe ratio and **{primary.max_drawdown:.2%}** maximum drawdown. Primary status records the designated research specification and does not imply metric dominance.

The money-market ETF averages **{cash_mean:.2%}** and reaches **{cash_max:.2%}**. The money-market ETF and three bond ETFs together average **{defensive:.2%}**. All 30 ETFs receive material weight during eligible periods, while zero weight remains allowed on any date.

All nine candidates fall within one Sharpe standard error in every annual validation. The procedure is reproducible, but the current sample does not identify unique penalty coefficients.

Run `python scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set. The linked files contain the configuration, audit, annual parameter schedule, candidate results and complete weekly holdings. Detailed holdings stay in repository CSV files rather than the thesis or defense appendix.
'''
    (ROOT / "README.md").write_text(readme, encoding="utf-8")

    agents = ROOT / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    start = text.index("Main research line")
    end = text.index("## ETF Asset Pool")
    model_rows = "\n".join(
        f"| {name} | {'Primary weekly model' if index == 0 else 'Monthly comparison'} |"
        for index, name in enumerate(data.model)
    )
    text = text[:start] + f'''Main research line follows convex risk-budget references, a feasible expected-return target and annual prior-only penalty calibration for a 30-ETF universe.

## Core Models and Public Labels

Use exactly these five model names in current publication prose, tables and figures. Parameter and frequency variants are experiments.

| Public label | Role |
|---|---|
{model_rows}

## Main Positioning

- Global RRP is the weekly primary model. It is long-only, fully invested and unlevered.
- The lookback and annualization conventions both use 252 trading days. Inputs use Ledoit-Wolf covariance shrinkage and 20-day half-life EWMA means.
- The return target equals the predicted return of the contemporaneous feasible risk-budget reference. There is no fixed target multiplier.
- Variance and shortfall penalties update annually from two strictly earlier 252-day blocks. The first block determines candidate scales and the second evaluates candidates after costs. Selected values remain fixed for the following year.
- Every annual validation admits all nine candidates to the one-standard-error set. Report this weak identification and do not describe the selected coefficients as unique estimates.
- All eligible ETFs may participate, including zero weights on a date. There is no artificial minimum allocation.
- rf=0 is the current rate convention. ChinaBond refresh is not required.
- Primary status records the designated research specification. Historical results do not imply performance dominance or future guarantees.

## Latest Core Results

Always read CSV before writing numbers. Authoritative metrics are `results/tables/model_performance_summary.csv` and `hrp_comparison.csv`. The annual parameter path is `primary_parameter_schedule.csv`, and asset statistics are in `asset_descriptive_statistics.csv` under the same directory.

Current results use 2018-01-02 to 2026-08-31, unfiltered realized returns, rf=0, 252-day annualization and 3-bp one-way cost. Global RRP is weekly; comparisons are monthly. Cache starts 2007-01-18. Eligibility requires 60 prior valid observations and positive variance.

{en_table}

Primary average money-market weight is {cash_mean:.2%}, with a maximum of {cash_max:.2%}. The average combined money-market and three-bond weight is {defensive:.2%}. All 30 ETFs receive material allocations during eligible periods. The annual calibration has {audit['parameter_selection_informative_years']} informative years out of {audit['parameter_selection_years']} under the one-standard-error rule.

---

''' + text[end:]
    (ROOT / "AGENTS.md").write_text(text, encoding="utf-8")

    (ROOT / "docs/MODEL_GOVERNANCE.md").write_text(
        f'''# Model Governance

## Published models

Global RRP is the weekly primary model. HRP Benchmark, HERC Benchmark, Equal Weight and 60/40 Benchmark are monthly comparisons. Parameter and frequency variants remain research experiments.

## Primary specification

A convex log risk-budget problem produces the reference portfolio. A second convex problem balances reference tracking, normalized variance and expected-return shortfall. The return target equals the predicted return of the contemporaneous feasible reference portfolio.

The lookback and annualization conventions both use 252 trading days. Covariance uses Ledoit-Wolf shrinkage, and expected returns use a 20-trading-day half-life. Weights are long-only, sum to one and receive no post-solve risk scaling. The model has no active CVaR or turnover constraint. One-way costs of 3 bps multiply the sum of absolute weight trades.

Variance and shortfall penalties update once a year. An earlier 252-day block supplies objective-term ratios for three data-derived candidates per penalty. The following 252-day block evaluates the nine combinations after costs. Selection uses the one-standard-error Sharpe set, an adjacent qualifying grid point when available, lower turnover and quarterly stability. The selected values remain fixed for the next year.

All nine candidates enter the one-standard-error set in every annual validation. The procedure therefore limits arbitrary fixed coefficients but does not identify a unique pair. This uncertainty must accompany any discussion of the parameter schedule.

## Data and evidence

Evaluation spans 2018-01-02 through 2026-08-31 with rf=0. The 30-ETF pool excludes six candidates. Eligibility requires 60 prior valid observations and positive variance. Returns retain extremes, and pre-listing prices are not backfilled.

The historical path records {primary.net_annual_return:.2%} net annual return, {primary.annualized_volatility:.2%} annual volatility, a {primary.sharpe_ratio:.3f} Sharpe ratio and {primary.max_drawdown:.2%} maximum drawdown. All {int(usage.ever_used.sum())} ETFs receive material allocations during eligible periods.

Rebalance inputs precede the trading date. Saved daily returns reconcile target weights, drifted weights, turnover and costs. The backtest does not establish actual execution prices, market impact or capacity. Historical design choices also prevent an untouched model-selection claim.

## Reproduction

Run `scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set. The pipeline refreshes ETF data, reruns annual calibration and four comparisons, generates current tables and figures, synchronizes prose, compiles both PDFs and removes temporary files. The rf=0 convention does not require ChinaBond data.

Configuration and validation live in `results/tables/primary_model_configuration.json` and `primary_publication_audit.json`. The annual schedule and all candidate results are stored beside them. Complete weekly holdings remain in repository CSV files.
''',
        encoding="utf-8",
    )

    (ROOT / "docs/OVERFITTING_AUDIT.md").write_text(
        '''# 模型选择与信息时序

Global RRP 与四个对照共同构成五模型发布结果。主模型每年根据生效日前数据更新惩罚系数，年内不再改变。

每次年度更新使用两个连续的252日历史区间。较早区间生成候选尺度，随后区间按扣费净夏普验证九组组合。选择先保留一倍标准误范围内的候选，再检查相邻网格点，随后比较换手和季度稳定性。

十个年度中，每年九组候选都进入一倍标准误集合。现有样本无法精确区分参数，年度选择主要由换手和稳定性规则决定。该结果已写入发布审计，论文和答辩不得将系数称作唯一最优值。

## 可核查证据

- `results/tables/primary_model_configuration.json` 记录完整配置和校准规则。
- `results/tables/primary_parameter_schedule.csv` 记录年度参数及信息截止日。
- `results/tables/primary_calibration_candidates.csv` 记录全部九十次验证结果。
- `results/tables/primary_publication_audit.json` 记录时序与约束检查。
- `results/tables/global_rrp_solver_diagnostics.csv` 记录每次求解。

逐期输入早于调仓日，可以排除直接使用未来收益。研究者仍根据历史结果确定了当前方法，因此现有结果属于探索性证据。后续检验应冻结模型和评价口径，等待新增数据。
''',
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
