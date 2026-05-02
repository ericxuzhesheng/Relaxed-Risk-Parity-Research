# 论文图表索引

## 中文

| 章节 | 类型 | 建议标题 | 来源路径 | 解释备注 |
|---|---|---|---|---|
| 第三章 方法 | 表 | 模型设定与约束说明 | `report/methodology_notes.md` | 说明 RRP、动态覆盖和凸自适应层的关系。 |
| 第四章 实证 | 表 | 主模型绩效汇总 | `results/tables/performance_summary.csv` | 主模型线，不由新增 benchmark 替代。 |
| 第四章 实证 | 表 | 凸自适应模型绩效汇总 | `results/tables/convex_adaptive_performance_summary.csv` | 展示基础与改进凸自适应模型。 |
| 第四章 实证 | 图 | 凸自适应 NAV 对比 | `results/figures/convex_adaptive_nav_comparison.png` | 用于展示净值路径差异。 |
| 第四章 实证 | 图 | 凸自适应回撤对比 | `results/figures/convex_adaptive_drawdown_comparison.png` | 用于展示回撤控制效果。 |
| 第五章 对比 | 表 | Benchmark 绩效汇总 | `results/tables/benchmark_performance_summary.csv` | 对比等权、最小方差、最大分散化、经典 RP、60/40、HRP、HERC。 |
| 第五章 对比 | 图 | Benchmark NAV 对比 | `results/figures/benchmark_nav_comparison.png` | 横向展示公开模型与 benchmark。 |
| 第五章 对比 | 图 | Benchmark 回撤对比 | `results/figures/benchmark_drawdown_comparison.png` | 横向展示不同方法的损失路径。 |
| 第六章 稳健性 | 表 | 稳健性总览 | `results/tables/robustness_overall_summary.csv` | 总结子区间、成本、协方差、压力、bootstrap 和过拟合诊断。 |
| 第六章 稳健性 | 表 | Bootstrap 摘要 | `results/tables/robustness_block_bootstrap_summary.csv` | 验证收益路径重采样下的 Sharpe 和回撤分布。 |
| 第六章 稳健性 | 图 | Bootstrap Sharpe 分布 | `results/figures/robustness_bootstrap_sharpe_distribution.png` | 展示估计不确定性。 |
| 第六章 稳健性 | 图 | Bootstrap 回撤分布 | `results/figures/robustness_bootstrap_drawdown_distribution.png` | 展示尾部回撤不确定性。 |
| 第七章 解释 | 表 | 因子暴露摘要 | `results/tables/asset_pricing_factor_exposure_summary.csv` | 解释层，不参与权重生成。 |
| 第七章 解释 | 表 | 收益归因 | `results/tables/asset_pricing_return_attribution.csv` | 分析资产类别收益贡献。 |
| 第七章 解释 | 表 | 风险归因 | `results/tables/asset_pricing_risk_attribution.csv` | 分析资产类别风险贡献。 |
| 第七章 解释 | 图 | 因子暴露图 | `results/figures/asset_pricing_factor_exposure.png` | 展示模型相对代理因子的 beta。 |

## English Summary

Use the main performance tables for core empirical findings, benchmark tables for cross-method comparison, robustness tables for validation, and asset-pricing tables only for interpretation. The additive research layer should not be described as a replacement for the existing Relaxed Risk Parity model line.
