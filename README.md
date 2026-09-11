# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

[中文](#中文) · [English](#english) · [完整论文](report/thesis_latex/main.pdf) · [答辩演示](report/ppt/rrp_defense.pdf) · [结果数据](results/tables/model_performance_summary.csv)

## 中文

### 项目概述

在多头、满仓和无杠杆的条件下，风险预算组合能否兼顾收益与风险分散？本项目使用中国市场上市、覆盖境内外资产的 **30只ETF**，研究如何在风险预算参考组合附近调整权重，并用统一的周度回测比较收益、回撤与交易成本。

**Global RRP** 是当前主模型。它先求解凸风险预算参考，再通过方差与预测收益短缺惩罚调整配置。研究同时保留四个对照，检验这种调整带来的收益是否伴随更高波动、换手或尾部损失。

当前样本中，Global RRP 的净年化收益为 **6.09%**，年化波动为 **3.59%**，最大回撤为 **-6.80%**。低风险表现需要结合货币与债券持仓理解，年度参数的统计识别也较弱。项目的研究价值在于把这些取舍放在同一套可核查证据中。

### 快速阅读与证据入口

首次阅读可先看下方结果和图表，再进入[论文](report/thesis_latex/main.pdf)查看推导与实证细节。[答辩演示](report/ppt/rrp_defense.pdf)适合快速了解研究设计。

| 阅读重点 | 可以核查的内容 | 入口 |
|---|---|---|
| 模型设计 | 凸风险预算参考、收益软目标与组合约束 | [求解实现](src/risk_parity.py) |
| 实证比较 | 五个模型的扣费收益、风险与换手 | [绩效总表](results/tables/model_performance_summary.csv) |
| 参数选择 | 年度信息截止日、候选验证与选择不确定性 | [参数路径](results/tables/primary_parameter_schedule.csv) · [候选明细](results/tables/primary_calibration_candidates.csv) |
| 可复现性 | 信息时序、约束满足和收益核对 | [发布审计](results/tables/primary_publication_audit.json) · [完整配置](results/tables/primary_model_configuration.json) |

### 研究动机与模型设计

按资金等权配置并不保证各资产承担相近的风险。风险预算方法把关注点移到风险贡献，但低波动资产也可能获得较高权重，压低组合的收益水平。本研究检验在这一参考结构附近引入收益软目标后的实际取舍。

| 模型 | 配置方法 | 研究角色 |
|---|---|---|
| **Global RRP** | 跟踪凸风险预算参考，平衡归一化方差与预测收益短缺 | 周频主模型 |
| HRP Benchmark | 根据资产相关结构聚类，再递归分配风险 | 层次风险平价对照 |
| HERC Benchmark | 按层次结构进行等风险贡献配置 | 层次等风险贡献对照 |
| Equal Weight | 在当期合格资产间等权配置 | 简单分散化对照 |
| 60/40 Benchmark | 按项目分类配置60%权益与40%债券，组内等权 | 固定股债比例对照 |

**主模型分两步求解。** 首先得到当期可行的风险预算参考组合 $q_t$，随后在参考附近优化实际权重。收益软目标采用参考组合自身的预测收益。

$$
R_t = μ_tᵀq_t
$$

其中 $μ_t$ 是当期预期收益向量。目标没有固定倍数，预测收益低于目标时会产生惩罚。优化同时考虑偏离参考的程度和归一化方差，具体目标项与尺度见[求解实现](src/risk_parity.py)。

| 设定 | 当前口径 |
|---|---|
| 估计窗口 | 最多252个交易日，资产进入至少需要60个有效历史观察及正方差 |
| 协方差与均值 | Ledoit-Wolf 收缩协方差，20日半衰期 EWMA 均值 |
| 权重约束 | 多头、满仓、无杠杆，允许单期零权重，无人工最低配置 |
| 调仓与参数更新 | 五个模型均按周调仓，主模型惩罚系数按年更新 |
| 收益与成本 | 保留极端收益观察，rf=0，252日年化，单边3 bps约定成本 |

**年度校准只使用生效日前的信息。** 较早的252日区间确定候选尺度，随后的252日区间检验九组参数的扣费表现。选择规则考虑一倍夏普标准误集合、相邻候选、换手与季度稳定性，所选参数在下一年保持固定。

### 历史结果与研究判断

评价区间为 **2018-01-02 至 2026-09-11**。下表由[权威绩效CSV](results/tables/model_performance_summary.csv)生成，并可与[对照结果](results/tables/hrp_comparison.csv)交叉核查。

| 模型 | 净年化收益 | 年化波动 | 夏普 | Sortino | 最大回撤 | 月均换手 |
|---|---:|---:|---:|---:|---:|---:|
| Global RRP | 6.09% | 3.59% | 1.664 | 2.377 | -6.80% | 17.38% |
| HRP Benchmark | 2.10% | 0.27% | 7.833 | 17.385 | -0.19% | 3.51% |
| HERC Benchmark | 2.53% | 0.81% | 3.088 | 4.650 | -1.57% | 15.91% |
| Equal Weight | 9.13% | 13.13% | 0.732 | 1.034 | -18.23% | 8.79% |
| 60/40 Benchmark | 6.83% | 12.06% | 0.608 | 0.873 | -20.46% | 7.65% |

Global RRP 的收益高于两个层次配置对照，波动和回撤也更高。Equal Weight 与 60/40 Benchmark 在这一时期获得更高收益，同时承担更大的波动与回撤。主模型身份表示当前研究设定，历史结果没有显示它在各项指标上全面占优。

日利ETF的平均权重为 **18.02%**，最高权重为 **26.43%**。它与5年国债ETF、10年国债ETF、信用债ETF的平均合计权重为 **66.29%**。这一持仓结构为理解较低波动提供了依据，尚不能单独证明优化方法带来了多少风险改善。HRP Benchmark 的高夏普也应结合极低波动和零无风险利率口径阅读。

年度校准中，每年的九组候选均进入一倍标准误集合，有区分力的年度为 **0/10**。因此，当前样本不足以识别唯一惩罚系数，最终选择更多依赖换手和稳定性规则。

### 图表与持仓解释

#### 累计净值

![五个周频模型的累计净值](results/figures/global_rrp_nav_comparison.png)

五个模型使用相同评价日期与周度调仓日历，净值反映扣除约定成本后的累计表现。比较增长速度时，也应结合 Global RRP 的货币与债券持仓比例理解其风险承担。

#### 历史回撤

![五个周频模型的历史回撤](results/figures/global_rrp_drawdown_comparison.png)

回撤表示净值相对历史高点的跌幅。它补充了净值图中不易辨认的下行过程，展示低风险持仓结构下实际经历的损失，不能代表未来回撤上限。

#### 月均换手

![五个周频模型的月均换手](results/figures/global_rrp_turnover_comparison.png)

换手按买卖绝对权重变化之和计算，再按自然月汇总。Global RRP 的月均换手为 **17.38%**，低波动并不意味着低交易需求。回测按单边3 bps扣费，实际冲击成本仍需单独检验。

#### 历史尾部损失

![五个周频模型的95%日度CVaR](results/figures/global_rrp_cvar_comparison.png)

95%日度 CVaR 描述历史收益分布尾部的平均损失，应与回撤和持仓结构一起阅读。主模型没有启用 CVaR 约束，该指标属于事后风险评价。

<details>
<summary>查看主模型持仓结构与逐周数据</summary>

![Global RRP 持仓结构](results/figures/primary_weights.png)

全部30只ETF均曾在合格期间获得实质配置，单个日期仍可为零权重。[周度持仓](results/tables/primary_weekly_holdings.csv)保留每次决策的全部资产及样本边界标记，[权重宽表](results/tables/primary_weekly_weights.csv)与[周度汇总](results/tables/primary_weekly_summary.csv)便于继续分析。完整持仓保存在CSV中，论文和答辩展示结构图。

</details>

图表采用红蓝配色，同时提供同名矢量PDF和300 dpi PNG。

### 数据与复现

资产池涵盖30只ETF和8类资产，通过境内上市产品获得债券、货币市场、境内外权益及商品相关敞口。缓存覆盖 **2007-01-18 至 2026-09-11**，各资产可用起点不同，上市前价格不回填。完整名单以[资产定义](src/asset_universe.py)为准，可用日期与缺失情况见[资产统计](results/tables/asset_descriptive_statistics.csv)。另有6只候选ETF等待下一次资产池评审，不参与当前回测。

完整复现需要 Python 环境、[项目依赖](requirements.txt)、可用的 `TUSHARE_TOKEN`，以及加入 PATH 的 XeLaTeX、BibTeX 和 Poppler `pdfinfo`。LaTeX 环境需要中文字体与相关宏包。

```powershell
python -m pip install -r requirements.txt
```

在本地环境中设置 `TUSHARE_TOKEN` 后，从仓库根目录运行发布入口。

```powershell
if (-not $env:TUSHARE_TOKEN) { throw "Set TUSHARE_TOKEN before running." }
python scripts/run_primary_publication_pipeline.py
```

入口首先刷新ETF数据，再运行年度校准与四个对照，生成表格和图形，同步文档，最后编译论文及答辩PDF。两个PDF均执行三轮 XeLaTeX 编译，流程退出时自动清理临时文件。当前 rf=0 口径不调用中债利率接口。

| 路径 | 内容 |
|---|---|
| [src/](src/) | 资产定义、估计方法、优化器与回测实现 |
| [scripts/run_primary_publication_pipeline.py](scripts/run_primary_publication_pipeline.py) | 当前正式结果的复现入口 |
| [results/tables/](results/tables/) | 绩效、年度参数、候选验证和逐周持仓 |
| [results/figures/](results/figures/) | 正式发布图表 |
| [report/](report/) | 论文、答辩源文件与PDF |
| [tests/](tests/) | 模型、数据与结果核验测试 |

### 研究边界与文献

逐期估计与年度校准均使用事前数据，但当前方法仍经过历史研究选择，现有回测属于探索性证据。约定交易成本也未验证实际成交价格、市场冲击或容量。后续检验应冻结研究设定，以新增数据检验参数与配置表现。详细边界见[模型治理](docs/MODEL_GOVERNANCE.md)和[模型选择审计](docs/OVERFITTING_AUDIT.md)。

理论背景包括 Maillard、Roncalli 与 Teiletche（2010）的等风险贡献研究，以及 Roncalli（2013）的风险预算体系。HRP 与 HERC 对照分别参考 López de Prado（2016）和 Raffinot（2018），协方差估计参考 Ledoit 与 Wolf（2004）。完整书目信息及文中引用见[论文参考文献](report/thesis_latex/references.bib)。使用本项目结果时，请同时注明仓库、研究设定和样本边界。

---

## English

[切换到中文](#中文) · [Full thesis](report/thesis_latex/main.pdf) · [Defense slides](report/ppt/rrp_defense.pdf)

### Overview

Can a risk-budget portfolio balance return and diversification while remaining long-only, fully invested and unlevered? This project studies **30 China-listed ETFs** with domestic and international exposures. It adjusts weights around a risk-budget reference and compares returns, drawdowns and trading costs under a common weekly backtest.

**Global RRP** is the designated primary model. It first solves a convex risk-budget problem, then adjusts the allocation using variance and expected-return shortfall penalties. Four comparisons test the resulting trade-offs. The current sample records **6.09%** net annual return, **3.59%** annual volatility and **-6.80%** maximum drawdown. Money-market and bond exposure, together with weak parameter identification, are central to interpreting these results.

### Reading guide and evidence

Start with the results below and the [figures](#图表与持仓解释), then consult the [thesis](report/thesis_latex/main.pdf) for derivations and empirical details. The [slides](report/ppt/rrp_defense.pdf) provide a shorter account of the design.

| Question | Evidence |
|---|---|
| How is the portfolio constructed? | [Solver](src/risk_parity.py) and [configuration](results/tables/primary_model_configuration.json) |
| How do the models compare? | [Performance summary](results/tables/model_performance_summary.csv) and [comparison table](results/tables/hrp_comparison.csv) |
| What was known when parameters were selected? | [Annual schedule](results/tables/primary_parameter_schedule.csv) and [candidate validation](results/tables/primary_calibration_candidates.csv) |
| Are timing, constraints and returns reconciled? | [Publication audit](results/tables/primary_publication_audit.json) |

### Motivation and method

Equal capital weights do not ensure equal risk contributions. Risk budgeting addresses that distinction, but a large allocation to low-volatility assets can also limit returns. This study examines the effect of adding a feasible return target near the risk-budget reference.

| Model | Allocation method | Role |
|---|---|---|
| **Global RRP** | Reference tracking with normalized variance and expected-return shortfall penalties | Weekly primary model |
| HRP Benchmark | Correlation clustering and recursive risk allocation | Hierarchical risk parity comparison |
| HERC Benchmark | Equal risk contributions within a hierarchical structure | Hierarchical equal risk contribution comparison |
| Equal Weight | Equal weights across eligible assets | Simple diversification comparison |
| 60/40 Benchmark | 60% equity and 40% bonds under project classifications, equal weights within each group | Fixed stock-bond comparison |

The first convex problem produces a feasible reference $q_t$. The second balances proximity to that reference, normalized variance and predicted-return shortfall. With expected returns $μ_t$, the soft target is

$$
R_t = μ_tᵀq_t
$$

There is no fixed target multiplier. The portfolio remains long-only, fully invested and unlevered, with zero weights allowed and no artificial minimum allocation. The current specification has no active CVaR or turnover constraint.

Inputs use up to 252 trading days, Ledoit-Wolf covariance shrinkage and EWMA means with a 20-day half-life. An asset needs at least 60 prior valid observations and positive variance. All five models rebalance weekly.

Penalty calibration uses two strictly earlier 252-day blocks. The first supplies candidate scales; the second evaluates nine combinations after costs. Selection considers the one-standard-error Sharpe set, neighboring candidates, turnover and quarterly stability. Selected coefficients remain fixed for the following year.

### Historical results and interpretation

The evaluation period is **2018-01-02 to 2026-09-11**. Realized returns retain extreme observations. Metrics use **rf=0**, 252-day annualization and assumed **3-bp one-way trading costs**.

| Model | Net annual return | Volatility | Sharpe | Sortino | Max drawdown | Monthly turnover |
|---|---:|---:|---:|---:|---:|---:|
| Global RRP | 6.09% | 3.59% | 1.664 | 2.377 | -6.80% | 17.38% |
| HRP Benchmark | 2.10% | 0.27% | 7.833 | 17.385 | -0.19% | 3.51% |
| HERC Benchmark | 2.53% | 0.81% | 3.088 | 4.650 | -1.57% | 15.91% |
| Equal Weight | 9.13% | 13.13% | 0.732 | 1.034 | -18.23% | 8.79% |
| 60/40 Benchmark | 6.83% | 12.06% | 0.608 | 0.873 | -20.46% | 7.65% |

Global RRP earns more than the two hierarchical comparisons while taking more volatility and drawdown. Equal Weight and 60/40 Benchmark earn more over this period with larger fluctuations and drawdowns. Primary status identifies the research specification and does not establish performance dominance.

The money-market ETF averages **18.02%** and reaches **26.43%**. Together with the two government-bond ETFs and the credit-bond ETF, it averages **66.29%**. This allocation helps explain the low volatility; isolating the optimizer's contribution requires further comparison. HRP Benchmark's high Sharpe also needs to be read alongside its very low volatility and the zero risk-free convention.

All nine candidates enter the one-standard-error set in every annual validation. There are **0/10** informative years, so the sample does not identify unique penalty coefficients. Turnover and stability rules play a larger role in the final selection.

### Figures and holdings

The shared [figure section](#图表与持仓解释) presents four complementary views with the same weekly evaluation calendar.

| Figure | Interpretation |
|---|---|
| [Cumulative NAV](results/figures/global_rrp_nav_comparison.png) | Growth after assumed costs, read alongside money-market and bond exposure |
| [Drawdown](results/figures/global_rrp_drawdown_comparison.png) | Loss from the historical high, with no guarantee of a future loss ceiling |
| [Monthly turnover](results/figures/global_rrp_turnover_comparison.png) | Absolute buy and sell weight changes aggregated by calendar month; low volatility does not imply low trading needs |
| [95% daily CVaR](results/figures/global_rrp_cvar_comparison.png) | Realized tail-loss description; CVaR is not an active optimization constraint |

All 30 ETFs receive material allocations during eligible periods. The [holdings chart](results/figures/primary_weights.png) shows the structure, while [weekly holdings](results/tables/primary_weekly_holdings.csv), [weights](results/tables/primary_weekly_weights.csv) and [weekly summaries](results/tables/primary_weekly_summary.csv) retain the detailed record. Every decision includes all 30 assets and sample-boundary flags. Figures use a red-blue palette with matching vector PDF and 300-dpi PNG files.

### Data and reproduction

The universe covers 30 ETFs across eight categories, with six candidates excluded until the next universe review. The cache spans **2007-01-18 to 2026-09-11**; individual assets have different availability dates, and pre-listing prices are not backfilled. See the [asset definitions](src/asset_universe.py) and [descriptive statistics](results/tables/asset_descriptive_statistics.csv).

Full reproduction requires Python, the pinned [dependencies](requirements.txt), a valid `TUSHARE_TOKEN`, and XeLaTeX, BibTeX and Poppler `pdfinfo` on PATH. The LaTeX installation also needs Chinese fonts and packages. Install dependencies, set the token in the local environment, and run from the repository root.

```powershell
python -m pip install -r requirements.txt
if (-not $env:TUSHARE_TOKEN) { throw "Set TUSHARE_TOKEN before running." }
python scripts/run_primary_publication_pipeline.py
```

The entry point refreshes ETF data, runs annual calibration and four comparisons, generates tables and figures, synchronizes documents, and compiles both PDFs with three XeLaTeX passes each. Temporary files are cleaned on exit. The zero risk-free convention does not require ChinaBond data.

| Path | Contents |
|---|---|
| [src/](src/) | Asset definitions, estimators, optimizers and backtests |
| [scripts/run_primary_publication_pipeline.py](scripts/run_primary_publication_pipeline.py) | Entry point for the designated publication results |
| [results/tables/](results/tables/) | Performance, annual parameters, candidates and weekly holdings |
| [results/figures/](results/figures/) | Publication figures |
| [report/](report/) | Thesis and presentation sources and PDFs |
| [tests/](tests/) | Model, data and output checks |

### Limitations and references

Rebalance inputs and annual calibration use prior information. Historical research choices still make the current specification exploratory, and the backtest is not an untouched out-of-sample model-selection test. Assumed costs do not establish actual execution prices, market impact or capacity. Further evaluation should freeze the specification and use new observations. See [model governance](docs/MODEL_GOVERNANCE.md) and the [selection audit](docs/OVERFITTING_AUDIT.md).

The research draws on Maillard, Roncalli and Teiletche (2010) and Roncalli (2013) for risk contributions and budgeting; López de Prado (2016) and Raffinot (2018) for the hierarchical comparisons; and Ledoit and Wolf (2004) for covariance shrinkage. Full entries are in the [thesis bibliography](report/thesis_latex/references.bib). When using these results, cite this repository and state the specification and sample boundaries.
