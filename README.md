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

Defensive Dynamic Relaxed Risk Parity is not designed to mechanically maximize Sharpe. Its role is to reduce risk exposure during adverse regimes, so it should be evaluated together with maximum drawdown, Calmar ratio, downside behavior, and turnover. In the current regenerated results, its Sharpe remains below Global Relaxed Risk Parity; the overlay prioritizes downside control and stability over pure Sharpe maximization.

### 最新结果看板
评估区间从 `2021-01-01` 开始。下表直接来自 `results/tables/showcase_performance_summary.csv`。
| Model | Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global Relaxed Risk Parity | 5.98% | 3.61% | 1.15 | 1.35 | -4.25% | 1.41 | 0.0115 | 1.63 |
| Defensive Dynamic Relaxed Risk Parity | 4.58% | 3.64% | 0.76 | 0.86 | -4.37% | 1.05 | 0.0112 | 1.24 |
| Defensive Dynamic RRP before overlay optimization | 3.22% | 3.93% | 0.36 | 0.37 | -7.12% | 0.45 | 0.0098 | 0.80 |

Benchmark 结果保留在公开表格中，但不作为本文的主要贡献。
| Model | Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Standard Risk Parity | 1.25% | 1.21% | -0.47 | -0.50 | -2.65% | 0.47 | 0.0107 | 0.97 |
| Local Relaxed Risk Parity | 5.53% | 3.65% | 1.02 | 1.10 | -5.12% | 1.08 | 0.0111 | 1.49 |
| HRP Benchmark | -0.09% | 0.37% | -5.19 | -3.84 | -0.77% | -0.12 | 0.0005 | -0.26 |
| HERC Benchmark | -0.09% | 0.37% | -5.16 | -4.65 | -0.77% | -0.11 | 0.0005 | -0.24 |

### 图表展示
<p align="center"><img src="results/figures/showcase_nav_comparison.png" width="820" alt="Showcase NAV Comparison"></p>
<p align="center"><em>Showcase NAV comparison.</em></p>
<p align="center"><img src="results/figures/showcase_drawdown_comparison.png" width="820" alt="Showcase Drawdown Comparison"></p>
<p align="center"><em>Showcase drawdown comparison.</em></p>

- `results/figures/showcase_risk_overlay_ablation.png`
- `results/figures/showcase_parameter_timeline.png`
- `results/figures/nav_comparison.png`
- `results/figures/drawdown_comparison.png`

### 方法框架
框架包括风险贡献均衡、宽松收益目标、全球多资产扩展、防御型动态覆盖、回撤缩放、软趋势过滤、波动率目标、再入场逻辑、换手控制和交易成本调整。

### AFML 风格验证设计
验证流程借鉴 Lopez de Prado 的 walk-forward、反过拟合和多重检验思想，但不声称完整实现 CSCV 或完整 Deflated Sharpe Ratio。每个测试期只使用此前数据进行参数选择，并报告稳定性、换手、简化 PBO 和保守调整 Sharpe 诊断。

### HRP / HERC Benchmark
HRP / HERC 是横向 benchmark，用于检验层次聚类风险配置在同一数据集和评估窗口下是否优于 RRP 型全球配置。结果透明保留，不隐藏弱于主模型的情形。

### 如何运行
```bash
pip install -r requirements.txt
python -m pytest
python scripts/optimize_showcase_rrp.py
python scripts/run_rrp_pipeline.py --mode full
python scripts/run_hrp_comparison.py
```

### 输出文件
- `results/tables/showcase_performance_summary.csv`
- `results/tables/showcase_risk_overlay_ablation.csv`
- `results/tables/showcase_walkforward_validation.csv`
- `results/tables/showcase_parameter_stability.csv`
- `results/tables/showcase_improvement_attribution.csv`
- `results/tables/performance_summary.csv`
- `results/tables/hrp_comparison.csv`
- `results/figures/showcase_nav_comparison.png`
- `results/figures/showcase_drawdown_comparison.png`

### 适用场景与局限性
本项目是回测研究，不构成投资建议。数据质量、资产映射、交易成本、滑点、杠杆融资成本、税费、流动性和实盘可交易性都需要独立复核。

