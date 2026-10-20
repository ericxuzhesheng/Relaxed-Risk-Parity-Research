# 模型选择与信息时序

Global RRP 与四个对照共同构成五模型发布结果。主模型每年根据生效日前数据更新惩罚系数，年内不再改变。

每次年度更新使用两个连续的252日历史区间。较早区间生成候选尺度，随后区间按扣费净夏普验证九组组合。选择先保留一倍标准误范围内的候选，再检查相邻网格点，随后比较换手和季度稳定性。

十个年度中，每年九组候选都进入一倍标准误集合。现有样本无法精确区分参数，年度选择主要由换手和稳定性规则决定。该结果已写入发布审计，论文和答辩不得将系数称作唯一最优值。

## 当前模型诊断

目标项消融、首年参数冻结、事前风险匹配和实施敏感性共同解释当前指定模型。风险匹配以共同历史样本协方差衡量双方风险，并记录Ledoit–Wolf估计下的可行性。配对区块抽样使用5、21和63日区块、每组2000次重抽样；区间属于固定历史规格下的逐项百分位区间。当前实验用于机制分析，不据结果选择新的主模型。

## 可核查证据

- `results/primary_diagnostics/protocol.json` 记录诊断设定及抽样种子。
- `results/tables/primary_diagnostics_audit.json` 记录路径、计费及风险匹配核验。
- `results/tables/primary_paired_bootstrap.csv` 记录配对差异与区间。

- `results/tables/primary_model_configuration.json` 记录完整配置和校准规则。
- `results/tables/primary_parameter_schedule.csv` 记录年度参数及信息截止日。
- `results/tables/primary_calibration_candidates.csv` 记录全部九十次验证结果。
- `results/tables/primary_publication_audit.json` 记录时序与约束检查。
- `results/tables/global_rrp_solver_diagnostics.csv` 记录每次求解。

逐期输入早于调仓日，可以排除直接使用未来收益。研究者仍根据历史结果确定了当前方法，因此现有结果属于探索性证据。后续检验应冻结模型和评价口径，等待新增数据。
