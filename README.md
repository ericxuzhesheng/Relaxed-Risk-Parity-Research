# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

<p align="center">
  <a href="#中文"><img src="https://img.shields.io/badge/语言-中文-E84D3D?style=for-the-badge&labelColor=3B3F47" alt="中文"></a>
  &nbsp;
  <a href="#english"><img src="https://img.shields.io/badge/Language-English-2F73C9?style=for-the-badge&labelColor=3B3F47" alt="English"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/资产池-30只ETF · 8类-F2C94C?style=for-the-badge" alt="30 ETF">
  <img src="https://img.shields.io/badge/评估区间-2018--2026 · 103个月-4CAF50?style=for-the-badge" alt="2018-2026">
  <img src="https://img.shields.io/badge/Sharpe-1.186 · MaxDD --3.81%25-9B51E0?style=for-the-badge" alt="Sharpe 1.186">
</p>

---

## 中文

### 一句话概览

本项目是一个面向本科论文与可复现实证研究的量化资产配置框架：在中国可交易 ETF 约束下，将经典风险平价扩展为 **Relaxed Risk Parity (RRP)**，并进一步构建 **Convex Adaptive Global RRP** 与 **Improved Convex Adaptive Global RRP**，用于研究低换手、CVaR 尾部风险控制和全球多资产配置的权衡。

**主结论不是“追求最高收益”，而是：** 在纯多头、无杠杆、月度再平衡和 3 bps 单边交易成本下，滚动自动选择的 Improved Convex Adaptive Global RRP 以 **5.60%** 净年化收益、**2.88%** 年化波动、**1.186** Sharpe、**-3.81%** 最大回撤和 **1.96%** 月均换手率，提供了一条强调路径风险与实施成本的配置方案。

### 快速导航

