# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

<p align="center">
  <a href="#zh"><img src="https://img.shields.io/badge/语言-中文-E84D3D?style=for-the-badge&labelColor=3B3F47" alt="中文"></a>
  &nbsp;
  <a href="#en"><img src="https://img.shields.io/badge/Language-English-2F73C9?style=for-the-badge&labelColor=3B3F47" alt="English"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/资产池-30只ETF · 8类-F2C94C?style=for-the-badge" alt="30 ETF">
  <img src="https://img.shields.io/badge/策略-宽松风险平价-7AC943?style=for-the-badge" alt="Relaxed Risk Parity">
  <img src="https://img.shields.io/badge/覆盖层-防御型动态-9B51E0?style=for-the-badge" alt="Defensive Dynamic">
</p>

---

<a id="zh"></a>

## 中文

### 项目概览

本项目是一篇关于**宽松风险平价（Relaxed Risk Parity, RRP）**在全球多资产配置中应用的学术研究。研究从最基础的标准风险平价出发，逐步扩展至包含 30 只中国可交易 ETF 的全球多资产框架，并引入凸自适应优化、CVaR 约束、换手率控制与防御型动态风险覆盖层，最终形成一套完整的、可实施的量化资产配置体系。

核心研究问题：在不依赖主观预期收益率的前提下，如何通过风险预算的松弛化设计，在风险均衡与收益目标之间取得系统性平衡？

---

### 研究背景与动机

传统风险平价要求所有资产的风险贡献严格均等，牺牲了组合的灵活性。本研究引入**松弛项（relaxation term）**，允许风险贡献在一定范围内偏离均等，同时通过凸化处理保证优化问题的可解性。主要创新点：

- 将风险平价约束松弛化，建立可调节的风险预算框架；
- 从国内资产池扩展至覆盖中国境内 + 港股 + 全球四大市场的 30 只 ETF；
- 引入凸自适应优化器（Convex Adaptive），将非凸的松弛风险平价问题转化为可高效求解的凸优化问题；
- 在凸自适应模型基础上进一步施加 CVaR 尾部风险约束与换手率约束，形成低成本可实施版本；
- 通过在线政权识别（Online Regime）与动态覆盖层对极端市场状态进行防御性降仓；
- 全面的稳健性验证体系（CSCV-PBO 过拟合诊断、Walk-Forward 验证、Holdout 样本外验证、Block Bootstrap 等）。

---

### 核心模型

| 模型 | 定位 | 核心特征 |
|---|---|---|
| Standard Risk Parity | 基准模型 | 风险贡献严格均等，无松弛项 |
| Local Relaxed Risk Parity | 本土宽松模型 | 仅限国内资产池，引入松弛项平衡风险均衡与收益目标 |
| Global RRP | 主展示模型 | 扩展至全球 30 只 ETF，当前最高收益效率的核心模型 |
| Convex Adaptive Global RRP | 凸自适应模型 | 将松弛风险平价凸化，显著降低换手率，提升 Sharpe |
| Improved Convex Adaptive Global RRP | 改进凸自适应 | 加入 CVaR 约束 + 换手率感知选参，进一步降低波动与回撤 |
| Defensive Dynamic RRP | 防御型动态模型 | 在全球 RRP 基础上加入动态风险覆盖层，管理极端行情下的回撤 |
| HRP Benchmark | 层次化基准 | 层次风险平价，用于衡量聚类配置能否替代 RRP 型全球配置 |
| HERC Benchmark | 层次化基准 | 层次等风险贡献，横向 benchmark |

> **注意：** Defensive Dynamic RRP 并非以机械最大化 Sharpe 为目标，其作用是在不利市场环境下降低风险暴露。评估时应结合最大回撤、Calmar 比率、下行行为与换手率综合判断。

---

### 资产池：30 只 ETF，8 类资产

评估区间所有 ETF 均通过时间点可投性过滤，最早入市 ETF 为 2018-01-30，全 30 只 ETF 均可投资的评估起始日为 2019-01-01。

