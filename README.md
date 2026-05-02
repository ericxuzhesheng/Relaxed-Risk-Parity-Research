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

## 中文

### 项目概览
本仓库研究宽松风险平价在全球多资产配置中的应用。项目从传统风险平价出发，引入带松弛项的风险预算约束，并进一步扩展到全球资产池、防御型动态风险覆盖、凸自适应优化，以及 HRP / HERC 层次化配置基准。

研究目标不是单一追求样本内收益，而是在收益效率、下行控制、换手约束、交易成本和可复现性之间建立清晰的实证比较框架。

### 研究框架

| 模型 | 定位 | 说明 |
|---|---|---|
| Standard Risk Parity | 基准模型 | 传统风险贡献均衡组合，作为研究的起点参照。 |
| Local RRP | 本地宽松模型 | 在本地资产池中引入风险平价松弛项，平衡风险预算约束与收益目标。 |
| Global RRP | 全球主模型 | 将宽松风险平价扩展到全球多资产配置，是核心 RRP 参照模型。 |
| Defensive Dynamic RRP | 防御型覆盖模型 | 在 Global RRP 上加入回撤、趋势、波动率、再入场和换手约束感知控制。 |
| Convex Adaptive Global RRP | 凸自适应模型 | 在全球配置约束下使用凸自适应优化器调整组合构建。 |
| Improved Convex Adaptive Global RRP | 改进凸自适应模型 | 对凸自适应优化器进行更严格的参数细化，并采用回撤与换手约束感知标准筛选。 |
| HRP Benchmark | 层次化基准 | 用于横向比较的 Hierarchical Risk Parity 基准。 |
| HERC Benchmark | 层次化基准 | 用于横向比较的 Hierarchical Equal Risk Contribution 基准。 |

Defensive Dynamic RRP 并非被设计为机械地最大化 Sharpe。它的定位是提高不利市场环境下的风险暴露管理能力，因此需要结合最大回撤、Calmar、下行表现和换手成本一起评价。

### 最新绩效看板
以下结果来自 [`results/tables/convex_adaptive_performance_summary.csv`](results/tables/convex_adaptive_performance_summary.csv)，按展示需要四舍五入。年化收益使用 net annual return，回撤以负值展示。

#### 核心模型结果

| Model | Net Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global RRP | 5.90% | 3.56% | 1.15 | 1.30 | -4.38% | 1.35 | 22.45% | 1.66 |
| Defensive Dynamic RRP | 3.88% | 4.25% | 0.48 | 0.54 | -6.51% | 0.60 | 20.22% | 0.91 |
| Convex Adaptive Global RRP | 5.36% | 6.15% | 0.58 | 0.89 | -8.15% | 0.66 | 1.03% | 0.87 |
| Improved Convex Adaptive Global RRP | 6.45% | 4.85% | 0.96 | 1.44 | -4.98% | 1.30 | 0.52% | 1.33 |

#### Benchmark 结果

| Benchmark | Net Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| HRP Benchmark | -0.12% | 0.30% | -6.36 | -3.04 | -0.73% | -0.16 | 1.56% | -0.39 |
| HERC Benchmark | -0.10% | 0.30% | -6.30 | -3.80 | -0.73% | -0.14 | 1.60% | -0.33 |

### 图表
![Convex Adaptive NAV Comparison](results/figures/convex_adaptive_nav_comparison.png)

![Convex Adaptive Drawdown Comparison](results/figures/convex_adaptive_drawdown_comparison.png)

### 方法论
项目采用滚动协方差估计、风险预算优化、交易成本扣减、动态风险覆盖和层次化基准比较。核心实现位于 `src/` 与 `scripts/`，研究输出保存在 `results/` 与 `report/`。

### 稳健性
仓库包含交易成本敏感性、压力区间、子样本、协方差估计、参数扰动、bootstrap、PBO 与 no-lookahead 审计等诊断，用于检验结果是否依赖单一设定。

### 资产定价解释
资产定价诊断从因子暴露、收益归因、风险归因和市场状态角度解释组合表现，帮助区分策略收益、风险预算变化和宏观环境暴露。

### 输出与报告

