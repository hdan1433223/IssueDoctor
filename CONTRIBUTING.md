# 参与贡献

感谢你关注 IssueDoctor。提交改动前，请先花两分钟读完下面几条约定。

## 开发环境

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
export ISSUEDOCTOR_DATA_DIR="$(pwd)/data"
python -m flask --app wsgi db upgrade
```

## 提交前自检

```bash
python -m ruff check .
python -m pytest --cov=issuedoctor --cov-report=term-missing
```

CI 会在 Ubuntu 与 Windows 上跑 Python 3.10/3.11/3.12 三个版本，并额外校验：

- 整体覆盖率不低于 80%，评分引擎不低于 95%，GitHub 客户端与安全模块不低于 90%
- `npm run build` 之后 `issuedoctor/static` 不得有差异（前端产物必须与源码同步提交）
- `pip-audit`、`bandit` 与 `npm audit` 无高危问题

修改前端样式或图表时，请同时提交重新构建的产物：

```bash
npm ci
npm run build
```

## 代码约定

- 核心诊断链路（采集 → 六维评分 → 报告构建 → JSON/Markdown 导出 → Web 界面）
  **不得引入重型第三方依赖**；新能力请走 `issuedoctor.plugins` 的可选能力机制。
- 评分规则只能来自 `config/scoring.default.yml` 等版本化配置，不要在校验逻辑里硬编码阈值。
- 任何新的 GitHub 写操作必须有独立的确认步骤，且只能通过新分支 + PR 落地。
- 新增或修改指标时，请同步更新 `docs/SCORING.md` 与对应单元测试。

## 提交信息

使用一句话说明「改了什么、为什么」，例如：

```
fix(scoring): 修正关闭耗时的 N/A 权重计算
```

## 安全

- 不要在 Issue、PR、代码或截图中粘贴真实 Token、API Key、私有仓库内容。
- 发现安全问题时请通过仓库的安全策略私下联系维护者，不要公开提交可利用细节。
- 演示写操作请使用你自己的测试仓库，禁止对第三方案例仓库创建 PR、Label 或评论。

## 许可

提交即表示你同意将贡献以本项目的 [MIT License](LICENSE) 授权发布。
