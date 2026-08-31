# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

<p align="center">
  <a href="#中文"><img src="https://img.shields.io/badge/语言-中文-E84D3D?style=for-the-badge&labelColor=3B3F47" alt="中文"></a>
  &nbsp;
  <a href="#english"><img src="https://img.shields.io/badge/Language-English-2F73C9?style=for-the-badge&labelColor=3B3F47" alt="English"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/资产池-30只ETF · 8类-F2C94C?style=for-the-badge" alt="30 ETF">
  <img src="https://img.shields.io/badge/评估区间-2018--2026 · 104个月-4CAF50?style=for-the-badge" alt="2018-2026">
  <img src="https://img.shields.io/badge/Sharpe-1.272 · MaxDD --3.83%25-9B51E0?style=for-the-badge" alt="Sharpe 1.272">
</p>

---

## 中文

### 给招生官的项目摘要

这份仓库记录了一个完整的本科量化研究过程。项目从一个明确的问题出发，研究严格风险平价在真实 ETF 资产池中的局限，随后提出宽松风险预算方法，并把它推进到可计算、可回测、可审计的全球多资产框架。仓库保留了数据更新、组合优化、滚动样本外选择、稳健性检验、论文和答辩材料，研究结论可以沿着代码与 CSV 结果逐项核对。

研究使用中国市场可交易的 30 只 ETF，覆盖 8 类资产。核心结果来自 `2018-01-02` 至 `2026-08-28` 的连续滚动样本外路径。在纯多头、无杠杆、月度再平衡和单边 3 bps 交易成本下，Improved Convex Adaptive Global RRP 取得 **5.85%** 净年化收益、**2.88%** 年化波动、**1.272** Sharpe、**-3.83%** 最大回撤和 **1.95%** 月均换手率。这些数字用于检验研究假设，无法承诺未来收益。

如果时间有限，可以先看下面几项。

| 内容 | 可以看到什么 |
|---|---|
| [论文 PDF](report/thesis_latex/main.pdf) | 研究问题、文献脉络、模型推导、实证结果与局限 |
| [答辩 PDF](report/ppt/rrp_defense.pdf) | 十余分钟内了解研究主线与关键证据 |
| [权威结果表](results/tables/convex_adaptive_performance_summary.csv) | README 与论文中核心绩效数字的来源 |
| [核心模型代码](src/convex_adaptive_rrp.py) | 凸自适应优化与实施约束 |
| [无前视审计](results/tables/robustness_no_lookahead_audit.csv) | 各模块怎样限制未来数据进入计算 |
| [下月模型持仓](results/tables/next_month_holdings.csv) | 截至 2026-08-28 的完整模型输出 |

### 研究问题

> 在不依赖主观收益率预测的条件下，怎样有控制地放宽严格风险平价，并在中国可交易 ETF 构成的全球资产池中兼顾风险分散、尾部损失、换手成本与求解稳定性？

经典风险平价要求各资产贡献相同的组合风险。这个规则容易解释，也可能在协方差结构变化时产生高换手，并压低部分风险收益特征较好资产的权重。项目保留风险预算的透明结构，允许风险贡献在目标附近浮动，再通过凸优化、CVaR 约束、换手惩罚和资产组上限约束组合行为。

### 研究工作与可核验证据

| 研究环节 | 项目中的处理 | 核验入口 |
|---|---|---|
| 问题定义 | 将宽松风险预算放入中国可交易的全球 ETF 资产池 | [论文正文](report/thesis_latex/main.pdf) |
| 数据设计 | 30 只 ETF、8 类资产、60 个有效观察后才进入时点可投池 | [`asset_universe.py`](src/asset_universe.py) |
| 模型实现 | 从标准风险平价逐步扩展到 Global RRP 与凸自适应版本 | [`src`](src) |
| 实施约束 | 在目标函数和约束中纳入 CVaR、换手与资产组集中度 | [`convex_adaptive_rrp.py`](src/convex_adaptive_rrp.py) |
| 样本外选择 | 候选模型只使用当时已经完成的验证窗，并设置一个交易日隔离期 | [无前视审计表](results/tables/robustness_no_lookahead_audit.csv) |
| 结论检验 | 使用 walk-forward、CSCV-PBO、block bootstrap、压力期和调仓频率检验 | [`results/tables`](results/tables) |
| 研究复现 | 数据、图表、论文数字与模型输出由脚本统一生成 | [`scripts`](scripts) |

### 模型定位

