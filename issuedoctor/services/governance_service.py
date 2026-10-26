import difflib
from collections import Counter
from dataclasses import dataclass

import yaml
from pydantic import BaseModel, Field, ValidationError

from issuedoctor.errors import IssueDoctorError
from issuedoctor.extensions import db
from issuedoctor.models import AIAnalysis, AnalysisRun, Finding, GovernancePackage
from issuedoctor.security.governance_paths import validate_governance_path


class IssueFormBodyItem(BaseModel):
    type: str
    id: str | None = None
    attributes: dict = Field(default_factory=dict)
    validations: dict = Field(default_factory=dict)


class IssueForm(BaseModel):
    name: str
    description: str
    title: str = ""
    labels: list[str] = Field(default_factory=list)
    body: list[IssueFormBodyItem]


@dataclass(frozen=True)
class GovernanceFile:
    path: str
    content: str
    reason: str


class GovernanceService:
    def generate(self, run: AnalysisRun) -> GovernancePackage:
        findings = db.session.execute(
            db.select(Finding).where(Finding.analysis_run_id == run.id)
        ).scalars().all()
        ai_rows = db.session.execute(
            db.select(AIAnalysis).where(AIAnalysis.analysis_run_id == run.id)
        ).scalars().all()
        codes = {finding.metric_code for finding in findings}
        workflow_plan = self._ai_workflow_plan(ai_rows, run)
        if workflow_plan["action_counts"].get("request_more_information"):
            codes.add("AI_NEEDS_INFO")
        files = self._base_files(codes)
        validated = {file.path: self.validate_file(file.path, file.content) for file in files}
        label_plan = self._label_plan(codes)
        package = db.session.execute(
            db.select(GovernancePackage).where(GovernancePackage.analysis_run_id == run.id)
        ).scalar_one_or_none()
        payload = {
            path: {
                "content": content,
                "reason": next(item.reason for item in files if item.path == path),
                "original_content": "",
            }
            for path, content in validated.items()
        }
        if package is None:
            package = GovernancePackage(
                analysis_run_id=run.id,
                version="1.0",
                status="DRAFT",
                files_json=payload,
                labels_plan_json=label_plan,
                workflow_plan_json=workflow_plan,
            )
            db.session.add(package)
        else:
            package.files_json = payload
            package.labels_plan_json = label_plan
            package.workflow_plan_json = workflow_plan
            package.status = "DRAFT"
        db.session.commit()
        return package

    @staticmethod
    def validate_file(path: str, content: str) -> str:
        normalized = validate_governance_path(path)
        if "\x00" in content or len(content) > 100_000:
            raise IssueDoctorError("GOVERNANCE_CONTENT_INVALID", "治理文件内容无效")
        if normalized.endswith((".yml", ".yaml")):
            try:
                payload = yaml.safe_load(content)
                if normalized != ".github/ISSUE_TEMPLATE/config.yml":
                    IssueForm.model_validate(payload)
                elif not isinstance(payload, dict):
                    raise ValueError("config must be an object")
            except (yaml.YAMLError, ValidationError, ValueError) as exc:
                raise IssueDoctorError(
                    "GOVERNANCE_YAML_INVALID",
                    "Issue Form YAML 校验失败",
                ) from exc
        elif not content.strip().startswith("#"):
            raise IssueDoctorError("GOVERNANCE_MARKDOWN_INVALID", "治理 Markdown 必须包含标题")
        return content.replace("\r\n", "\n")

    @staticmethod
    def diff(package: GovernancePackage) -> dict[str, str]:
        result = {}
        for path, file_data in package.files_json.items():
            validate_governance_path(path)
            before = file_data.get("original_content", "").splitlines(keepends=True)
            after = file_data["content"].splitlines(keepends=True)
            result[path] = "".join(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                )
            )
        return result

    @staticmethod
    def _base_files(codes: set[str]) -> list[GovernanceFile]:
        files = [
            GovernanceFile(
                ".github/ISSUE_TEMPLATE/bug_report.yml",
                _bug_form(),
                "提升 Bug 关键信息完整度",
            ),
            GovernanceFile(
                ".github/ISSUE_TEMPLATE/feature_request.yml",
                _feature_form(),
                "统一功能请求结构与分类",
            ),
            GovernanceFile(
                ".github/ISSUE_TEMPLATE/config.yml",
                "blank_issues_enabled: false\ncontact_links: []\n",
                "引导用户选择结构化模板",
            ),
            GovernanceFile("CONTRIBUTING.md", _contributing(), "明确 Issue 提交规范"),
            GovernanceFile(".github/ISSUE_TRIAGE.md", _triage(), "建立响应与关闭闭环"),
        ]
        if codes & {"M6.1", "M6.2", "AI6.1"}:
            files.append(
                GovernanceFile("docs/ISSUE_GUIDE.md", _issue_guide(), "减少重复问题提交")
            )
        return files

    @staticmethod
    def _label_plan(codes: set[str]) -> list[dict]:
        base = [
            {
                "action": "create",
                "name": "type: bug",
                "color": "d73a4a",
                "description": "可复现的缺陷",
            },
            {
                "action": "create",
                "name": "type: feature",
                "color": "a2eeef",
                "description": "功能建议",
            },
            {
                "action": "create",
                "name": "needs-info",
                "color": "fbca04",
                "description": "等待提交者补充信息",
            },
        ]
        return (
            base
            if codes & {"M4.1", "M4.2", "M4.3", "M4.4", "AI_NEEDS_INFO"}
            else base[:2]
        )

    @staticmethod
    def _ai_workflow_plan(rows: list[AIAnalysis], run: AnalysisRun) -> dict:
        action_counts = Counter(
            row.recommended_action
            for row in rows
            if row.recommended_action and row.recommended_action != "none"
        )
        missing_counts = Counter(
            item for row in rows for item in (row.completeness_json or [])
        )
        lowest_quality = sorted(
            (
                {"issue_number": row.issue_number, "score": row.semantic_quality_score}
                for row in rows
                if row.semantic_quality_score is not None
            ),
            key=lambda item: item["score"],
        )[:10]
        issues = {issue.issue_number: issue for issue in run.issues}
        action_items = [
            {
                "issue_number": row.issue_number,
                "issue_title": (
                    issues[row.issue_number].title
                    if row.issue_number in issues
                    else f"Issue #{row.issue_number}"
                ),
                "issue_url": (
                    issues[row.issue_number].html_url
                    if row.issue_number in issues
                    else f"{run.repository.html_url}/issues/{row.issue_number}"
                ),
                "action": row.recommended_action,
                "summary": row.summary,
                "reason": row.explanation,
                "missing_information": row.completeness_json or [],
                "confidence": row.semantic_confidence,
            }
            for row in rows
            if row.recommended_action and row.recommended_action != "none"
        ][:50]
        return {
            "requires_preview": True,
            "requires_confirmation": True,
            "source": "RULE_AND_AI" if rows else "RULE_ONLY",
            "action_counts": dict(action_counts),
            "missing_information_counts": dict(missing_counts.most_common(10)),
            "knowledge_candidate_count": sum(row.knowledge_candidate for row in rows),
            "lowest_quality_issues": lowest_quality,
            "action_items": action_items,
        }