| Type | Link |
|---|---|
| Performance summary | [`results/tables/convex_adaptive_performance_summary.csv`](results/tables/convex_adaptive_performance_summary.csv) |
| Showcase summary | [`results/tables/showcase_performance_summary.csv`](results/tables/showcase_performance_summary.csv) |
| Transaction cost summary | [`results/tables/convex_adaptive_transaction_cost_summary.csv`](results/tables/convex_adaptive_transaction_cost_summary.csv) |
| Solver diagnostics | [`results/tables/convex_adaptive_solver_diagnostics.csv`](results/tables/convex_adaptive_solver_diagnostics.csv) |
| Asset graph diagnostics | [`results/tables/asset_graph_diagnostics.csv`](results/tables/asset_graph_diagnostics.csv) |
| Online regime diagnostics | [`results/tables/online_regime_diagnostics.csv`](results/tables/online_regime_diagnostics.csv) |
| Asset-pricing interpretation | [`report/asset_pricing_interpretation.md`](report/asset_pricing_interpretation.md) |
| Methodology notes | [`report/methodology_notes.md`](report/methodology_notes.md) |
| Insurance allocation perspective | [`report/insurance_allocation_perspective.md`](report/insurance_allocation_perspective.md) |
| Thesis figures and tables | [`report/thesis_figures_and_tables.md`](report/thesis_figures_and_tables.md) |

### 复现
一键复现完整研究流程：

```bash
python scripts/run_full_research_pipeline.py
```

分步运行：

```bash
python -m pytest
python scripts/run_rrp_pipeline.py --mode full
python scripts/optimize_showcase_rrp.py
python scripts/run_hrp_comparison.py
python scripts/run_convex_adaptive_rrp.py
```

### 局限性
历史回测不代表未来表现。结果会受到样本区间、资产池、交易成本假设、协方差估计方法和参数选择影响。防御型覆盖层降低部分风险暴露的同时，也可能牺牲上涨阶段的收益弹性。

### 参考文献
参考资料与论文 PDF 存放在 [`report/`](report/)；关键方法说明见 [`report/methodology_notes.md`](report/methodology_notes.md)。

<a id="en"></a>

## English

### Project Overview
This repository studies Relaxed Risk Parity for global multi-asset allocation. It starts from classical risk parity, introduces relaxed risk-budget constraints, and extends the framework across a global asset universe, defensive dynamic overlays, convex adaptive optimization, and HRP / HERC hierarchical benchmarks.

The research objective is not to maximize in-sample return in isolation. The repository presents a reproducible empirical framework for comparing return efficiency, downside control, turnover, transaction costs, and robustness.

### Research Framework

| Model | Role | Description |
|---|---|---|
| Standard Risk Parity | Baseline model | Classical risk-contribution balancing portfolio used as the starting reference. |
| Local RRP | Local relaxed model | Introduces relaxation terms into the risk-parity constraint while retaining a local asset-universe setting. |
| Global RRP | Main global model | Extends relaxed risk parity to global multi-asset allocation and serves as the main RRP reference. |
| Defensive Dynamic RRP | Defensive overlay model | Adds drawdown, trend, volatility, re-entry, and turnover-aware controls on top of the global RRP framework. |
| Convex Adaptive Global RRP | Adaptive convex model | Uses a convex adaptive optimizer to adjust portfolio construction under global allocation constraints. |
| Improved Convex Adaptive Global RRP | Refined adaptive model | Applies a more constrained parameter refinement selected with drawdown and turnover-aware criteria. |
| HRP Benchmark | Hierarchical benchmark | Hierarchical Risk Parity benchmark for cross-method comparison. |
| HERC Benchmark | Hierarchical benchmark | Hierarchical Equal Risk Contribution benchmark for cross-method comparison. |

Defensive Dynamic RRP is not designed to mechanically maximize Sharpe. Its role is to manage risk exposure during adverse regimes, so it should be evaluated together with maximum drawdown, Calmar ratio, downside behavior, and turnover.

### Latest Performance Dashboard
The results below come from [`results/tables/convex_adaptive_performance_summary.csv`](results/tables/convex_adaptive_performance_summary.csv) and are rounded for display. Annual return uses net annual return, and drawdown is shown as a negative value.

#### Core Model Results

