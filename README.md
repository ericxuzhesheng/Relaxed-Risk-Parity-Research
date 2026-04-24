# 宽松风险平价研究框架 | Relaxed Risk Parity Research

<p align="center">
  <a href="#zh"><img src="https://img.shields.io/badge/LANGUAGE-%E4%B8%AD%E6%96%87-E84D3D?style=for-the-badge&labelColor=3B3F47" alt="LANGUAGE 中文"></a>
  <a href="#en"><img src="https://img.shields.io/badge/LANGUAGE-ENGLISH-2F73C9?style=for-the-badge&labelColor=3B3F47" alt="LANGUAGE ENGLISH"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/Asset%20Allocation-Risk%20Parity-F2C94C?style=for-the-badge" alt="Asset Allocation">
  <img src="https://img.shields.io/badge/Model-Relaxed%20Risk%20Parity-7AC943?style=for-the-badge" alt="Relaxed Risk Parity">
</p>

<p align="center">
  A quantitative asset allocation research framework bridging standard Risk Parity, Relaxed Risk Parity, and dynamic walk-forward parameter selection.
</p>

---

<a id="zh"></a>

## 简体中文

当前语言：中文 | [Switch to English](#en)

### 📌 项目简介

本项目旨在低利率与全球宏观剧烈波动的环境下，对传统风险平价（Risk Parity）框架进行工程化改良。通过引入 **宽松风险平价（Relaxed Risk Parity, RRP）** 模型，解决了标准 RP 组合在低波动资产配置过高、收益弹性不足的问题。

本项目不仅包含了学术论文的复现，更提供了一套完整的**动态参数选择（Dynamic Parameter Selection）**与**前向行走验证（Walk-Forward Optimization）**框架。

### 🚀 核心版本演进

| 版本 | 模型类型 | 资产池范围 | 特性说明 |
| :--- | :--- | :--- | :--- |
| **V1** | 标准 RP | 本土资产 | 严格等风险贡献，无杠杆，稳健基准。 |
| **V2** | 宽松 RRP | 本土资产 | 引入松弛变量 $\rho$ 与惩罚项 $\lambda$，优化风险收益比。 |
| **V3** | 宽松 RRP | 全球资产 | 加入美债、标普500、日经225，利用全球分散化。 |
| **Dynamic** | 动态 RRP | 全球资产 | **最新升级**：滚动窗口自动选参，Top-K 参数平滑集成。 |

### 🧠 动态选参框架 (Walk-Forward)

为了解决 RRP 模型对惩罚系数 $\lambda$ 和收益增强乘数 $m$ 的参数敏感性，我们构建了以下自动化流程：
1.  **滚动训练 (Rolling Train)**: 过去 24 个月回看，遍历 90+ 种参数组合。
2.  **效用优化 (Utility Optimization)**: 采用 $Utility = R - 2.0 \cdot \sigma$ 作为评价指标，追求卓越的夏普比率。
3.  **集成平滑 (Ensemble)**: 选取 Top-3 表现最优的参数进行权重集成，有效对冲数据噪声。

### 📊 绩效看板 (Fast Mode)

| 指标 | V1 Standard | V3 Global (Static) | **Dynamic RRP** |
| :--- | :--- | :--- | :--- |
| **年化收益** | 3.63% | 6.41% | **6.11%** |
| **夏普比率** | 0.29 | 0.64 | **0.59** |
| **最大回撤** | -14.65% | -14.92% | **-14.92%** |
| **月度换手率** | 0.21% | 0.87% | **0.47%** |

> **结论**：Dynamic RRP 在无需人工干预的情况下，通过自动演化达到了接近顶尖研究员手工调优（Static V3）的水平，且换手率显著更低。

### 📂 仓库结构

```text
Relaxed-Risk-Parity-Research/
├── RRP.py (兼容入口/Wrapper)
├── src/ (核心模块库)
│   ├── risk_parity.py (RRP优化核心)
│   ├── dynamic_selection.py (动态选参引擎)
│   └── data_loader.py (Excel/Wind数据处理)
├── scripts/
│   └── run_rrp_pipeline.py (全流程一键运行)
├── results/ (报告与图表)
└── data/ (原始行情数据)
```

---

<a id="en"></a>

## English

Current Language: English | [切换到中文](#zh)

### 📌 Project Overview

This research project focuses on enhancing the traditional Risk Parity framework under low-interest-rate regimes. By implementing the **Relaxed Risk Parity (RRP)** model, we address the limitations of standard RP, such as over-allocation to low-yield bonds and insufficient return elasticity.

Beyond model reproduction, the repository provides a robust **Dynamic Parameter Selection** and **Walk-Forward Optimization** framework.

### 🚀 Evolution of Models

- **V1 (Standard RP)**: Hard constraint of equal risk contribution. Solid benchmark.
- **V2 (Relaxed RRP)**: Soft constraints via relaxation variables and penalty terms ($\lambda$).
- **V3 (Global RRP)**: Expansion into global assets (S&P 500, Nikkei 225, US Treasuries).
- **Dynamic RRP**: **Latest Update**. Automated parameter tuning using an ensemble of Top-K configurations via a rolling window.

### 🧠 Dynamic Optimization Workflow

1.  **Rolling Training**: 24-month lookback period across 90+ parameter combinations.
2.  **Utility Selection**: Maximizing $Utility = R - 2.0 \cdot \sigma$ for superior risk-adjusted returns.
3.  **Top-K Ensemble**: Averaging the Top-3 best-performing parameters to mitigate overfitting and market noise.

### 📊 Performance Summary (Fast Mode)

| Metric | V1 Standard | V3 Global (Static) | **Dynamic RRP** |
| :--- | :--- | :--- | :--- |
| **Ann. Return** | 3.63% | 6.41% | **6.11%** |
| **Sharpe Ratio** | 0.29 | 0.64 | **0.59** |
| **Max Drawdown** | -14.65% | -14.92% | **-14.92%** |
| **Turnover** | 0.21% | 0.87% | **0.47%** |

### 🛠 Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run full pipeline (Standard vs Relaxed vs Dynamic)
python scripts/run_rrp_pipeline.py --mode full --fast-mode
```

---

## 📚 References
1. Gambeta & Kwon (2020). *Risk return trade-off in relaxed risk parity portfolio optimization*.
2. López de Prado (2018). *Advances in Financial Machine Learning*.

## 📄 License
MIT License.
