"""Synchronize publication prose with the designated rolling Global RRP results."""
from pathlib import Path
from datetime import datetime
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
    diagnostics = pd.read_csv(tables / "primary_diagnostic_summary.csv").set_index("experiment")
    diagnostic_audit = json.loads((tables / "primary_diagnostics_audit.json").read_text(encoding="utf-8"))
    robust = pd.read_csv(tables / "primary_robustness.csv").set_index("experiment")
    diagnostic_keys = ["reference", "frozen", "matched_equal", "matched_60_40"]
    zh_labels = ["Global RRP：仅持有风险预算参考", "Global RRP：冻结评价首年参数",
                 "Equal Weight：事前风险匹配", "60/40 Benchmark：事前风险匹配"]
    en_labels = ["Global RRP: reference only", "Global RRP: initial parameters frozen",
                 "Equal Weight: ex-ante risk matching", "60/40 Benchmark: ex-ante risk matching"]

    def diagnostic_table(labels):
        return "\n".join(
            f"| {label} | {diagnostics.loc[key, 'net_annual_return']:.2%} | "
            f"{diagnostics.loc[key, 'annualized_volatility']:.2%} | "
            f"{diagnostics.loc[key, 'sharpe_ratio']:.3f} |"
            for key, label in zip(diagnostic_keys, labels)
        )

    zh_diagnostics = diagnostic_table(zh_labels)
    en_diagnostics = diagnostic_table(en_labels)

    readme = f'''# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

[中文](#中文) · [English](#english) · [完整论文](report/thesis_latex/main.pdf) · [答辩演示](report/ppt/rrp_defense.pdf) · [结果数据](results/tables/model_performance_summary.csv)

更新日期 / Last updated: **{datetime.now().date().isoformat()}**

## 中文

### 项目概述

在多头、满仓和无杠杆的条件下，风险预算组合能否兼顾收益与风险分散？本项目使用中国市场上市、覆盖境内外资产的 **30只ETF**，研究如何在风险预算参考组合附近调整权重，并用统一的周度回测比较收益、回撤与交易成本。

**Global RRP** 是当前主模型。它先求解凸风险预算参考，再通过方差与预测收益短缺惩罚调整配置。研究同时保留四个对照，检验这种调整带来的收益是否伴随更高波动、换手或尾部损失。

这里的“宽松”指最终权重允许偏离等风险贡献参考。资本距离惩罚不直接限制风险贡献偏离，实际关系见[周度配对诊断](results/tables/primary_tracking_risk.csv)和[图形](results/figures/primary_tracking_risk.png)。本研究检验参考正则化结构的配置效果，不主张优于未在同一数据上复现的原始RRP方法。

当前样本中，Global RRP 的净年化收益为 **{primary.net_annual_return:.2%}**，年化波动为 **{primary.annualized_volatility:.2%}**，最大回撤为 **{primary.max_drawdown:.2%}**。研究通过目标项消融、事前风险匹配和配对区块抽样，量化优化规则、风险承担与参数更新形成的取舍。

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
| HERC Benchmark | 相关性排序、列表递归二分及子簇波动比例分配 | 简化层次对照，不是原始HERC的完整复现 |
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

筛选宽度采用独立同分布正态近似下的夏普标准误，未校正序列相关，不是候选差异的联合置信集合。候选分位点、网格邻接与换手排序是本文实施约定；全部候选入围不等于统计等价。公式与来源见论文第三章（Hastie等，2009；Lo，2002）。

### 历史结果与研究判断

评价区间为 **2018-01-02 至 2026-10-30**。下表由[权威绩效CSV](results/tables/model_performance_summary.csv)生成，并可与[对照结果](results/tables/hrp_comparison.csv)交叉核查。

{zh_table}

Global RRP 的收益高于两个层次配置对照，波动和回撤也更高。Equal Weight 与 60/40 Benchmark 在这一时期获得更高收益，同时承担更大的波动与回撤。主模型身份表示当前研究设定，历史结果没有显示它在各项指标上全面占优。

日利ETF的平均权重为 **{cash_mean:.2%}**，最高权重为 **{cash_max:.2%}**。它与5年国债ETF、10年国债ETF、信用债ETF的平均合计权重为 **{defensive:.2%}**。这一持仓结构与目标项消融、风险匹配实验共同解释组合的风险收益权衡。HRP Benchmark 的高夏普也应结合极低波动和零无风险利率口径阅读。

年度校准中，每年的九组候选均进入一倍标准误集合，有区分力的年度为 **{audit['parameter_selection_informative_years']}/{audit['parameter_selection_years']}**。因此，当前样本不足以识别唯一惩罚系数，最终选择更多依赖换手和稳定性规则。

### 机制实验与图表

诊断实验围绕当前主模型逐项改变目标项和实施条件。固定参数取评价期开始前选出的系数；事前风险匹配通过简单配置与货币ETF混合实现，以同一历史样本协方差衡量双方风险，包含货币资产自身风险并保持无杠杆。原Ledoit–Wolf估计下的匹配可行性另行保存，用于解释收缩对低波动货币资产的影响。

| 诊断设定 | 净年化收益 | 实现年化波动 | 夏普 |
|---|---:|---:|---:|
{zh_diagnostics}

同一主模型持仓路径在单边20 bps费用下的净年化收益为 **{robust.loc['cost_20', 'net_annual_return']:.2%}**；延后一交易日执行的净年化收益为 **{diagnostics.loc['delay_1', 'net_annual_return']:.2%}**。均值半衰期、固定子区间和5/21/63日区块长度共同刻画结果敏感性。配对抽样区间反映固定历史规格下的统计不确定性。

[消融与辅助比较](results/tables/primary_diagnostic_summary.csv) · [稳健性检验](results/tables/primary_robustness.csv) · [配对抽样](results/tables/primary_paired_bootstrap.csv) · [实验协议](results/primary_diagnostics/protocol.json) · [核验记录](results/tables/primary_diagnostics_audit.json)

#### 累计净值

![五个周频模型的累计净值](results/figures/global_rrp_nav_comparison.png)

五个模型使用相同评价日期与周度调仓日历，净值反映扣除约定成本后的累计表现。比较增长速度时，也应结合 Global RRP 的货币与债券持仓比例理解其风险承担。

#### 历史回撤

![五个周频模型的历史回撤](results/figures/global_rrp_drawdown_comparison.png)

回撤表示净值相对历史高点的跌幅。它补充了净值图中不易辨认的下行过程，展示低风险持仓结构下实际经历的损失，不能代表未来回撤上限。

#### 月均换手

![五个周频模型的月均换手](results/figures/global_rrp_turnover_comparison.png)

换手按买卖绝对权重变化之和计算，再按自然月汇总。Global RRP 的月均换手为 **{primary.avg_monthly_turnover:.2%}**，低波动并不意味着低交易需求。回测按单边3 bps扣费，实际冲击成本仍需单独检验。

#### 历史尾部损失

![五个周频模型的95%日度CVaR](results/figures/global_rrp_cvar_comparison.png)

95%日度 CVaR 描述历史收益分布尾部的平均损失，应与回撤和持仓结构一起阅读。主模型没有启用 CVaR 约束，该指标属于事后风险评价。

<details>
<summary>查看主模型持仓结构与逐周数据</summary>

![Global RRP 持仓结构](results/figures/primary_weights.png)

全部30只ETF均曾在合格期间获得实质配置，单个日期仍可为零权重。[周度持仓](results/tables/primary_weekly_holdings.csv)保留每次决策的全部资产及样本边界标记，[权重宽表](results/tables/primary_weekly_weights.csv)与[周度汇总](results/tables/primary_weekly_summary.csv)便于继续分析。完整持仓保存在CSV中，论文和答辩展示结构图。

</details>

图表采用红蓝配色，同时提供同名矢量PDF和300 dpi PNG。

[最新目标持仓](results/tables/latest_holdings.csv)使用最新收盘信息求解，保留全部30只ETF及零权重。该结果为下一次周度调仓的预估配置，正式决策仍须纳入届时新增行情；信息截止日、年度参数与求解核验见[持仓审计](results/tables/latest_holdings_audit.json)。

### 无杠杆设定的经济含义

本研究完成的是境内ETF持有组合的资本配置。相对桥水全球机构框架，当前30只工具覆盖的独立利率、通胀与货币对冲风险来源较少；多头单位预算使风险规模与资本占用直接相连。论文据[桥水官方说明](https://www.bridgewater.com/research-and-insights/the-all-weather-story)区分两者工具范围，并以[Frazzini与Pedersen（2014，JFE）](https://doi.org/10.1016/j.jfineco.2013.10.005)和[Brunnermeier与Pedersen（2009，RFS）](https://doi.org/10.1093/rfs/hhn098)解释杠杆约束、融资与流动性风险。无杠杆约束使配置绩效与当前可核算的ETF持仓和费用相对应。

### 风险估计与解释口径

Ledoit–Wolf将经验协方差与等方差对角目标加权组合，强度由当期历史样本估计。低波动货币工具的估计方差可能因此上升，风险贡献须说明使用哪一个矩阵。[两种矩阵下的同一持仓风险份额](results/tables/primary_group_risk_contribution.csv)和[收缩特征](results/tables/primary_covariance_interpretation.csv)展示这一影响。主模型使用LW矩阵，辅助风险匹配以共同样本矩阵衡量双方，Brinson则直接核算实现收益差。风险贡献份额与收益贡献分别报告。

主模型回看上限为252日，四个正式对照沿用240日；五模型比较对应完整规则，消融实验用于保持其余主模型设定一致的机制比较。Brinson与净值收益统计共同排除首个净值基期观察。

### 仓位管理与收益归因

货币和债券配置使满额投资组合仍能调节风险承担。论文借助海龟交易法的波动持仓单位解释风险数量管理，并用[调仓前市场状态与持仓](results/tables/primary_position_summary.csv)核查这种关系。

[Brinson–Fachler归因](results/tables/primary_brinson_summary.csv)以原始等权及风险匹配等权为基准，将日收益差拆为配置、组内ETF选择、交互和费用差。[各资产组贡献](results/tables/primary_brinson_categories.csv)单列现金、国债和信用债；下跌日按沪深300ETF当日负收益事后划分。数值为平均单日基点，基准选择决定贡献含义。方法依据[Brinson与Fachler（1985）](https://doi.org/10.3905/jpm.1985.409005)和[CFA Institute归因综述](https://rpc.cfainstitute.org/research/foundation/2019/performance-attribution)。

### 数据与复现

资产池涵盖30只ETF和8类资产，通过境内上市产品获得债券、货币市场、境内外权益及商品相关敞口。数据覆盖 **2007-01-18 至 2026-10-30**，各资产可用起点不同，上市前价格不回填。完整名单以[资产定义](src/asset_universe.py)为准，可用日期与缺失情况见[资产统计](results/tables/asset_descriptive_statistics.csv)。另有6只候选ETF等待下一次资产池评审，不参与当前回测。

完整复现需要 Python 环境、[项目依赖](requirements.txt)、可用的 `TUSHARE_TOKEN`，以及加入 PATH 的 XeLaTeX、BibTeX 和 Poppler `pdfinfo`。LaTeX 环境需要中文字体与相关宏包。

```powershell
python -m pip install -r requirements.txt
```

在本地环境中设置 `TUSHARE_TOKEN` 后，从仓库根目录运行发布入口。

```powershell
if (-not $env:TUSHARE_TOKEN) {{ throw "Set TUSHARE_TOKEN before running." }}
python scripts/run_primary_publication_pipeline.py
```

入口首先刷新ETF数据，再运行年度校准与四个对照，生成表格和图形，同步文档，最后编译论文及答辩PDF。两个PDF均执行三轮 XeLaTeX 编译，流程退出时自动清理临时文件。当前 rf=0 口径不调用中债利率接口。

日常更新使用 `.venv/Scripts/python.exe scripts/run_daily_publication.py`，在北京时间17:00后获取最新完整行情并推进评价截止日。无新增收益或历史修订时跳过发布；已有年度校准和主模型回测按缓存复用，现有诊断仅在数据变化后刷新。周频调仓日期取交易所日历中的周末最后交易日，开题报告不随行情改写。

完整重算年度校准与五个模型的回测：

```powershell
python scripts/run_primary_publication_pipeline.py --force-recalibrate --force-backtest
```

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

**Global RRP** is the designated primary model. It first solves a convex risk-budget problem, then adjusts the allocation using variance and expected-return shortfall penalties. Four comparisons test the resulting trade-offs. The current sample records **{primary.net_annual_return:.2%}** net annual return, **{primary.annualized_volatility:.2%}** annual volatility and **{primary.max_drawdown:.2%}** maximum drawdown. Money-market and bond exposure, together with weak parameter identification, are central to interpreting these results.

“Relaxed” means that final weights may depart from the equal-risk-contribution reference. Capital-weight regularization does not impose a risk-contribution deviation ceiling. The [paired weekly diagnostic](results/tables/primary_tracking_risk.csv) and [figure](results/figures/primary_tracking_risk.png) evaluate both distances. This study tests the reference-based structure and does not claim superiority over original RRP methods not reproduced on the same data.

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
| HERC Benchmark | Correlation ordering, list bisection and subcluster volatility allocation | Simplified comparison, not a complete reproduction of original HERC |
| Equal Weight | Equal weights across eligible assets | Simple diversification comparison |
| 60/40 Benchmark | 60% equity and 40% bonds under project classifications, equal weights within each group | Fixed stock-bond comparison |

The first convex problem produces a feasible reference $q_t$. The second balances proximity to that reference, normalized variance and predicted-return shortfall. With expected returns $μ_t$, the soft target is

$$
R_t = μ_tᵀq_t
$$

There is no fixed target multiplier. The portfolio remains long-only, fully invested and unlevered, with zero weights allowed and no artificial minimum allocation. The current specification has no active CVaR or turnover constraint.

Inputs use up to 252 trading days, Ledoit-Wolf covariance shrinkage and EWMA means with a 20-day half-life. An asset needs at least 60 prior valid observations and positive variance. All five models rebalance weekly.

Penalty calibration uses two strictly earlier 252-day blocks. The first supplies candidate scales; the second evaluates nine combinations after costs. Selection considers the one-standard-error Sharpe set, neighboring candidates, turnover and quarterly stability. Selected coefficients remain fixed for the following year.

The screening width uses an IID-normal approximation to the Sharpe standard error without serial-correlation adjustment. It is not a joint confidence set for candidate differences. Quantile grids, adjacency and turnover ordering are implementation choices; admission of every candidate does not establish statistical equivalence. Chapter 3 gives the formula and sources (Hastie et al., 2009; Lo, 2002).

### Historical results and interpretation

The evaluation period is **2018-01-02 to 2026-10-30**. Realized returns retain extreme observations. Metrics use **rf=0**, 252-day annualization and assumed **3-bp one-way trading costs**.

{en_table}

Global RRP earns more than the two hierarchical comparisons while taking more volatility and drawdown. Equal Weight and 60/40 Benchmark earn more over this period with larger fluctuations and drawdowns. Primary status identifies the research specification and does not establish performance dominance.

The money-market ETF averages **{cash_mean:.2%}** and reaches **{cash_max:.2%}**. Together with the two government-bond ETFs and the credit-bond ETF, it averages **{defensive:.2%}**. This allocation, objective ablations and risk-matched comparisons jointly explain the risk-return trade-off. HRP Benchmark's high Sharpe also needs to be read alongside its very low volatility and the zero risk-free convention.

All nine candidates enter the one-standard-error set in every annual validation. There are **{audit['parameter_selection_informative_years']}/{audit['parameter_selection_years']}** informative years, so the sample does not identify unique penalty coefficients. Turnover and stability rules play a larger role in the final selection.

### Diagnostic experiments

The study evaluates objective-term ablations, parameters frozen before evaluation, and ex-ante risk matching. The auxiliary comparisons mix each simple allocation with the money-market ETF using the same prior sample covariance for both portfolios, including cash-asset risk and covariance, while remaining unlevered. Original Ledoit–Wolf feasibility is reported separately.

| Diagnostic setting | Net annual return | Realized volatility | Sharpe |
|---|---:|---:|---:|
{en_diagnostics}

At 20-bp one-way costs, the primary holdings path records **{robust.loc['cost_20', 'net_annual_return']:.2%}** net annual return. Executing original targets one trading day later records **{diagnostics.loc['delay_1', 'net_annual_return']:.2%}**. Mean half-life changes, fixed subperiods and paired moving-block bootstrap intervals with 5/21/63-day blocks describe sensitivity conditional on the historical specification.

[Diagnostic results](results/tables/primary_diagnostic_summary.csv) · [Robustness](results/tables/primary_robustness.csv) · [Paired bootstrap](results/tables/primary_paired_bootstrap.csv) · [Protocol](results/primary_diagnostics/protocol.json)

### Figures and holdings

The shared [figure section](#图表与持仓解释) presents four complementary views with the same weekly evaluation calendar.

| Figure | Interpretation |
|---|---|
| [Cumulative NAV](results/figures/global_rrp_nav_comparison.png) | Growth after assumed costs, read alongside money-market and bond exposure |
| [Drawdown](results/figures/global_rrp_drawdown_comparison.png) | Loss from the historical high, with no guarantee of a future loss ceiling |
| [Monthly turnover](results/figures/global_rrp_turnover_comparison.png) | Absolute buy and sell weight changes aggregated by calendar month; low volatility does not imply low trading needs |
| [95% daily CVaR](results/figures/global_rrp_cvar_comparison.png) | Realized tail-loss description; CVaR is not an active optimization constraint |

All 30 ETFs receive material allocations during eligible periods. The [holdings chart](results/figures/primary_weights.png) shows the structure, while [weekly holdings](results/tables/primary_weekly_holdings.csv), [weights](results/tables/primary_weekly_weights.csv) and [weekly summaries](results/tables/primary_weekly_summary.csv) retain the detailed record. Every decision includes all 30 assets and sample-boundary flags. Figures use a red-blue palette with matching vector PDF and 300-dpi PNG files.

The [latest target allocation](results/tables/latest_holdings.csv) uses the latest observed close and includes all 30 ETFs, including zero weights. It is a forecast for the next weekly decision, which must incorporate newly available data before execution. The [holdings audit](results/tables/latest_holdings_audit.json) records the information cutoff, annual penalties and solver checks.

### Why the model is unlevered

The chosen China-listed ETF universe offers narrower independent rate, inflation and currency-hedging exposures than a global institutional instrument set. A long-only unit budget connects risk allocation directly to capital use. The thesis distinguishes this setting from [Bridgewater's All Weather framework](https://www.bridgewater.com/research-and-insights/the-all-weather-story), and uses research on [leverage constraints](https://doi.org/10.1016/j.jfineco.2013.10.005) and [funding liquidity](https://doi.org/10.1093/rfs/hhn098) to explain the financing and margin considerations behind the unlevered specification.

### Risk estimation and interpretation

Ledoit–Wolf combines the empirical covariance with an equal-variance diagonal target using a sample-estimated intensity. It can raise the estimated money-market variance. [Risk shares under both matrices for identical holdings](results/tables/primary_group_risk_contribution.csv) and [covariance diagnostics](results/tables/primary_covariance_interpretation.csv) document this effect. The primary model uses LW; auxiliary matching uses a common sample matrix; Brinson decomposes realized return differences. Risk shares and return effects have distinct units.

The primary lookback is up to 252 days; the four published benchmarks retain 240 days. Model comparisons evaluate complete rules, while objective ablations hold the remaining primary settings fixed. Brinson and NAV-derived return statistics both exclude the initial NAV observation.

### Position management and return attribution

Cash and bond allocations adjust risk within a fully invested portfolio. The thesis relates this principle to volatility-based Turtle position units and reports [holdings by prior market state](results/tables/primary_position_summary.csv).

[Brinson–Fachler attribution](results/tables/primary_brinson_summary.csv) reconciles daily active returns into allocation, within-group ETF selection, interaction and cost differences against both original and risk-matched Equal Weight. [Category results](results/tables/primary_brinson_categories.csv) distinguish money-market, government-bond and credit-bond contributions. Down days are identified ex post by negative CSI 300 ETF returns. Effects are arithmetic mean daily basis points and depend on the chosen benchmark. References include [Brinson and Fachler (1985)](https://doi.org/10.3905/jpm.1985.409005) and the [CFA Institute attribution review](https://rpc.cfainstitute.org/research/foundation/2019/performance-attribution).

### Data and reproduction

The universe covers 30 ETFs across eight categories, with six candidates excluded until the next universe review. The price data span **2007-01-18 to 2026-10-30**; individual assets have different availability dates, and pre-listing prices are not backfilled. See the [asset definitions](src/asset_universe.py) and [descriptive statistics](results/tables/asset_descriptive_statistics.csv).

Full reproduction requires Python, the pinned [dependencies](requirements.txt), a valid `TUSHARE_TOKEN`, and XeLaTeX, BibTeX and Poppler `pdfinfo` on PATH. The LaTeX installation also needs Chinese fonts and packages. Install dependencies, set the token in the local environment, and run from the repository root.

```powershell
python -m pip install -r requirements.txt
if (-not $env:TUSHARE_TOKEN) {{ throw "Set TUSHARE_TOKEN before running." }}
python scripts/run_primary_publication_pipeline.py
```

The entry point refreshes ETF data, runs annual calibration and four comparisons, generates tables and figures, synchronizes documents, and compiles both PDFs with three XeLaTeX passes each. Temporary files are cleaned on exit. The zero risk-free convention does not require ChinaBond data.

For daily updates, run `.venv/Scripts/python.exe scripts/run_daily_publication.py` after 17:00 Asia/Shanghai. It advances the snapshot only after complete market data are available, skips unchanged returns, reuses matching calibration and primary backtest caches, and refreshes existing diagnostics only when inputs change. Weekly decisions use the exchange calendar's last trading day of the week. Proposal documents remain unchanged.

To recompute every annual calibration and all five backtests from the beginning:

```powershell
python scripts/run_primary_publication_pipeline.py --force-recalibrate --force-backtest
```

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
'''
    (ROOT / "README.md").write_text(readme, encoding="utf-8")

    agents = ROOT / "AGENTS.md"
    text = agents.read_text(encoding="utf-8")
    start = text.index("Main research line")
    end = text.index("## ETF Asset Pool")
    model_rows = "\n".join(
        f"| {name} | {'Primary weekly model' if index == 0 else 'Weekly comparison'} |"
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
- Relaxed refers to capital-weight regularization around an equal-risk-contribution reference, not a hard bound on risk-share deviations. `primary_tracking_risk.csv` and its summary report both measures. HERC Benchmark is a simplified list-bisection implementation, not a full reproduction of original HERC.
- The lookback and annualization conventions both use 252 trading days. Inputs use Ledoit-Wolf covariance shrinkage and 20-day half-life EWMA means.
- The return target equals the predicted return of the contemporaneous feasible risk-budget reference. There is no fixed target multiplier.
- Variance and shortfall penalties update annually from two strictly earlier 252-day blocks. The first block determines candidate scales and the second evaluates candidates after costs. Selected values remain fixed for the following year.
- Every annual validation admits all nine candidates to the one-standard-error set. Report this weak identification and do not describe the selected coefficients as unique estimates.
- The screening standard error uses an IID-normal approximation without serial-correlation correction. The set is a heuristic, not a joint confidence set; grid adjacency and turnover ordering are implementation choices.
- All eligible ETFs may participate, including zero weights on a date. There is no artificial minimum allocation.
- rf=0 is the current rate convention. ChinaBond refresh is not required.
- Primary status records the designated research specification. Historical results do not imply performance dominance or future guarantees.

## Latest Core Results

Always read CSV before writing numbers. Authoritative metrics are `results/tables/model_performance_summary.csv` and `hrp_comparison.csv`. The annual parameter path is `primary_parameter_schedule.csv`, and asset statistics are in `asset_descriptive_statistics.csv` under the same directory.

Current results use 2018-01-02 to 2026-10-30, unfiltered realized returns, rf=0, 252-day annualization and 3-bp one-way cost. All five models rebalance weekly. Price history starts 2007-01-18. Eligibility requires 60 prior valid observations and positive variance.

{en_table}

Primary average money-market weight is {cash_mean:.2%}, with a maximum of {cash_max:.2%}. The average combined money-market and three-bond weight is {defensive:.2%}. All 30 ETFs receive material allocations during eligible periods. The annual calibration has {audit['parameter_selection_informative_years']} informative years out of {audit['parameter_selection_years']} under the one-standard-error rule.

Current-specification ablations, ex-ante risk-matched comparisons and robustness diagnostics are in `primary_diagnostic_summary.csv`, `primary_robustness.csv`, `primary_subperiods.csv` and `primary_paired_bootstrap.csv`. They explain the designated model and do not select a replacement. Risk matching uses the same prior sample covariance for both portfolios, while original Ledoit-Wolf feasibility is recorded separately. All {diagnostic_audit['risk_matching_decisions'] - diagnostic_audit['risk_matching_infeasible_count']} sample-covariance matches attain the target; {diagnostic_audit['lw_risk_matching_infeasible_count']} original-shrinkage matches are infeasible because of the money-market variance estimate. The protocol is a reproducibility record for this historical diagnostic study. Bootstrap intervals are pointwise and conditional on the historical specification.

Holdings-based Brinson-Fachler attribution is in `primary_brinson_summary.csv`, `primary_brinson_categories.csv` and `primary_attribution_audit.json`. Seven attribution groups separate cash, government bonds and credit bonds without changing the ETF universe. Attribution excludes the initial NAV date to align with NAV-derived return statistics. `primary_group_risk_contribution.csv` evaluates identical decision weights under LW and sample covariance; risk-budget deviations are percentage points. `primary_defense_consistency_audit.json` verifies LW reconstruction and Euler identities. The primary model uses a 252-day lookback; published benchmark implementations retain 240 days. Effects are arithmetic mean daily basis points, not annualized or compounded; down-day attribution is ex-post descriptive. Risk contribution, prior-state position analysis and return attribution are distinct outputs. Turtle position sizing is an economic analogy, not an implemented breakout strategy.

---

''' + text[end:]
    text = text.replace("Only the designated weekly specification is published; other experiment results remain archival.",
                        "The designated weekly specification and its explanatory diagnostic experiments are published; unrelated historical specifications remain archival.")
    (ROOT / "AGENTS.md").write_text(text, encoding="utf-8")

    (ROOT / "docs/MODEL_GOVERNANCE.md").write_text(
        f'''# Model Governance

## Published models

Global RRP is the weekly primary model. HRP Benchmark, HERC Benchmark, Equal Weight and 60/40 Benchmark are weekly comparisons. Parameter and frequency variants remain research experiments.

## Primary specification

A convex log risk-budget problem produces the reference portfolio. A second convex problem balances reference tracking, normalized variance and expected-return shortfall. The return target equals the predicted return of the contemporaneous feasible reference portfolio.

Capital-weight proximity is not a hard bound on risk-contribution deviations. The paired tracking/risk diagnostic evaluates both using the same decision weights and covariance. HERC Benchmark uses simplified list bisection and subcluster volatility allocation; comparisons do not establish superiority over original HERC or RRP formulations not reproduced here.

The lookback and annualization conventions both use 252 trading days. Covariance uses Ledoit-Wolf shrinkage, and expected returns use a 20-trading-day half-life. Weights are long-only, sum to one and receive no post-solve risk scaling. The model has no active CVaR or turnover constraint. One-way costs of 3 bps multiply the sum of absolute weight trades.

Variance and shortfall penalties update once a year. An earlier 252-day block supplies objective-term ratios for three data-derived candidates per penalty. The following 252-day block evaluates the nine combinations after costs. Selection uses the one-standard-error Sharpe set, an adjacent qualifying grid point when available, lower turnover and quarterly stability. The selected values remain fixed for the next year.

All nine candidates enter the one-standard-error set in every annual validation. The procedure therefore limits arbitrary fixed coefficients but does not identify a unique pair. This uncertainty must accompany any discussion of the parameter schedule.

The screening width is an IID-normal approximation to annualized Sharpe uncertainty, without serial-correlation correction. It is neither a joint confidence set nor a test of candidate equivalence. Quantile grids, adjacency, turnover and quarterly ordering are implementation conventions. The thesis distinguishes this heuristic from the separate paired block-bootstrap diagnostics.

## Data and evidence

Evaluation spans 2018-01-02 through 2026-10-30 with rf=0. The 30-ETF pool excludes six candidates. Eligibility requires 60 prior valid observations and positive variance. Returns retain extremes, and pre-listing prices are not backfilled.

The historical path records {primary.net_annual_return:.2%} net annual return, {primary.annualized_volatility:.2%} annual volatility, a {primary.sharpe_ratio:.3f} Sharpe ratio and {primary.max_drawdown:.2%} maximum drawdown. All {int(usage.ever_used.sum())} ETFs receive material allocations during eligible periods.

Rebalance inputs precede the trading date. Saved daily returns reconcile target weights, drifted weights, turnover and costs. The backtest does not establish actual execution prices, market impact or capacity. Historical design choices also prevent an untouched model-selection claim.

## Diagnostic evidence and economic interpretation

Objective ablations separate variance reduction from expected-return maintenance. Frozen initial penalties isolate annual updating. Risk matching mixes each simple benchmark with the money-market ETF, uses a common prior sample covariance for both portfolios and charges each path's own turnover. Ledoit-Wolf feasibility is recorded separately because common-diagonal shrinkage raises the estimated money-market variance. Cost, execution-delay, mean-half-life and fixed-subperiod experiments evaluate the current model. Paired bootstrap intervals use 2,000 draws at block lengths 5, 21 and 63 and are pointwise exploratory evidence.

The unlevered budget reflects the limited risk coverage of the chosen China-listed ETF set relative to global institutional instruments and financing arrangements. Thesis references distinguish Bridgewater's official implementation explanation from peer-reviewed research on estimation error, risk management and funding liquidity.

## Reproduction

Run `scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set. Add `--force-recalibrate --force-backtest` for a complete recomputation. The pipeline refreshes ETF data, updates backtests and four comparisons, generates current tables and figures, synchronizes prose, compiles both PDFs and removes temporary files. The rf=0 convention does not require ChinaBond data.

Configuration and validation live in `results/tables/primary_model_configuration.json` and `primary_publication_audit.json`. The annual schedule and all candidate results are stored beside them. Complete weekly holdings remain in repository CSV files.
''',
        encoding="utf-8",
    )

    (ROOT / "docs/OVERFITTING_AUDIT.md").write_text(
        '''# 模型选择与信息时序

Global RRP 与四个对照共同构成五模型发布结果。主模型每年根据生效日前数据更新惩罚系数，年内不再改变。

每次年度更新使用两个连续的252日历史区间。较早区间生成候选尺度，随后区间按扣费净夏普验证九组组合。选择先保留一倍标准误范围内的候选，再检查相邻网格点，随后比较换手和季度稳定性。

十个年度中，每年九组候选都进入一倍标准误集合。现有样本无法精确区分参数，年度选择主要由换手和稳定性规则决定。该结果已写入发布审计，论文和答辩不得将系数称作唯一最优值。

## 当前模型诊断

目标项消融、首年参数冻结、事前风险匹配和实施敏感性共同解释当前指定模型。风险匹配以共同历史样本协方差衡量双方风险，并记录Ledoit–Wolf估计下的可行性。配对区块抽样使用5、21和63日区块、每组2000次重抽样；区间属于固定历史规格下的逐项百分位区间。当前实验用于机制分析，不据结果选择新的主模型。

## 可核查证据

- `results/primary_diagnostics/protocol.json` 记录诊断设定及抽样种子。
- `results/tables/primary_diagnostics_audit.json` 记录路径、计费及风险匹配核验。
- `results/tables/primary_paired_bootstrap.csv` 记录配对差异与区间。

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
