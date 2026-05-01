# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

<p align="center">
  <a href="#zh"><img src="https://img.shields.io/badge/LANGUAGE-%E4%B8%AD%E6%96%87-E84D3D?style=for-the-badge&labelColor=3B3F47" alt="LANGUAGE 中文"></a>
  <a href="#en"><img src="https://img.shields.io/badge/LANGUAGE-ENGLISH-2F73C9?style=for-the-badge&labelColor=3B3F47" alt="LANGUAGE ENGLISH"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.8%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.8+">
  <img src="https://img.shields.io/badge/Asset-Global%20Multi--Asset-F2C94C?style=for-the-badge" alt="Global Multi-Asset">
  <img src="https://img.shields.io/badge/Strategy-Relaxed%20Risk%20Parity-7AC943?style=for-the-badge" alt="Relaxed Risk Parity">
  <img src="https://img.shields.io/badge/Overlay-Defensive%20Dynamic%20RRP-9B51E0?style=for-the-badge" alt="Defensive Dynamic RRP">
</p>

<a id="zh"></a>

## 简体中文

当前语言：中文 | [Switch to English](#en)

---

### 项目概览

本仓库研究宽松风险平价（Relaxed Risk Parity, RRP）在全球多资产配置中的应用。项目从传统风险平价出发，比较本土宽松风险平价、全球宽松风险平价、防守型动态风险覆盖模型，以及 HRP / HERC 层次化风险配置基准。

核心研究问题是：在低利率、全球宏观波动和跨资产相关性变化的环境下，如何在风险贡献均衡、收益目标、回撤控制和交易约束之间取得更稳健的平衡。

### 核心模型

| 模型 | 定位 | 说明 |
|---|---|---|
| Standard Risk Parity | 基准模型 | 传统风险平价模型，用于衡量风险贡献均衡的基础效果 |
| Local Relaxed Risk Parity | 本土宽松风险平价 | 在风险平价约束上引入松弛项，用于权衡风险均衡与收益目标 |
| Global Relaxed Risk Parity | 主展示模型 | 扩展到全球多资产配置，是当前主要的收益效率模型 |
| Defensive Dynamic Relaxed Risk Parity | 防守型动态模型 | 在 Global Relaxed Risk Parity 基础上加入风险覆盖层，目标是控制回撤和改善组合稳定性 |
| HRP / HERC Benchmarks | 横向基准 | 用作层次化风险配置 benchmark，不作为本文主模型 |

Global Relaxed Risk Parity 是当前主要的收益效率模型。Defensive Dynamic Relaxed Risk Parity 是防守型风险控制模型，用于在不利市场状态下降低风险暴露、改善组合稳定性，并提供可验证的动态覆盖层工作流。HRP / HERC 仅作为横向 benchmark，用于检验层次化聚类配置是否能够替代 RRP 型全球配置。

Defensive Dynamic Relaxed Risk Parity is not designed to mechanically maximize Sharpe. Its role is to act as a defensive overlay strategy that reduces risk exposure during adverse regimes. Therefore, it should be evaluated together with maximum drawdown, Calmar ratio, downside behavior, and turnover, not Sharpe alone.

### 最新结果看板

评估区间从 `2021-01-01` 开始。下表来自 `results/tables/showcase_performance_summary.csv`，展示当前 GitHub 看板使用的主要模型结果。

| Model | Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global Relaxed Risk Parity | 6.30% | 3.65% | 1.23 | 1.46 | -4.07% | 1.55 | 0.0118 | 1.71 |
| Defensive Dynamic Relaxed Risk Parity | 4.25% | 4.17% | 0.58 | 0.66 | -5.23% | 0.81 | 0.0189 | 0.99 |

完整 pipeline 的横向结果来自 `results/tables/performance_summary.csv` 和 `results/tables/hrp_comparison.csv`。为避免过度包装，HRP / HERC benchmark 的表现如下透明列示。

| Benchmark | Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Standard Risk Parity | 1.25% | 1.21% | -0.47 | -0.50 | -2.65% | 0.47 | 0.0107 | 0.97 |
| Local Relaxed Risk Parity | 5.53% | 3.65% | 1.02 | 1.10 | -5.12% | 1.08 | 0.0111 | 1.49 |
| HRP Benchmark | -0.09% | 0.37% | -5.19 | -3.84 | -0.77% | -0.12 | 0.0005 | -0.26 |
| HERC Benchmark | -0.09% | 0.37% | -5.16 | -4.65 | -0.77% | -0.11 | 0.0005 | -0.24 |

### 图表展示

<p align="center">
  <img src="results/figures/showcase_nav_comparison.png" width="820" alt="Showcase NAV Comparison">
</p>

<p align="center"><em>Showcase NAV comparison: global return-efficient RRP versus defensive dynamic overlay.</em></p>

<p align="center">
  <img src="results/figures/showcase_drawdown_comparison.png" width="820" alt="Showcase Drawdown Comparison">
</p>

<p align="center"><em>Drawdown comparison for the main showcase models.</em></p>

Additional diagnostics:

- `results/figures/showcase_risk_overlay_ablation.png`
- `results/figures/showcase_parameter_timeline.png`
- `results/figures/nav_comparison.png`
- `results/figures/drawdown_comparison.png`

### 方法框架

本项目的核心方法包括：

- Standard Risk Parity：通过风险贡献均衡构造基础风险平价组合。
- Relaxed Risk Parity：在风险平价约束中引入松弛项，使组合能够在风险均衡与收益目标之间进行权衡。
- Global Multi-Asset Extension：将资产池扩展到权益、债券、商品、黄金及海外资产，用于检验全球多资产分散化效果。
- Defensive Dynamic Risk Overlay：在 Global Relaxed Risk Parity 权重基础上加入防守型动态覆盖层，不以激进提高收益为目标，而以风险暴露管理和稳定性为核心。
- Drawdown-aware Scaling：当组合进入回撤区间时，按规则降低风险暴露。
- Soft Trend Filter：使用趋势状态对风险暴露进行温和调整，而不是简单地追求高换手择时。
- Volatility Targeting：根据实现波动率调整风险尺度。
- Re-entry Logic：风险状态改善后逐步恢复风险暴露，避免一次性跳回满仓。
- Turnover Control：显式记录换手率和交易成本影响，用于评估策略可实施性。

### AFML 风格验证设计

项目借鉴 López de Prado (2018) 的验证与反过拟合思想，但不声称完整实现《Advances in Financial Machine Learning》中的全部算法。

当前实现包含：

- walk-forward validation：每个测试期只使用该期之前的数据进行参数选择；
- no full-sample parameter tuning：避免用完整样本回看选择展示参数；
- parameter stability analysis：检查参数选择是否过度跳变；
- turnover-aware evaluation：报告换手率、交易成本和 turnover-adjusted Sharpe；
- simplified PBO-style diagnostic：提供简化版 PBO 风格诊断，不等同于完整 CSCV；
- adjusted Sharpe diagnostics：提供保守调整后的 Sharpe 诊断，不等同于完整 Deflated Sharpe Ratio。

### HRP / HERC Benchmark

HRP / HERC 是横向 benchmark，不是本项目的主要贡献。它们的作用是检验仅依赖层次化聚类和风险分配能否优于 RRP 型全球多资产配置。

当前结果显示，HRP / HERC 在本数据集和当前评估设定下没有超越 Global Relaxed Risk Parity。该结果保留在 README 和结果表中，不做隐藏。

### 如何运行

```bash
pip install -r requirements.txt
python -m pytest
python scripts/run_rrp_pipeline.py --mode full
python scripts/optimize_showcase_rrp.py
python scripts/run_hrp_comparison.py
```

主要输出：

- `results/tables/performance_summary.csv`
- `results/tables/showcase_performance_summary.csv`
- `results/tables/dynamic_overlay_diagnostics.csv`
- `results/tables/showcase_risk_overlay_ablation.csv`
- `results/tables/showcase_walkforward_validation.csv`
- `results/tables/showcase_parameter_stability.csv`
- `results/tables/showcase_afml_diagnostics.csv`
- `results/tables/showcase_pbo_diagnostic.csv`
- `results/tables/hrp_comparison.csv`

### 局限性

本项目是回测研究，不构成投资建议。数据源、资产映射、交易成本、滑点、杠杆融资成本、税费和实盘可交易性均需要在正式使用前单独验证。防守型动态模型的目标是风险控制和稳定性管理，不应被解读为保证收益或保证低回撤。

<a id="en"></a>

## English

Current language: English | [切换到中文](#zh)

---

### Overview

This repository studies Relaxed Risk Parity for global multi-asset allocation. It compares classical risk parity, local relaxed risk parity, global relaxed risk parity, a defensive dynamic overlay model, and HRP / HERC hierarchical allocation benchmarks.

The research focus is the trade-off among risk-contribution balance, return targets, drawdown control, turnover, and implementation stability under global macro and multi-asset market conditions.

### Core Models

| Model | Role | Description |
|---|---|---|
| Standard Risk Parity | Baseline | Classical risk parity model for risk-contribution balancing |
| Local Relaxed Risk Parity | Local relaxed model | Introduces relaxation terms to balance risk parity and return objectives |
| Global Relaxed Risk Parity | Main showcase model | Extends relaxed risk parity to global multi-asset allocation and serves as the return-efficient model |
| Defensive Dynamic Relaxed Risk Parity | Defensive dynamic model | Adds a defensive risk overlay on top of Global Relaxed Risk Parity to manage drawdowns and improve stability |
| HRP / HERC Benchmarks | Cross-sectional benchmarks | Hierarchical allocation benchmarks, not the main contribution |

Global Relaxed Risk Parity is the main return-efficient global diversification model. Defensive Dynamic Relaxed Risk Parity is a defensive risk-control model designed to manage exposure in adverse regimes. HRP / HERC are benchmark models only.

Defensive Dynamic Relaxed Risk Parity is not designed to mechanically maximize Sharpe. Its role is to act as a defensive overlay strategy that reduces risk exposure during adverse regimes. Therefore, it should be evaluated together with maximum drawdown, Calmar ratio, downside behavior, and turnover, not Sharpe alone.

### Latest Results

Evaluation starts on `2021-01-01`. The main showcase table is sourced from `results/tables/showcase_performance_summary.csv`.

| Model | Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global Relaxed Risk Parity | 6.30% | 3.65% | 1.23 | 1.46 | -4.07% | 1.55 | 0.0118 | 1.71 |
| Defensive Dynamic Relaxed Risk Parity | 4.25% | 4.17% | 0.58 | 0.66 | -5.23% | 0.81 | 0.0189 | 0.99 |

Benchmark results are retained transparently rather than promoted as the main contribution.

| Benchmark | Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Standard Risk Parity | 1.25% | 1.21% | -0.47 | -0.50 | -2.65% | 0.47 | 0.0107 | 0.97 |
| Local Relaxed Risk Parity | 5.53% | 3.65% | 1.02 | 1.10 | -5.12% | 1.08 | 0.0111 | 1.49 |
| HRP Benchmark | -0.09% | 0.37% | -5.19 | -3.84 | -0.77% | -0.12 | 0.0005 | -0.26 |
| HERC Benchmark | -0.09% | 0.37% | -5.16 | -4.65 | -0.77% | -0.11 | 0.0005 | -0.24 |

### Figures

<p align="center">
  <img src="results/figures/showcase_nav_comparison.png" width="820" alt="Showcase NAV Comparison">
</p>

<p align="center"><em>Showcase NAV comparison.</em></p>

<p align="center">
  <img src="results/figures/showcase_drawdown_comparison.png" width="820" alt="Showcase Drawdown Comparison">
</p>

<p align="center"><em>Showcase drawdown comparison.</em></p>

Additional figures:

- `results/figures/showcase_risk_overlay_ablation.png`
- `results/figures/showcase_parameter_timeline.png`
- `results/figures/nav_comparison.png`
- `results/figures/drawdown_comparison.png`

### Methodology

The framework combines:

- Standard Risk Parity for baseline risk-contribution balancing.
- Relaxed Risk Parity for balancing risk parity constraints with return objectives.
- A global multi-asset extension across equities, bonds, commodities, gold, and overseas assets.
- A defensive dynamic overlay for exposure control, not aggressive return enhancement.
- Drawdown-aware scaling for adverse regimes.
- Soft trend filtering to moderate exposure when trend conditions deteriorate.
- Volatility targeting based on realized risk.
- Re-entry logic to restore exposure gradually after risk conditions improve.
- Turnover control and transaction-cost-aware evaluation.

### AFML-Inspired Validation

The project borrows validation and anti-overfitting ideas from López de Prado (2018). It does not claim to implement every algorithm in *Advances in Financial Machine Learning*.

Implemented diagnostics include walk-forward validation, strict past-only parameter selection, parameter stability analysis, turnover-aware evaluation, simplified PBO-style diagnostics, and adjusted / turnover-adjusted Sharpe reporting where available.

### HRP / HERC Benchmark

HRP / HERC are benchmark models, not the main contribution. Their role is to test whether hierarchical clustering alone can outperform RRP-based global diversification. In the current dataset and evaluation window, they underperform the Global Relaxed Risk Parity showcase, and this result is reported transparently.

### How to Run

```bash
pip install -r requirements.txt
python -m pytest
python scripts/run_rrp_pipeline.py --mode full
python scripts/optimize_showcase_rrp.py
python scripts/run_hrp_comparison.py
```

### Repository Structure

```text
Relaxed-Risk-Parity-Research/
|-- src/
|   |-- risk_parity.py
|   |-- risk_overlay.py
|   |-- dynamic_selection.py
|   |-- validation.py
|   |-- backtest.py
|   |-- metrics.py
|   `-- visualization.py
|-- scripts/
|   |-- run_rrp_pipeline.py
|   |-- optimize_showcase_rrp.py
|   `-- run_hrp_comparison.py
|-- results/
|   |-- tables/
|   `-- figures/
`-- tests/
```

### Limitations

This is backtest research and does not constitute investment advice. Data quality, asset mappings, transaction costs, slippage, financing costs, taxes, liquidity, and live trading feasibility require separate review before practical use.

### References

1. Gambeta, V., & Kwon, R. (2020). Risk return trade-off in relaxed risk parity portfolio optimization.
2. López de Prado, M. (2018). *Advances in Financial Machine Learning*.
3. Bailey, D. H., Borwein, J. M., López de Prado, M., & Zhu, Q. J. (2015). The Probability of Backtest Overfitting.
4. Bailey, D. H., & López de Prado, M. (2014). The Deflated Sharpe Ratio.
5. López de Prado, M. (2016). Building Diversified Portfolios that Outperform Out-of-Sample.
6. Zheshang Securities. (2026). Relaxed Risk Parity: From Localization to Globalization.

## License

MIT License.
