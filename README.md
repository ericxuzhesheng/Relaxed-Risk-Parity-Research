# 宽松风险平价全球资产配置框架 | Relaxed Risk Parity Framework for Global Asset Allocation

<p align="center">
  <a href="#zh"><img src="https://img.shields.io/badge/LANGUAGE-%E4%B8%AD%E6%96%87-E84D3D?style=for-the-badge&labelColor=3B3F47" alt="LANGUAGE 中文"></a>
  <a href="#en"><img src="https://img.shields.io/badge/LANGUAGE-ENGLISH-2F73C9?style=for-the-badge&labelColor=3B3F47" alt="LANGUAGE ENGLISH"></a>
</p>

<a id="zh"></a>

## 中文

### 项目概览

本仓库是一个面向论文研究的全球多资产配置框架，围绕宽松风险平价、全球资产扩展、凸优化近似、CVaR 尾部风险控制、换手约束和稳健性验证展开。项目目标不是短期交易信号，而是构建可解释、可复现、可实施的长期机构型资产配置研究流程。

最终组合权重由透明优化流程生成。机器学习、图特征和状态识别模块仅作为诊断信息或约束输入，不直接生成组合权重。

### 研究框架

| 模型 / 模块 | 公开标签 | 研究定位 |
|---|---|---|
| 传统风险平价 | Standard Risk Parity | 基础风险预算参照 |
| 本地宽松风险平价 | Local Relaxed Risk Parity | 本地资产池中的宽松风险平价模型 |
| 全球宽松风险平价 | Global RRP | 主要的收益效率展示模型 |
| 防御型动态宽松风险平价 | Defensive Dynamic RRP | 防御型风险覆盖实验，不是主要收益最大化模型 |
| 凸自适应全球宽松风险平价 | Convex Adaptive Global RRP | 凸化的宽松风险预算近似 |
| 改进凸自适应全球宽松风险平价 | Improved Convex Adaptive Global RRP | 强调低换手、CVaR 尾部风险控制和可实施性的凸优化改进 |
| 层次风险平价基准 | HRP Benchmark | 层次化风险配置基准 |
| 层次等风险贡献基准 | HERC Benchmark | 层次化风险配置基准 |

### 数据与方法

| 项目 | 说明 |
|---|---|
| 价格数据 | `data/processed/etf_prices_updated.csv` |
| 资产映射 | `data/processed/etf_asset_mapping.csv` |
| 数据区间 | `2018-01-02` 至 `2026-04-30` |
| 评估起点 | `2021-01-01` |
| 再平衡频率 | 月度再平衡 |
| 交易成本 | 默认 3 bps，并区分 gross return 与 net return |

每个再平衡日只使用当时已具备足够历史观测的 ETF 估计信号、协方差和权重；尚未上市或历史不足的 ETF 不参与优化。历史结果不代表未来表现。

### ETF 资产池

资产池使用可交易 ETF 表达债券、中国股票、港股、全球股票和商品等主要风险来源。部分原始指数或连续合约被替换为可交易 ETF，以保持回测与可实施组合之间的一致性。

| ETF | 代码 | 资产类别 | 配置角色 |
|---|---|---|---|
| 短融ETF | 511360.SH | 短久期信用债 | 防御性债券与流动性配置 |
| 可转债ETF | 511380.SH | 可转债 | 股债混合弹性暴露 |
| 沪深300ETF | 510300.SH | 中国股票 | A 股大盘核心暴露 |
| 中证1000ETF | 512100.SH | 中国股票 | A 股小盘与成长暴露 |
| 科创50ETF | 588000.SH | 中国股票 | 科创板成长暴露 |
| 红利ETF | 510880.SH | 中国股票红利 | 高股息与价值风格暴露 |
| 上证指数ETF | 510210.SH | 中国股票 | 宽基 A 股市场暴露 |
| 恒生ETF | 159920.SZ | 港股 | 香港股票市场暴露 |
| 恒生科技ETF | 513180.SH | 港股科技 | 香港科技成长暴露 |
| 纳指ETF | 159941.SZ | 全球股票 | 美国科技与成长股暴露 |
| 标普500ETF | 513500.SH | 全球股票 | 美国大盘股票暴露 |
| 日经225ETF | 513880.SH | 全球股票 | 日本股票市场暴露 |
| 黄金ETF | 518880.SH | 商品 | 贵金属与避险资产暴露 |
| 有色ETF | 159980.SZ | 商品 / 资源 | 有色金属与资源周期暴露 |
| 豆粕ETF | 159985.SZ | 商品 | 农产品商品暴露 |

