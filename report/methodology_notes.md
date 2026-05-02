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

### 协方差估计

协方差估计作为共享的稳健性诊断组件使用，不改变官方模型排序，也不替代当前 Improved Convex Adaptive Global RRP 结果。

样本协方差：

```text
Sigma_sample = 1 / (T - 1) * sum_t (r_t - r_bar)(r_t - r_bar)'
```

Ledoit-Wolf 收缩估计：

```text
Sigma_LW = delta * F + (1 - delta) * Sigma_sample
```

代码优先使用 `sklearn.covariance.LedoitWolf`。如果 sklearn 不可用或拟合失败，只有在调用方明确允许 fallback 时才退回样本协方差；诊断字段会记录 `covariance_fallback_used=True`、`covariance_fallback_method=sample` 和失败说明。

EWMA 协方差使用指数衰减权重：

```text
lambda = exp(log(0.5) / halflife)
Sigma_t = (1 - lambda) * sum_{i=1..T} lambda^(T-i) (r_i - r_bar)(r_i - r_bar)'
```

每个再平衡日只使用 `returns.index < rebalance_date` 的历史收益窗口，属于 point-in-time 估计。支持 `ewma_halflife_20`、`ewma_halflife_60` 和 `ewma_halflife_120`。估计器默认输出日度协方差；优化器显式传入 `annualize=True` 和交易日数量。

### CVaR 公式

对组合损失 `L = -R w`，置信水平 `alpha` 下：

```text
CVaR_alpha(L) = min_eta eta + 1 / ((1 - alpha) * T) * sum_t max(L_t - eta, 0)
```

脚本中的辅助变量形式与该表达一致，用于尾部损失惩罚，不用于预测未来收益。

### 稳健性输出定位

`results/tables/covariance_robustness_summary.csv`、`results/tables/covariance_estimator_diagnostics.csv` 以及对应图表只作为协方差估计敏感性诊断。它们用于验证 Global RRP、Convex Adaptive Global RRP 和 Improved Convex Adaptive Global RRP 对样本协方差、Ledoit-Wolf 和不同 EWMA 半衰期的敏感性，不进行重新调参、重新排序或模型替换。

### DCC-GARCH 未来扩展

DCC-GARCH 可作为未来动态条件相关建模方向，用于研究时变相关和波动聚类。但当前版本仅在文档中说明，不新增依赖，不接入现有回测或优化流水线。

### 局限

数据来自可获得的历史资产价格，存在样本区间、资产可交易性、汇率、流动性、税费和滑点限制。稳健性检验为验证用途，不进行模型选择或重新调参。历史结果不代表未来表现。

## English

This project studies Relaxed Risk Parity for global multi-asset allocation. The convex adaptive layer is a practical constrained approximation to risk budgeting, not an exact convex reformulation of classical risk parity.

Covariance estimation is implemented as a shared diagnostic robustness component. It does not change the official model lineup, rerank models, or replace the current Improved Convex Adaptive Global RRP result.

Sample covariance:

```text
Sigma_sample = 1 / (T - 1) * sum_t (r_t - r_bar)(r_t - r_bar)'
```

Ledoit-Wolf shrinkage:

```text
Sigma_LW = delta * F + (1 - delta) * Sigma_sample
```

The implementation uses `sklearn.covariance.LedoitWolf` when available. If it is unavailable or fitting fails, fallback to sample covariance is only allowed when explicitly requested, and diagnostics record the fallback flag, fallback method, and failure note.

EWMA covariance uses exponentially decaying historical weights:

```text
lambda = exp(log(0.5) / halflife)
Sigma_t = (1 - lambda) * sum_{i=1..T} lambda^(T-i) (r_i - r_bar)(r_i - r_bar)'
```

At every rebalance, covariance is estimated point-in-time from observations where `returns.index < rebalance_date`. The estimator returns daily covariance by default; optimizers explicitly request annualized covariance using the configured trading-day count.

The covariance robustness tables and figures validate sensitivity across `sample`, `ledoit_wolf`, `ewma_halflife_20`, `ewma_halflife_60`, and `ewma_halflife_120`. These outputs are diagnostic validation only and do not retune, rerank, or replace the main models.

DCC-GARCH is a future documentation-only extension for dynamic conditional correlation modeling. No new dependency or pipeline integration is added in the current implementation.