### 参考文献
1. Gambeta, V., & Kwon, R. (2020). Risk return trade-off in relaxed risk parity portfolio optimization.
2. Lopez de Prado, M. (2018). Advances in Financial Machine Learning.
3. Bailey, D. H., Borwein, J. M., Lopez de Prado, M., & Zhu, Q. J. (2015). The Probability of Backtest Overfitting.
4. Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio.
5. Lopez de Prado, M. (2016). Building Diversified Portfolios that Outperform Out-of-Sample.

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

Defensive Dynamic Relaxed Risk Parity is not designed to mechanically maximize Sharpe. Its role is to reduce risk exposure during adverse regimes, so it should be evaluated together with maximum drawdown, Calmar ratio, downside behavior, and turnover. In the current regenerated results, its Sharpe remains below Global Relaxed Risk Parity; the overlay prioritizes downside control and stability over pure Sharpe maximization.

### Latest Results
Evaluation starts on `2021-01-01`. The table is generated from `results/tables/showcase_performance_summary.csv`.
| Model | Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global Relaxed Risk Parity | 5.98% | 3.61% | 1.15 | 1.35 | -4.25% | 1.41 | 0.0115 | 1.63 |
| Defensive Dynamic Relaxed Risk Parity | 4.58% | 3.64% | 0.76 | 0.86 | -4.37% | 1.05 | 0.0112 | 1.24 |
| Defensive Dynamic RRP before overlay optimization | 3.22% | 3.93% | 0.36 | 0.37 | -7.12% | 0.45 | 0.0098 | 0.80 |

Benchmark results are retained transparently.
| Model | Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Standard Risk Parity | 1.25% | 1.21% | -0.47 | -0.50 | -2.65% | 0.47 | 0.0107 | 0.97 |
| Local Relaxed Risk Parity | 5.53% | 3.65% | 1.02 | 1.10 | -5.12% | 1.08 | 0.0111 | 1.49 |
| HRP Benchmark | -0.09% | 0.37% | -5.19 | -3.84 | -0.77% | -0.12 | 0.0005 | -0.26 |
| HERC Benchmark | -0.09% | 0.37% | -5.16 | -4.65 | -0.77% | -0.11 | 0.0005 | -0.24 |

### Figures
<p align="center"><img src="results/figures/showcase_nav_comparison.png" width="820" alt="Showcase NAV Comparison"></p>
<p align="center"><img src="results/figures/showcase_drawdown_comparison.png" width="820" alt="Showcase Drawdown Comparison"></p>

### Methodology
The framework combines relaxed risk parity, global diversification, defensive risk overlays, drawdown-aware scaling, soft trend filtering, volatility targeting, re-entry logic, turnover control, and transaction-cost-aware evaluation.

### AFML-Inspired Validation Design
The showcase uses strict walk-forward validation. Candidate selection only uses data before each test period, with simplified PBO-style diagnostics, parameter stability checks, turnover-aware metrics, and conservative adjusted Sharpe diagnostics.

### HRP / HERC Benchmark
HRP / HERC are benchmarks used to test whether hierarchical clustering alone can outperform RRP-based global diversification under the same evaluation setup.

### How to Run
```bash
pip install -r requirements.txt
python -m pytest
python scripts/optimize_showcase_rrp.py
python scripts/run_rrp_pipeline.py --mode full
python scripts/run_hrp_comparison.py
```

### Output Files
- `results/tables/showcase_performance_summary.csv`
- `results/tables/showcase_risk_overlay_ablation.csv`
- `results/tables/showcase_walkforward_validation.csv`
- `results/tables/showcase_parameter_stability.csv`
- `results/tables/showcase_improvement_attribution.csv`
- `results/tables/performance_summary.csv`
- `results/tables/hrp_comparison.csv`
- `results/figures/showcase_nav_comparison.png`
- `results/figures/showcase_drawdown_comparison.png`

### Use Cases and Limitations
This is backtest research, not investment advice. Data quality, asset mappings, transaction costs, slippage, financing costs, taxes, liquidity, and live tradability require independent review.

### References
1. Gambeta, V., & Kwon, R. (2020). Risk return trade-off in relaxed risk parity portfolio optimization.
2. Lopez de Prado, M. (2018). Advances in Financial Machine Learning.
3. Bailey, D. H., Borwein, J. M., Lopez de Prado, M., & Zhu, Q. J. (2015). The Probability of Backtest Overfitting.
4. Bailey, D. H., & Lopez de Prado, M. (2014). The Deflated Sharpe Ratio.
5. Lopez de Prado, M. (2016). Building Diversified Portfolios that Outperform Out-of-Sample.

## License
MIT License.
