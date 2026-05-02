# Overfitting and Look-Ahead Audit
# 过拟合与未来函数审计

## Executive Summary

This audit separates three issues that should not be merged into one claim:

- Direct look-ahead bias: whether a rebalance uses future prices, returns, risk estimates, or weights.
- Same-period execution bias: whether weights formed on a rebalance date are applied to the same date's return in a way that may be too optimistic.
- Parameter-selection overfitting: whether a reported model variant is selected from candidate settings using the same historical sample later used for presentation.

No obvious direct look-ahead pattern is identified from the reviewed rolling-window design. The reviewed rolling routines use historical windows such as `returns.index < date` before estimating covariance, risk budgets, graph diagnostics, regime state, CVaR penalties, or portfolio weights. This statement is intentionally limited: it does not prove that the repository has no look-ahead bias, and it does not prove that the reported model selection is free from overfitting.

The main residual research risk is candidate-selection overfitting in Improved Convex Adaptive Global RRP. The candidate search in `scripts/run_convex_adaptive_rrp.py` defines constrained alternatives in `candidate_configurations`, evaluates them through historical metrics in `selection_score`, executes the comparison in `run_improvement_search`, and records the audit fields through `config_row`. Improved Convex Adaptive Global RRP should therefore be reported as a constrained in-sample refinement / research extension, not as a completed frozen out-of-sample result.

## 执行摘要

本审计区分三类问题，避免把它们合并成一个过度确定的结论：

- 直接未来函数偏差：再平衡时是否使用未来价格、收益、风险估计或权重。
- 同期执行偏差：再平衡日形成的权重是否被用于同一日期收益，从而可能产生偏乐观执行假设。
- 参数选择过拟合：公开报告的模型变体是否由同一历史样本中的候选参数筛选得到。

从已审阅的滚动窗口设计看，未识别出明显的直接未来函数模式。相关滚动例程在估计协方差、风险预算、图诊断、状态识别、CVaR 惩罚或组合权重前，使用 `returns.index < date` 等历史窗口边界。该结论有意保持克制：它不证明仓库完全没有未来函数偏差，也不证明公开模型筛选不存在过拟合。

主要剩余研究风险来自 Improved Convex Adaptive Global RRP 的候选参数筛选。`scripts/run_convex_adaptive_rrp.py` 中的 `candidate_configurations` 定义受约束候选参数，`selection_score` 使用历史评价指标打分，`run_improvement_search` 执行候选比较，`config_row` 记录审计字段。因此，Improved Convex Adaptive Global RRP 应表述为受约束样本内细化 / 研究扩展，而不是已经完成冻结样本外验证的最终结果。

## Direct Look-Ahead Audit

### Direct Look-Ahead Bias

Direct look-ahead bias would occur if portfolio weights at time `t` used observations from `t` or later that would not be known before the rebalance decision. The reviewed core backtest paths avoid this obvious pattern:

- `src/convex_adaptive_rrp.py` forms `window_full = returns[returns.index < date].iloc[-cfg.lookback_days:]` before investability filtering, graph feature construction, online regime update, adaptive budget generation, CVaR calculation, and convex optimization.
- `src/backtest.py` forms `df_window_full = returns[returns.index < d].iloc[-lookback:]` before covariance estimation, trend confirmation, relaxed risk parity optimization, and risk-overlay inputs.
- `scripts/run_convex_adaptive_rrp.py` uses `returns.index < date` in the HRP/HERC benchmark wrapper and delegates Convex Adaptive Global RRP evaluation to the same rolling-window optimizer.
- `scripts/run_robustness_tests.py` uses `returns.index < date` in covariance robustness routines and records the point-in-time assumption in `robustness_no_lookahead_audit.csv`.

Based on these reviewed patterns, no obvious direct look-ahead pattern is identified from the reviewed rolling-window design.

### Same-Period Execution Bias

The reviewed loops compute new weights on rebalance dates from data strictly before that date, then apply the resulting weights to `returns.loc[date]`. This is not the same as direct look-ahead, because the inputs used for weight formation exclude that date's return. However, it can still encode a same-period execution assumption: the backtest effectively assumes the rebalance can be implemented before the return measured at `date` is earned.

This is acceptable as a documented convention only if the return index represents the next tradable holding-period return after the decision. If `returns.loc[date]` represents the full same-day close-to-close return and weights are determined at month-end close, the implementation may be optimistic. The current audit therefore recommends an explicit execution-timing check, such as shifting new weights by one trading day or documenting the price timestamp convention.