| Public Label | 研究角色 | 说明 |
|---|---|---|
| Standard Risk Parity | 基准 | 严格等风险贡献参考 |
| Local Relaxed Risk Parity | 本土扩展 | 仅使用本土资产池的 RRP |
| **Global RRP** | **主要收益效率模型** | 在 30-ETF 全球资产池中检验宽松风险平价 |
| Convex Adaptive Global RRP | 凸近似模型 | 可求解的宽松风险预算凸化近似 |
| **Improved Convex Adaptive Global RRP** | **可实施改进模型** | 强调低换手、CVaR 尾部风险控制与稳定配置 |
| Defensive Dynamic RRP | 防御实验 | 风险覆盖层实验，不承担主要收益模型的角色 |
| HRP Benchmark / HERC Benchmark | 基准 | 层次化风险分配参考 |

最终权重均由透明优化产生。图结构、市场状态与统计诊断只为模型提供信息，不直接生成组合权重。

### 主要实证结果

评价区间为 `2018-01-02` 至 `2026-08-28`，共 104 个月度观察。回测采用月度再平衡和单边 3 bps 交易成本。Sharpe 与 Sortino 使用每月最后一个有效的 1 年期中债国债到期收益率，滞后一个月并按 243 个交易日复利换算为日度无风险收益。

| 模型 | 净年化收益 | 年化波动 | Sharpe | Sortino | 最大回撤 | Calmar | 月均换手 |
|---|---|---|---|---|---|---|---|
| Global RRP | 4.70% | 4.16% | 0.63 | 0.89 | -6.39% | 0.74 | 24.08% |
| Defensive Dynamic RRP | 5.21% | 4.72% | 0.66 | 0.94 | -7.02% | 0.74 | 24.23% |
| Convex Adaptive Global RRP | 9.30% | 17.31% | 0.48 | 0.70 | -28.87% | 0.32 | 0.00% |
| **Improved Convex Adaptive Global RRP** | **5.85%** | **2.88%** | **1.27** | **1.83** | **-3.83%** | **1.53** | **1.95%** |
| HRP Benchmark | 2.06% | 0.26% | -0.12 | -0.19 | -0.19% | 10.90 | 2.34% |
| HERC Benchmark | 2.62% | 0.72% | 0.73 | 1.06 | -0.69% | 3.80 | 9.01% |
| Equal Weight | 8.27% | 10.57% | 0.61 | 0.88 | -12.88% | 0.64 | 0.95% |
| 60/40 Benchmark | 6.62% | 9.80% | 0.49 | 0.71 | -19.52% | 0.34 | 0.93% |

Improved Convex Adaptive Global RRP 的价值主要体现在风险调整后表现和实施成本。它放弃了 Convex Adaptive Global RRP 的一部分收益，换来更低的波动、回撤和换手。HRP 与 HERC 的风险尺度明显不同，Calmar 等比率不能脱离收益、波动和 Sharpe 单独排序。

<p align="center"><img src="results/figures/convex_adaptive_nav_comparison.png" width="860" alt="Convex Adaptive NAV Comparison"></p>

净值图展示 Global RRP、Convex Adaptive Global RRP 与改进模型的累计收益路径。三条路径说明了收益、波动和实施约束之间的实际取舍。

<p align="center"><img src="results/figures/convex_adaptive_drawdown_comparison.png" width="860" alt="Convex Adaptive Drawdown Comparison"></p>

回撤图把压力期风险直接放在同一尺度上。改进模型的低波动有明确的风险约束和稳定配置作为依据，也能在压力期路径中直接观察。

### 结论怎样接受检验

Improved Convex Adaptive Global RRP 是从 2018 年开始连续拼接的 AFML 风格滚动样本外路径。每季度只使用当时已经完成的六个月验证窗选择候选，并设置一个交易日隔离期。36 组参数构成探索网格，公开结果来自预先声明的置信集与低换手选择顺序。

| 检验 | 当前证据 | 能说明什么 |
|---|---|---|
| 滚动样本外审计 | 季度选择只读取历史窗口 | 降低测试窗信息进入选择过程的风险 |
| CSCV-PBO | PBO 为 **31.43%** | 提供过拟合诊断，不能证明模型不会过拟合 |
| Block bootstrap | 重采样 Sharpe 与回撤路径 | 检查结论对样本顺序扰动的敏感度 |
| 协方差稳健性 | 比较 sample、Ledoit-Wolf、EWMA 等估计器 | 检查结论是否依赖单一估计方法 |
| 参数扰动 | 改变惩罚项与 CVaR 阈值 | 检查结果是否出现断崖式变化 |
| 调仓频率 | 比较周度、双周、月度与季度 | 检查收益、风险与换手之间的实施取舍 |

