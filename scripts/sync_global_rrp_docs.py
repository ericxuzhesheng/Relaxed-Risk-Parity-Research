"""Synchronize current publication prose with authoritative saved metrics."""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]


def main():
    data = pd.read_csv(ROOT/'results/tables/convex_adaptive_performance_summary.csv')
    daily = pd.read_csv(ROOT/'results/tables/comparison_global_rrp_returns.csv')
    rows = '\n'.join(f'| {r.model} | {r.net_annual_return:.2%} | {r.annualized_volatility:.2%} | {r.sharpe_ratio:.3f} | {r.sortino_ratio:.3f} | {r.max_drawdown:.2%} | {r.avg_monthly_turnover:.2%} |' for r in data.itertuples())
    zh = '| 模型 | 净年化收益 | 年化波动 | 夏普 | Sortino | 最大回撤 | 月均换手 |\n|---|---:|---:|---:|---:|---:|---:|\n'+rows
    en = '| Model | Net annual return | Volatility | Sharpe | Sortino | Max drawdown | Monthly turnover |\n|---|---:|---:|---:|---:|---:|---:|\n'+rows
    cash_mean = daily['weight_日利ETF'].mean()
    cash_max = daily['weight_日利ETF'].max()
    r = data.iloc[0]
    readme = f'''# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

[中文](#中文) · [English](#english) · [论文](report/thesis_latex/main.pdf) · [答辩](report/ppt/rrp_defense.pdf)

## 中文

### 模型与方法

**Global RRP** 为周频主模型，HRP Benchmark、HERC Benchmark、Equal Weight 和 60/40 Benchmark 为月频对照。正式比较仅包含这五个模型。

主模型先求凸风险预算参考，再通过凸优化平衡参考跟踪、组合方差和预测收益短缺。历史窗口为 240 个交易日，使用 Ledoit–Wolf 收缩协方差、20 日半衰期指数加权收益估计，并以当期等权组合方差归一化风险项。组合多头、无杠杆，权重由优化器直接给出。

### 绩效与解释

共同评价区间为 **2018-01-02 至 2026-08-31**，保留极端收益，按 **243 日年化、rf=0、单边 3 bps** 的统一口径计算。

{zh}

数字来自[绩效表](results/tables/convex_adaptive_performance_summary.csv)。Global RRP 达到历史净年化约 10%、最大回撤不超过 8% 的研究目标。平均现金类 ETF 权重为 **{cash_mean:.2%}**，最高为 **{cash_max:.2%}**。月均换手按买入与卖出金额之和计算，较高换手使成本与执行能力成为重要限制；约定成本使年化收益减少 **{r.transaction_cost_drag*100:.2f} 个百分点**。

全部 30 只 ETF 都曾在合格期间形成实质持仓，允许当期零权重，不设微小持仓配额。逐期输入只使用调仓日前数据，完整历史复跑逐日一致。配置经过两轮历史估计实验筛选，属于探索性证据，仍需新增数据验证。

### 图表

![累计净值](results/figures/convex_adaptive_nav_comparison.png)

五模型累计净值使用同一评价区间。

![历史回撤](results/figures/convex_adaptive_drawdown_comparison.png)

回撤展示净值偏离历史高点的幅度，需与持仓结构共同理解。

![月均换手](results/figures/convex_adaptive_turnover_comparison.png)

换手按自然月汇总，主模型实际每周调仓。

![历史尾部损失](results/figures/convex_adaptive_cvar_comparison.png)

95% CVaR 描述历史日度尾部损失，未作为主模型的优化约束。

![频率比较](results/figures/rebalance_frequency_sensitivity.png)

频率实验保持估计方法及优化参数不变，排名仅为历史描述。

![周度持仓](results/figures/primary_weights.png)

### 数据与复现

资产池为 30 只 ETF、8 类资产，另有 6 只候选资产不参与回测。缓存覆盖 2007-01-18 至 2026-08-31。资产须有至少 60 个有效历史观察及正方差，上市前不回填数据。

配置 `TUSHARE_TOKEN` 后运行 `python scripts/run_primary_publication_pipeline.py`。入口刷新 ETF 数据，复跑固定配置、对照及频率实验，生成表格、红蓝配色图和两份 PDF，并清理临时文件。无风险利率固定为零，不调用中债利率接口。依赖见 `requirements.txt`，PDF 编译需要 XeLaTeX 和 BibTeX。

| 内容 | 文件 |
|---|---|
| 主模型参数 | [配置记录](results/tables/primary_model_configuration.json) |
| 信息时序与约束检查 | [发布审计](results/tables/primary_publication_audit.json) |
| 估计配置实验 | [实验结果](results/global_rrp_frontier/summary.csv) |
| 自然年结果 | [年度绩效](results/tables/primary_annual_summary.csv) |
| 每周持仓与收益 | [持仓 CSV](results/tables/primary_weekly_holdings.csv) · [权重矩阵](results/tables/primary_weekly_weights.csv) · [周收益 CSV](results/tables/primary_weekly_summary.csv) |
| 资产池 | [资产定义](src/asset_universe.py) |
| 研究边界 | [模型说明](docs/MODEL_GOVERNANCE.md) |

逐周明细仅保存在仓库 CSV 中，论文和答辩展示结构图，不附逐周明细表。图表提供矢量 PDF 与 300 dpi PNG。参考教材不随项目发布，旧归档不作为当前配置的验证证据。

## English

### Models and method

**Global RRP** is the weekly primary model. HRP Benchmark, HERC Benchmark, Equal Weight and 60/40 Benchmark are monthly comparisons. Parameter and frequency variants remain experiments within this five-model study.

The primary model uses a convex risk-budget reference and a convex objective for tracking, variance and expected-return shortfall. A 240-observation window feeds Ledoit–Wolf covariance shrinkage and exponentially weighted returns with a 20-trading-day half-life. Variance is normalized by the contemporaneous equal-weight portfolio variance. The portfolio is long-only and unlevered.

### Performance

The common period is **2018-01-02 to 2026-08-31**, with unfiltered returns, 243-day annualization, zero risk-free return and assumed 3-bp one-way costs.

{en}

The primary model meets the historical research target of approximately 10% net annual return and no more than 8% maximum drawdown. Its average money-market weight is **{cash_mean:.2%}**, reaching **{cash_max:.2%}**. Assumed costs reduce annual return by **{r.transaction_cost_drag*100:.2f} percentage points**. Monthly turnover sums both purchases and sales; execution and capacity remain unverified.

All 30 ETFs receive material holdings during eligible periods. Inputs precede each rebalance, and a full-history rerun reproduces every evaluated day. Selection followed two historical estimation rounds, so these results are exploratory rather than untouched model-selection evidence.

Run `python scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set. The links above provide configurations, audit records and complete weekly CSVs. PDFs contain allocation figures without detailed holdings appendices. Archived diagnostics do not validate the current specification.
'''
    (ROOT/'README.md').write_text(readme,encoding='utf-8')
    path = ROOT/'AGENTS.md'
    text = path.read_text(encoding='utf-8')
    start = text.index('Main research line:')
    end = text.index('## ETF Asset Pool')
    model_rows = '\n'.join(f'| {x} | {"Primary weekly model" if i == 0 else "Monthly comparison"} |' for i,x in enumerate(data.model))
    text = text[:start]+f'''Main research line follows convex risk-budget references, Global RRP return/risk relaxation, and historical estimation experiments for a 30-ETF universe.

## Core Models and Public Labels

Use exactly these five model names in current publication prose, tables and figures. Parameter and frequency variants are experiments.

| Public label | Role |
|---|---|
{model_rows}

## Main Positioning

- Global RRP is weekly, long-only and unlevered. It uses 240 historical observations, Ledoit–Wolf covariance shrinkage, 20-day half-life EWMA means and equal-weight variance normalization.
- The convex objective combines reference tracking, variance and return shortfall. Inherited coefficients are research conventions. There is no active CVaR or turnover constraint; costs are deducted from returns.
- All eligible ETFs may participate, including zero weights on a date. Audit actual participation without artificial minimum allocations.
- rf=0 is the only current rate convention. ChinaBond refresh is not required.
- Configuration selection followed historical structural research and two estimation rounds. Do not claim untouched OOS selection evidence or future guarantees.

## Latest Core Results

Always read CSV before writing numbers. Authoritative metrics are `results/tables/convex_adaptive_performance_summary.csv` and `hrp_comparison.csv`; asset statistics are in `asset_descriptive_statistics.csv`, and frequency results in `rebalance_frequency_sensitivity.csv` under the same directory.

Current results use 2018-01-02 to 2026-08-31, unfiltered realized returns, rf=0, 243-day annualization and 3-bp one-way cost. Global RRP is weekly; comparisons are monthly. Cache starts 2007-01-18. Eligibility requires 60 prior valid observations and positive variance.

{en}

Primary average money-market weight is {cash_mean:.2%}, maximum {cash_max:.2%}. All 30 ETFs were materially held. Full-history verification, parameters and diagnostics are saved with the publication audit. Historical archived tables are not current-model validation.

---

'''+text[end:]
    text = text.replace('The publication pipeline exports every weekly holding and redraws all currently published figures from saved results. `primary_weekly_holdings.xlsx` contains all 30 ETFs at each decision, with separate calendar-week and holding-period returns. Retain sample-boundary flags. Excel export requires Node.js and `@oai/artifact-tool`; `NODE_BINARY` and `NODE_PATH` can select the local runtime. Keep matching vector PDF and 300-dpi PNG figures.', 'The publication pipeline exports weekly holdings to CSV only and redraws current figures. Retain all 30 ETFs and sample-boundary flags, with separate calendar-week and holding-period returns. Do not create standalone holdings Excel/PDF files or detailed holdings appendices. Keep matching vector PDF and 300-dpi PNG figures.')
    text = text.replace('python scripts/update_risk_free_rate.py --start-date 20000101 --end-date 20260831\n','')
    (ROOT/'AGENTS.md').write_text(text,encoding='utf-8')
    (ROOT/'docs/MODEL_GOVERNANCE.md').write_text('''# Model Governance

## Published models

Global RRP is the weekly primary model. HRP Benchmark, HERC Benchmark, Equal Weight and 60/40 Benchmark are monthly comparisons. Estimation and frequency variants are experiments, not additional models.

## Primary specification

A convex log risk-budget problem produces the reference. A second convex problem balances reference tracking, normalized variance and expected-return shortfall. The variance scale is the contemporaneous equal-weight portfolio variance. The inherited variance and shortfall coefficients are 0.10 and 1.9; the forecast target is 1.9 times the nonnegative cross-asset mean forecast. These are research conventions.

The 240-observation window uses Ledoit–Wolf covariance shrinkage and EWMA return estimates with a 20-trading-day half-life. Weights are long-only, sum to one, and receive no post-solve risk scaling. There is no active CVaR or turnover constraint. One-way costs of 3 bps multiply the sum of absolute weight trades.

## Data and evidence

Evaluation spans 2018-01-02 through 2026-08-31, with 243-day annualization and rf=0. The 30-ETF pool excludes six candidates. Eligibility requires 60 prior valid observations and positive variance. Returns retain extremes and pre-listing prices are not backfilled. All 30 assets were materially held, without artificial minimum weights.

Rebalance inputs precede the trading date. The daily backtest applies target weights to that day's return and deducts costs; actual execution prices and capacity need separate validation. Full-history verification matches the evaluated daily results exactly.

The historical research target is approximately 10% net annual return and maximum drawdown no greater than 8%. Selection followed structural research and two logged estimation rounds. Prior-only inputs do not remove retrospective selection bias. Freeze the specification for validation on new observations. Archived significance and overfitting results do not validate this configuration.

## Reproduction

Run `scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set. The pipeline refreshes ETF data, reruns fixed experiments and comparisons, generates tables and figures, synchronizes prose, compiles both PDFs and cleans temporary files. ChinaBond is not required under rf=0.

Configuration and validation are recorded in `results/tables/primary_model_configuration.json` and `primary_publication_audit.json`. Full weekly holdings remain in repository CSVs. Check code, tables, figures and both PDFs before release.
''',encoding='utf-8')


if __name__ == '__main__':
    main()