### Parameter-Selection Overfitting

Parameter-selection overfitting is the main concern for the improved variant. The code does not merely evaluate one pre-specified configuration:

- `candidate_configurations` enumerates alternative lookback windows, turnover caps, turnover penalties, CVaR penalties, max-weight bounds, covariance estimators, CVaR confidence levels, and return rewards.
- `selection_score` ranks candidates using historical Sharpe, Calmar, drawdown, daily CVaR loss, turnover, net return deterioration gates, and solver fallback status.
- `run_improvement_search` backtests each candidate and selects the highest-scoring accepted candidate, or the best available candidate when no preferred candidate passes all gates.
- `config_row` writes candidate parameters, selection score, rejection reason, solver fallback rate, and the note that the selected candidate is a research-extension candidate rather than frozen OOS.

This design improves transparency, but it also means the selected Improved Convex Adaptive Global RRP has candidate-selection risk. The audit should not describe it as free of overfitting. It should be described as a constrained in-sample refinement / research extension with explicit candidate-selection risk disclosed.

## 直接未来函数审计

### 直接未来函数偏差

直接未来函数偏差是指 `t` 时点组合权重使用了 `t` 或之后才可观察到的信息。已审阅的核心回测路径没有出现这一明显模式：

- `src/convex_adaptive_rrp.py` 在可投资资产过滤、图特征构造、在线状态更新、自适应风险预算、CVaR 计算和凸优化前，使用 `window_full = returns[returns.index < date].iloc[-cfg.lookback_days:]`。
- `src/backtest.py` 在协方差估计、趋势确认、宽松风险平价优化和风险覆盖输入前，使用 `df_window_full = returns[returns.index < d].iloc[-lookback:]`。
- `scripts/run_convex_adaptive_rrp.py` 的 HRP/HERC benchmark 包装逻辑使用 `returns.index < date`，Convex Adaptive Global RRP 评估则交由同一滚动窗口优化器完成。
- `scripts/run_robustness_tests.py` 在协方差稳健性路径中使用 `returns.index < date`，并在 `robustness_no_lookahead_audit.csv` 中记录 point-in-time 假设。

基于这些已审阅模式，从滚动窗口设计看，未识别出明显的直接未来函数模式。

### 同期执行偏差

已审阅循环在再平衡日使用该日之前的数据形成新权重，然后将该权重用于 `returns.loc[date]`。这不等同于直接未来函数，因为权重生成输入排除了该日收益。不过，它仍可能包含同期执行假设：回测默认在 `date` 对应收益实现之前已经完成调仓。

只有当收益索引代表决策后下一段可持有期收益时，这一约定才是充分可解释的。如果 `returns.loc[date]` 是完整的同日 close-to-close 收益，而权重在月末收盘才确定，则该实现可能偏乐观。因此，本审计建议增加明确的执行时点检查，例如将新权重滞后一交易日，或在方法说明中明确价格时间戳约定。

### 参数选择过拟合

改进模型的主要风险是参数选择过拟合。代码并非只评估一个预先固定的配置：

- `candidate_configurations` 枚举不同回看窗口、换手上限、换手惩罚、CVaR 惩罚、单资产上限、协方差估计器、CVaR 置信水平和收益奖励。
- `selection_score` 使用历史 Sharpe、Calmar、回撤、日度 CVaR 损失、换手率、净收益恶化门槛和求解器 fallback 状态进行排序。
- `run_improvement_search` 回测每个候选，并在通过门槛的候选中选择最高分；若没有 preferred candidate，则选择可接受候选或全体候选中的最高分。
- `config_row` 写出候选参数、筛选分数、拒绝原因、求解器 fallback 比例，并记录该候选是研究扩展而非冻结样本外结果。

该设计提高了透明度，但也意味着入选的 Improved Convex Adaptive Global RRP 存在候选选择风险。审计不应表述为该模型没有过拟合，而应表述为受约束样本内细化 / 研究扩展，并显式披露候选参数筛选风险。

## Evidence And Scope Limits

Reviewed evidence supports a limited conclusion:

- Rolling model inputs generally use trailing windows ending strictly before the rebalance date.
- CVaR penalties are computed from historical losses in the trailing window, not from future realized returns.
- Graph features and online regime states are diagnostics or constraint inputs derived from historical windows, not direct weight generators.
- Existing robustness outputs, no-lookahead audit rows, solver diagnostics, parameter perturbation, covariance robustness, block bootstrap, and simplified overfitting diagnostics improve auditability.

Reviewed evidence does not support stronger claims:

- It does not prove that every helper, report, cache, or downstream table is free of timing assumptions.
- It does not prove that same-period execution is conservative.
- It does not convert candidate-selected historical performance into frozen out-of-sample validation.
- It does not prove that the improved candidate will generalize.

## 证据边界

已审阅证据支持有限结论：

- 滚动模型输入通常使用严格早于再平衡日的历史窗口。
- CVaR 惩罚来自历史窗口中的尾部损失，而不是未来已实现收益。
- 图特征和在线状态识别是由历史窗口生成的诊断或约束输入，不直接生成最终权重。
- 现有鲁棒性输出、无前视审计、求解器诊断、参数扰动、协方差稳健性、block bootstrap 和简化过拟合诊断提高了可审计性。

已审阅证据不支持更强结论：

- 不能证明每个辅助函数、报告、缓存或下游表格都不存在时点假设问题。
- 不能证明同期执行假设一定保守。
- 不能把候选筛选后的历史表现转化为冻结样本外验证。
- 不能证明改进候选未来一定具有泛化能力。

## Model-Positioning Recommendation

Public-facing documentation should preserve the following positioning:

- Global RRP remains the main return-efficient global multi-asset research model.
- Convex Adaptive Global RRP remains the convexified relaxed risk-budgeting approximation.
- Improved Convex Adaptive Global RRP should be described as a constrained in-sample refinement / research extension with explicit candidate-selection risk disclosed.
- Defensive Dynamic RRP should remain a defensive risk-overlay experiment, not the main return-maximizing model.
- HRP Benchmark and HERC Benchmark should remain benchmarks only.

The recommended public wording is: "Improved Convex Adaptive Global RRP is reported as a constrained in-sample refinement / research extension selected from candidate settings using historical evaluation metrics; it should not be interpreted as a completed frozen out-of-sample result."

## 模型定位建议

公开文档应保持以下定位：

- Global RRP 仍是主要的收益效率型全球多资产研究模型。
- Convex Adaptive Global RRP 仍是凸化的宽松风险预算近似。
- Improved Convex Adaptive Global RRP 应表述为受约束样本内细化 / 研究扩展，并显式披露候选参数筛选风险。
- Defensive Dynamic RRP 应保持为防御型风险覆盖实验，而不是主要收益最大化模型。
- HRP Benchmark 与 HERC Benchmark 应保持为 benchmark。

建议公开措辞为：“Improved Convex Adaptive Global RRP 是使用历史评价指标从候选参数中筛选出的受约束样本内细化 / 研究扩展，不应被解读为已经完成冻结样本外验证的最终结果。”

## Validation Roadmap

1. Walk-forward parameter selection: choose candidate parameters only on rolling train/validation windows, then evaluate the selected rule on the next unseen test window.
2. Nested train/validation/test: separate model design, parameter selection, and final testing so the same sample is not used for both selection and final claims.
3. CSCV/PBO diagnostic: use combinatorially symmetric cross-validation and probability-of-backtest-overfitting metrics to quantify selection bias.
4. Frozen OOS period: predefine a final out-of-sample period and run it only once after the candidate-selection rule is frozen.
5. Sensitivity tests: test whether conclusions are stable under weight-lag execution, transaction-cost stress, parameter perturbation, covariance-estimator changes, and sample-window changes.

## Executed Validation Status
## 已执行验证状态

### English

- Executed script: `scripts/run_cscv_pbo.py`
- Command used: `python scripts/run_cscv_pbo.py --max-candidates 4 --num-blocks 6 --max-combinations 6`
- Output files: `results/tables/cscv_pbo_results.csv`, `results/tables/cscv_pbo_summary.csv`
- Validation type: intermediate
- Key summary metrics: PBO `0.3333333333333333`, median logit rank `0.6931471805599457`, mean relative rank `0.5833333333333334`, candidate count `4`, block count `6`, split count `6`
- Interpretation: this is intermediate validation evidence, not proof. Candidate-selection overfitting risk remains, and the result should not be read as “no overfitting.”
- Limitation: the run used a reduced candidate set and capped combinations, so it is not formal full validation.

- Executed script: `scripts/run_frozen_oos_validation.py`
- Command used: `python scripts/run_frozen_oos_validation.py`
- Output files: `results/tables/frozen_oos_validation.csv`, `results/tables/frozen_oos_validation_notes.csv`
- Validation type: formal in script terms, but the interpretation is pseudo-frozen if the 2025+ period was already inspected during development.
- Key metrics: test net annual return `0.10742083764605925`, test Sharpe `1.8084233975252448`, test max drawdown `-0.04273908753805111`, test total return `0.1438107163246971`, requested frozen start `2025-01-01`, actual test start `2025-01-02`
- Interpretation: frozen OOS is preliminary if the period was already inspected during development; it should not be treated as conclusive proof of untouched out-of-sample generalization.

