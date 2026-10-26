# Reference Research

本文件记录开发过程中实际查阅的开源项目、许可证核验与自主开发边界。除非明确记录“使用代码”，IssueDoctor 仅学习公开架构、指标定义或交互原则，不复制实现。

检索与许可证核验日期：2026-09-25。

| 项目名 | URL | 版本/快照 | 许可证 | 参考模块 | 学习点 | 是否使用代码 | 具体文件/修改方式 |
|---|---|---|---|---|---|---|---|
| GitHub Community `issue-metrics` | https://github.com/github-community-projects/issue-metrics | `main`（2026-09-25 查阅） | MIT（仓库 `LICENSE`） | 指标与报告结构 | 首次响应、关闭耗时等指标应有独立计算与测试；报告保留逐项记录 | 否 | 无；IssueDoctor 的维护者身份规则、评分和数据模型均为本项目自研 |
| Pallets Flask | https://github.com/pallets/flask | `main`（2026-09-25 查阅） | BSD-3-Clause（`LICENSE.txt` / `pyproject.toml`） | Application Factory、包结构 | 使用工厂创建应用，扩展延迟绑定，便于测试配置隔离 | 否 | 无；使用 Flask 的公开 API 自主实现项目骨架 |
| VS Code GitHub Triage Actions | https://github.com/microsoft/vscode-github-triage-actions | 归档仓库，2026-09-25 查阅 | MIT（仓库许可证） | GitHub API 抽象与测试替身 | 将 GitHub 接口与命令逻辑分离，用 mock/testbed 避免测试触发真实写操作 | 否 | 无；后续以 Python/httpx 接口和 MockTransport 自研 |
| BAAI `bge-small-zh-v1.5` | https://huggingface.co/BAAI/bge-small-zh-v1.5 | `main`，模型页 2026-09-25 查阅 | MIT（模型卡 License） | 本地文本 Embedding | 24M 参数；`model.safetensors` 约 95.8 MB；Sentence Transformers 兼容；适合中文语义召回 | 否 | 不复制源码；运行时由 `sentence-transformers` 下载公开模型权重到用户本地缓存 |

## 合规结论

- 上述项目许可证均已在其 GitHub 仓库许可证文件或项目元数据中核验。
- 本阶段没有复制第三方源码、模板或资源，仅依据公开文档学习架构与测试边界。
- ECharts、Tailwind CSS、Flask、Sentence Transformers 与模型权重等运行/开发依赖的版本、许可证义务和分发方式将在 `docs/THIRD_PARTY_RESOURCES.md` 统一登记。
