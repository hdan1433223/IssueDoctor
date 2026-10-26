# 第三方资源清单

项目采用分层依赖：**核心层**为完整诊断所必需，**可选层**按需安装、缺失时自动降级，
**开发层**仅用于测试与评测脚本，不进入运行时。

| 资源名称 | 类型 | 版本 | 来源 | 许可证/授权类型 | 安装层级 | 项目中的用途 | 关键许可义务 | 是否修改 | 自主开发边界 | 合规状态 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Flask | Python 库 | 3.1.3 | PyPI / pallets/flask | BSD-3-Clause | 核心 | Web 框架 | 保留版权和许可声明 | 否 | 路由、业务服务与页面自主开发 | 合规 |
| Gunicorn | Python 服务 | 23.0.0 | PyPI | MIT | 核心 | Docker WSGI 服务 | 保留许可声明 | 否 | 仅用于容器进程托管 | 合规 |
| SQLAlchemy / Flask-SQLAlchemy | Python 库 | 2.0.43 / 3.1.1 | PyPI | MIT | 核心 | ORM | 保留许可声明 | 否 | 数据模型与仓储自主开发 | 合规 |
| Alembic / Flask-Migrate | Python 库 | 1.x / 4.1.0 | PyPI | MIT | 核心 | 数据迁移 | 保留许可声明 | 否 | 迁移版本自主生成 | 合规 |
| Pydantic | Python 库 | 2.11.9 | PyPI | MIT | 核心 | 边界数据校验 | 保留许可声明 | 否 | Schema 定义自主开发 | 合规 |
| httpx | Python 库 | 0.28.1 | PyPI | BSD-3-Clause | 核心 | GitHub HTTP | 保留版权和许可声明 | 否 | API 安全封装自主开发 | 合规 |
| keyring | Python 库 | 25.6.0 | PyPI | MIT | 核心 | 系统凭据库 | 保留许可声明 | 否 | SecretStore 适配自主开发 | 合规 |
| PyYAML | Python 库 | 6.0.3 | PyPI | MIT | 核心 | 评分与标签配置解析 | 保留许可声明 | 否 | 配置结构与评分规则自主设计 | 合规 |
| OpenAI Python SDK | Python 库 | 2.6.1 | PyPI | Apache-2.0 | 核心 | OpenAI-compatible 客户端 | 保留 NOTICE/许可证 | 否 | 批处理、缓存、Prompt 与校验自主开发 | 合规 |
| NumPy | Python 库 | 2.2.6 | PyPI | BSD-3-Clause | 可选（vector） | 稠密向量余弦相似度 | 保留版权和许可声明 | 否 | 相似度计算与缓存自主开发 | 合规 |
| sentence-transformers | Python 库 | 5.1.1 | PyPI | Apache-2.0 | 可选（vector） | 本地 Embedding 推理 | 保留 NOTICE/许可证，注明修改 | 否 | 模型管理与降级自主开发 | 合规 |
| PyTorch（CPU） | Python 库 | 随 vector 依赖解析 | PyPI / PyTorch CPU wheel index | BSD-3-Clause | 可选（vector，传递依赖） | 本地 Embedding 推理运行时 | 保留版权和许可声明 | 否 | 仅在启用 vector 时安装；Docker 使用 CPU wheel 避免引入 CUDA 运行时 | 合规 |
| BAAI/bge-small-zh-v1.5 | 模型权重 | 固定模型名 | Hugging Face | MIT | 可选（vector） | 中英文语义向量 | 保留许可声明 | 否 | 不训练或修改权重 | 合规 |
| Playwright | Python/浏览器工具 | 1.55.0 | PyPI / Microsoft | Apache-2.0 | 可选（pdf） | 正式 PDF 渲染 | 保留 NOTICE/许可证 | 否 | 报告模板自主开发 | 合规 |
| Apache ECharts | 前端库 | 6.1.0 | npm | Apache-2.0 | 前端构建产物（已提交） | 诊断图表 | 保留 NOTICE/许可证 | 否 | 图表配置和数据接口自主开发 | 合规 |
| Tailwind CSS | 前端构建库 | 3.4.17 | npm | MIT | 前端构建产物（已提交） | CSS 构建 | 保留许可声明 | 否 | 页面结构与视觉设计自主开发 | 合规 |
| scikit-learn | Python 库 | 1.7.1 | PyPI | BSD-3-Clause | 仅开发 / 评测 | `evaluation/` 标注指标计算 | 保留版权和许可声明 | 否 | 评测规则与标注流程自主开发 | 合规 |
| pandas | Python 库 | 2.3.2 | PyPI | BSD-3-Clause | 仅开发 / 评测 | 评测 CSV 汇总 | 保留版权和许可声明 | 否 | 评测规则自主开发 | 合规 |
| pypdf | Python 库 | 6.1.1 | PyPI | BSD-3-Clause | 仅开发 / 评测 | PDF QA 文本检查 | 保留许可声明 | 否 | 仅用于测试验证 | 合规 |
| pytest / coverage.py / Ruff | 开发工具 | 8.4.2 / 7.16.1 / 0.13.2 | PyPI | MIT / Apache-2.0 / MIT | 仅开发 | 测试、覆盖率和静态检查 | 保留对应许可声明 | 否 | 测试用例与质量门禁自主开发 | 合规 |
| GitHub REST API | 外部服务 | 2022-11-28 | GitHub | GitHub 服务条款 | 运行时外部服务 | 读取仓库与确认后写入 | 遵守 API 条款与速率限制 | 否 | 客户端、评分和治理逻辑自主开发 | 合规 |

## 运行时不依赖的说明

自研的重复问题检测后端（`issuedoctor/embedding/hashing_tfidf.py`，字符 n-gram 哈希 TF-IDF）
为**完全自主实现**，不依赖 NumPy 或 scikit-learn，因此核心安装不需要任何数值计算库。
NumPy 仅在启用 `vector` 可选能力（稠密模型向量）时用于余弦相似度。

项目对可选依赖的隔离由架构约束保证：任何 `issuedoctor` 模块都不得在模块顶层导入可选依赖，
该规则由 `tests/unit/test_capabilities.py` 中的静态检查用例强制执行。

本项目未复制参考仓库源码。架构调研与许可证核验另见 `docs/REFERENCE_RESEARCH.md`。依赖的完整
传递许可证以各发行包内元数据和上游仓库为准，发布二进制镜像时保留本清单与根目录 MIT License。