### 中文

- 已执行脚本：`scripts/run_cscv_pbo.py`
- 使用命令：`python scripts/run_cscv_pbo.py --max-candidates 4 --num-blocks 6 --max-combinations 6`
- 输出文件：`results/tables/cscv_pbo_results.csv`、`results/tables/cscv_pbo_summary.csv`
- 验证类型：intermediate
- 关键汇总指标：PBO `0.3333333333333333`、median logit rank `0.6931471805599457`、mean relative rank `0.5833333333333334`、候选数 `4`、块数 `6`、分割数 `6`
- 解释：这是 intermediate validation evidence，不是证明。candidate-selection overfitting risk remains，不能据此声称 “no overfitting”。
- 限制：本次运行使用了缩减候选集和上限分割组合，因此不能视为 formal full validation。

- 已执行脚本：`scripts/run_frozen_oos_validation.py`
- 使用命令：`python scripts/run_frozen_oos_validation.py`
- 输出文件：`results/tables/frozen_oos_validation.csv`、`results/tables/frozen_oos_validation_notes.csv`
- 验证类型：脚本语义上为 formal，但如果 2025+ 区间在开发期间已被检查过，则应解释为 pseudo-frozen
- 关键指标：test net annual return `0.10742083764605925`、test Sharpe `1.8084233975252448`、test max drawdown `-0.04273908753805111`、test total return `0.1438107163246971`、requested frozen start `2025-01-01`、actual test start `2025-01-02`
- 解释：如果该冻结区间在开发过程中已被观察过，则 frozen OOS 只是 preliminary / pseudo-frozen evidence，不能当作已经完全未见的样本外证明。

## Implemented Validation Scripts

The validation roadmap now has reproducible scripts and CSV outputs. These scripts are an additive validation layer around the existing Convex Adaptive Global RRP stack; they do not replace the existing model code and should not be used to rewrite the public performance table without an explicit regeneration step.

| Script | Main output | Status | Limitation |
|---|---|---|---|
| `scripts/run_walkforward_validation.py` | `results/tables/walkforward_validation.csv`, `results/tables/walkforward_validation_summary.csv` | Implemented validation script | Test-window metrics are reported after validation-window selection and should not be recycled into candidate choice. |
| `scripts/run_nested_validation.py` | `results/tables/nested_validation.csv`, `results/tables/nested_validation_summary.csv` | Implemented validation script | Reports validation-to-test Sharpe and Calmar decay; it does not prove future generalization. |
| `scripts/run_cscv_pbo.py` | `results/tables/cscv_pbo_results.csv`, `results/tables/cscv_pbo_summary.csv` | Implemented diagnostic script | PBO is a diagnostic estimate of selection bias, not proof that a strategy will or will not generalize. |
| `scripts/run_frozen_oos_validation.py` | `results/tables/frozen_oos_validation.csv`, `results/tables/frozen_oos_validation_notes.csv` | Implemented reporting script | Default `2025-01-01` frozen start is pseudo-frozen if 2025+ data was already visible during earlier candidate development. |
| `scripts/run_parameter_sensitivity.py` | `results/tables/parameter_sensitivity.csv`, `results/tables/parameter_sensitivity_summary.csv` | Implemented diagnostic script | One-at-a-time perturbations test robustness around the selected candidate; they are not a new tuning pass. |

Preliminary outputs may be produced with `--smoke`, `--max-candidates`, or capped split counts. Such bounded runs are useful for reproducibility checks, but they should be labeled preliminary and should not be cited as final validation evidence.

## 后续验证路线

1. Walk-forward parameter selection：只在滚动训练 / 验证窗口中选择候选参数，并把入选规则应用到下一段未见测试窗口。
2. Nested train/validation/test：严格区分模型设计、参数选择和最终测试，避免同一样本同时用于筛选和最终结论。
3. CSCV/PBO diagnostic：使用组合对称交叉验证和 PBO 指标量化候选选择偏误。
4. Frozen OOS period：预先冻结最终样本外区间，并在候选选择规则固定后只运行一次。
5. Sensitivity tests：检查结论在权重滞后执行、交易成本压力、参数扰动、协方差估计器变化和样本窗口变化下是否稳定。