| 类别 | ETF 名称 | 代码 | 资产说明 |
|---|---|---|---|
| **债券** | 可转债ETF | 511380.SH | 可转债，兼具债券保护与股票上行弹性 |
| | 国债ETF | 511010.SH | 长久期利率锚，风险平价组合的久期核心 |
| | 信用债ETF | 511030.SH | 信用利差敞口，高于国债的收益补偿 |
| | 日利ETF | 511880.SH | 货币市场，超短久期现金管理层 |
| **A股宽基** | 沪深300ETF | 510300.SH | A股大盘蓝筹，CSI 300指数 |
| | 中证500ETF | 510500.SH | A股中盘，CSI 500指数 |
| | 中证1000ETF | 512100.SH | A股小盘，CSI 1000指数 |
| | 创业板ETF | 159915.SZ | 创业板成长股，上市年限较长的增长型企业 |
| | 红利ETF | 510880.SH | 高股息防御型A股，偏稳健风格 |
| **中国科技与成长** | 半导体ETF | 512480.SH | 半导体硬件，芯片产业链核心因子 |
| | 人工智能ETF | 159819.SZ | AI应用软件、算法与服务 |
| | 机器人ETF | 562500.SH | 工业自动化与智能制造 |
| | 新能源ETF | 516160.SH | 电动车、储能与光伏综合敞口 |
| | 中韩半导体ETF | 513310.SH | 叠加DRAM/NAND记忆芯片与韩元汇率维度 |
| | 科创50ETF | 588000.SH | 科创板50，中国科技自主化蓝筹 |
| | 云计算ETF | 516980.SH | SaaS、云基础设施与数字服务 |
| **中国行业与消费** | 证券ETF | 512880.SH | 券商板块，市场周期性贝塔 |
| | 军工ETF | 512660.SH | 国防与军工，航空航天与高端装备 |
| | 消费ETF | 159928.SZ | 主要消费品，食品饮料与家庭用品 |
| **港股** | 恒生ETF | 159920.SZ | 港股宽基，香港市场综合敞口 |
| **全球股票** | 纳指ETF | 159941.SZ | 纳斯达克100，美国科技与成长敞口 |
| | 标普500ETF | 513500.SH | 标普500，美国大盘蓝筹 |
| | 日经225ETF | 513880.SH | 日经225，日本股市敞口 |
| | 欧洲ETF | 513030.SH | 标普欧洲350，欧洲发达市场 |
| **贵金属** | 黄金ETF | 518880.SH | 黄金，抗通胀与尾部风险对冲 |
| | 白银LOF | 161226.SZ | 白银，贵金属通胀对冲，与股票相关性低 |
| **大宗商品** | 有色ETF | 159980.SZ | 有色金属，工业商品需求敞口 |
| | 豆粕ETF | 159985.SZ | 豆粕，农产品商品敞口 |
| | 煤炭ETF | 515220.SH | 煤炭，传统能源供给动态 |
| | 原油ETF | 162411.SZ | 标普能源指数，原油价格敞口 |

---

### 最新绩效看板

评估区间：`2019-01-01` 至 `2026-04-30`（88个月）。交易成本设定为单边 3bps，按月再平衡。数据来源：`results/tables/convex_adaptive_performance_summary.csv`。

| 模型 | 净年化收益 | 年化波动率 | Sharpe | Sortino | 最大回撤 | Calmar | 月均换手率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Improved Convex Adaptive Global RRP** | **5.66%** | **2.61%** | **1.47** | **2.17** | **-3.70%** | **1.53** | **2.25%** |
| Convex Adaptive Global RRP | 6.96% | 5.25% | 0.98 | 1.50 | -6.65% | 1.05 | 1.21% |
| Global RRP | 4.78% | 4.11% | 0.72 | 0.83 | -7.14% | 0.67 | 22.81% |
| Defensive Dynamic RRP | 4.95% | 4.48% | 0.70 | 0.87 | -7.11% | 0.70 | 24.57% |
| HRP Benchmark | 1.69% | 0.18% | -0.75 | -1.18 | -0.08% | 20.72 | 1.08% |
| HERC Benchmark | 2.25% | 0.57% | 0.75 | 1.10 | -0.58% | 3.86 | 5.55% |
| Equal Weight | 10.81% | 11.09% | 0.81 | 1.30 | -13.91% | 0.78 | 1.24% |
| 60/40 Benchmark | 8.10% | 8.92% | 0.70 | 1.13 | -14.58% | 0.56 | 1.43% |

**核心结论：**
- Improved Convex Adaptive Global RRP 以最低波动率（2.61%）和最小回撤（-3.70%）实现 Sharpe 1.47、Calmar 1.53，是兼顾实施成本与风险控制的最优模型；
- Convex Adaptive Global RRP 实现最高净年化收益（6.96%），适合对波动容忍度较高的配置场景；
- Global RRP 保持良好的风险收益均衡，是体现宽松风险平价核心逻辑的主展示模型；
- Defensive Dynamic RRP 在回撤控制上与 Global RRP 相近，其价值体现在极端市场情境下的动态降仓能力。

---

### 稳健性验证

研究包含以下系统性稳健性检验：

