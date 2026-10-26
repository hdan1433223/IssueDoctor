# IssueDoctor 评测

本目录覆盖真实公开仓库案例、单标注者开发期人工标注集与改进前后离线回放。所有汇总指标均由脚本生成，禁止手工修改 `evaluation/results/` 中的数字。

## 一键复现

```powershell
python -m evaluation.scripts.compute_metrics
python -m evaluation.scripts.run_simulation
python -m evaluation.scripts.run_real_cases
python -m evaluation.scripts.validate_results
```

真实案例使用 GitHub REST API。匿名额度不足时，先在环境变量 `ISSUEDOCTOR_GITHUB_TOKEN` 中配置只读 Token；脚本不会导出该值。LLM 默认关闭，因此结果属于 BASIC 模式。每次运行会重建 `evaluation/.runtime/evaluation.db` 的表，但不会修改任何第三方仓库。

## 数据边界

- `cases.yml` 固定仓库、窗口、数量上限、评分版本、Embedding 与 LLM 配置。
- `annotations/` 保存 Ground Truth、预测、字段说明和标注规则。当前内容是受控流程验收
  fixture，仅验证标注与指标管线，不作为真实模型性能主张；当前只有一名开发期标注者，
  因此不计算标注者一致性。
- `simulation/scenarios.csv` 是受控输入；结果必须始终声明“离线模拟 / controlled simulation；不是该仓库真实部署后的线上结果”。
- `results/real_cases/*.json` 包含六维分数、Findings、证据、治理建议、运行耗时和 API/AI 调用数。

真实仓库内容会随时间变化。脚本、参数和计算过程可重复，已提交的结果则是清单所示日期的审计快照，不应被解释为仓库的永久状态。