### 最新绩效看板

核心模型结果：

| Model | Net Annual Return | Sharpe | Max Drawdown | Calmar | Avg Monthly Turnover |
|---|---:|---:|---:|---:|---:|
| Global RRP | 5.90% | 1.15 | -4.38% | 1.35 | 22.45% |
| Defensive Dynamic RRP | 3.88% | 0.48 | -6.51% | 0.60 | 20.22% |
| Convex Adaptive Global RRP | 5.36% | 0.58 | -8.15% | 0.66 | 1.03% |
| Improved Convex Adaptive Global RRP | 6.45% | 0.96 | -4.98% | 1.30 | 0.52% |

基准结果：

| Benchmark | Net Annual Return | Sharpe | Max Drawdown | Calmar | Avg Monthly Turnover |
|---|---:|---:|---:|---:|---:|
| HRP Benchmark | -0.12% | -6.36 | -0.73% | -0.16 | 1.56% |
| HERC Benchmark | -0.10% | -6.30 | -0.73% | -0.14 | 1.60% |

Global RRP 是主要的收益效率展示模型。Improved Convex Adaptive Global RRP 在保持有竞争力风险收益特征的同时，将平均月度换手率降至 0.52%，体现了凸约束在低换手、尾部风险控制和稳定配置中的价值。HRP/HERC 仅作为层次化风险配置基准；在当前资产池中，相关性聚类和递归配置本身不足以替代 Global RRP 与 Convex Adaptive RRP 框架。

### 图表展示

#### 净值曲线

![Convex Adaptive NAV Comparison](results/figures/convex_adaptive_nav_comparison.png)

净值曲线展示 Global RRP、Convex Adaptive Global RRP 与 Improved Convex Adaptive Global RRP 的累计表现差异。

#### 回撤曲线

![Convex Adaptive Drawdown Comparison](results/figures/convex_adaptive_drawdown_comparison.png)

回撤曲线用于比较不同模型在压力阶段的风险控制能力。

#### 换手率比较

![Convex Adaptive Turnover Comparison](results/figures/convex_adaptive_turnover_comparison.png)

换手率图展示凸优化约束对组合可实施性和交易成本敏感性的影响。

#### CVaR / 尾部风险比较

![Convex Adaptive CVaR Comparison](results/figures/convex_adaptive_cvar_comparison.png)

CVaR 图用于观察不同模型在尾部风险控制方面的差异。

### 输出与报告

| 文件 | 内容 |
|---|---|
| `results/tables/convex_adaptive_performance_summary.csv` | 凸自适应模型绩效汇总 |
| `results/tables/showcase_performance_summary.csv` | 展示模型绩效汇总 |
| `results/tables/convex_adaptive_transaction_cost_summary.csv` | 交易成本敏感性结果 |
| `results/tables/convex_adaptive_solver_diagnostics.csv` | 凸优化求解诊断 |
| `results/tables/asset_graph_diagnostics.csv` | 资产图诊断 |
| `results/tables/online_regime_diagnostics.csv` | 在线状态识别诊断 |
| `report/asset_pricing_interpretation.md` | 资产定价解释 |
| `report/methodology_notes.md` | 方法论说明 |
| `report/insurance_allocation_perspective.md` | 保险资金配置视角 |
| `report/thesis_figures_and_tables.md` | 论文图表索引 |

### 复现命令

```bash
python scripts/update_etf_data.py
python scripts/run_rrp_pipeline.py --mode full
python scripts/optimize_showcase_rrp.py
python scripts/run_hrp_comparison.py
python scripts/run_convex_adaptive_rrp.py
python scripts/run_benchmark_suite.py
python scripts/run_full_research_pipeline.py --quick
python -m pytest
```

### 协方差估计稳健性

协方差稳健性检验覆盖样本协方差、Ledoit-Wolf 收缩估计，以及 20、60、120 日半衰期的 EWMA 估计。该模块只用于敏感性诊断，不改变 Global RRP、Convex Adaptive Global RRP 与 Improved Convex Adaptive Global RRP 的官方定位或主结果表。

输出文件包括 `results/tables/covariance_robustness_summary.csv`、`results/tables/covariance_estimator_diagnostics.csv` 和下列图表。

