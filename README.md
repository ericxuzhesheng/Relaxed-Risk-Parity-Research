# Relaxed Risk Parity Framework | 宽松风险平价全球资产配置框架

<a id="en"></a>
## English

This repository studies Relaxed Risk Parity for global multi-asset allocation. The latest extension adds a convex adaptive layer with bounded graph diagnostics, transaction-cost-aware optimization, CVaR regularization, and stable online regime labels. Final portfolio weights are always produced by the optimization layer.

Evaluation starts on `2021-01-01`. Gross and net results are both shown so transaction costs are visible.

| Model | Gross Return | Net Return | Cost Drag | Avg Monthly Turnover | Turnover-adjusted Sharpe | Max Drawdown | Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| Global Relaxed Risk Parity | 5.99% | 5.90% | 0.09% | 0.224 | 1.66 | -4.38% | 1.35 |
| Defensive Dynamic Relaxed Risk Parity | 3.96% | 3.88% | 0.08% | 0.202 | 0.91 | -6.51% | 0.60 |
| HRP Benchmark | -0.11% | -0.12% | 0.01% | 0.016 | -0.39 | -0.73% | -0.16 |
| HERC Benchmark | -0.09% | -0.10% | 0.01% | 0.016 | -0.33 | -0.73% | -0.14 |
| Convex Global Relaxed Risk Parity | 5.55% | 5.55% | 0.00% | 0.009 | 0.92 | -7.96% | 0.70 |
| Turnover-Aware Convex Global RRP | 5.15% | 5.15% | 0.00% | 0.001 | 0.78 | -8.54% | 0.60 |
| CVaR-Aware Convex Global RRP | 5.54% | 5.54% | 0.00% | 0.009 | 0.94 | -7.74% | 0.72 |
| Convex Adaptive Global Relaxed Risk Parity | 5.37% | 5.36% | 0.00% | 0.010 | 0.87 | -8.15% | 0.66 |
| Convex Adaptive Global RRP + Asset Graph Features | 5.39% | 5.39% | 0.00% | 0.009 | 0.87 | -8.21% | 0.66 |
| Convex Adaptive Global RRP + Transaction-Cost-Aware Objective | 4.00% | 4.00% | 0.00% | 0.002 | 0.57 | -10.28% | 0.39 |
| Convex Adaptive Global RRP + Graph + Transaction Cost + Stable Online Regime | 3.89% | 3.89% | 0.00% | 0.002 | 0.56 | -10.32% | 0.38 |

Key outputs:
- `results/tables/convex_adaptive_performance_summary.csv`
- `results/tables/convex_adaptive_transaction_cost_summary.csv`
- `results/tables/asset_graph_diagnostics.csv`
- `results/tables/online_regime_diagnostics.csv`
- `results/tables/convex_adaptive_solver_diagnostics.csv`
- `results/figures/convex_adaptive_nav_comparison.png`
- `results/figures/convex_adaptive_transaction_cost_comparison.png`

Solver fallback rate in the latest convex run: `0.0%`. Fallback rows are explicitly flagged in solver diagnostics.

Run:
```bash
pip install -r requirements.txt
python -m pytest
python scripts/run_convex_adaptive_rrp.py
```

<a id="zh"></a>
## 中文

本项目研究宽松风险平价在全球多资产配置中的应用。最新扩展加入凸优化自适应层、轻量资产相关性图诊断、交易成本约束、CVaR 正则项和稳定在线风险状态标签。最终组合权重始终由优化层生成，图特征和状态标签只作为有界风险输入。

评估区间从 `2021-01-01` 开始。下表同时展示毛收益、净收益和交易成本拖累。

| 模型 | 毛年化收益 | 净年化收益 | 成本拖累 | 月均换手 | 换手调整夏普 | 最大回撤 | Calmar |
|---|---:|---:|---:|---:|---:|---:|---:|
| Global Relaxed Risk Parity | 5.99% | 5.90% | 0.09% | 0.224 | 1.66 | -4.38% | 1.35 |
| Defensive Dynamic Relaxed Risk Parity | 3.96% | 3.88% | 0.08% | 0.202 | 0.91 | -6.51% | 0.60 |
| HRP Benchmark | -0.11% | -0.12% | 0.01% | 0.016 | -0.39 | -0.73% | -0.16 |
| HERC Benchmark | -0.09% | -0.10% | 0.01% | 0.016 | -0.33 | -0.73% | -0.14 |
| Convex Global Relaxed Risk Parity | 5.55% | 5.55% | 0.00% | 0.009 | 0.92 | -7.96% | 0.70 |
| Turnover-Aware Convex Global RRP | 5.15% | 5.15% | 0.00% | 0.001 | 0.78 | -8.54% | 0.60 |
| CVaR-Aware Convex Global RRP | 5.54% | 5.54% | 0.00% | 0.009 | 0.94 | -7.74% | 0.72 |
| Convex Adaptive Global Relaxed Risk Parity | 5.37% | 5.36% | 0.00% | 0.010 | 0.87 | -8.15% | 0.66 |
| Convex Adaptive Global RRP + Asset Graph Features | 5.39% | 5.39% | 0.00% | 0.009 | 0.87 | -8.21% | 0.66 |
| Convex Adaptive Global RRP + Transaction-Cost-Aware Objective | 4.00% | 4.00% | 0.00% | 0.002 | 0.57 | -10.28% | 0.39 |
| Convex Adaptive Global RRP + Graph + Transaction Cost + Stable Online Regime | 3.89% | 3.89% | 0.00% | 0.002 | 0.56 | -10.32% | 0.38 |

主要输出保存在 `results/tables/` 和 `results/figures/`。本研究不构成投资建议，数据质量、滑点、流动性、税费和实盘可交易性需要独立复核。

## License
MIT License.
