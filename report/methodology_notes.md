# 方法说明与论文复现备注

## 中文

### 研究目标

本项目研究 Relaxed Risk Parity 在全球多资产配置中的实现方式。主线模型保留风险预算思想，但放松经典风险平价中严格等风险贡献的要求，并加入动态选择、风险覆盖、交易成本、CVaR 尾部风险约束和凸优化增强。

### 概念性优化问题

给定收益窗口 `R_t`、协方差估计 `Sigma_t`、自适应风险预算 `b_t` 和上一期权重 `w_{t-1}`，凸自适应层可概念化为：

```text
min_w  lambda_var * w' Sigma_t w
     + lambda_budget * ||w - b_t||_2^2
     + lambda_turnover * ||w - w_{t-1}||_1
     + lambda_cvar * CVaR_alpha(-R_t w)
     - lambda_return * mu_t' w

s.t.  sum_i w_i = 1
      0 <= w_i <= upper_bound_i
      group_lower_g <= sum_{i in g} w_i <= group_upper_g
      ||w - w_{t-1}||_1 <= turnover_cap
```

这不是把经典风险平价问题精确改写为全局凸问题，而是以可解释、可求解、可加入约束的方式近似风险预算目标。

### CVaR 公式

对组合损失 `L = -R w`，置信水平 `alpha` 下：

```text
CVaR_alpha(L) = min_eta eta + 1 / ((1 - alpha) * T) * sum_t max(L_t - eta, 0)
```

脚本中的辅助变量形式与该表达一致，用于尾部损失惩罚，不用于预测未来收益。

### 实证输出

核心结果来自 `results/tables/performance_summary.csv` 与 `results/tables/convex_adaptive_performance_summary.csv`。新增 benchmark、robustness 和 asset-pricing 文件只作为论文级比较、稳健性检验与解释层，不替换主模型线。

### 局限

数据来自可获得的历史资产价格，存在样本区间、资产可交易性、汇率、流动性、税费和滑点限制。因子解释层使用资产池内部代理，不等同于外部学术因子。稳健性检验为验证用途，不进行模型选择或重新调参。

### 未来研究

后续可扩展到更长的跨市场数据、更严格的交易执行成本、外部宏观因子、真实基金或期货连续合约复权数据，以及组合约束的统计显著性检验。

### 参考文献

- Risk Return Trade-Off in Relaxed Risk Parity.
- Building Diversified Portfolios that Outperform Out-of-Sample.
- A machine learning approach to risk based asset allocation in portfolio optimization.
- Using Deep Reinforcement Learning with Hierarchical Risk Parity for Portfolio Optimization.

## English Summary

This project studies Relaxed Risk Parity for global multi-asset allocation. The convex adaptive layer is a practical constrained approximation to risk budgeting, not an exact convex reformulation of classical risk parity. Benchmark, robustness, and asset-pricing outputs are additive thesis validation layers and do not select, retune, or replace the main model results.
