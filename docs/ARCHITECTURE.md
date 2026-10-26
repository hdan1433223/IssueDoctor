# IssueDoctor 架构

IssueDoctor 是单机优先的 Flask 应用。浏览器只与本地 Web 服务交互；服务通过 GitHub REST API
读取公开仓库数据，将快照保存到 SQLite，再由确定性评分引擎生成六维分数。LLM 是可关闭的批量增强层。

## 分层与依赖策略

架构遵循一条硬性约束：**核心诊断链路不得依赖任何第三方重型库**。
核心链路 = 采集 → 六维规则评分 → 报告构建 → JSON/Markdown 导出 → Web 界面。
它只依赖 Flask、SQLAlchemy、httpx、pydantic、PyYAML、openai，安装体积约 30 MB。

重型能力（本地向量模型、服务端 PDF）被隔离为**可选能力 + 插件**，按需启用。

```
┌──────────────────────────────────────────────┐
│ Web 界面 / CLI（两种入口，复用同一服务层）      │
├──────────────────────────────────────────────┤
│ services/  编排：分析、评分、导出、治理、问答    │
├──────────────────────────────────────────────┤
│ scoring/   纯函数六维引擎（零外部依赖）  ← 核心 │
│ github/    REST 采集与受控写操作        ← 核心 │
│ exports/   JSON / Markdown / 打印 HTML  ← 核心 │
├──────────────────────────────────────────────┤
│ capabilities.py + plugins.py  可选能力解析     │
├──────────────────────────────────────────────┤
│ embedding/ 向量：内置纯 Python 或可选模型       │
│ pdf        服务端渲染：可选 Playwright          │
└──────────────────────────────────────────────┘
```

## 组件边界

- `issuedoctor/capabilities.py`：可选能力探测。用 `find_spec` 判断依赖是否存在，不触发导入，
  因而探测本身不会加载 PyTorch。返回缺失依赖与启用方式。
- `issuedoctor/plugins.py`：插件发现。内置插件显式注册，第三方插件通过
  `issuedoctor.plugins` entry point 组注册。依赖缺失的插件被标记为不可用而非导致启动失败。
- `issuedoctor/cli.py`：命令行入口，支持 `audit` 与 `doctor`，与 Web 复用同一服务层。
- `issuedoctor/github/`：严格 GitHub URL、分页、限流、只读采集与经确认的写操作。
- `issuedoctor/tasks/`：进程内单工作线程、阶段进度、异常恢复；不依赖 Redis/Celery。
- `issuedoctor/models/` 与 `repositories/`：SQLite 快照、缓存、Finding、治理包和审计事件。
- `issuedoctor/scoring/`：20 个版本化确定性指标、N/A 动态权重和置信度。
- `issuedoctor/embedding/`：两种后端。内置 `hashing_tfidf` 为纯 Python 实现，无第三方依赖；
  `model_manager` 在 `vector` 能力可用时才导入 `sentence-transformers`。
- `issuedoctor/ai/`：OpenAI-compatible 批处理、Pydantic 校验、Prompt 注入防护和限额重试。
- `issuedoctor/services/governance_service.py`：生成 Issue Forms、贡献指南、Triage 与 Label 计划。
- `issuedoctor/rag/`：把一次审计转换为带来源元数据的知识块，并提供轻量混合检索。
- `issuedoctor/services/assistant_service.py`：按 `analysis_run_id` 隔离知识库、组织检索上下文，
  并在 LLM 不可用时降级为引用式回答。
- `issuedoctor/exports/`：统一 ReportDTO 驱动 JSON、Markdown、打印页和可选 Playwright PDF。

写路径始终是“生成预览 → 用户确认 → 新分支 → Pull Request”。默认分支不会被直接修改，
Label 删除另需危险操作二次确认。

## 可选依赖的隔离规则

1. `issuedoctor` 中任何模块**不得在模块顶层**导入 numpy、sklearn、sentence-transformers、playwright。
   导入必须位于函数内部，并由 `capabilities.is_available()` 守卫。
2. 缺失能力必须**降级而非抛异常**。降级原因写入分析结果的运行时字段，让用户可见。
3. 每个能力提供 `install_hint`，UI 据此告知用户启用方式。

## 内置向量后端的算法

`embedding/hashing_tfidf.py` 实现字符 n-gram 哈希 TF-IDF：

1. 文本小写归一化后切分为 2–5 字符 n-gram（对中文友好，不依赖分词）。
2. n-gram 用 `blake2b` 哈希到固定 4096 维（哈希技巧，无需存储词表，跨进程可复现）。
3. 次线性词频抑制高频 n-gram。
4. 按文档频次加权。
5. L2 归一化，使余弦相似度即为点积。

全流程纯 Python，无 numpy、无 sklearn。对目标规模（≤1000 Issues）性能充足，
且结果确定性可复现 —— 这点很重要，因为重复检测会进入计分指标。

## 报告知识助手

报告完成或部分完成后，分析任务会把结构化结果写入 `assistant_knowledge_chunks`。知识块覆盖
报告总览、六维与二级指标、Findings、Issue、AI 分析、证据、重复候选和治理包；固定产品知识
同时提供指标定义和评分解释。

检索前总是验证 `analysis_run_id`，不进行跨仓库或跨报告混合。默认后端使用字符 2-gram/3-gram
哈希特征、指标编号精确加权、内容类型加权和报告总览保底，不需要新增服务。配置
OpenAI-compatible LLM 时，检索结果作为不可信引用资料传入，输出经 Pydantic 校验并以结构化
JSON 返回；LLM 不可用时返回可点击的检索片段，不影响报告阅读。
