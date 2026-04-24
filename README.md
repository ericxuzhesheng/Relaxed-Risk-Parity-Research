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
本项目旨在低利率与全球宏观剧烈波动的环境下，对传统风险平价（Risk Parity）框架进行工程化改良。引入 **宽松风险平价（Relaxed Risk Parity, RRP）** 模型，解决了标准 RP 组合收益弹性不足的问题，并集成了**动态风险闸门**与**趋势过滤**等先进控撤手段。

### 🚀 核心版本演进
| 版本 | 模型类型 | 资产池范围 | 特性说明 |
| :--- | :--- | :--- | :--- |
| V1 | 标准 RP | 本土资产 | 严格等风险贡献，极致稳健。 |
| V2 | 宽松 RRP | 本土资产 | **引入松弛变量**，本土股债混合增强。 |
| V3 | 宽松 RRP | 全球资产 | 加入美债、标普、汇率，利用全球分散化。 |
| **Dynamic** | 动态 RRP | 全球资产 | **最新升级**：趋势过滤 + 动态风险闸门自适应。 |

### 🧠 风险控制杀手锏 (Risk Overlay)
1.  **动态风险闸门**: 实时监控回撤，一旦超过 3.5%，波动率预算自动减半。
2.  **趋势过滤器**: 扫描 60 日均线，自动规避处于下行趋势的风险资产。
3.  **波动率目标管理**: 全量资产遵循 6.0% 的激进波动率目标约束。

### 📊 绩效看板 (Evaluation: 2021-01-01 to Present)
| 指标 | V1 Standard | V2 Relaxed | V3 Global | **Dynamic RRP** |
| :--- | :--- | :--- | :--- | :--- |
| **年化收益** | 1.67% | 2.91% | 5.96% | 4.87% |
| **最大回撤** | -0.70% | -2.15% | -3.85% | -5.12% |
| **夏普比率** | -0.30 | 0.31 | **1.04** | 0.76 |
| **月度换手率** | 0.024 | 0.018 | 0.024 | 0.021 |

#### 📈 净值走势对比 (NAV Comparison)
<p align="center">
  <img src="results/figures/static_vs_dynamic_nav.png" width="800" alt="NAV Comparison">
</p>

#### 🧩 动态权重与参数演进 (Weights & Parameters)
<p align="center">
  <img src="results/figures/dynamic_rrp_weights.png" width="400" alt="Weights">
  <img src="results/figures/lambda_selection_timeline.png" width="400" alt="Lambda Timeline">
</p>

> **结论**：在 6.0% 的目标波动率约束下，V3 模型成功实现了夏普比率 > 1 的目标，通过全球资产的分散化显著提升了单位风险收益。

### 📂 仓库结构
```text
Relaxed-Risk-Parity-Research/
├── RRP.py (兼容入口/Wrapper)
├── src/ (核心模块库)
│   ├── risk_parity.py (RRP优化核心)
│   ├── dynamic_selection.py (动态选参引擎)
│   ├── backtest.py (集成风险闸门的回测引擎)
│   └── data_loader.py (Tushare Pro 数据引擎)
├── scripts/
│   └── run_rrp_pipeline.py (全流程一键运行)
└── results/ (报告与图表)
```

### 🛠 快速开始
```bash
# 安装依赖
pip install -r requirements.txt

# 运行全流程 (默认使用 Tushare)
python scripts/run_rrp_pipeline.py --mode full
```

### 📚 参考文献
1. Gambeta, V., & Kwon, R. (2020). *Risk return trade-off in relaxed risk parity portfolio optimization*.
2. López de Prado, M. (2018). *Advances in Financial Machine Learning*.
3. 浙商证券. (2026). 《债市专题研究：宽松改进下的风险平价，从本土化到全球化》.

---

<a id="en"></a>

## English

Current Language: English | [切换到中文](#zh)

### 📌 Project Overview
This project enhances the traditional Risk Parity framework with **Relaxed Risk Parity (RRP)** and **Dynamic Risk Overlays**. It addresses return elasticity limitations and integrates advanced drawdown controls like **Risk Budget Overlay** and **Momentum Filters**.

### 🚀 Evolution of Models
| Version | Model Type | Asset Pool | Key Features |
| :--- | :--- | :--- | :--- |
| V1 | Standard RP | Local Assets | Strict ERC, extreme stability. |
| V2 | Relaxed RRP | Local Assets | **Relaxation introduced**, domestic enhancement. |
| V3 | Relaxed RRP | Global Assets | Diversification with USDX, S&P, Treasuries. |
| **Dynamic** | Dynamic RRP | Global Assets | **Latest**: Adaptive risk budget + trend filtering. |

### 🧠 Killer Risk Controls (Risk Overlay)
1.  **Risk Budget Overlay**: Automatically halves Vol Target if drawdown exceeds 3.5%.
2.  **Momentum Filter**: Scans 60-day MA to avoid assets in downward trends.
3.  **Volatility Targeting**: Enforces a strict 6.0% aggressive volatility target.

### 📊 Performance Dashboard (Evaluation: 2021-01-01 to Present)
| Metric | V1 Standard | V2 Relaxed | V3 Global | **Dynamic RRP** |
| :--- | :--- | :--- | :--- | :--- |
| **Ann. Return** | 1.67% | 2.91% | 5.96% | 4.87% |
| **Max Drawdown** | -0.70% | -2.15% | -3.85% | -5.12% |
| **Sharpe Ratio** | -0.30 | 0.31 | **1.04** | 0.76 |
| **Turnover** | 0.024 | 0.018 | 0.024 | 0.021 |

#### 📈 NAV Comparison
<p align="center">
  <img src="results/figures/static_vs_dynamic_nav.png" width="800" alt="NAV Comparison">
</p>

#### 🧩 Model Dynamics
<p align="center">
  <img src="results/figures/dynamic_rrp_weights.png" width="400" alt="Weights">
  <img src="results/figures/m_selection_timeline.png" width="400" alt="M Timeline">
</p>

> **Conclusion**: With a 6.0% Vol Target, V3 model achieved Sharpe > 1, proving that global diversification significantly enhances risk-adjusted returns.

### 📂 Repository Structure
```text
Relaxed-Risk-Parity-Research/
├── RRP.py (Legacy Wrapper)
├── src/ (Core Modules)
│   ├── risk_parity.py (Optimization core)
│   ├── dynamic_selection.py (Selection engine)
│   ├── backtest.py (Backtest with Risk Gates)
│   └── data_loader.py (Tushare Pro engine)
├── scripts/
│   └── run_rrp_pipeline.py (Main execution script)
└── data/ (Market data)
```

### 🛠 Quick Start
```bash
# Install dependencies
pip install -r requirements.txt

# Run full pipeline
python scripts/run_rrp_pipeline.py --mode full
```

### 📚 References
1. Gambeta & Kwon (2020). *Risk return trade-off in relaxed risk parity*.
2. López de Prado (2018). *Advances in Financial Machine Learning*.
3. Zheshang Securities. (2026). *Special Report on Bond Market: Relaxed Risk Parity - From Localization to Globalization*.

## 📄 License
MIT License.
