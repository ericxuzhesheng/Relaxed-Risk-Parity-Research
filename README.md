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

### 📌 项目概览
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
为了解决 RRP 模型对参数 $\lambda$ 和 $m$ 的敏感性，我们构建了自动化流程：
1.  **滚动训练 (Rolling Train)**: 过去 24 个月回看，遍历 90+ 种参数组合。
2.  **效用优化 (Utility Optimization)**: 采用 $Utility = R - 2.0 \cdot \sigma$ 作为评价指标。
3.  **集成平滑 (Ensemble)**: 选取 Top-3 表现最优的参数进行权重集成，对冲数据噪声。

### 📊 绩效看板 (Fast Mode)
| 指标 | V1 Standard | V3 Global (Static) | **Dynamic RRP** |
| :--- | :--- | :--- | :--- |
| **年化收益** | 3.63% | 6.41% | **6.11%** |
| **夏普比率** | 0.29 | 0.64 | **0.59** |
| **最大回撤** | -14.65% | -14.92% | **-14.92%** |
| **月度换手率** | 0.21% | 0.87% | **0.47%** |

> **结论**：Dynamic RRP 在无需人工干预的情况下，达到了接近专家调优（Static V3）的水平，且换手率显著更低。

### 📂 仓库结构
```text
Relaxed-Risk-Parity-Research/
├── RRP.py (兼容入口/Wrapper)
├── src/ (核心模块库)
│   ├── risk_parity.py (RRP优化核心)
│   ├── dynamic_selection.py (动态选参引擎)
│   ├── backtest.py (回测引擎)
│   └── visualization.py (绘图模块)
├── scripts/
│   └── run_rrp_pipeline.py (执行主脚本)
├── results/ (输出结果)
│   ├── figures/ (图表)
│   └── tables/ (数据表)
└── data/ (行情数据)
```

### 🛠 快速开始
```bash
# 安装依赖
pip install -r requirements.txt

# 运行全流程 (含动态选参)
python scripts/run_rrp_pipeline.py --mode full --fast-mode
```

---

<a id="en"></a>

## English

Current Language: English | [切换到中文](#zh)

### 📌 Project Overview
This project focuses on enhancing the traditional Risk Parity framework under low-interest-rate regimes. By implementing the **Relaxed Risk Parity (RRP)** model, we address the limitations of standard RP, such as over-allocation to low-yield bonds and insufficient return elasticity.

Beyond model reproduction, the repository provides a robust **Dynamic Parameter Selection** and **Walk-Forward Optimization** framework.

### 🚀 Evolution of Models
| Version | Model Type | Asset Pool | Key Features |
| :--- | :--- | :--- | :--- |
| **V1** | Standard RP | Local Assets | Strict ERC, no leverage, stable benchmark. |
| **V2** | Relaxed RRP | Local Assets | Introduced relaxation $\rho$ and penalty $\lambda$ for better trade-off. |
| **V3** | Relaxed RRP | Global Assets | Included US Treasuries, S&P 500, Nikkei 225 for diversification. |
| **Dynamic** | Dynamic RRP | Global Assets | **Latest Update**: Automated tuning via Top-K ensemble in rolling windows. |

### 🧠 Dynamic Selection Framework (Walk-Forward)
To mitigate the sensitivity of $\lambda$ and $m$, we built an automated pipeline:
1.  **Rolling Training**: 24-month lookback period across 90+ parameter combinations.
2.  **Utility Selection**: Maximizing $Utility = R - 2.0 \cdot \sigma$ for risk-adjusted returns.
3.  **Top-K Ensemble**: Averaging the Top-3 best-performing parameters to mitigate noise and overfitting.

### 📊 Performance Dashboard (Fast Mode)
| Metric | V1 Standard | V3 Global (Static) | **Dynamic RRP** |
| :--- | :--- | :--- | :--- |
| **Ann. Return** | 3.63% | 6.41% | **6.11%** |
| **Sharpe Ratio** | 0.29 | 0.64 | **0.59** |
| **Max Drawdown** | -14.65% | -14.92% | **-14.92%** |
| **Turnover** | 0.21% | 0.87% | **0.47%** |

> **Conclusion**: Dynamic RRP achieves performance close to expert-tuned levels (Static V3) without manual intervention, while maintaining a significantly lower turnover.

### 📂 Repository Structure
```text
Relaxed-Risk-Parity-Research/
├── RRP.py (Legacy Wrapper)
├── src/ (Core Modules)
│   ├── risk_parity.py (Optimization core)
│   ├── dynamic_selection.py (Selection engine)
│   ├── backtest.py (Backtest engine)
│   └── visualization.py (Plotting module)
├── scripts/
│   └── run_rrp_pipeline.py (Main execution script)
├── results/ (Outputs)
│   ├── figures/ (Charts)
│   └── tables/ (Tables)
└── data/ (Market data)
```

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