| 验证方法 | 说明 |
|---|---|
| CSCV-PBO 过拟合诊断 | 组合横截验证（CSCV）+ 概率偏倚过拟合（PBO）检验，量化策略过拟合风险 |
| Walk-Forward Validation | 滚动样本外回测，验证参数在未见数据上的稳定性 |
| Holdout Validation | 独立 Holdout 区间的样本外验证 |
| Block Bootstrap | 有放回分块重采样，评估绩效指标的统计显著性 |
| 子区间分析 | 多个子区间绩效分解，检验跨周期一致性 |
| 协方差矩阵稳健性 | 多种协方差估计器下的结果对比 |
| 参数扰动测试 | 关键参数小幅扰动下的输出敏感性 |
| 压力情景测试 | 极端市场区间（如2020年2月、2022年全年）下的表现 |

---

### 文件结构

```
.
├── src/                         # 核心模块
│   ├── asset_universe.py        # 30只ETF定义与映射
│   ├── risk_parity.py           # 标准与宽松风险平价优化器
│   ├── convex_adaptive_rrp.py   # 凸自适应优化器（主模型）
│   ├── risk_overlay.py          # 防御型动态风险覆盖层
│   ├── covariance_estimators.py # 协方差估计器集合
│   ├── hierarchical_risk_parity.py # HRP / HERC benchmark
│   ├── metrics.py               # 绩效指标计算
│   ├── backtest.py              # 回测引擎
│   └── validation.py            # 稳健性验证工具
├── scripts/                     # 运行脚本
│   ├── run_full_research_pipeline.py  # 完整研究流水线
│   ├── run_convex_adaptive_rrp.py     # 凸自适应模型
│   ├── run_robustness_tests.py        # 稳健性检验套件
│   ├── run_hrp_comparison.py          # HRP/HERC基准对比
│   └── update_etf_data.py             # ETF数据更新
├── results/tables/              # 所有数值结果（CSV）
├── report/thesis_latex/         # LaTeX论文源文件
├── data/                        # ETF价格数据
├── docs/                        # 项目文档
└── requirements.txt
```

---

### 快速开始

**环境配置**

```bash
pip install -r requirements.txt
```

**数据更新**（需要 Tushare Token）

```bash
export TUSHARE_TOKEN=your_token_here
python scripts/update_etf_data.py
```

**运行完整研究流水线**

```bash
python scripts/run_full_research_pipeline.py
```

**仅运行核心模型**

```bash
python scripts/run_convex_adaptive_rrp.py
```

---

<a id="en"></a>

## English

### Project Overview

This repository contains an academic research project on **Relaxed Risk Parity (RRP)** for global multi-asset allocation. Starting from classical risk parity, the research progressively extends to a global framework of 30 investable Chinese ETFs, incorporating convex adaptive optimization, CVaR tail-risk constraints, turnover controls, and a defensive dynamic risk overlay. The result is a complete, implementable quantitative asset allocation system.

Central research question: without relying on subjective return forecasts, how can a relaxed risk-budgeting design systematically balance risk equalization with return objectives?

---

### Research Background & Motivation

Classical risk parity imposes strict equal risk contribution across all assets, limiting portfolio flexibility. This research introduces a **relaxation term** that allows risk contributions to deviate from equality within bounds, while a convexification step guarantees tractable optimization. Key innovations:

- Relaxed risk parity constraints with a tunable risk-budget framework;
- Asset universe expanded from domestic-only to 30 ETFs covering China onshore, Hong Kong, and four major global equity markets;
- Convex Adaptive optimizer reformulating the non-convex relaxed risk parity problem into an efficiently solvable convex program;
- CVaR tail-risk constraints and turnover constraints applied to the convex adaptive model to produce a low-cost implementable variant;
- Online regime detection with a dynamic risk overlay for defensive de-risking during adverse market states;
- Comprehensive robustness validation (CSCV-PBO overfitting diagnostics, Walk-Forward, Holdout, Block Bootstrap, and more).

---

### Core Models

| Model | Role | Key Characteristics |
|---|---|---|
| Standard Risk Parity | Baseline | Strict equal risk contributions, no relaxation term |
| Local Relaxed Risk Parity | Local relaxed variant | Domestic asset pool only; relaxation term balances risk equality with return objective |
| Global RRP | Main showcase model | Global 30-ETF universe; the core return-efficient model |
| Convex Adaptive Global RRP | Convex adaptive variant | Convexifies relaxed risk parity; substantially lowers turnover and improves Sharpe |
| Improved Convex Adaptive Global RRP | Refined implementable model | Adds CVaR constraints and turnover-aware parameter selection; minimizes volatility and drawdown |
| Defensive Dynamic RRP | Defensive overlay | Adds a dynamic risk overlay on top of Global RRP to manage drawdown in adverse regimes |
| HRP Benchmark | Hierarchical benchmark | Hierarchical Risk Parity; tests whether cluster-based allocation can replace RRP-type global allocation |
| HERC Benchmark | Hierarchical benchmark | Hierarchical Equal Risk Contribution; cross-sectional benchmark |

