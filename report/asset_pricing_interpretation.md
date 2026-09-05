# 收益与风险归因

## 中文

归因用于解释七个正式模型的收益来源。它读取既有权重和收益，不参与调仓。

收益归因按资产类别分解实际收益，风险归因使用协方差贡献和压力期损失。因子代理取自同一 ETF 池，缺失类别由 `available_factors` 记录。这些代理无法替代外部因子检验。

Improved Convex Adaptive Global RRP 的解释应结合现金集中度、风险预算参考和换手约束。当前 CVaR 惩罚为零，不能将其表现归因于尾部风险惩罚。Global RRP 与 Convex Adaptive Global RRP 提供配置方法上的对照。

归档回归系数未用于当前主模型的结论。重新引用前，应按当前收益路径、样本和口径运行归因，并核对输出。

## English

Attribution explains returns for the seven published models and does not generate weights. Return contributions use realized holdings and asset returns. Risk contributions use covariance and stress-period losses.

Factor proxies come from the same ETF universe. Missing groups are recorded in `available_factors`. Their interpretation depends on the sample and available assets.

The primary model has no active CVaR penalty. Its results should be interpreted through cash concentration, the risk-budget reference and turnover controls. Archived regression coefficients require a rerun on current paths before use.
