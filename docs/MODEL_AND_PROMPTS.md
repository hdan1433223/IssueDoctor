# 模型、Prompt 与降级

## 相似 Issue 候选

重复问题检测有两种后端，按可选能力自动选择：

- **内置后端（默认，无需任何第三方依赖）**：`issuedoctor/embedding/hashing_tfidf.py`，
  自研字符 n-gram 哈希 TF-IDF，4096 维，L2 归一化。纯 Python 实现，结果确定性可复现。
- **本地语义模型（可选能力 `vector`）**：`BAAI/bge-small-zh-v1.5`，许可证为 MIT。启用后由
  sentence-transformers 下载到应用数据目录，之后复用模型和按文本哈希缓存的向量。

两种后端的相似度分数尺度不同，因此各自使用独立的候选阈值（`candidate_threshold` 与
`candidate_threshold_hashing`），由后端自动选择。报告会明确记录 `embedding_mode`
（`embedding` 或 `hashing`）。

模型下载或加载失败时自动回退到内置后端，不影响分析完成，仅在运行结果中标记告警。

## LLM 语义增强

LLM 使用 OpenAI-compatible 接口，只分析规则筛选出的低信息或 Bug 候选，按最多 8 条、总计
14,000 字符分批；单次审计的安全上限为 200 条 Issue、120,000 字符、40 个逻辑批次。系统
Prompt 与用户模板位于 `issuedoctor/ai/prompts/`，当前版本 `issue-batch-v2`。输入中的 Issue
内容被明确包裹为不可信数据，输出必须通过 Pydantic Schema；单批失败只降低 AI 覆盖率，不影响
确定性报告。

AI 解释不能直接触发 GitHub 写操作。治理写入仍需本地确定性校验、可视化 Diff 和人工确认。