| Model | Net Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Global RRP | 5.90% | 3.56% | 1.15 | 1.30 | -4.38% | 1.35 | 22.45% | 1.66 |
| Defensive Dynamic RRP | 3.88% | 4.25% | 0.48 | 0.54 | -6.51% | 0.60 | 20.22% | 0.91 |
| Convex Adaptive Global RRP | 5.36% | 6.15% | 0.58 | 0.89 | -8.15% | 0.66 | 1.03% | 0.87 |
| Improved Convex Adaptive Global RRP | 6.45% | 4.85% | 0.96 | 1.44 | -4.98% | 1.30 | 0.52% | 1.33 |

#### Benchmark Results

| Benchmark | Net Annual Return | Annual Volatility | Sharpe | Sortino | Max Drawdown | Calmar | Avg Monthly Turnover | Turnover-adjusted Sharpe |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| HRP Benchmark | -0.12% | 0.30% | -6.36 | -3.04 | -0.73% | -0.16 | 1.56% | -0.39 |
| HERC Benchmark | -0.10% | 0.30% | -6.30 | -3.80 | -0.73% | -0.14 | 1.60% | -0.33 |

### Figures
![Convex Adaptive NAV Comparison](results/figures/convex_adaptive_nav_comparison.png)

![Convex Adaptive Drawdown Comparison](results/figures/convex_adaptive_drawdown_comparison.png)

### Methodology
The project uses rolling covariance estimation, risk-budget optimization, transaction-cost deductions, dynamic risk overlays, and hierarchical benchmark comparisons. Core implementation lives in `src/` and `scripts/`, while research outputs are stored in `results/` and `report/`.

### Robustness
The repository includes diagnostics for transaction-cost sensitivity, stress periods, subperiods, covariance choices, parameter perturbation, bootstrap tests, PBO, and no-lookahead checks to test whether results depend on a single configuration.

### Asset-Pricing Interpretation
Asset-pricing diagnostics explain portfolio behavior through factor exposures, return attribution, risk attribution, and market-regime context, helping separate strategy effects from changing macro and factor exposures.

### Outputs and Reports

| Type | Link |
|---|---|
| Performance summary | [`results/tables/convex_adaptive_performance_summary.csv`](results/tables/convex_adaptive_performance_summary.csv) |
| Showcase summary | [`results/tables/showcase_performance_summary.csv`](results/tables/showcase_performance_summary.csv) |
| Transaction cost summary | [`results/tables/convex_adaptive_transaction_cost_summary.csv`](results/tables/convex_adaptive_transaction_cost_summary.csv) |
| Solver diagnostics | [`results/tables/convex_adaptive_solver_diagnostics.csv`](results/tables/convex_adaptive_solver_diagnostics.csv) |
| Asset graph diagnostics | [`results/tables/asset_graph_diagnostics.csv`](results/tables/asset_graph_diagnostics.csv) |
| Online regime diagnostics | [`results/tables/online_regime_diagnostics.csv`](results/tables/online_regime_diagnostics.csv) |
| Asset-pricing interpretation | [`report/asset_pricing_interpretation.md`](report/asset_pricing_interpretation.md) |
| Methodology notes | [`report/methodology_notes.md`](report/methodology_notes.md) |
| Insurance allocation perspective | [`report/insurance_allocation_perspective.md`](report/insurance_allocation_perspective.md) |
| Thesis figures and tables | [`report/thesis_figures_and_tables.md`](report/thesis_figures_and_tables.md) |

### Reproduction
Run the full research pipeline in one command:

```bash
python scripts/run_full_research_pipeline.py
```

Or run the main steps separately:

```bash
python -m pytest
python scripts/run_rrp_pipeline.py --mode full
python scripts/optimize_showcase_rrp.py
python scripts/run_hrp_comparison.py
python scripts/run_convex_adaptive_rrp.py
```

### Limitations
Historical backtests do not guarantee future performance. Results are sensitive to the sample period, asset universe, transaction-cost assumptions, covariance estimation method, and parameter choices. Defensive overlays may reduce downside exposure while giving up some upside participation.

### References
Reference PDFs and notes are stored in [`report/`](report/). The main methodology summary is available in [`report/methodology_notes.md`](report/methodology_notes.md).

## License
MIT License.
