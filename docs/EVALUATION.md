# 验证方案与结果

评测源数据、脚本和机器可读结果位于 `evaluation/`。运行：

```powershell
python -m evaluation.scripts.compute_metrics
python -m evaluation.scripts.run_simulation
python -m evaluation.scripts.run_real_cases
python -m evaluation.scripts.validate_results
```

## 真实仓库案例

固定 1 个月窗口、Issue/PR 上限各 30、评分配置 1.0、Embedding
`BAAI/bge-small-zh-v1.5`，LLM 关闭。2026-09-26 的只读快照结果如下；仓库状态会变化，完整
证据与配置以 `evaluation/results/real_cases/*.json` 为准。

| 仓库 | 规模 | 总分 | 置信度 | Issue / PR / 评论 | GitHub / LLM 调用 | 耗时 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| pallets/flask | 中型 | 46.95 | 100% | 5 / 14 / 21 | 4 / 0 | 15.957s |
| psf/requests | 中大型 | 42.00 | 100% | 12 / 3 / 45 | 4 / 0 | 9.965s |
| cli/cli | 大型 | 49.82 | 90% | 30 / 30 / 529 | 9 / 0 | 13.261s |

## 人工标注管线

仓库包含 24 条单标注者受控 fixture，用于验证五类标注任务和 Accuracy、Precision、Recall、
Macro-F1、Pair Precision/Recall 的计算管线。它不是实际模型性能主张，也不计算标注者一致性。

## 改进前后实验

> **离线模拟 / controlled simulation；不是该仓库真实部署后的线上结果。**

以 `pallets/flask` 为公开流程案例，对 12 个预设场景执行方案 B 离线回放。结构化表单在受控输入
中把字段完整率从 50.7% 提高到 100%，平均追问从 1.75 降为 0，分类正确率从 58.3% 变为
100%，同时平均预设填写时间增加 1.05 分钟。这些只是固定模拟规则的机械输出，不能外推为真实
用户实验或线上改善。