![Covariance Robustness Sharpe](results/figures/covariance_robustness_sharpe.png)
![Covariance Robustness Drawdown](results/figures/covariance_robustness_drawdown.png)
![Covariance Robustness Turnover](results/figures/covariance_robustness_turnover.png)

<a id="en"></a>

## English

### Project Overview

This repository is a thesis-oriented global multi-asset allocation research project built around Relaxed Risk Parity, global asset extension, convex approximation, CVaR tail-risk control, turnover constraints, and robustness validation. It is not a short-term trading strategy repository; the emphasis is long-term institutional and insurance-style allocation interpretation.

Final portfolio weights are generated by transparent optimization. Machine learning, graph, and regime modules are used as diagnostics or constraint inputs; they do not directly generate portfolio weights.

### Research Framework

| Model / Module | Public Label | Research Role |
|---|---|---|
| Classical risk parity | Standard Risk Parity | Baseline risk-budgeting reference |
| Local relaxed risk parity | Local Relaxed Risk Parity | Relaxed risk parity in the local asset universe |
| Global relaxed risk parity | Global RRP | Main return-efficient showcase model |
| Defensive dynamic relaxed risk parity | Defensive Dynamic RRP | Defensive risk-overlay experiment, not the main return-maximizing model |
| Convex adaptive global relaxed risk parity | Convex Adaptive Global RRP | Convexified relaxed risk-budgeting approximation |
| Improved convex adaptive global relaxed risk parity | Improved Convex Adaptive Global RRP | Implementable convex refinement emphasizing low turnover, CVaR control, and stable allocation |
| Hierarchical risk parity | HRP Benchmark | Hierarchical risk-allocation benchmark |
| Hierarchical equal risk contribution | HERC Benchmark | Hierarchical risk-allocation benchmark |

### Data And Method

| Item | Description |
|---|---|
| Price cache | `data/processed/etf_prices_updated.csv` |
| Asset map | `data/processed/etf_asset_mapping.csv` |
| Data range | `2018-01-02` to `2026-04-30` |
| Evaluation start | `2021-01-01` |
| Rebalancing | Monthly |
| Transaction cost | Default 3 bps, with gross and net return separated |

At each monthly rebalance, the optimizer uses only ETFs with sufficient point-in-time history. Not-yet-listed or history-insufficient ETFs are excluded from optimization. Historical results do not imply future performance.

### ETF Asset Pool

The asset universe represents major risk sources through tradable ETFs, including bonds, China equities, Hong Kong equities, global equities, and commodities. Some original indices or continuous futures series are replaced with tradable ETFs to keep the backtest aligned with implementable portfolio construction.

| ETF | Ticker | Asset Class | Allocation Role |
|---|---|---|---|
| Short-Term Financing ETF | 511360.SH | Short-duration credit | Defensive bond and liquidity allocation |
| Convertible Bond ETF | 511380.SH | Convertible bond | Hybrid equity-bond convexity exposure |
| CSI 300 ETF | 510300.SH | China equity | Core China large-cap exposure |
| CSI 1000 ETF | 512100.SH | China equity | China small-cap and growth exposure |
| STAR 50 ETF | 588000.SH | China equity | STAR Market growth exposure |
| Dividend ETF | 510880.SH | China equity dividend | High-dividend and value-style exposure |
| Shanghai Composite ETF | 510210.SH | China equity | Broad A-share market exposure |
| Hang Seng ETF | 159920.SZ | Hong Kong equity | Hong Kong equity market exposure |
| Hang Seng Tech ETF | 513180.SH | Hong Kong technology | Hong Kong technology growth exposure |
| Nasdaq ETF | 159941.SZ | Global equity | U.S. technology and growth equity exposure |
| S&P 500 ETF | 513500.SH | Global equity | U.S. large-cap equity exposure |
| Nikkei 225 ETF | 513880.SH | Global equity | Japan equity market exposure |
| Gold ETF | 518880.SH | Commodity | Precious-metal and defensive asset exposure |
| Non-Ferrous Metals ETF | 159980.SZ | Commodity / resources | Metals and resource-cycle exposure |
| Soybean Meal ETF | 159985.SZ | Commodity | Agricultural commodity exposure |

### Latest Performance Dashboard

Core model results:

