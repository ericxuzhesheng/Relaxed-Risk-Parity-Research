# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

[中文](#中文) · [English](#english) · [论文](report/thesis_latex/main.pdf) · [答辩](report/ppt/rrp_defense.pdf)

## 中文

### 主模型与研究问题

**Improved Convex Adaptive Global RRP** 是本项目主模型：在中国市场可交易的 30 只全球多资产 ETF 中，以凸优化生成多头、无杠杆配置，每周最后一个实际交易日调仓。模型取消现金组与单资产集中度上限，保留其他组别边界、换手惩罚、80% 单期换手硬上限和单边 3 bps 成本。Global RRP、基础凸模型、HRP、HERC、等权及 60/40 均为对照。

研究检验风险预算参考与实施约束如何影响组合，而不是直接最大化全样本夏普。第一阶段求解凸对数障碍风险预算参考，第二阶段跟踪参考权重并惩罚换手。当前主模型的方差、收益奖励与 CVaR 惩罚系数均为零，不能将其回撤表现归因于 CVaR 约束。

### 主要实证结果

评价区间 **2018-01-02 至 2026-08-31**，243 日年化，无风险利率固定为 **0**，保留实际极端收益。主模型为周频，其余核心模型保留月频，频率影响另作同参数对照。每项指标均扣除同一单边 3 bps 约定成本，不代表实测成交成本。

| Model | Net annual return | Annual vol | Sharpe | Sortino | Max drawdown | Calmar | Avg monthly turnover |
|---|---:|---:|---:|---:|---:|---:|---:|
| Improved Convex Adaptive Global RRP | 2.92% | 1.56% | 1.859 | 2.648 | -2.63% | 1.110 | 4.36% |
| Global RRP | 2.40% | 0.58% | 4.103 | 6.496 | -1.01% | 2.384 | 12.89% |
| Convex Adaptive Global RRP | 5.87% | 6.02% | 0.979 | 1.382 | -8.18% | 0.718 | 2.59% |
| HRP Benchmark | 2.03% | 0.26% | 7.674 | 17.069 | -0.19% | 10.758 | 1.95% |
| HERC Benchmark | 2.44% | 0.82% | 2.958 | 4.432 | -1.53% | 1.597 | 7.17% |
| Equal Weight | 9.21% | 12.92% | 0.747 | 1.057 | -18.25% | 0.505 | 4.73% |
| 60/40 Benchmark | 6.98% | 11.84% | 0.629 | 0.905 | -20.04% | 0.348 | 4.21% |

来源：[权威绩效 CSV](results/tables/convex_adaptive_performance_summary.csv)。主模型净年化收益 **2.92%**、波动 **1.56%**、夏普 **1.859**、最大回撤 **-2.63%**。平均现金类 ETF 权重 **70.23%**，最高 **86.61%**。以滞后一月的 1 年期中债国债收益率作为机会成本，同一组合夏普为 **0.529**。零利率是报告口径，不增加实际收益；近现金对照可能呈现更高夏普。

主模型规格经历史约束实验后选定，冻结既有候选日历（当前全部为 `candidate_03`）并统一施加周频和取消集中度上限的变换。每期风险输入只使用调仓日前数据，但模型规格选择是事后的，结果属于探索性历史证据，不能称作未参与选择的独立样本外验证，也不保证未来夏普达到 1.0。

### 结果与约束解释

![累计净值](results/figures/convex_adaptive_nav_comparison.png)

净值图比较主模型与所有核心对照，结合收益与风险尺度解读，不按主模型身份预设胜负。

![回撤](results/figures/convex_adaptive_drawdown_comparison.png)

回撤体现历史风险路径；现金集中度是解释低波动的重要组成部分。

![换手](results/figures/convex_adaptive_turnover_comparison.png)

月均换手是按自然月汇总的交易量，主模型实际每周调仓。

![CVaR](results/figures/convex_adaptive_cvar_comparison.png)

CVaR 为历史尾部损失诊断。研究约束采用 95% 精确经验 CVaR（分位点质量可拆分），核心对照表保留项目历史尾均值定义。

![调仓频率](results/figures/rebalance_frequency_sensitivity.png)

频率实验在主模型参数下仅改变日历。周频是当前指定配置，频率排名属于描述性结果。

![主模型权重](results/figures/primary_weights.png)

### 可复现入口

在已配置 `TUSHARE_TOKEN` 的环境中执行：

```powershell
python scripts/run_primary_publication_pipeline.py
```

该入口先刷新 ETF 和利率数据，重算主模型、核心对照、频率实验与描述统计，生成论文数字和权重快照，编译论文与答辩 PDF，最后清理临时文件。使用固定资产池、评价日期和成本，不扩展参数搜索。依赖见 `requirements.txt`；PDF 编译需要 XeLaTeX 和 BibTeX。

| 核验内容 | 文件 |
|---|---|
| 主模型实际配置 | [primary_model_configuration.json](results/tables/primary_model_configuration.json) |
| 时序、约束与复现检查 | [primary_publication_audit.json](results/tables/primary_publication_audit.json) |
| 集中度与风险约束对照 | [primary_constraint_comparison.csv](results/tables/primary_constraint_comparison.csv) |
| 分自然年结果 | [primary_annual_summary.csv](results/tables/primary_annual_summary.csv) |
| 期末持仓快照（非整月指令） | [next_month_holdings.csv](results/tables/next_month_holdings.csv) |
| 资产池单一来源 | [asset_universe.py](src/asset_universe.py) |
| 模型与证据边界 | [MODEL_GOVERNANCE.md](docs/MODEL_GOVERNANCE.md) |

资产池覆盖 8 类，另有 6 只候选 ETF 不参与回测。每只 ETF 至少具有 60 个有效历史观察方可进入当期组合。收益只前向填充已出现的价格，不回填上市前数据，不按全样本均值和标准差剔除极端值。缓存实际覆盖 2007-01-18 至 2026-08-31。

`results/legacy_monthly_reference/` 与其他尚未纳入本次主模型发布入口的历史诊断仅供追溯，不作为当前主模型的显著性或稳健性证明。参考教材 PDF/EPUB 不包含在发布提交中。

## English

### Primary specification

**Improved Convex Adaptive Global RRP** is the designated primary model. It rebalances on the last actual trading day of each week, removes the cash-group and individual-asset concentration caps, and retains the other group bounds, turnover penalty, 80% turnover limit and 3-bp one-way cost assumption. It is long-only and unlevered. Global RRP, the base convex model, HRP, HERC, Equal Weight and 60/40 are comparisons.

Weights are produced by a convex risk-budget reference followed by a convex tracking and turnover problem. The active specification has zero expected-return reward, zero variance penalty and zero CVaR penalty. CVaR is a diagnostic for this specification.

### Performance and interpretation

All headline metrics use unfiltered realized returns, the same 2018-01-02 to 2026-08-31 evaluation window, 243 trading days per year and a **zero risk-free rate**. The primary model is weekly; core comparisons retain their monthly schedules. Separate frequency experiments isolate the calendar effect.

| Model | Net annual return | Annual vol | Sharpe | Sortino | Max drawdown | Calmar | Avg monthly turnover |
|---|---:|---:|---:|---:|---:|---:|---:|
| Improved Convex Adaptive Global RRP | 2.92% | 1.56% | 1.859 | 2.648 | -2.63% | 1.110 | 4.36% |
| Global RRP | 2.40% | 0.58% | 4.103 | 6.496 | -1.01% | 2.384 | 12.89% |
| Convex Adaptive Global RRP | 5.87% | 6.02% | 0.979 | 1.382 | -8.18% | 0.718 | 2.59% |
| HRP Benchmark | 2.03% | 0.26% | 7.674 | 17.069 | -0.19% | 10.758 | 1.95% |
| HERC Benchmark | 2.44% | 0.82% | 2.958 | 4.432 | -1.53% | 1.597 | 7.17% |
| Equal Weight | 9.21% | 12.92% | 0.747 | 1.057 | -18.25% | 0.505 | 4.73% |
| 60/40 Benchmark | 6.98% | 11.84% | 0.629 | 0.905 | -20.04% | 0.348 | 4.21% |

The primary model averages **70.23%** in the money-market ETF, reaching **86.61%**. Its Sharpe is **0.529** with the lagged one-year ChinaBond government yield as opportunity cost, compared with **1.859** at zero risk-free. The convention changes the reported ratio, not portfolio returns. Near-cash comparisons can have higher zero-rate Sharpe ratios.

The specification was chosen after inspecting historical constraint experiments. It replays a frozen candidate schedule with uniform weekly and concentration-cap changes. Inputs at each rebalance use prior data, but specification selection is retrospective. These results are exploratory historical evidence, not untouched out-of-sample model-selection evidence or a future performance guarantee.

Run `python scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set to reproduce the current publication. The authoritative CSV, audit, configuration and annual results are linked above. Historical diagnostics outside this publication pipeline are archival and do not validate the current primary model. Reference textbooks are excluded from the published repository changes.
