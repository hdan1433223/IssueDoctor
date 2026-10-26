# 人工标注数据结构

`ground_truth.csv` 与 `predictions.csv` 以 `(task, item_id)` 唯一定位样本。

| 字段 | 说明 |
| --- | --- |
| task | `issue_type`、`bug_completeness`、`duplicate_pair`、`closure_reason` 或 `ai_evidence_consistency` |
| item_id | GitHub 对象或候选 Pair 的稳定标识 |
| label | Ground Truth 或系统预测标签 |
| annotator | 匿名标注者编号；系统预测中固定为 `system` |
| notes | 可选的证据说明，不放入指标计算 |

当前仓库附带的是一名开发期标注者完成的**受控标注流程验收集**，其 `fixture-*`
编号不冒充真实 GitHub 对象，也不能代表跨标注者一致性或总体模型性能。新增真实样本时
必须先记录对象 URL 并完成 Ground Truth，再单独生成预测文件，避免用预测反向修改标签。
