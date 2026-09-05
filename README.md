# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

[中文](#中文) · [English](#english) · [论文](report/thesis_latex/main.pdf) · [答辩](report/ppt/rrp_defense.pdf)

## 中文

### 研究与模型

项目研究风险预算和实施约束如何影响全球 ETF 配置。正式比较包含七个模型。**Improved Convex Adaptive Global RRP** 为主模型，每周最后一个实际交易日调仓。其余六个模型作为月频对照，名单见下表。

主模型先求风险预算参考权重，再通过凸优化平衡参考权重偏离与换手成本。它采用多头、无杠杆配置，取消现金组和单资产集中度上限，保留其他组别边界及 80% 单期换手上限。当前 CVaR 惩罚为零，尾部风险通过历史损失指标观察。

### 绩效与解释

统一评价区间为 **2018-01-02 至 2026-08-31**，按 243 日年化，无风险利率为 **0**。净收益扣除单边 3 bps 的约定成本，收益数据保留真实极端值。

| 模型 | 净年化收益 | 年化波动 | 夏普 | Sortino | 最大回撤 | 月均换手 |
|---|---:|---:|---:|---:|---:|---:|
| Improved Convex Adaptive Global RRP | 2.92% | 1.56% | 1.859 | 2.648 | -2.63% | 4.36% |
| Global RRP | 2.40% | 0.58% | 4.103 | 6.496 | -1.01% | 12.89% |
| Convex Adaptive Global RRP | 5.87% | 6.02% | 0.979 | 1.382 | -8.18% | 2.59% |
| HRP Benchmark | 2.03% | 0.26% | 7.674 | 17.069 | -0.19% | 1.95% |
| HERC Benchmark | 2.44% | 0.82% | 2.958 | 4.432 | -1.53% | 7.17% |
| Equal Weight | 9.21% | 12.92% | 0.747 | 1.057 | -18.25% | 4.73% |
| 60/40 Benchmark | 6.98% | 11.84% | 0.629 | 0.905 | -20.04% | 4.21% |

数字来自[绩效表](results/tables/convex_adaptive_performance_summary.csv)。主模型平均持有 **70.23%** 现金类 ETF，最高 **86.61%**。同一收益路径以滞后一月的中债 1 年期国债利率为机会成本时，夏普为 **0.529**。高现金权重有助于解释低波动，也使零利率夏普对评价口径较敏感。

主模型配置是在查看历史约束实验后选定的。逐期输入只使用调仓日前数据，规格选择仍属于事后研究。后续需要冻结配置并用新增数据检验，历史夏普不保证未来表现。

### 图表

![累计净值](results/figures/convex_adaptive_nav_comparison.png)

累计净值比较七个模型的收益路径。

![历史回撤](results/figures/convex_adaptive_drawdown_comparison.png)

回撤与现金权重共同反映组合承担的风险。

![平均月度换手](results/figures/convex_adaptive_turnover_comparison.png)

换手按自然月汇总，主模型实际每周调仓。

![历史尾部损失](results/figures/convex_adaptive_cvar_comparison.png)

CVaR 用于描述历史尾部损失，主模型未启用相应惩罚。

![调仓频率比较](results/figures/rebalance_frequency_sensitivity.png)

频率实验保持主模型参数不变，仅调整日历，不另计为模型。

![持仓结构](results/figures/primary_weights.png)

### 每周完整持仓

[下载 Excel](results/tables/primary_weekly_holdings.xlsx)，可按调仓日或 ETF 筛选。共 444 次调仓、13,320 条资产记录，每期保留全部 30 只 ETF，包括零权重。表内列出信息截止日、交易前漂移权重、目标权重、增减仓、换手与成本。

收益分为自然周实际收益和本次新持仓的持有期收益。两者覆盖不同日期，不能混用；样本末周与末次持有期均标明截断。查看[每周收益 CSV](results/tables/primary_weekly_summary.csv)、[全部持仓 CSV](results/tables/primary_weekly_holdings.csv)、[权重矩阵 CSV](results/tables/primary_weekly_weights.csv)或[逐年周度持仓图 PDF](results/figures/primary_weekly_weights_by_year.pdf)。

当前展示图均提供 300 dpi PNG 与同名矢量 PDF。持仓图单列现金，其余 29 只 ETF 使用共同的线性色阶，不合并为“其他”。

### 数据与复现

资产池含 30 只 ETF，覆盖 8 类资产，另有 6 只候选 ETF 不参与回测。每只资产须有 60 个有效历史观察才可进入组合。缓存覆盖 2007-01-18 至 2026-08-31，上市前价格不回填。

配置 `TUSHARE_TOKEN` 后运行以下命令。Python 依赖见 `requirements.txt`，PDF 编译需要 XeLaTeX 和 BibTeX，Excel 导出需要 Node.js 与 `@oai/artifact-tool`。可通过 `NODE_BINARY` 指定 Node 可执行文件，`NODE_PATH` 指定包目录。

```powershell
python scripts/run_primary_publication_pipeline.py
```

入口依次刷新数据、运行回测、生成图表与论文数字、编译 PDF 并清理临时文件。

| 内容 | 文件 |
|---|---|
| 主模型参数 | [配置记录](results/tables/primary_model_configuration.json) |
| 信息时序与约束检查 | [发布审计](results/tables/primary_publication_audit.json) |
| 约束实验 | [约束比较](results/tables/primary_constraint_comparison.csv) |
| 自然年结果 | [年度绩效](results/tables/primary_annual_summary.csv) |
| 每周持仓与收益 | [完整 Excel](results/tables/primary_weekly_holdings.xlsx) |
| 资产池 | [资产定义](src/asset_universe.py) |
| 研究边界 | [模型说明](docs/MODEL_GOVERNANCE.md) |

只重建周度表与图表时，依次运行 `python scripts/export_primary_weekly_holdings.py` 和 `python scripts/render_publication_figures.py`。Excel 使用 `node scripts/export_primary_weekly_workbook.mjs` 生成，需要可用的 `@oai/artifact-tool` 包。归档诊断只用于追溯，参考教材不随项目发布。

## English

The [weekly workbook](results/tables/primary_weekly_holdings.xlsx) contains all 444 rebalance decisions and 13,320 ETF records, with pretrade weights, targets, changes and costs. Calendar-week returns and subsequent holding-period returns are separate; the final week and holding period are truncated at the sample boundary. All 30 ETFs remain visible, including zero weights. Publication charts have matching vector PDFs and 300-dpi PNGs.

### Models and method

The project compares seven models. **Improved Convex Adaptive Global RRP** is the primary model and rebalances on the last trading day of each week. The other six models retain monthly schedules.

The primary model tracks a convex risk-budget reference and penalizes turnover. It is long-only and unlevered, with no cash-group or individual-asset concentration cap. Other group bounds and the 80% turnover limit remain. The active CVaR penalty is zero.

### Performance

The common evaluation window is **2018-01-02 to 2026-08-31**. Returns retain extreme observations, deduct the assumed 3-bp one-way cost, and use 243-day annualization with a **zero risk-free rate**.

| Model | Net return | Volatility | Sharpe | Sortino | Max drawdown | Monthly turnover |
|---|---:|---:|---:|---:|---:|---:|
| Improved Convex Adaptive Global RRP | 2.92% | 1.56% | 1.859 | 2.648 | -2.63% | 4.36% |
| Global RRP | 2.40% | 0.58% | 4.103 | 6.496 | -1.01% | 12.89% |
| Convex Adaptive Global RRP | 5.87% | 6.02% | 0.979 | 1.382 | -8.18% | 2.59% |
| HRP Benchmark | 2.03% | 0.26% | 7.674 | 17.069 | -0.19% | 1.95% |
| HERC Benchmark | 2.44% | 0.82% | 2.958 | 4.432 | -1.53% | 7.17% |
| Equal Weight | 9.21% | 12.92% | 0.747 | 1.057 | -18.25% | 4.73% |
| 60/40 Benchmark | 6.98% | 11.84% | 0.629 | 0.905 | -20.04% | 4.21% |

The primary model averages **70.23%** in the money-market ETF, reaching **86.61%**. Its Sharpe is **0.529** when lagged one-year ChinaBond yields are used as opportunity cost. Cash concentration and the rate convention both matter when interpreting the headline ratio.

The specification was selected after reviewing historical experiments. Rebalance inputs use prior data, while specification selection is retrospective. Validation on new data is still required. The designation of a primary model does not imply the highest Sharpe among comparisons.

Run `python scripts/run_primary_publication_pipeline.py` with `TUSHARE_TOKEN` set to reproduce the results and PDFs. The linked files above provide parameters, audits, annual results and holdings. Constraint and frequency variants are experiments within the seven-model study. Archived diagnostics do not validate the current specification.
