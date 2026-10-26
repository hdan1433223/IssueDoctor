# 安全模型

## 凭据

Windows 本地模式把 GitHub Token 与 LLM API Key 保存在系统 Credential Manager；SQLite 只保存
非敏感配置。Docker 使用环境变量，UI 新输入仅保留在进程内。日志、Prompt、导出和审计载荷均
经过脱敏，任何页面或 API 都不回显密钥。

## 输入与网络

- 仓库只接受规范的 `https://github.com/<owner>/<repo>`，拒绝凭据、端口、片段和非 GitHub 主机。
- GitHub API 翻页只跟随 `https://api.github.com`，防止 SSRF 和令牌外泄。
- Issue 正文按不可信纯文本处理，模板启用自动转义，不渲染任意 HTML。
- HTTP 请求有超时；GitHub 错误不无限重试，LLM 最多额外重试两次。

## 写操作

治理文件路径使用白名单并拒绝路径穿越。创建治理 PR 前会重新读取默认分支与远端文件；所有
文件提交到新分支。Label 创建/更新需明确确认，删除需对象名确认和危险操作二次确认。每次写
操作都生成脱敏审计记录。

报告安全问题时请不要在公开 Issue 中包含真实 Token、个人数据或未公开漏洞细节。