| 你想看什么 | 入口 |
|---|---|
| 核心模型和定位 | [模型定位](#模型定位) |
| 最新绩效数字 | [最新绩效](#最新绩效) |
| ETF 资产池 | [资产池](#资产池) |
| 图表和持仓解释 | [关键图表](#关键图表) |
| 稳健性与过拟合控制 | [稳健性验证](#稳健性验证) |
| 如何复现 | [快速开始](#快速开始) |

---

### 研究问题

> 在不依赖主观收益率预测的前提下，如何通过风险预算的系统性松弛设计，在风险均衡与收益目标之间取得可控平衡，并在中国可交易 ETF 的全球多资产框架下实现低成本落地？

经典风险平价要求各资产风险贡献严格相等，在实证中容易压制高夏普资产配置，并在协方差结构变化时带来高换手。本文的处理方式是：保留风险预算的可解释性，同时允许风险贡献在目标附近有约束地浮动，再通过凸优化、CVaR 约束和换手惩罚把模型推向可执行版本。

### 模型定位

| Public Label | 定位 | 说明 |
|---|---|---|
| Standard Risk Parity | 基准 | 风险贡献严格均等 |
| Local Relaxed Risk Parity | 本土扩展 | 仅使用本土资产池的 RRP |
| **Global RRP** | **主展示模型** | 体现宽松风险平价在 30-ETF 全球资产池中的收益效率 |
| Convex Adaptive Global RRP | 凸自适应版本 | 将松弛风险预算近似为可解的凸优化问题 |
| **Improved Convex Adaptive Global RRP** | **低换手、CVaR-aware 实施版本** | 主打可实施性、低换手、尾部风险控制与稳定配置 |
| Defensive Dynamic RRP | 防御实验 | 风险覆盖层实验，不是主收益最大化模型 |
| HRP Benchmark / HERC Benchmark | 基准 | 层次化风险分配参考，不是本文主模型 |

### 方法摘要

| 模块 | 作用 |
|---|---|
| 风险预算松弛 | 将严格风险贡献平价放宽为可调风险预算，避免过度刚性 |
| 凸自适应重构 | 用凸化近似替代原始非凸问题，提高求解稳定性和速度 |
| CVaR 约束 | 显式限制尾部损失，服务风险厌恶型长期资金 |
| 换手惩罚 | 将交易成本和调仓稳定性纳入目标函数 |
| 资产组约束 | 防止单一资产类别过度集中 |
| 稳健性验证 | 通过滚动样本外、walk-forward、CSCV-PBO、bootstrap 和压力期检验约束结论范围 |

---

### 资产池

当前资产池来自 `src/asset_universe.py`，共 **30 只 ETF、8 类资产**。ETF请求区间为 `2000-01-01` 至 `2026-07-31`，实际最长有效行情为 `2007-01-18` 至 `2026-07-31`；绩效评价固定从 `2018-01-02` 开始。时点可投过滤要求每支ETF累计达到60个有效观察后才进入组合，2018年初可投18支；6支候选ETF始终不参与回测。

| 类别 | ETF 数量 | 代表性标的 |
|---|---:|---|
| 债券与现金 | 5 | 可转债ETF、5年国债ETF、10年国债ETF、信用债ETF、日利ETF |
| A股宽基 | 6 | 沪深300ETF、中证500ETF、中证1000ETF、中证2000ETF、创业板ETF、红利ETF |
| 中国科技与成长 | 4 | 半导体ETF、人工智能ETF、新能源ETF、科创50ETF |
| 中国行业与消费 | 3 | 证券ETF、军工ETF、消费ETF |
| 港股 | 1 | 恒生ETF |
| 全球股票 | 4 | 纳指ETF、标普500ETF、日经225ETF、欧洲ETF |
| 贵金属 | 2 | 黄金ETF、白银LOF |
| 大宗商品与资源 | 5 | 有色金属期货ETF、能源化工期货ETF、豆粕ETF、煤炭ETF、原油ETF |

候选池共 6 只，暂不进入回测：30年国债ETF（511090.SH）、中韩半导体ETF（513310.SH）、证券公司先锋策略ETF（516980.SH）、沙特ETF（520830.SH）、巴西ETF（520870.SH）、机器人ETF（562500.SH）。其中 `516980.SH` 此前在项目中误标为“云计算ETF”，现已按 Tushare 官方基金信息更正。

若未来出现具备足够流动性和可用历史的公募 REITs ETF，项目将在下一轮资产池评审中重点评估其纳入价值，以补充基础设施与不动产收益来源。

本次同时生成了 36 只 ETF 的 7 维 Barra-style 代理敞口及相关性诊断，覆盖中国市场、规模、价值、久期、信用、商品和全球股票风险源。该结果是基于 ETF 收益率构造的透明代理，并非商业 MSCI Barra 模型数据；方法定义与完整矩阵见 `data/processed/barra_style_methodology.json` 和 `data/processed/barra_style_exposure_correlation.csv`。

### 最新绩效

评价区间：`2018-01-02` 至 `2026-07-31`。交易成本：单边 3 bps，月度再平衡。Sharpe与Sortino使用每月最后有效的1年期中债国债到期收益率，滞后一个月并按243个交易日复利转换为日度无风险收益。

利率更新以 [Tushare `yc_cb`](https://tushare.pro/document/2?doc_id=201) 为首选；本次因本地账户无该接口权限，实际使用[中国债券信息网官方历史曲线](https://yield.chinabond.com.cn/cbweb-czb-web/czb/showHistory?locale=cn_ZH&nameType=1)补取。两来源同日数值若冲突则停止发布，不静默择值。

| 模型 | 净年化收益 | 年化波动 | Sharpe | Sortino | 最大回撤 | Calmar | 月均换手 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Global RRP | 4.28% | 4.13% | 0.53 | 0.75 | -6.32% | 0.68 | 24.51% |
| Defensive Dynamic RRP | 5.09% | 4.71% | 0.64 | 0.90 | -6.64% | 0.77 | 24.58% |
| Convex Adaptive Global RRP | 9.35% | 17.25% | 0.48 | 0.71 | -28.87% | 0.32 | 0.00% |
| Improved Convex Adaptive Global RRP | 5.60% | 2.88% | 1.19 | 1.70 | -3.81% | 1.47 | 1.96% |
| HRP Benchmark | 2.07% | 0.26% | -0.12 | -0.18 | -0.19% | 10.96 | 2.34% |
| HERC Benchmark | 2.57% | 0.72% | 0.65 | 0.93 | -0.69% | 3.73 | 9.12% |
| Equal Weight | 7.73% | 10.56% | 0.56 | 0.81 | -12.89% | 0.60 | 0.96% |
| 60/40 Benchmark | 6.34% | 9.78% | 0.47 | 0.67 | -19.55% | 0.32 | 0.93% |

Improved Convex Adaptive Global Relaxed Risk Parity 是自 2018-01-02 起连续拼接的 AFML 风格滚动样本外路径。每季度仅在预先声明的低换手候选族中，依据已完成的六个月验证窗构造95%置信集，并设置一个交易日的隔离期；统计并列时按事先规定的低换手顺序选择，完整样本排名不回填历史权重。

### 关键图表

**全模型净值对比**

<p align="center"><img src="results/figures/convex_adaptive_nav_comparison.png" width="860" alt="Convex Adaptive NAV Comparison"></p>

**回撤路径对比**

<p align="center"><img src="results/figures/convex_adaptive_drawdown_comparison.png" width="860" alt="Convex Adaptive Drawdown Comparison"></p>

**换手率对比**

<p align="center"><img src="results/figures/convex_adaptive_turnover_comparison.png" width="860" alt="Convex Adaptive Turnover Comparison"></p>

**CVaR 尾部风险对比**

<p align="center"><img src="results/figures/convex_adaptive_cvar_comparison.png" width="860" alt="Convex Adaptive CVaR Comparison"></p>

**Improved Convex Adaptive Global RRP 持仓路径**

<p align="center"><img src="results/figures/improved_weights_timeline.png" width="860" alt="Improved Convex Adaptive Global RRP Weights"></p>

组合长期以5年国债ETF和日利ETF为稳定底仓，黄金ETF提供尾部风险和通胀对冲，A股宽基与全球股票暴露随协方差结构动态调整。2020 年 3 月流动性冲击期间，组合明显向债券和现金管理工具倾斜，体现自适应风险预算的防御特征。

<!-- BEGIN MONTHLY_HS300_COMPARISON_CN -->
### 与沪深300ETF的月度收益对比

截至 `2026-07`，Improved Convex Adaptive Global RRP 与沪深300ETF的月度对比显示：策略累计收益为 **59.97%**，沪深300ETF为 **66.50%**；策略月度波动率 **0.79%**，显著低于沪深300ETF的 **4.63%**；日频最大回撤分别为 **-3.81%** 与 **-38.85%**。策略在 53/103 个月跑赢沪深300ETF，最近一个月（2026-07）策略收益 **0.63%**，沪深300ETF **-7.29%**。

![Improved RRP vs CSI 300 ETF monthly comparison](results/figures/improved_rrp_vs_hs300_monthly_comparison.png)
<!-- END MONTHLY_HS300_COMPARISON_CN -->
### 稳健性验证

| 验证方法 | 用途 | 结论边界 |
|---|---|---|
| Walk-forward validation | 滚动样本外参数选择 | 检验参数是否只适配完整样本 |
| 滚动样本外审计 | 仅使用历史数据的季度选择 | 核验隔离期、置信集、换手门槛及测试窗不重选 |
| CSCV-PBO | 多候选过拟合概率诊断 | 当前 PBO 低于 0.5，但仍是参考值而非未来保证 |
| Block bootstrap | 对 Sharpe 和回撤做重采样 | 评估结果对样本路径扰动的敏感性 |
| 协方差估计稳健性 | 比较 sample、Ledoit-Wolf、EWMA 等估计器 | 主要结论不依赖单一协方差估计器 |
| 参数扰动 | 改变关键惩罚项和 CVaR 阈值 | 输出随参数平滑变化，无明显断崖 |
| 调仓频率敏感性 | 比较周度、双周、月度、季度调仓 | 月度当前排名第一，但仍是预设实施规则而非事后择优结果 |

<p align="center"><img src="results/figures/robustness_bootstrap_sharpe_distribution.png" width="760" alt="Bootstrap Sharpe Distribution"></p>

<p align="center"><img src="results/figures/rebalance_frequency_sensitivity.png" width="860" alt="Rebalance Frequency Sensitivity"></p>

保持已发布滚动样本外选择日历不变、仅改变调仓频率时，周度和双周调仓的净年化收益分别为 **5.38%** 和 **5.36%**，Sharpe 分别为 **1.118** 和 **1.109**，平均月换手率分别为 **3.06%** 和 **2.54%**。月度调仓对应 **5.60%** 净年化收益、**1.186** Sharpe、**-3.81%** 最大回撤和 **1.96%** 平均月换手率；季度调仓换手率降至 **1.69%**，净年化收益和 Sharpe 为 **5.26%** 和 **1.042**。月度调仓在本次样本中恰好取得四种频率中的最高净收益和 Sharpe，但仍是基于响应速度、交易成本和配置稳定性的预设实施规则。

### 项目结构

```text
.
├── src/                       # 核心优化、回测、验证模块
├── scripts/                   # 数据更新与研究流水线
├── results/tables/            # 权威 CSV 结果
├── results/figures/           # README、论文和答辩使用的图
├── report/thesis_latex/       # 论文 LaTeX 源文件
├── report/ppt/                # 答辩 Beamer 源文件与 PDF
└── data/                      # ETF 价格数据与中间数据
```

### 快速开始

```bash
pip install -r requirements.txt

# 更新 ETF 数据，需要 Tushare token
export TUSHARE_TOKEN=your_token_here
python scripts/update_etf_data.py --provider tushare --start-date 20150101

# 运行完整研究流水线
python scripts/run_full_research_pipeline.py

# 仅运行凸自适应主模型
python scripts/run_convex_adaptive_rrp.py
```

---

## English

### At A Glance

This repository is a thesis-oriented quantitative asset allocation project. It extends classical Risk Parity into a **Relaxed Risk Parity (RRP)** framework, then builds convex, turnover-aware, CVaR-aware variants for a China-accessible global ETF universe.

The main result is not a maximum-return trading strategy. Under a long-only, unlevered, monthly-rebalanced ETF setting with 3 bps one-way transaction cost, the rolling automatically selected **Improved Convex Adaptive Global RRP** delivers **5.60%** net annual return, **2.88%** annual volatility, **1.186** Sharpe, **-3.81%** maximum drawdown, and **1.96%** average monthly turnover.

### Navigation

| Looking for | Section |
|---|---|
| Model definitions | [Model Positioning](#model-positioning) |
| Latest results | [Latest Performance](#latest-performance) |
| ETF universe | [Asset Universe](#asset-universe) |
| Charts and interpretation | [Key Figures](#key-figures) |
| Robustness checks | [Robustness Validation](#robustness-validation) |
| Reproduction | [Quick Start](#quick-start) |

### Research Question

> Without relying on subjective return forecasts, how can a systematically relaxed risk-budgeting design balance risk equalization against return objectives, while remaining implementable in a globally diversified universe of China-accessible ETFs?

Classical Risk Parity forces all risk contributions to be equal. This is interpretable but rigid: it can suppress exposure to high-Sharpe assets and generate excessive turnover when the covariance structure changes. This project keeps the interpretability of risk budgeting while allowing controlled deviations from strict equality, then adds convex optimization, CVaR constraints, turnover penalties, and group limits for implementation.

### Model Positioning

| Public Label | Role | Description |
|---|---|---|
| Standard Risk Parity | Baseline | Strict equal risk contributions |
| Local Relaxed Risk Parity | Local extension | RRP restricted to the local asset pool |
| **Global RRP** | **Main showcase model** | Return-efficient global 30-ETF RRP |
| Convex Adaptive Global RRP | Convex approximation | Convexified relaxed risk-budgeting approximation |
| **Improved Convex Adaptive Global RRP** | **Implementable refinement** | Low-turnover, CVaR-aware, stable allocation model |
| Defensive Dynamic RRP | Defensive experiment | Risk-overlay experiment, not the main return-maximizing model |
| HRP Benchmark / HERC Benchmark | Benchmarks | Hierarchical allocation references |

### Method Summary

| Module | Purpose |
|---|---|
| Relaxed risk budgeting | Softens strict equal-risk-contribution constraints |
| Convex adaptive reformulation | Improves solver stability and scalability |
| CVaR constraint | Controls tail-loss exposure |
| Turnover penalty | Internalizes trading cost and allocation stability |
| Group limits | Prevents excessive concentration in one asset class |
| Robustness validation | Bounds conclusions through rolling OOS, walk-forward, CSCV-PBO, bootstrap, and stress-period checks |

### Asset Universe

The universe is defined in `src/asset_universe.py`: **30 ETFs across 8 asset categories**. Requests cover `2000-01-01` through `2026-07-31`; the longest valid ETF history is `2007-01-18` through `2026-07-31`, and performance evaluation is fixed at `2018-01-02` through `2026-07-31`. Each ETF enters only after 60 valid observations; 18 were investable at the start. The six candidates remain fully excluded from backtests.

| Category | ETF Count | Representative Exposures |
|---|---:|---|
| Bonds and cash | 5 | Convertible bond, 5-year government bond, 10-year government bond, credit bond, money market |
| China broad equity | 6 | CSI 300, CSI 500, CSI 1000, CSI 2000, ChiNext, dividend |
| China technology and growth | 4 | Semiconductor, AI, new energy, STAR 50 |
| China sectors and consumer | 3 | Securities, defense, consumer |
| Hong Kong equity | 1 | Hang Seng ETF |
| Global equity | 4 | Nasdaq-100, S&P 500, Nikkei 225, Europe |
| Precious metals | 2 | Gold, silver |
| Commodities and resources | 5 | Non-ferrous metals futures, energy and chemicals futures, soybean meal, coal, crude oil |

The six-ETF candidate pool, excluded from backtests until the next universe review, is: 30-year government bond (511090.SH), China-Korea semiconductor (513310.SH), securities-company pioneer strategy (516980.SH), Saudi Arabia (520830.SH), Brazil (520870.SH), and robotics (562500.SH). Tushare's official fund record identifies `516980.SH` as a securities-company strategy ETF; the former project label “cloud computing ETF” was incorrect and has been corrected.

If a public REITs ETF develops sufficient liquidity and usable history, the next universe review will evaluate it as an infrastructure and real-estate income sleeve.

This update also produces seven-dimensional Barra-style proxy exposures and exposure correlations for all 36 ETFs, covering China market, size, value, duration, credit, commodity, and global-equity risk sources. These are transparent ETF-return proxies, not licensed MSCI Barra model data; see `data/processed/barra_style_methodology.json` and `data/processed/barra_style_exposure_correlation.csv` for the definitions and full matrix.

### Latest Performance

Evaluation period: `2018-01-02` to `2026-07-31`. Transaction cost: 3 bps one-way, monthly rebalancing. Sharpe and Sortino use the final valid monthly 1-year ChinaBond government yield, lagged one month and compounded to a daily rate over 243 trading days.

The updater prefers [Tushare `yc_cb`](https://tushare.pro/document/2?doc_id=201). Because the local account lacked permission for that endpoint in this run, the audited fallback came from the [official ChinaBond historical curve](https://yield.chinabond.com.cn/cbweb-czb-web/czb/showHistory?locale=cn_ZH&nameType=1). A same-day source conflict stops publication.

| Model | Net Annual Return | Annual Vol | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly TO |
|---|---:|---:|---:|---:|---:|---:|---:|
| Global RRP | 4.28% | 4.13% | 0.53 | 0.75 | -6.32% | 0.68 | 24.51% |
| Defensive Dynamic RRP | 5.09% | 4.71% | 0.64 | 0.90 | -6.64% | 0.77 | 24.58% |
| Convex Adaptive Global RRP | 9.35% | 17.25% | 0.48 | 0.71 | -28.87% | 0.32 | 0.00% |
| Improved Convex Adaptive Global RRP | 5.60% | 2.88% | 1.19 | 1.70 | -3.81% | 1.47 | 1.96% |
| HRP Benchmark | 2.07% | 0.26% | -0.12 | -0.18 | -0.19% | 10.96 | 2.34% |
| HERC Benchmark | 2.57% | 0.72% | 0.65 | 0.93 | -0.69% | 3.73 | 9.12% |
| Equal Weight | 7.73% | 10.56% | 0.56 | 0.81 | -12.89% | 0.60 | 0.96% |
| 60/40 Benchmark | 6.34% | 9.78% | 0.47 | 0.67 | -19.55% | 0.32 | 0.93% |

Improved Convex Adaptive Global Relaxed Risk Parity is one continuous AFML-inspired rolling OOS path from 2018-01-02. Each quarter forms a 95% confidence set within the predeclared low-turnover family using only the completed six-month validation window, followed by a one-trading-day embargo. Statistical ties follow the predeclared low-turnover order; full-sample ranks never backfill historical weights.

### Key Figures

<p align="center"><img src="results/figures/convex_adaptive_nav_comparison.png" width="860" alt="Convex Adaptive NAV Comparison"></p>

<p align="center"><img src="results/figures/convex_adaptive_drawdown_comparison.png" width="860" alt="Convex Adaptive Drawdown Comparison"></p>

<p align="center"><img src="results/figures/convex_adaptive_turnover_comparison.png" width="860" alt="Convex Adaptive Turnover Comparison"></p>

<p align="center"><img src="results/figures/convex_adaptive_cvar_comparison.png" width="860" alt="Convex Adaptive CVaR Comparison"></p>

<p align="center"><img src="results/figures/improved_weights_timeline.png" width="860" alt="Improved Convex Adaptive Global RRP Weights"></p>

<!-- BEGIN MONTHLY_HS300_COMPARISON_EN -->
### Monthly Return Comparison vs CSI 300 ETF

Through `2026-07`, the Improved Convex Adaptive Global RRP delivered **59.97%** cumulative return versus **66.50%** for the CSI 300 ETF proxy. Its monthly volatility was **0.79%**, far below the CSI 300 ETF's **4.63%**; daily maximum drawdowns were **-3.81%** and **-38.85%**, respectively. The strategy outperformed in 53/103 months. In the latest month (2026-07), the strategy returned **0.63%** versus **-7.29%** for the CSI 300 ETF.

![Improved RRP vs CSI 300 ETF monthly comparison](results/figures/improved_rrp_vs_hs300_monthly_comparison.png)
<!-- END MONTHLY_HS300_COMPARISON_EN -->
### Robustness Validation

| Method | Purpose | Boundary |
|---|---|---|
| Walk-forward validation | Rolling out-of-sample parameter selection | Tests whether parameters only fit the full sample |
| Rolling OOS audit | Prior-data-only quarterly selection | Verifies embargo, confidence-set selection, turnover gates, and absence of test-window reselection |
| CSCV-PBO | Overfitting probability diagnostic | PBO is below 0.5, but remains a diagnostic rather than a future guarantee |
| Block bootstrap | Resampling of Sharpe and drawdown | Tests sensitivity to path variation |
| Covariance robustness | Sample, Ledoit-Wolf, EWMA and related estimators | Main conclusions do not depend on one estimator |
| Parameter perturbation | Vary key penalties and CVaR threshold | Performance changes smoothly without cliff-edge behavior |
| Rebalance frequency sensitivity | Weekly, biweekly, monthly, and quarterly rebalancing | Monthly currently ranks first, but remains an implementation choice rather than an ex-post selection rule |

<p align="center"><img src="results/figures/robustness_bootstrap_sharpe_distribution.png" width="760" alt="Bootstrap Sharpe Distribution"></p>

<p align="center"><img src="results/figures/rebalance_frequency_sensitivity.png" width="860" alt="Rebalance Frequency Sensitivity"></p>

Holding the published rolling OOS selection schedule constant and changing only the rebalance calendar, weekly and biweekly rebalancing deliver **5.38%** and **5.36%** net annual return, Sharpe ratios of **1.118** and **1.109**, and average monthly turnover of **3.06%** and **2.54%**. Monthly rebalancing delivers **5.60%** net annual return, **1.186** Sharpe, **-3.81%** maximum drawdown, and **1.96%** average monthly turnover. Quarterly rebalancing lowers turnover to **1.69%**, with **5.26%** net annual return and **1.042** Sharpe. Monthly happens to rank first in this sample, but remains a predeclared implementation choice based on responsiveness, trading cost, and allocation stability.

### Repository Structure

```text
.
├── src/                       # Core optimization, backtest, and validation modules
├── scripts/                   # Data update and research pipeline scripts
├── results/tables/            # Authoritative CSV results
├── results/figures/           # Figures used by README, thesis, and defense slides
├── report/thesis_latex/       # Thesis LaTeX source
├── report/ppt/                # Defense Beamer source and PDF
└── data/                      # ETF price data and intermediate files
```

### Quick Start

```bash
pip install -r requirements.txt

export TUSHARE_TOKEN=your_token_here
python scripts/update_etf_data.py --provider tushare --start-date 20150101

python scripts/run_full_research_pipeline.py
python scripts/run_convex_adaptive_rrp.py
```

---

## License

MIT License.
