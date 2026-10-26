# IssueDoctor

**面向公开 GitHub 仓库的 Issue 流程健康度审计与治理工具。**

[![CI](https://github.com/hdan1433223/IssueDoctor/actions/workflows/ci.yml/badge.svg)](https://github.com/hdan1433223/IssueDoctor/actions/workflows/ci.yml)
[![Security](https://github.com/hdan1433223/IssueDoctor/actions/workflows/security.yml/badge.svg)](https://github.com/hdan1433223/IssueDoctor/actions/workflows/security.yml)
[![Docker](https://github.com/hdan1433223/IssueDoctor/actions/workflows/docker.yml/badge.svg)](https://github.com/hdan1433223/IssueDoctor/actions/workflows/docker.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](pyproject.toml)

IssueDoctor 把 Issues、Pull Requests、评论和仓库治理文件转换为**可解释、可复现**的六维健康度指标，
并把诊断结论继续转化为**可预览、可人工确认**的治理方案。

核心诊断（采集、六维评分、报告导出、Web 界面）**不依赖任何重型第三方库**，基础安装约 30 MB
即可完整运行；本地语义向量与服务端 PDF 属于可选能力，按需启用，缺失时自动降级。

> 本项目以**本地单机**方式运行：Web 服务只监听 `127.0.0.1`，数据保存在本地 SQLite，
> 不会把你的仓库数据上传到任何第三方服务。

---

## 为什么不只用 GitHub Insights

GitHub Insights 擅长看数量与时间趋势。IssueDoctor 进一步检查：

- 首次维护者响应是否及时，长期积压集中在哪
- Bug 报告是否缺失复现步骤、环境、期望行为
- 标签体系是否真实参与分流，还是形同虚设
- Issue 是否形成到 PR 的可观测闭环
- 是否存在重复问题，知识是否沉淀进文档
- **每个主要结论都保留证据链接**，可点回真实 Issue/PR

## 六维健康度

| 维度 | 关注点 | 权重 |
| --- | --- | :--: |
| 响应效率 | 首次维护者响应、响应分布 | 20 |
| 处理与积压健康度 | 关闭节奏、长期未响应存量 | 20 |
| Issue 信息质量 | 复现信息完整度、模板字段覆盖 | 20 |
| 分类与标签治理 | 标签覆盖率、标签使用混乱度 | 15 |
| 协作闭环健康度 | Issue→PR→合并的可观测性 | 15 |
| 重复问题与知识沉淀 | 相似问题密度、文档沉淀 | 10 |

系统始终保留由版本化配置（`config/scoring.default.yml`）驱动、可复现的**规则基础分**。
配置 LLM 后，会在受控预算内增加语义信息质量、协作闭环、重复候选复核、建议动作和知识候选判断；
**只有 AI 请求成功率与置信度达标时**，才额外显示「规则 80% + AI 20%」的增强综合分。
没有 LLM Key 时，基础诊断仍可完整运行（BASIC 模式）。

## 主要能力

- **Web 诊断流程**：仓库预检 → 后台分析（实时阶段进度）→ 六维报告 → 证据抽屉 → 导出
- **治理包生成**：Issue Forms、CONTRIBUTING、Triage 流程、Label 计划，统一 Diff 逐文件预览
- **安全写操作**：只创建新分支 + Pull Request，绝不直接提交默认分支；删除 Label 需二次确认
- **报告知识助手**：审计完成后可就当前报告提问，答案强制引用报告页与 GitHub 来源
- **多种导出**：Web 报告页、浏览器打印 PDF、后端正式 PDF、Markdown、JSON（共享同一 ReportDTO）
- **CLI 与 Web 复用同一服务层**：便于批处理与 CI 集成
- **插件机制**：`vector` / `pdf` 即以插件形式实现，第三方可通过 entry point 扩展

## 快速开始

### 方式一：Windows 一键脚本（推荐给非开发者）

1. 安装 64 位 **Python 3.10+**（安装时勾选 `Add python.exe to PATH`）
2. 双击 `01_首次安装.bat` —— 自动创建 `.venv`、安装核心依赖、初始化数据库
3. 双击 `02_启动网站.bat` —— 自动选择可用端口并打开浏览器

### 方式二：手动安装（任意平台）

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

export ISSUEDOCTOR_DATA_DIR="$(pwd)/data"      # Windows: $env:ISSUEDOCTOR_DATA_DIR=(Join-Path $PWD "data")
python -m flask --app wsgi db upgrade
python app.py
```

访问 <http://127.0.0.1:5000>。默认只监听本机。

### 方式三：Docker

```bash
docker compose up --build
```

容器同样只映射到 `127.0.0.1:5000`，数据存入命名卷。

## 命令行用法

```bash
python -m issuedoctor.cli audit owner/repo --format markdown
python -m issuedoctor.cli audit owner/repo --format json --output report.json
python -m issuedoctor.cli audit owner/repo --format summary --issue-limit 200
python -m issuedoctor.cli audit owner/repo --no-ai
python -m issuedoctor.cli doctor        # 查看当前启用了哪些可选能力
```

## 配置与密钥

所有密钥都通过界面「设置」页或环境变量提供，**不写入 SQLite，也不会出现在报告和日志中**。

| 变量 | 作用 | 是否必需 |
| --- | --- | :--: |
| `ISSUEDOCTOR_SECRET_KEY` | Flask Session/CSRF 密钥 | 生产部署必需 |
| `ISSUEDOCTOR_DATA_DIR` | 数据目录（SQLite、报告、缓存） | 建议显式设置 |
| `ISSUEDOCTOR_GITHUB_TOKEN` | 提高 GitHub API 额度、执行写操作 | 可选 |
| `ISSUEDOCTOR_LLM_API_KEY` | OpenAI-compatible LLM 密钥 | 可选 |
| `ISSUEDOCTOR_LLM_BASE_URL` | LLM 接口地址 | 配置 LLM 时必填 |
| `ISSUEDOCTOR_LLM_MODEL` | 模型名称 | 配置 LLM 时必填 |

- 公开仓库的 BASIC 只读诊断**不需要** GitHub Token。
- Windows 本地运行使用 Windows Credential Manager（`keyring`）保存 Token 与 API Key。
- 复制 `.env.example` 为 `.env` 自行填写；`.env` 已被 `.gitignore` 排除，请勿提交。

> **安全提示**：不要对第三方案例仓库执行写操作。演示 PR / Label 变更请使用你自己的测试仓库。

## 可选能力

未启用的能力会自动降级，不影响核心诊断，也不会导致启动失败。

| 能力 | 作用 | 启用方式 | 未启用时的行为 |
| --- | --- | --- | --- |
| `vector` | 本地语义向量，提升重复问题检测精度 | `pip install "issuedoctor[vector]"` | 使用内置纯 Python 相似度，功能不缺失 |
| `pdf` | 服务端正式 PDF 导出 | `pip install "issuedoctor[pdf]"` + `playwright install chromium` | 使用网页报告页的浏览器打印导出 |

也可在 Web 「设置」页或 `GET /api/capabilities` 查看当前能力状态。

## 项目结构

```
issuedoctor/
├─ github/        GitHub REST 采集、限流与受控写操作
├─ scoring/       纯函数六维评分引擎（零重型依赖）
├─ services/      分析、评分、导出、治理、问答编排
├─ ai/            OpenAI-compatible 批处理、校验、缓存与 Prompt 防护
├─ embedding/     内置 n-gram 哈希 TF-IDF / 可选本地向量模型
├─ tasks/         进程内后台任务与阶段进度（不需要 Redis/Celery）
├─ models/ repositories/   SQLite 快照、缓存、Finding、治理包
├─ exports/       JSON / Markdown / 打印 HTML / 正式 PDF
├─ web/ templates/ static/  Flask 路由与 Jinja2 + Tailwind + ECharts 前端
└─ cli.py         命令行入口（与 Web 复用服务层）
config/           版本化评分与标签配置（确定性规则的唯一来源）
evaluation/       评测脚本、标注 fixture 与可复现结果
docs/             架构、API、评分、安全、评测与第三方资源说明
migrations/       Alembic 数据库迁移
tests/            单元测试与集成测试
```

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 分层、依赖策略、组件边界 |
| [docs/API.md](docs/API.md) | 本地 API 与错误码约定 |
| [docs/SCORING.md](docs/SCORING.md) | 指标定义、权重与置信度 |
| [docs/SECURITY.md](docs/SECURITY.md) | 凭据管理、写操作边界与威胁模型 |
| [docs/ASSISTANT.md](docs/ASSISTANT.md) | 报告知识助手设计 |
| [docs/MODEL_AND_PROMPTS.md](docs/MODEL_AND_PROMPTS.md) | 模型、Prompt 版本与输入约束 |
| [docs/EVALUATION.md](docs/EVALUATION.md) | 评测方案与真实仓库案例结果 |
| [docs/THIRD_PARTY_RESOURCES.md](docs/THIRD_PARTY_RESOURCES.md) | 第三方依赖、许可证与自主开发边界 |
| [docs/REFERENCE_RESEARCH.md](docs/REFERENCE_RESEARCH.md) | 参考项目与许可证核验记录 |
| [docs/AI_USAGE.md](docs/AI_USAGE.md) | 生成式 AI 在开发与运行时的使用说明 |

## 开发与测试

```bash
pip install -r requirements-dev.txt
python -m ruff check .
python -m pytest --cov=issuedoctor --cov-report=term-missing
```

前端构建产物（Tailwind CSS 与 ECharts）已提交到仓库，**普通用户不需要 Node.js**。
仅修改样式或图表时需要：

```bash
npm ci
npm run build
```

### 复现评测

```bash
python -m evaluation.scripts.compute_metrics
python -m evaluation.scripts.run_simulation
python -m evaluation.scripts.run_real_cases     # 会消耗 GitHub API 额度
python -m evaluation.scripts.validate_results
```

人工标注数据是受控管线 fixture，不是模型性能主张；离线模拟明确**不是**第三方仓库部署后的线上改善。
引用任何数字时请一并保留样本量、窗口、配置版本、执行日期与 BASIC/AI 模式。

## 可复现性说明

- 六维规则基础分来自版本化 YAML + 确定性规则，同一快照重跑结果一致。
- LLM 语义分与增强综合分单独标注，不覆盖规则分。
- 每次审计可选最多 200 条 Issue 进入 AI 分析，并受 120,000 字符 / 40 个逻辑批次的安全上限约束；
  相同内容、模型与 Prompt 版本复用本地缓存。
- 内置相似度为纯 Python 字符 n-gram 哈希 TF-IDF，无需额外依赖即可确定性复现；启用 `vector`
  后改用本地 Embedding 模型，首次自动下载并缓存。

## 安全边界

- 仅读取标准 `github.com` 公开仓库，不支持 GitHub Enterprise。
- 所有文件类改进只能通过新分支 + PR 提交；IssueDoctor 不会 push 到默认分支。
- Label 变更先预览再确认；删除 Label 需要高级危险操作二次确认。
- 报告知识助手只做只读问答，不执行任何 GitHub 写操作，也不读取或输出 Token/API Key。
- 修改类请求受 CSRF 保护；错误响应统一返回稳定 `code`，不泄露内部细节。

## 许可与致谢

本项目代码采用 [MIT License](LICENSE)。所依赖的第三方库、模型权重与前端产物的许可证义务见
[docs/THIRD_PARTY_RESOURCES.md](docs/THIRD_PARTY_RESOURCES.md)。

项目在开发过程中使用了生成式 AI 辅助（需求拆解、代码草拟、测试设计、文档结构、缺陷排查），
所有改动均经静态检查、测试与真实公开仓库只读案例复核，详见 [docs/AI_USAGE.md](docs/AI_USAGE.md)。

## 贡献

欢迎提交 Issue 与 Pull Request。开始之前请阅读 [CONTRIBUTING.md](CONTRIBUTING.md)；
提交前请确保 `ruff check .` 与 `pytest` 全部通过。
请勿在 Issue、PR 或截图中粘贴真实 Token、API Key 或私有仓库内容。

## 免责声明

IssueDoctor 输出的是**流程健康度的量化参考**，不是对仓库维护质量的最终判决，也不构成任何担保。
评分基于快照数据与公开规则，仓库状态变化后结果会随之变化。
