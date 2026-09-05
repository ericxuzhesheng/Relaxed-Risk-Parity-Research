# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

[中文](#中文) · [English](#english) · [论文](report/thesis_latex/main.pdf) · [答辩](report/ppt/rrp_defense.pdf)

## 中文

### 模型与方法

**Global RRP** 为周频主模型，HRP Benchmark、HERC Benchmark、Equal Weight 和 60/40 Benchmark 为月频对照。正式比较仅包含这五个模型。

主模型先求凸风险预算参考，再通过凸优化平衡参考跟踪、组合方差和预测收益短缺。历史窗口为 240 个交易日，使用 Ledoit–Wolf 收缩协方差、20 日半衰期指数加权收益估计，并以当期等权组合方差归一化风险项。组合多头、无杠杆，权重由优化器直接给出。

### 绩效与解释

共同评价区间为 **2018-01-02 至 2026-08-31**，保留极端收益，按 **243 日年化、rf=0、单边 3 bps** 的统一口径计算。

| 模型 | 净年化收益 | 年化波动 | 夏普 | Sortino | 最大回撤 | 月均换手 |
|---|---:|---:|---:|---:|---:|---:|
| Global RRP | 10.59% | 7.62% | 1.361 | 2.102 | -7.16% | 96.76% |
| HRP Benchmark | 2.03% | 0.26% | 7.674 | 17.069 | -0.19% | 1.95% |
| HERC Benchmark | 2.44% | 0.82% | 2.958 | 4.432 | -1.53% | 7.17% |
| Equal Weight | 9.21% | 12.92% | 0.747 | 1.057 | -18.25% | 4.73% |
| 60/40 Benchmark | 6.98% | 11.84% | 0.629 | 0.905 | -20.04% | 4.21% |

数字来自[绩效表](results/tables/convex_adaptive_performance_summary.csv)。Global RRP 达到历史净年化约 10%、最大回撤不超过 8% 的研究目标。平均现金类 ETF 权重为 **15.94%**，最高为 **26.03%**。月均换手按买入与卖出金额之和计算，较高换手使成本与执行能力成为重要限制；约定成本使年化收益减少 **0.39 个百分点**。

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

| Model | Net annual return | Volatility | Sharpe | Sortino | Max drawdown | Monthly turnover |
|---|---:|---:|---:|---:|---:|---:|
| Global RRP | 10.59% | 7.62% | 1.361 | 2.102 | -7.16% | 96.76% |
| HRP Benchmark | 2.03% | 0.26% | 7.674 | 17.069 | -0.19% | 1.95% |
| HERC Benchmark | 2.44% | 0.82% | 2.958 | 4.432 | -1.53% | 7.17% |
| Equal Weight | 9.21% | 12.92% | 0.747 | 1.057 | -18.25% | 4.73% |
| 60/40 Benchmark | 6.98% | 11.84% | 0.629 | 0.905 | -20.04% | 4.21% |

The primary model meets the historical research target of approximately 10% net annual return and no more than 8% maximum drawdown. Its average money-market weight is **15.94%**, reaching **26.03%**. Assumed costs reduce annual return by **0.39 percentage points**. Monthly turnover sums both purchases and sales; execution and capacity remain unverified.

All 30 ETFs receive material holdings during eligible periods. Inputs precede each rebalance, and a full-history rerun reproduces every evaluated day. Selection followed two historical estimation rounds, so these results are exploratory rather than untouched model-selection evidence.

Run `python scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set. The links above provide configurations, audit records and complete weekly CSVs. PDFs contain allocation figures without detailed holdings appendices. Archived diagnostics do not validate the current specification.
