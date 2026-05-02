# 过拟合审计与验证路线 | Overfitting Audit And Validation Roadmap

## 中文

### 审计结论

本项目区分两类问题：直接前视偏差和候选选择过拟合风险。

直接前视偏差指再平衡时使用了未来价格、收益或权重信息。现有回测逻辑在每个再平衡日使用 `returns.index < date` 的历史窗口估计协方差、风险预算、CVaR 惩罚和组合权重，因此没有发现直接使用未来收益生成当期权重的证据。

候选选择过拟合风险是另一类问题。Improved Convex Adaptive Global RRP 来自一组受约束候选参数的历史绩效比较，并使用 Sharpe、Calmar、回撤、CVaR、换手率和求解器状态等历史评价指标进行筛选。因此，它应定位为受约束的样本内参数细化研究扩展，而不是已经完成冻结样本外验证的最终模型。

### 透明证据

候选搜索位于 `scripts/run_convex_adaptive_rrp.py`，关键入口包括：

- `candidate_configurations`：定义候选参数集合。
- `selection_score`：根据历史评价指标和拒绝条件计算候选分数。
- `run_improvement_search`：运行候选回测并选择候选。
- `config_row`：写出候选参数、评分、拒绝原因和审计备注。

现有透明证据包括 `results/tables/convex_adaptive_improvement_candidates.csv`、无前视审计、鲁棒性诊断、参数扰动、协方差估计敏感性、交易成本压力测试和简化过拟合诊断。这些输出提高了可审计性，但不等同于完整的冻结样本外验证。

### 后续验证路线

1. Walk-forward selection：在滚动训练/验证窗口中选择候选参数，并仅在下一段未见测试窗口评估。
2. Nested train/validation/test：把参数选择和最终测试期严格分离，避免同一历史区间同时用于筛选和结论展示。
3. CSCV/PBO diagnostics：使用组合对称交叉验证和 PBO 指标评估候选选择偏误。
4. Frozen OOS period：预先冻结一个样本外区间，只在参数规则确定后运行一次。
5. Parameter stability：检查入选参数在不同窗口中的稳定性，而不是只报告单次最优组合。
6. Transaction-cost stress tests：提高交易成本、滑点和换手惩罚假设，观察低换手结论是否保持。

## English

### Audit Conclusion

This repository separates two issues: direct look-ahead bias and candidate-selection overfitting risk.

Direct look-ahead bias would mean using future prices, returns, or weights at a rebalance date. The current backtest logic estimates covariance, risk budgets, CVaR penalties, and portfolio weights from windows where `returns.index < date`, so there is no evidence that future returns are directly used to generate current weights.

Candidate-selection overfitting is different. Improved Convex Adaptive Global RRP is selected from constrained candidate parameters using historical evaluation metrics such as Sharpe, Calmar, drawdown, CVaR, turnover, and solver status. It should therefore be described as a constrained in-sample parameter-refinement research extension, not as a completed frozen out-of-sample result.

### Transparent Evidence

The candidate search is implemented in `scripts/run_convex_adaptive_rrp.py`. The main audit points are:

- `candidate_configurations`: defines the candidate parameter set.
- `selection_score`: scores candidates using historical metrics and rejection gates.
- `run_improvement_search`: runs candidate backtests and selects the preferred candidate.
- `config_row`: writes candidate parameters, scores, rejection reasons, and audit notes.

Existing transparent evidence includes `results/tables/convex_adaptive_improvement_candidates.csv`, robustness diagnostics, the no-lookahead audit, parameter perturbation, covariance-estimator sensitivity, transaction-cost stress tests, and simplified overfitting diagnostics. These outputs improve auditability, but they are not a completed frozen OOS validation.

### Validation Roadmap

1. Walk-forward selection: select candidate parameters on rolling train/validation windows and evaluate only on the next unseen test window.
2. Nested train/validation/test: separate parameter selection from final testing so the same history is not used for both selection and conclusion.
3. CSCV/PBO diagnostics: use combinatorially symmetric cross-validation and PBO metrics to assess selection bias.
4. Frozen OOS period: predefine a held-out sample and run it once after the parameter rule is fixed.
5. Parameter stability: test whether selected parameters are stable across windows instead of reporting only one best candidate.
6. Transaction-cost stress tests: raise cost, slippage, and turnover assumptions to test whether low-turnover conclusions remain stable.
