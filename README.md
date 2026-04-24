# Relaxed Risk Parity Research: Dynamic Parameter Selection & Walk-Forward Optimization

### 宽松风险平价研究：动态参数选择与样本外验证框架

<p align="center">
  <a href="#简体中文">
    <img src="https://img.shields.io/badge/LANGUAGE-中文-E74C3C?style=for-the-badge&labelColor=4B4B4B" alt="Language Chinese" />
  </a>
  <a href="#english">
    <img src="https://img.shields.io/badge/LANGUAGE-ENGLISH-2D77D1?style=for-the-badge&labelColor=4B4B4B" alt="Language English" />
  </a>
</p>

---

<a id="简体中文"></a>

## 简体中文 | [English](#english)

## 📌 项目概览

本仓库是针对 **Relaxed Risk Parity (RRP)** 模型的工程化升级版本。在原有的 V1 (标准 RP)、V2 (本土 RRP) 和 V3 (全球 RRP) 基础上，引入了**动态参数选择 (Dynamic Parameter Selection)** 与 **前向行走验证 (Walk-Forward Optimization)** 框架。

核心目标是解决 RRP 模型中惩罚系数 $\lambda$ 和收益增强乘数 $m$ 的参数敏感性问题，通过滚动窗口自动选择最优参数，构建更具鲁棒性的资产配置策略。

## 🚀 核心功能升级

### 1. 动态参数选择 (Dynamic RRP)
- **滚动训练窗口**：使用过去 24 个月的数据作为训练集。
- **网格搜索**：在多维参数空间（$\lambda, m, leverage$）中搜索最优组合。
- **样本外验证**：在随后 1 个月的样本外窗口执行，形成 walk-forward NAV。
- **评价指标**：支持夏普比率、卡玛比率、年化收益等多种选择标准。

### 2. 参数稳定性审计
- 追踪参数随时间的切换频率。
- 分析 $\lambda$ 和 $m$ 在不同市场环境下的分布特征。
- 评估由于参数切换带来的额外换手率。

### 3. 工程化重构
- **模块化设计**：逻辑拆分为 `src/` 下的数据加载、风险平价、回测引擎等模块。
- **一键运行**：通过 `scripts/run_rrp_pipeline.py` 自动化执行全流程。
- **向后兼容**：保留 `RRP.py` 作为入口，兼容原有调用方式。

## 📊 回测结果对比 (示例)

| 模型 | 年化收益 | 年化波动 | 夏普比率 | 最大回撤 | 换手率 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| V1 Standard | 3.63% | 6.19% | 0.29 | -14.65% | 0.21% |
| V2 Relaxed | 4.95% | 7.15% | 0.44 | -14.65% | 0.68% |
| V3 Global | 6.41% | 7.18% | 0.64 | -14.92% | 0.87% |
| **Dynamic RRP** | **4.35%** | **6.35%** | **0.40** | **-14.92%** | **0.38%** |

*注：以上为 Fast Mode 运行结果，Dynamic RRP 在全球资产池上表现出比静态 V1 更优的风险调整后收益。*

## 📂 目录结构

```text
Relaxed-Risk-Parity-Research/
├── RRP.py (兼容入口)
├── src/ (核心模块)
│   ├── data_loader.py (数据加载与Wind对接)
│   ├── risk_parity.py (RRP模型优化器)
│   ├── dynamic_selection.py (滚动窗口选参)
│   ├── backtest.py (回测引擎)
│   └── visualization.py (绘图模块)
├── scripts/
│   └── run_rrp_pipeline.py (执行主脚本)
├── results/ (输出结果)
│   ├── figures/ (图表)
│   └── tables/ (数据表)
└── data/ (原始与处理后数据)
```

## 🛠 快速开始

### 安装依赖
```bash
pip install -r requirements.txt
```

### 运行全流程 (含动态选参)
```bash
# 快速模式 (小网格)
python scripts/run_rrp_pipeline.py --mode full --fast-mode

# 完整模式 (大网格)
python scripts/run_rrp_pipeline.py --mode full
```

---

<a id="english"></a>

## English | [简体中文](#简体中文)

## 📌 Project Overview

This repository is an engineered upgrade of the **Relaxed Risk Parity (RRP)** model. Based on the original V1 (Standard RP), V2 (Local RRP), and V3 (Global RRP), it introduces a **Dynamic Parameter Selection** and **Walk-Forward Optimization** framework.

The core objective is to address the parameter sensitivity of $\lambda$ (penalty) and $m$ (return multiplier) in the RRP model by automatically selecting optimal parameters via a rolling window, building a more robust asset allocation strategy.

## 🚀 Key Feature Upgrades

### 1. Dynamic Parameter Selection (Dynamic RRP)
- **Rolling Training Window**: Uses the past 24 months for training.
- **Grid Search**: Searches for the optimal combination in a multi-dimensional space ($\lambda, m, leverage$).
- **Out-of-Sample Validation**: Executes on the subsequent 1-month window to form a walk-forward NAV.
- **Selection Metrics**: Supports Sharpe Ratio, Calmar Ratio, Annualized Return, etc.

### 2. Parameter Stability Audit
- Tracks parameter switching frequency over time.
- Analyzes the distribution of $\lambda$ and $m$ across different market regimes.
- Evaluates additional turnover caused by parameter changes.

### 3. Engineering Refactoring
- **Modular Design**: Logic separated into `src/` for data loading, optimization, backtesting, etc.
- **Pipeline Execution**: Automated via `scripts/run_rrp_pipeline.py`.
- **Backward Compatibility**: `RRP.py` serves as a wrapper for legacy calls.

## 📊 Performance Comparison (Example)

| Model | Ann. Return | Ann. Vol | Sharpe | MaxDD | Turnover |
| :--- | :--- | :--- | :--- | :--- | :--- |
| V1 Standard | 3.63% | 6.19% | 0.29 | -14.65% | 0.21% |
| V2 Relaxed | 4.95% | 7.15% | 0.44 | -14.65% | 0.68% |
| V3 Global | 6.41% | 7.18% | 0.64 | -14.92% | 0.87% |
| **Dynamic RRP** | **4.35%** | **6.35%** | **0.40** | **-14.92%** | **0.38%** |

*Note: Results based on Fast Mode. Dynamic RRP shows improved risk-adjusted returns over static V1 in global pools.*

## 📂 Repository Structure

```text
Relaxed-Risk-Parity-Research/
├── RRP.py (Wrapper)
├── src/ (Core Modules)
│   ├── data_loader.py
│   ├── risk_parity.py
│   ├── dynamic_selection.py
│   ├── backtest.py
│   └── visualization.py
├── scripts/
│   └── run_rrp_pipeline.py
├── results/ (Outputs)
│   ├── figures/
│   └── tables/
└── data/ (Raw & Processed)
```

## 🛠 Quick Start

### Install Dependencies
```bash
pip install -r requirements.txt
```

### Run Full Pipeline
```bash
# Fast Mode (Small Grid)
python scripts/run_rrp_pipeline.py --mode full --fast-mode

# Full Mode (Comprehensive Grid)
python scripts/run_rrp_pipeline.py --mode full
```

---

## 📚 References
1. Gambeta & Kwon (2020). Risk return trade-off in relaxed risk parity.
2. López de Prado (2018). Advances in Financial Machine Learning.
3. Roncalli (2013). Introduction to Risk Parity and Budgeting.

## 📄 License
MIT License. See [LICENSE](LICENSE) for details.
