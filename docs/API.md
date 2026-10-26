# 本地 API

所有接口默认绑定 `127.0.0.1:5000`，修改类请求受 CSRF 保护。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/healthz` | 健康检查 |
| GET | `/api/capabilities` | 可选能力与插件状态（含启用方式） |
| POST | `/api/preflight` | 仓库 URL、权限、额度与预计规模预检 |
| POST | `/api/analyses` | 创建后台分析任务 |
| GET | `/api/analyses/<id>/status` | 查看阶段进度和错误 |
| GET | `/api/analyses/<id>/report` | 读取结构化诊断数据 |
| POST | `/api/analyses/<id>/assistant/query` | 基于当前报告知识库回答问题 |
| POST | `/api/analyses/<id>/governance/generate` | 生成治理包草稿 |
| GET | `/api/governance/<id>/diff` | 查看统一 Diff |
| POST | `/api/governance/<id>/create-pr` | 确认后创建新分支与 PR |
| POST | `/api/governance/<id>/labels/apply` | 确认后创建/更新 Label |
| DELETE | `/api/governance/<id>/labels/<name>` | 双重确认后删除 Label |
| GET | `/api/analyses/<id>/export/{json,markdown,pdf}` | 导出统一报告 |

错误统一返回稳定 `code` 与中文 `message`。接口不会返回 Token/API Key。

## 报告知识助手

审计进入 `SUCCEEDED` 或 `PARTIAL` 后，可以调用：

```http
POST /api/analyses/<id>/assistant/query
Content-Type: application/json
X-CSRFToken: <token>

{
  "question": "为什么 D5 协作闭环分数低？",
  "history": [
    {"role": "user", "content": "先总结这份报告"},
    {"role": "assistant", "content": "..."}
  ]
}
```

问题长度限制为 2–2000 个字符，历史最多使用最近 6 条。知识检索严格限定当前 `analysis_run_id`。
返回内容包含 `answer`、`key_points`、`limitations`、`sources`、`mode` 和 `scope`。其中 `mode`
为 `enhanced`（LLM 综合回答）或 `extractive`（无 LLM Key 时返回引用片段）。来源包含本地报告页
和可选的 GitHub 原始链接。

## 可选能力与降级

`/api/capabilities` 返回当前安装启用了哪些可选能力：

```json
{
  "ok": true,
  "core": { "label": "核心诊断", "available": true },
  "capabilities": [
    { "name": "vector", "label": "本地语义向量", "available": false,
      "missing": ["sentence_transformers"], "install_hint": "pip install \"issuedoctor[vector]\"" }
  ],
  "plugins": []
}
```

当可选能力未启用时，相关接口以稳定错误码降级，而不是抛出未捕获异常：

| 能力 | 未启用时的错误码 | 替代方案 |
| --- | --- | --- |
| `pdf` | `PDF_CAPABILITY_MISSING`（HTTP 503） | 使用 `/analysis/<id>/report` 浏览器打印导出 |

重复问题检测没有错误码：未启用 `vector` 时自动使用内置纯 Python 相似度，
结果照常返回，仅在运行时信息中标注 `embedding_mode`。