> **Note:** Defensive Dynamic RRP is not designed to mechanically maximize Sharpe. Its role is to reduce risk exposure during adverse market regimes. It should be evaluated together with maximum drawdown, Calmar ratio, downside behavior, and turnover.

---

### Asset Universe: 30 ETFs across 8 Categories

All ETFs pass point-in-time investability filtering. The earliest ETF entered trading on 2018-01-30; the full 30-ETF universe becomes investable on 2019-01-01, which is used as the evaluation start date.

| Category | ETF Name | Ticker | Description |
|---|---|---|---|
| **Bonds** | Convertible Bond ETF (可转债ETF) | 511380.SH | Equity-linked credit exposure with downside protection |
| | Government Bond ETF (国债ETF) | 511010.SH | Duration anchor; core interest rate exposure in the risk parity portfolio |
| | Credit Bond ETF (信用债ETF) | 511030.SH | Credit spread exposure for yield pickup over government bonds |
| | Money Market ETF (日利ETF) | 511880.SH | Ultra-short duration cash management layer |
| **China Broad Equity** | CSI 300 ETF (沪深300ETF) | 510300.SH | China large-cap blue chips tracking the CSI 300 index |
| | CSI 500 ETF (中证500ETF) | 510500.SH | China mid-cap equity tracking the CSI 500 index |
| | CSI 1000 ETF (中证1000ETF) | 512100.SH | China small-cap equity tracking the CSI 1000 index |
| | ChiNext ETF (创业板ETF) | 159915.SZ | GEB growth companies with established listing history |
| | Dividend ETF (红利ETF) | 510880.SH | High-yield defensive A-share tilt |
| **China Tech & Growth** | Semiconductor ETF (半导体ETF) | 512480.SH | Core hardware factor across the China chip value chain |
| | Artificial Intelligence ETF (人工智能ETF) | 159819.SZ | AI software, algorithms, and applied services |
| | Robotics ETF (机器人ETF) | 562500.SH | Industrial automation and intelligent manufacturing |
| | New Energy ETF (新能源ETF) | 516160.SH | Electric vehicles, energy storage, and solar |
| | China-Korea Semiconductor ETF (中韩半导体ETF) | 513310.SH | Adds DRAM/NAND memory chip and KRW FX dimension |
| | STAR 50 ETF (科创50ETF) | 588000.SH | China's technology self-reliance blue chips on the STAR Market |
| | Cloud Computing ETF (云计算ETF) | 516980.SH | SaaS, cloud infrastructure, and digital services |
| **China Sectors & Consumer** | Securities ETF (证券ETF) | 512880.SH | China brokerage sector; market-cyclical beta |
| | Defense ETF (军工ETF) | 512660.SH | Aerospace, shipbuilding, and high-end equipment |
| | Consumer ETF (消费ETF) | 159928.SZ | Food, beverages, and household goods; domestic demand factor |
| **Hong Kong Equity** | Hang Seng ETF (恒生ETF) | 159920.SZ | Broad Hong Kong equity exposure tracking the Hang Seng index |
| **Global Equity** | Nasdaq-100 ETF (纳指ETF) | 159941.SZ | US growth and technology exposure |
| | S&P 500 ETF (标普500ETF) | 513500.SH | US large-cap blue-chip exposure |
| | Nikkei 225 ETF (日经225ETF) | 513880.SH | Japanese equity exposure |
| | Europe ETF (欧洲ETF) | 513030.SH | Developed European markets via S&P Europe 350 |
| **Precious Metals** | Gold ETF (黄金ETF) | 518880.SH | Inflation hedge and tail-risk diversifier |
| | Silver LOF (白银LOF) | 161226.SZ | Precious metal inflation hedge with low equity correlation |
| **Commodities** | Non-ferrous ETF (有色ETF) | 159980.SZ | Industrial commodity demand; base metals |
| | Soybean Meal ETF (豆粕ETF) | 159985.SZ | Agricultural commodity exposure |
| | Coal ETF (煤炭ETF) | 515220.SH | Traditional energy with independent supply dynamics |
| | Crude Oil ETF (原油ETF) | 162411.SZ | Global oil price exposure via S&P energy index |

---

### Latest Performance

