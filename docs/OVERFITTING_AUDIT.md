# 模型选择与信息时序

Improved Convex Adaptive Global RRP 的周频配置是在查看历史约束实验后确定的。每次调仓只使用此前数据，但这一检查无法消除事后选择规格带来的偏差。

主模型冻结既有参数日历，取消现金与单资产集中度上限。当前发布使用零无风险利率，另列滞后中债利率的机会成本结果。正式模型共七个，约束和频率变化作为实验设置保留。

## 可核查证据

- `results/tables/primary_model_configuration.json` 记录实际参数。
- `results/tables/primary_publication_audit.json` 记录时序、约束与路径复现检查。
- `results/tables/convex_adaptive_solver_diagnostics.csv` 记录每次求解。
- `results/tables/afml_oos_selection.csv` 保存冻结参数日历。

历史候选评分及过拟合诊断仅供追溯，不能直接证明当前主模型有效。后续检验应冻结模型和评价口径，使用新增数据。
