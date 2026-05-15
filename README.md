# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

<p align="center">
  <a href="#zh"><img src="https://img.shields.io/badge/LANGUAGE-中文-E84D3D?style=for-the-badge&labelColor=3B3F47" alt="LANGUAGE 中文"></a>
  <a href="#en"><img src="https://img.shields.io/badge/LANGUAGE-ENGLISH-2F73C9?style=for-the-badge&labelColor=3B3F47" alt="LANGUAGE ENGLISH"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/Asset-Global%20Multi--Asset-F2C94C?style=for-the-badge" alt="Global Multi-Asset">
  <img src="https://img.shields.io/badge/Strategy-Relaxed%20Risk%20Parity-7AC943?style=for-the-badge" alt="Relaxed Risk Parity">
  <img src="https://img.shields.io/badge/Overlay-Defensive%20Dynamic%20RRP-9B51E0?style=for-the-badge" alt="Defensive Dynamic RRP">
</p>

<a id="zh"></a>

## 中文

### 项目概览
本项目研究宽松风险平价在全球多资产配置中的应用，重点比较传统风险平价、本土宽松风险平价、全球宽松风险平价、防御型动态风险覆盖模型，以及 HRP / HERC 层次化配置 benchmark。

### 核心模型
| 模型 | 定位 | 说明 |
|---|---|---|
| Standard Risk Parity | 基准模型 | 传统风险贡献均衡组合 |
| Local Relaxed Risk Parity | 本土宽松模型 | 在风险平价约束中引入松弛项，平衡风险均衡与收益目标 |
| Global Relaxed Risk Parity | 主展示模型 | 扩展到全球多资产配置，是当前收益效率最高的主模型 |
| Defensive Dynamic Relaxed Risk Parity | 防御型动态模型 | 在全球宽松风险平价基础上加入风险覆盖层，管理回撤、趋势、波动率和换手 |
| HRP Benchmark / HERC Benchmark | 横向 benchmark | 用于检验层次聚类配置是否能替代 RRP 型全球配置 |

Defensive Dynamic Relaxed Risk Parity is not designed to mechanically maximize Sharpe. Its role is to reduce risk exposure during adverse regimes, so it should be evaluated together with maximum drawdown, Calmar ratio, downside behavior, and turnover.

### 最新结果看板
评估区间从 `2019-01-01` 开始，截至 `2026-04-30`，数据来源 `results/tables/convex_adaptive_performance_summary.csv`。
| 模型 | 净年化收益 | 年化波动 | Sharpe | Sortino | 最大回撤 | Calmar | 月度换手率 |
|---|---:|---:|---:|---:|---:|---:|---:|
| Global RRP | 4.57% | 4.07% | 0.677 | 0.797 | -6.43% | 0.711 | 19.90% |
| Defensive Dynamic RRP | 3.81% | 4.08% | 0.488 | 0.576 | -6.51% | 0.586 | 17.91% |
| Convex Adaptive Global RRP | 7.09% | 5.23% | 1.007 | 1.541 | -6.65% | 1.065 | 1.03% |
| **Improved Convex Adaptive Global RRP** | **5.84%** | **2.72%** | **1.480** | **2.181** | **-3.90%** | **1.499** | **3.28%** |
| HRP Benchmark | 1.69% | 0.18% | -0.761 | -1.199 | -0.08% | 20.69 | 0.88% |
| HERC Benchmark | 2.26% | 0.54% | 0.828 | 1.261 | -0.58% | 3.891 | 5.24% |

Improved Convex Adaptive Global RRP 是对凸自适应优化器的受约束参数细化版本，采用回撤与换手约束感知的选择标准，在净年化收益、Sharpe 比率与最大回撤之间取得最均衡的结果。

<a id="en"></a>

## English

### Project Overview
This repository studies Relaxed Risk Parity for global multi-asset allocation, comparing classical risk parity, local and global relaxed variants, a defensive dynamic overlay, and HRP / HERC hierarchical benchmarks.

### Core Models
| Model | Role | Description |
|---|---|---|
| Standard Risk Parity | Baseline | Classical risk-contribution balancing |
| Local Relaxed Risk Parity | Local relaxed model | Balances risk parity with return objectives through relaxation terms |
| Global Relaxed Risk Parity | Main showcase model | Global multi-asset extension and the main return-efficient model |
| Defensive Dynamic Relaxed Risk Parity | Defensive overlay | Manages drawdown, trend, volatility, re-entry, and turnover controls |
| HRP Benchmark / HERC Benchmark | Benchmarks | Hierarchical allocation references, not the main contribution |

Defensive Dynamic Relaxed Risk Parity is not designed to mechanically maximize Sharpe. Its role is to reduce risk exposure during adverse regimes, so it should be evaluated together with maximum drawdown, Calmar ratio, downside behavior, and turnover.

### Latest Results
Evaluation window: `2019-01-01` to `2026-04-30`. Source: `results/tables/convex_adaptive_performance_summary.csv`.
| Model | Net Annual Return | Annual Vol | Sharpe | Sortino | Max Drawdown | Calmar | Monthly TO |
|---|---:|---:|---:|---:|---:|---:|---:|
| Global RRP | 4.57% | 4.07% | 0.677 | 0.797 | -6.43% | 0.711 | 19.90% |
| Defensive Dynamic RRP | 3.81% | 4.08% | 0.488 | 0.576 | -6.51% | 0.586 | 17.91% |
| Convex Adaptive Global RRP | 7.09% | 5.23% | 1.007 | 1.541 | -6.65% | 1.065 | 1.03% |
| **Improved Convex Adaptive Global RRP** | **5.84%** | **2.72%** | **1.480** | **2.181** | **-3.90%** | **1.499** | **3.28%** |
| HRP Benchmark | 1.69% | 0.18% | -0.761 | -1.199 | -0.08% | 20.69 | 0.88% |
| HERC Benchmark | 2.26% | 0.54% | 0.828 | 1.261 | -0.58% | 3.891 | 5.24% |

Improved Convex Adaptive Global RRP is a constrained parameter refinement of the convex adaptive optimizer, selected with drawdown and turnover-aware criteria. It achieves Sharpe 1.480 and Sortino 2.181 with 3.28% average monthly turnover and maximum drawdown limited to -3.90%.

## License
MIT License.