Evaluation period: `2019-01-01` to `2026-04-30` (88 months). Transaction cost: 3 bps one-way, monthly rebalancing. Source: `results/tables/convex_adaptive_performance_summary.csv`.

| Model | Net Annual Return | Annual Vol | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly TO |
|---|---:|---:|---:|---:|---:|---:|---:|
| **Improved Convex Adaptive Global RRP** | **5.66%** | **2.61%** | **1.47** | **2.17** | **-3.70%** | **1.53** | **2.25%** |
| Convex Adaptive Global RRP | 6.96% | 5.25% | 0.98 | 1.50 | -6.65% | 1.05 | 1.21% |
| Global RRP | 4.78% | 4.11% | 0.72 | 0.83 | -7.14% | 0.67 | 22.81% |
| Defensive Dynamic RRP | 4.95% | 4.48% | 0.70 | 0.87 | -7.11% | 0.70 | 24.57% |
| HRP Benchmark | 1.69% | 0.18% | -0.75 | -1.18 | -0.08% | 20.72 | 1.08% |
| HERC Benchmark | 2.25% | 0.57% | 0.75 | 1.10 | -0.58% | 3.86 | 5.55% |
| Equal Weight | 10.81% | 11.09% | 0.81 | 1.30 | -13.91% | 0.78 | 1.24% |
| 60/40 Benchmark | 8.10% | 8.92% | 0.70 | 1.13 | -14.58% | 0.56 | 1.43% |

**Key takeaways:**
- Improved Convex Adaptive Global RRP achieves Sharpe 1.47 and Calmar 1.53 with the lowest volatility (2.61%) and smallest drawdown (-3.70%) of all risk-managed models — the best risk-adjusted implementable choice;
- Convex Adaptive Global RRP delivers the highest net annual return (6.96%) among risk-managed strategies, suitable when higher volatility tolerance is acceptable;
- Global RRP is the main showcase of the core relaxed risk parity logic, with a well-balanced risk-return profile;
- Defensive Dynamic RRP is not a return-maximizing model; its value lies in dynamic de-risking capability during adverse market regimes.

---

### Robustness Validation

The research includes the following systematic robustness checks:

| Method | Description |
|---|---|
| CSCV-PBO Overfitting Diagnostics | Combinatorially Symmetric Cross-Validation (CSCV) + Probability of Backtest Overfitting (PBO) to quantify overfitting risk |
| Walk-Forward Validation | Rolling out-of-sample backtest verifying parameter stability on unseen data |
| Holdout Validation | Independent holdout period out-of-sample test |
| Block Bootstrap | Resampling with replacement in blocks to assess statistical significance of performance metrics |
| Sub-period Analysis | Multi-period performance decomposition to verify cross-cycle consistency |
| Covariance Robustness | Results compared across multiple covariance estimators |
| Parameter Perturbation | Output sensitivity to small perturbations of key parameters |
| Stress Period Testing | Performance in extreme market episodes (e.g., February 2020, full-year 2022) |

---

### Repository Structure

```
.
├── src/                         # Core modules
│   ├── asset_universe.py        # 30-ETF definitions and mappings
│   ├── risk_parity.py           # Standard and relaxed risk parity optimizers
│   ├── convex_adaptive_rrp.py   # Convex adaptive optimizer (main model)
│   ├── risk_overlay.py          # Defensive dynamic risk overlay
│   ├── covariance_estimators.py # Covariance estimator suite
│   ├── hierarchical_risk_parity.py # HRP / HERC benchmarks
│   ├── metrics.py               # Performance metric calculations
│   ├── backtest.py              # Backtesting engine
│   └── validation.py            # Robustness validation utilities
├── scripts/                     # Execution scripts
│   ├── run_full_research_pipeline.py  # Full research pipeline
│   ├── run_convex_adaptive_rrp.py     # Convex adaptive model
│   ├── run_robustness_tests.py        # Robustness validation suite
│   ├── run_hrp_comparison.py          # HRP / HERC benchmark comparison
│   └── update_etf_data.py             # ETF data update
├── results/tables/              # All numerical results (CSV)
├── report/thesis_latex/         # LaTeX thesis source files
├── data/                        # ETF price data
├── docs/                        # Project documentation
└── requirements.txt
```

---

### Quick Start

**Install dependencies**

```bash
pip install -r requirements.txt
```

**Update ETF data** (requires a Tushare token)

```bash
export TUSHARE_TOKEN=your_token_here
python scripts/update_etf_data.py
```

**Run the full research pipeline**

```bash
python scripts/run_full_research_pipeline.py
```

**Run the core model only**

```bash
python scripts/run_convex_adaptive_rrp.py
```

---

## License

MIT License.