| Model | Net Annual Return | Sharpe | Max Drawdown | Calmar | Avg Monthly Turnover |
|---|---:|---:|---:|---:|---:|
| Global RRP | 5.90% | 1.15 | -4.38% | 1.35 | 22.45% |
| Defensive Dynamic RRP | 3.88% | 0.48 | -6.51% | 0.60 | 20.22% |
| Convex Adaptive Global RRP | 5.36% | 0.58 | -8.15% | 0.66 | 1.03% |
| Improved Convex Adaptive Global RRP | 6.45% | 0.96 | -4.98% | 1.30 | 0.52% |

Benchmark results:

| Benchmark | Net Annual Return | Sharpe | Max Drawdown | Calmar | Avg Monthly Turnover |
|---|---:|---:|---:|---:|---:|
| HRP Benchmark | -0.12% | -6.36 | -0.73% | -0.16 | 1.56% |
| HERC Benchmark | -0.10% | -6.30 | -0.73% | -0.14 | 1.60% |

Global RRP remains the main return-efficient global multi-asset model. Improved Convex Adaptive Global RRP achieves a competitive risk-return profile while reducing average monthly turnover to 0.52%, highlighting the value of convex constraints for implementable, low-turnover portfolio construction. HRP/HERC are included only as hierarchical risk-allocation benchmarks; in the current asset universe, correlation clustering and recursive allocation alone are insufficient to replace the Global RRP and Convex Adaptive RRP framework.

### Figures

#### NAV Curve

![Convex Adaptive NAV Comparison](results/figures/convex_adaptive_nav_comparison.png)

The NAV curve compares the cumulative performance of Global RRP, Convex Adaptive Global RRP, and Improved Convex Adaptive Global RRP.

#### Drawdown Curve

![Convex Adaptive Drawdown Comparison](results/figures/convex_adaptive_drawdown_comparison.png)

The drawdown curve compares model risk control during stressed periods.

#### Turnover Comparison

![Convex Adaptive Turnover Comparison](results/figures/convex_adaptive_turnover_comparison.png)

The turnover chart shows how convex optimization constraints affect implementability and transaction-cost sensitivity.

#### CVaR / Tail-Risk Comparison

![Convex Adaptive CVaR Comparison](results/figures/convex_adaptive_cvar_comparison.png)

The CVaR chart helps compare tail-risk control across models.

### Outputs And Reports

| File | Content |
|---|---|
| `results/tables/convex_adaptive_performance_summary.csv` | Convex adaptive model performance summary |
| `results/tables/showcase_performance_summary.csv` | Showcase model performance summary |
| `results/tables/convex_adaptive_transaction_cost_summary.csv` | Transaction-cost sensitivity results |
| `results/tables/convex_adaptive_solver_diagnostics.csv` | Convex solver diagnostics |
| `results/tables/asset_graph_diagnostics.csv` | Asset graph diagnostics |
| `results/tables/online_regime_diagnostics.csv` | Online regime diagnostics |
| `results/tables/covariance_robustness_summary.csv` | Covariance-estimator robustness summary, with annualized volatility and daily CVaR clearly separated |
| `results/tables/covariance_estimator_diagnostics.csv` | Covariance diagnostics covering PSD repair, condition number, fallback, and point-in-time flags |
| `report/asset_pricing_interpretation.md` | Asset-pricing interpretation |
| `report/methodology_notes.md` | Methodology notes |
| `report/insurance_allocation_perspective.md` | Insurance allocation perspective |
| `report/thesis_figures_and_tables.md` | Thesis figures and tables index |

### Covariance Robustness

The covariance robustness layer tests sample covariance, Ledoit-Wolf shrinkage, and EWMA estimates with 20-, 60-, and 120-day halflives. These outputs are sensitivity diagnostics only; they do not retune, rerank, or replace the official Global RRP, Convex Adaptive Global RRP, or Improved Convex Adaptive Global RRP results.

![Covariance Robustness Sharpe](results/figures/covariance_robustness_sharpe.png)
![Covariance Robustness Drawdown](results/figures/covariance_robustness_drawdown.png)
![Covariance Robustness Turnover](results/figures/covariance_robustness_turnover.png)

### Reproduction Commands

```bash
python scripts/update_etf_data.py
python scripts/run_rrp_pipeline.py --mode full
python scripts/optimize_showcase_rrp.py
python scripts/run_hrp_comparison.py
python scripts/run_convex_adaptive_rrp.py
python scripts/run_benchmark_suite.py
python scripts/run_covariance_robustness.py --quick
python scripts/run_full_research_pipeline.py --quick
python -m pytest
```

## License

MIT License.