def _bug_form() -> str:
    return """name: Bug report
description: 报告可复现的软件缺陷
title: "[Bug] "
labels: ["type: bug"]
body:
  - type: markdown
    attributes:
      value: "提交前请搜索现有 Issue，避免重复报告。"
  - type: input
    id: version
    attributes: {label: 版本, description: 请填写软件版本}
    validations: {required: true}
  - type: input
    id: environment
    attributes: {label: 运行环境, description: 操作系统和相关环境}
    validations: {required: true}
  - type: textarea
    id: reproduction
    attributes: {label: 复现步骤}
    validations: {required: true}
  - type: textarea
    id: expected
    attributes: {label: 预期结果}
    validations: {required: true}
  - type: textarea
    id: actual
    attributes: {label: 实际结果}
    validations: {required: true}
  - type: textarea
    id: logs
    attributes: {label: 日志或错误信息, render: shell}
    validations: {required: false}
"""


def _feature_form() -> str:
    return """name: Feature request
description: 提议可验证的新功能或改进
title: "[Feature] "
labels: ["type: feature"]
body:
  - type: textarea
    id: problem
    attributes: {label: 要解决的问题}
    validations: {required: true}
  - type: textarea
    id: proposal
    attributes: {label: 建议方案}
    validations: {required: true}
  - type: textarea
    id: alternatives
    attributes: {label: 考虑过的替代方案}
    validations: {required: false}
"""


def _contributing() -> str:
    return """# Contributing

## 提交 Issue

提交前请搜索现有 Issue，并选择与问题类型匹配的表单。
Bug 报告应包含版本、环境、复现步骤、预期结果、实际结果和必要日志。
请勿提交密钥、访问令牌或其他敏感数据。

维护者可能添加 `needs-info` 标签请求补充信息；信息补齐后请留言说明。
"""


def _triage() -> str:
    return """# Issue Triage

1. 确认类型、复现信息和安全影响。
2. 在首次响应中说明下一步，并为缺失信息添加 `needs-info`。
3. 关联解决 PR；关闭时说明 fixed、duplicate、invalid、wontfix 或 stale 原因。
4. 删除 Label 或批量修改前必须人工复核影响范围。
"""


def _issue_guide() -> str:
    return """# Issue Guide

提交前请用错误信息、组件名和关键症状搜索现有 Issues。
若找到相似问题，请补充可复现信息而不是重复创建；安全问题不要在公开 Issue 中披露。
"""