<p align="center"><img src="results/figures/robustness_bootstrap_sharpe_distribution.png" width="760" alt="Bootstrap Sharpe Distribution"></p>

<p align="center"><img src="results/figures/rebalance_frequency_sensitivity.png" width="860" alt="Rebalance Frequency Sensitivity"></p>

保持滚动样本外选择日历不变，只改变调仓频率时，周度、双周、月度和季度调仓的 Sharpe 分别为 **1.194**、**1.192**、**1.272** 和 **1.139**。月度调仓在当前样本中恰好排名第一。项目采用月度规则的依据仍是响应速度、交易成本和配置稳定性之间的实施平衡，这项选择不依赖事后排名。

本研究仍有明确边界。ETF 成立时间不同，早期可投资产少于完整资产池。历史样本包含的市场状态有限，交易成本也采用统一假设。PBO、bootstrap 与压力测试只能帮助识别脆弱性，无法把历史表现转化为未来保证。

<!-- BEGIN MONTHLY_HS300_COMPARISON_CN -->
### 与沪深300ETF的月度收益对比

截至 `2026-08`，Improved Convex Adaptive Global RRP 与沪深300ETF的月度对比显示，策略累计收益为 **64.09%**，沪深300ETF为 **60.64%**。策略月度波动率为 **0.80%**，沪深300ETF为 **4.60%**。两者的日频最大回撤分别为 **-3.83%** 与 **-39.56%**。策略在 55/104 个月跑赢沪深300ETF。2026 年 8 月，策略收益为 **2.32%**，沪深300ETF为 **0.56%**。

![Improved RRP vs CSI 300 ETF monthly comparison](results/figures/improved_rrp_vs_hs300_monthly_comparison.png)
<!-- END MONTHLY_HS300_COMPARISON_CN -->

### 数据与资产池

资产池以 [`src/asset_universe.py`](src/asset_universe.py) 为单一事实来源，共有 **30 只 ETF、8 类资产**。最长有效行情覆盖 `2007-01-18` 至 `2026-08-28`，绩效评价固定从 `2018-01-02` 开始。每只 ETF 积累 60 个有效观察后才进入时点可投池，2018 年初共有 18 只可投资产。

| 类别 | ETF 数量 | 代表性标的 |
|---|---|---|
| 债券与现金 | 5 | 可转债ETF、5年国债ETF、信用债ETF、日利ETF |
| A股宽基 | 6 | 沪深300ETF、中证500ETF、中证1000ETF、红利ETF |
| 中国科技与成长 | 4 | 半导体ETF、人工智能ETF、新能源ETF、科创50ETF |
| 中国行业与消费 | 3 | 证券ETF、军工ETF、消费ETF |
| 港股 | 1 | 恒生ETF |
| 全球股票 | 4 | 纳指ETF、标普500ETF、日经225ETF、欧洲ETF |
| 贵金属 | 2 | 黄金ETF、白银LOF |
| 大宗商品与资源 | 5 | 有色金属期货ETF、豆粕ETF、煤炭ETF、原油ETF |

另有 6 只候选 ETF，直到下一次资产池评审前都不进入回测。完整清单和分类见 [`asset_universe.py`](src/asset_universe.py)。项目还生成 7 维 Barra-style 代理敞口，用于解释 ETF 的收益风险来源。这些敞口是基于 ETF 收益率的透明分析估计，与商业 MSCI Barra 数据有明确区别。

