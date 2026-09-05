# 模型选择与信息时序

Global RRP 与四个对照共同构成五模型发布结果。主模型每年根据生效日前数据更新惩罚系数，年内不再改变。

每次年度更新使用两个连续的252日历史区间。较早区间生成候选尺度，随后区间按扣费净夏普验证九组组合。选择先保留一倍标准误范围内的候选，再检查相邻网格点，随后比较换手和季度稳定性。

十个年度中，每年九组候选都进入一倍标准误集合。现有样本无法精确区分参数，年度选择主要由换手和稳定性规则决定。该结果已写入发布审计，论文和答辩不得将系数称作唯一最优值。

## 可核查证据

- `results/tables/primary_model_configuration.json` 记录完整配置和校准规则。
- `results/tables/primary_parameter_schedule.csv` 记录年度参数及信息截止日。
- `results/tables/primary_calibration_candidates.csv` 记录全部九十次验证结果。
- `results/tables/primary_publication_audit.json` 记录时序与约束检查。
- `results/tables/global_rrp_solver_diagnostics.csv` 记录每次求解。

逐期输入早于调仓日，可以排除直接使用未来收益。研究者仍根据历史结果确定了当前方法，因此现有结果属于探索性证据。后续检验应冻结模型和评价口径，等待新增数据。