无风险利率优先读取 [Tushare `yc_cb`](https://tushare.pro/document/2?doc_id=201)。当前账户无接口权限时，流水线改用[中国债券信息网官方历史曲线](https://yield.chinabond.com.cn/cbweb-czb-web/czb/showHistory?locale=cn_ZH&nameType=1)。同日数据发生冲突时，流水线会停止发布。

### 2026 年 9 月模型持仓

以下权重使用截至 `2026-08-28` 的可得信息，适用于 2026 年 9 月。完整 26 项实质非零权重见 [`next_month_holdings.csv`](results/tables/next_month_holdings.csv)。它们是历史模型输出，不构成个别证券建议。

| ETF | 代码 | 权重 |
|---|---|---|
| 日利ETF | 511880.SH | 30.00% |
| 信用债ETF | 511030.SH | 16.32% |
| 5年国债ETF | 511010.SH | 13.20% |
| 10年国债ETF | 511260.SH | 8.83% |
| 黄金ETF | 518880.SH | 5.40% |
| 红利ETF | 510880.SH | 3.49% |
| 可转债ETF | 511380.SH | 3.34% |
| 豆粕ETF | 159985.SZ | 3.05% |
| 标普500ETF | 513500.SH | 3.01% |
| 原油ETF | 162411.SZ | 2.42% |
| 纳指ETF | 159941.SZ | 1.60% |
| 有色金属期货ETF | 159980.SZ | 1.55% |

### 复现研究

```bash
pip install -r requirements.txt

export TUSHARE_TOKEN=your_token_here
python scripts/update_etf_data.py --provider tushare --start-date 20000101 --end-date 20260828

python scripts/run_full_research_pipeline.py
python scripts/run_convex_adaptive_rrp.py
```

```text
.
├── src/                       # 核心优化、回测与验证模块
├── scripts/                   # 数据更新和研究流水线
├── results/tables/            # 权威 CSV 结果
├── results/figures/           # README、论文和答辩图表
├── report/thesis_latex/       # 论文源文件与 PDF
├── report/ppt/                # 答辩源文件与 PDF
└── data/                      # ETF 行情和中间数据
```

---

## English

### Project Summary for Admissions Review

This repository presents a complete undergraduate quantitative research project. It begins with a specific limitation of strict Risk Parity, develops a relaxed risk-budgeting framework, and carries that idea through data construction, optimization, rolling out-of-sample selection, robustness tests, thesis writing, and defense materials. The code and authoritative CSV outputs provide an auditable path from the research question to each reported result.

The study uses 30 China-accessible ETFs across eight asset categories. Its core evidence is a continuous rolling out-of-sample path from `2018-01-02` to `2026-08-28`. Under long-only, unlevered, monthly rebalancing with 3 bps one-way transaction cost, Improved Convex Adaptive Global RRP records **5.85%** net annual return, **2.88%** annual volatility, **1.272** Sharpe, **-3.83%** maximum drawdown, and **1.95%** average monthly turnover. These figures test the research hypothesis and do not imply future performance.

| Start here | What it shows |
|---|---|
| [Thesis PDF](report/thesis_latex/main.pdf) | Research question, literature, model derivation, evidence, and limitations |
| [Defense PDF](report/ppt/rrp_defense.pdf) | A concise presentation of the research argument |
| [Authoritative results](results/tables/convex_adaptive_performance_summary.csv) | Source for the headline performance figures |
| [Core model](src/convex_adaptive_rrp.py) | Convex adaptive optimization and implementation constraints |
| [No-look-ahead audit](results/tables/robustness_no_lookahead_audit.csv) | How each component prevents future data from entering calculations |
| [Next-month allocation](results/tables/next_month_holdings.csv) | Complete model output as of 2026-08-28 |

### Research Question

> How can strict Risk Parity be relaxed in a controlled and transparent way, without relying on subjective return forecasts, while addressing diversification, tail loss, turnover, and solver stability in a global universe of China-accessible ETFs?

Classical Risk Parity assigns equal contributions to portfolio risk. The rule is interpretable, yet it can produce high turnover when covariance changes and can limit exposure to assets with stronger risk-adjusted characteristics. This project allows risk contributions to move within controlled bounds, then constrains portfolio behavior through convex optimization, CVaR control, turnover penalties, and asset-group limits.

### Research Work and Evidence

| Research stage | Implementation | Evidence |
|---|---|---|
| Problem formulation | Relaxed risk budgeting in a China-accessible global ETF universe | [Thesis](report/thesis_latex/main.pdf) |
| Data design | 30 ETFs, eight categories, point-in-time eligibility after 60 valid observations | [`asset_universe.py`](src/asset_universe.py) |
| Model implementation | Standard Risk Parity through Global RRP and convex adaptive variants | [`src`](src) |
| Implementation constraints | CVaR, turnover, and group concentration in the objective and constraints | [`convex_adaptive_rrp.py`](src/convex_adaptive_rrp.py) |
| Out-of-sample selection | Completed validation windows with a one-trading-day embargo | [No-look-ahead audit](results/tables/robustness_no_lookahead_audit.csv) |
| Validation | Walk-forward, CSCV-PBO, block bootstrap, stress periods, and rebalance tests | [`results/tables`](results/tables) |
| Reproduction | Scripts regenerate data, figures, thesis numbers, and model outputs | [`scripts`](scripts) |

### Model Positioning

| Public Label | Research Role | Description |
|---|---|---|
| Standard Risk Parity | Baseline | Strict equal-risk-contribution reference |
| Local Relaxed Risk Parity | Local extension | RRP restricted to the local asset pool |
| **Global RRP** | **Main return-efficient model** | Tests relaxed risk budgeting in the global 30-ETF universe |
| Convex Adaptive Global RRP | Convex approximation | Solvable convexified relaxed risk-budgeting approximation |
| **Improved Convex Adaptive Global RRP** | **Implementable refinement** | Low turnover, CVaR tail-risk control, and stable allocation |
| Defensive Dynamic RRP | Defensive experiment | Risk-overlay experiment outside the main return model |
| HRP Benchmark / HERC Benchmark | Benchmarks | Hierarchical allocation references |

Final portfolio weights come from transparent optimization. Graph features, market-state information, and statistical diagnostics inform the process but do not directly generate weights.

### Main Empirical Results

The evaluation covers `2018-01-02` through `2026-08-28`, with 104 monthly observations, monthly rebalancing, and 3 bps one-way transaction cost. Sharpe and Sortino use the final valid monthly one-year ChinaBond government yield, lagged one month and compounded to a daily rate over 243 trading days.

| Model | Net Annual Return | Annual Vol | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly TO |
|---|---|---|---|---|---|---|---|
| Global RRP | 4.70% | 4.16% | 0.63 | 0.89 | -6.39% | 0.74 | 24.08% |
| Defensive Dynamic RRP | 5.21% | 4.72% | 0.66 | 0.94 | -7.02% | 0.74 | 24.23% |
| Convex Adaptive Global RRP | 9.30% | 17.31% | 0.48 | 0.70 | -28.87% | 0.32 | 0.00% |
| **Improved Convex Adaptive Global RRP** | **5.85%** | **2.88%** | **1.27** | **1.83** | **-3.83%** | **1.53** | **1.95%** |
| HRP Benchmark | 2.06% | 0.26% | -0.12 | -0.19 | -0.19% | 10.90 | 2.34% |
| HERC Benchmark | 2.62% | 0.72% | 0.73 | 1.06 | -0.69% | 3.80 | 9.01% |
| Equal Weight | 8.27% | 10.57% | 0.61 | 0.88 | -12.88% | 0.64 | 0.95% |
| 60/40 Benchmark | 6.62% | 9.80% | 0.49 | 0.71 | -19.52% | 0.34 | 0.93% |

Improved Convex Adaptive Global RRP is strongest on risk-adjusted performance and implementation cost. It gives up part of the Convex Adaptive Global RRP return in exchange for materially lower volatility, drawdown, and turnover. HRP and HERC operate at very different risk scales, so Calmar should be read together with return, volatility, and Sharpe.

<p align="center"><img src="results/figures/convex_adaptive_nav_comparison.png" width="860" alt="Convex Adaptive NAV Comparison"></p>

<p align="center"><img src="results/figures/convex_adaptive_drawdown_comparison.png" width="860" alt="Convex Adaptive Drawdown Comparison"></p>

### How the Claim Is Tested

Improved Convex Adaptive Global RRP is a continuous AFML-inspired rolling out-of-sample path from 2018. Quarterly selection uses only the completed six-month validation window and applies a one-trading-day embargo. The 36-configuration grid is exploratory. The public path follows a predeclared confidence-set and low-turnover tie-break order.

| Test | Current evidence | Interpretation |
|---|---|---|
| Rolling OOS audit | Quarterly choices read historical windows only | Reduces the risk of test-window information entering selection |
| CSCV-PBO | Overfitting probability diagnostic is **31.43%** | A diagnostic of overfitting risk, with no proof against overfitting |
| Block bootstrap | Resampled Sharpe and drawdown paths | Measures sensitivity to changes in sample ordering |
| Covariance robustness | Sample, Ledoit-Wolf, EWMA, and related estimators | Checks dependence on a single covariance estimator |
| Parameter perturbation | Penalties and CVaR thresholds vary | Checks for cliff-edge behavior |
| Stress-period checks | Portfolio paths during major market shocks | Examines whether risk control remains visible in difficult periods |
| Rebalance frequency sensitivity | Weekly, biweekly, monthly, and quarterly | Shows the implementation tradeoff among performance, risk, and turnover |

<p align="center"><img src="results/figures/robustness_bootstrap_sharpe_distribution.png" width="760" alt="Bootstrap Sharpe Distribution"></p>

<p align="center"><img src="results/figures/rebalance_frequency_sensitivity.png" width="860" alt="Rebalance Frequency Sensitivity"></p>

With the rolling OOS selection schedule held constant, weekly, biweekly, monthly, and quarterly Sharpe ratios are **1.194**, **1.192**, **1.272**, and **1.139**. Monthly rebalancing happens to rank first in this sample. It remains a predeclared implementation choice based on responsiveness, transaction cost, and allocation stability.

The study has clear limits. ETF inception dates differ, leaving fewer investable assets early in the sample. Historical data cover a finite set of market regimes, and transaction costs use a uniform assumption. PBO, bootstrap, and stress tests can reveal fragility but cannot turn historical performance into a future guarantee.

<!-- BEGIN MONTHLY_HS300_COMPARISON_EN -->
### Monthly Return Comparison with the CSI 300 ETF

Through `2026-08`, Improved Convex Adaptive Global RRP delivered **64.09%** cumulative return, compared with **60.64%** for the CSI 300 ETF proxy. Monthly volatility was **0.80%** and **4.60%**, respectively, while daily maximum drawdowns were **-3.83%** and **-39.56%**. The model outperformed in 55 of 104 months. In August 2026, it returned **2.32%**, compared with **0.56%** for the CSI 300 ETF.

![Improved RRP vs CSI 300 ETF monthly comparison](results/figures/improved_rrp_vs_hs300_monthly_comparison.png)
<!-- END MONTHLY_HS300_COMPARISON_EN -->

### Data and Asset Universe

[`src/asset_universe.py`](src/asset_universe.py) is the single source of truth for the **30 ETFs across eight asset categories**. The longest valid price history runs from `2007-01-18` through `2026-08-28`, while performance evaluation begins on `2018-01-02`. Each ETF enters the point-in-time universe after 60 valid observations, leaving 18 investable assets at the start of 2018.

Six candidate ETFs remain excluded until the next scheduled universe review. The complete active and candidate lists are in [`asset_universe.py`](src/asset_universe.py). The project also produces seven-dimensional Barra-style proxy exposures estimated transparently from ETF returns. They are analytical proxies, not licensed MSCI Barra data.

The risk-free-rate updater prefers [Tushare `yc_cb`](https://tushare.pro/document/2?doc_id=201). When the local account lacks endpoint permission, the pipeline uses the [official ChinaBond historical curve](https://yield.chinabond.com.cn/cbweb-czb-web/czb/showHistory?locale=cn_ZH&nameType=1). A same-date source conflict stops publication.

### September 2026 Model Allocation

These weights use information available through `2026-08-28` and apply to September 2026. The complete 26-position materially nonzero allocation is in [`next_month_holdings.csv`](results/tables/next_month_holdings.csv). It is a historical model output, not individualized investment advice.

| ETF | Ticker | Weight |
|---|---|---|
| Money Market ETF | 511880.SH | 30.00% |
| Credit Bond ETF | 511030.SH | 16.32% |
| 5-Year Government Bond ETF | 511010.SH | 13.20% |
| 10-Year Government Bond ETF | 511260.SH | 8.83% |
| Gold ETF | 518880.SH | 5.40% |
| Dividend ETF | 510880.SH | 3.49% |
| Convertible Bond ETF | 511380.SH | 3.34% |
| Soybean Meal ETF | 159985.SZ | 3.05% |
| S&P 500 ETF | 513500.SH | 3.01% |
| Crude Oil ETF | 162411.SZ | 2.42% |
| Nasdaq-100 ETF | 159941.SZ | 1.60% |
| Non-ferrous Metals Futures ETF | 159980.SZ | 1.55% |

### Reproduce the Research

```bash
pip install -r requirements.txt

export TUSHARE_TOKEN=your_token_here
python scripts/update_etf_data.py --provider tushare --start-date 20000101 --end-date 20260828

python scripts/run_full_research_pipeline.py
python scripts/run_convex_adaptive_rrp.py
```

```text
.
├── src/                       # Optimization, backtesting, and validation
├── scripts/                   # Data updates and research pipelines
├── results/tables/            # Authoritative CSV outputs
├── results/figures/           # README, thesis, and defense figures
├── report/thesis_latex/       # Thesis sources and PDF
├── report/ppt/                # Defense sources and PDF
└── data/                      # ETF prices and intermediate data
```

---

## License

MIT License.
