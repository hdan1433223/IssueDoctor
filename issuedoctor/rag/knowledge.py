from __future__ import annotations

import hashlib
from collections import defaultdict

from issuedoctor.extensions import db
from issuedoctor.guidance import AI_ACTION_NAMES, DIMENSIONS, METRICS, WORKFLOW_STEPS
from issuedoctor.models import (
    AIAnalysis,
    AnalysisRun,
    DimensionScore,
    DuplicateCandidate,
    EvidenceItem,
    Finding,
    GovernancePackage,
    MetricResult,
)
from issuedoctor.models.assistant import AssistantKnowledgeChunk

INDEX_VERSION = "1.2"
MAX_CHUNK_CONTENT = 3_800


class AssistantKnowledgeBuilder:
    """Convert one completed audit run into traceable retrieval chunks."""

    def build(self, run: AnalysisRun) -> list[AssistantKnowledgeChunk]:
        chunks = [self._overview(run)]
        chunks.extend(self._guide_chunks())
        chunks.extend(self._report_chunks(run))
        chunks.extend(self._issue_chunks(run))
        chunks.extend(self._ai_chunks(run))
        chunks.extend(self._evidence_chunks(run))
        chunks.extend(self._duplicate_chunks(run))
        governance = self._governance_chunk(run)
        if governance is not None:
            chunks.append(governance)
        return chunks

    @staticmethod
    def _overview(run: AnalysisRun) -> AssistantKnowledgeChunk:
        runtime = (run.analysis_config_json or {}).get("runtime", {})
        content = "\n".join(
            [
                f"仓库：{run.repository.full_name}",
                f"审计状态：{run.status}",
                f"分析模式：{run.mode}",
                f"分析时间：{run.created_at.isoformat()}",
                f"观察窗口：{run.window_start.isoformat()} 至 {run.window_end.isoformat()}",
                f"采集数量：Issue {run.issue_count}，PR {run.pr_count}，评论 {run.comment_count}",
                (
                    f"规则基础健康度：{run.total_score:.2f}"
                    if run.total_score is not None
                    else "规则基础健康度：数据不足"
                ),
                f"数据置信度：{(run.confidence_score or 0):.2f}",
                f"AI 覆盖率：{(run.ai_coverage_percent or 0):.2f}%",
                (
                    f"增强综合分：{run.enhanced_total_score:.2f}"
                    if run.enhanced_total_score is not None
                    else "增强综合分：未生成"
                ),
                f"数据截断：{'是' if run.is_truncated else '否'}",
                (
                    "数据限制：本次 AI 语义覆盖率不足或部分批次失败，回答时必须说明这一限制。"
                    if run.mode == "AI_ENHANCED"
                    and (run.ai_coverage_percent or 0) < 80
                    else "数据限制：报告仅代表已采集窗口与样本，不能推断窗口外状态。"
                ),
                (
                    f"运行时降级信息：{runtime}"
                    if runtime
                    else "运行时降级信息：无"
                ),
            ]
        )
        return _chunk(
            run,
            source_type="overview",
            source_key="overview",
            title=f"{run.repository.full_name} 诊断总览",
            content=content,
            metadata={"page_url": f"/analysis/{run.id}", "codes": []},
            rank_boost=0.34,
        )

    @staticmethod
    def _guide_chunks() -> list[AssistantKnowledgeChunk]:
        chunks: list[AssistantKnowledgeChunk] = []
        for code, dimension in DIMENSIONS.items():
            content = (
                f"{code} {dimension['name']}：{dimension['summary']} "
                f"这个维度回答的问题是：{dimension['question']}"
            )
            chunks.append(
                _static_chunk(
                    source_type="guide",
                    source_key=f"guide-dimension-{code}",
                    title=f"{code} {dimension['name']} 维度说明",
                    content=content,
                    metadata={
                        "page_url": f"/guide#dimension-{code}",
                        "codes": [code],
                    },
                )
            )
        for code, metric in METRICS.items():
            dimension_code = code[1] if code.startswith("M") else code[2]
            content = (
                f"{code} {metric['name']}：{metric['meaning']} "
                f"该指标{metric['better']}。"
            )
            chunks.append(
                _static_chunk(
                    source_type="guide",
                    source_key=f"guide-metric-{code}",
                    title=f"{code} {metric['name']} 指标说明",
                    content=content,
                    metadata={
                        "page_url": f"/guide#dimension-D{dimension_code}",
                        "codes": [code, f"D{dimension_code}"],
                    },
                )
            )
        workflow = "；".join(
            f"{item['number']}. {item['name']}：{item['summary']}"
            for item in WORKFLOW_STEPS
        )
        chunks.append(
            _static_chunk(
                source_type="guide",
                source_key="guide-workflow",
                title="IssueDoctor 使用流程",
                content=workflow,
                metadata={"page_url": "/guide#workflow", "codes": []},
            )
        )
        return chunks

    @staticmethod
    def _report_chunks(run: AnalysisRun) -> list[AssistantKnowledgeChunk]:
        chunks: list[AssistantKnowledgeChunk] = []
        metrics = db.session.execute(
            db.select(MetricResult).where(MetricResult.analysis_run_id == run.id)
        ).scalars().all()
        findings = db.session.execute(
            db.select(Finding).where(Finding.analysis_run_id == run.id)
        ).scalars().all()
        evidence_rows = db.session.execute(
            db.select(EvidenceItem).where(EvidenceItem.analysis_run_id == run.id)
        ).scalars().all()
        evidence_issues = {
            item.id: item.issue_number
            for item in evidence_rows
            if item.issue_number is not None
        }
        metric_groups: dict[str, list[MetricResult]] = defaultdict(list)
        for metric in metrics:
            metric_groups[metric.dimension_code].append(metric)
        finding_groups: dict[str, list[Finding]] = defaultdict(list)
        for finding in findings:
            finding_groups[finding.dimension_code].append(finding)
        issue_titles = {issue.issue_number: issue.title for issue in run.issues}

        for dimension_code, dimension in DIMENSIONS.items():
            dimension_score = db.session.execute(
                db.select(DimensionScore).where(
                    DimensionScore.analysis_run_id == run.id,
                    DimensionScore.dimension_code == dimension_code,
                )
            ).scalar_one_or_none()
            score_value = (
                dimension_score.score_0_100 if dimension_score is not None else None
            )
            confidence_value = (
                dimension_score.confidence if dimension_score is not None else None
            )
            lines = [
                f"{dimension_code} {dimension['name']}",
                f"维度得分：{_format_score(score_value)}",
                f"维度置信度：{_format_score(confidence_value)}",
                f"维度含义：{dimension['summary']}",
            ]
            for metric in sorted(
                metric_groups[dimension_code], key=lambda item: item.metric_code
            ):
                metric_help = METRICS.get(metric.metric_code, {})
                lines.append(
                    f"{metric.metric_code} {metric_help.get('name', metric.metric_code)}："
                    f"原始值 {_format_number(metric.raw_value)} {metric.unit}，"
                    f"得分 {_format_score(metric.normalized_score)}，"
                    f"样本 {metric.sample_size}，"
                    f"{'适用' if metric.applicable else '数据不足'}。"
                    f"{metric_help.get('meaning', '')}"
                )
            related = sorted(
                finding_groups[dimension_code],
                key=lambda item: item.priority_score,
                reverse=True,
            )
            if related:
                lines.append("相关 Findings：")
                lines.extend(
                    f"- {item.priority_level} {item.title}：{item.summary}"
                    for item in related
                )
            chunks.append(
                _chunk(
                    run,
                    source_type="dimension",
                    source_key=f"dimension-{dimension_code}",
                    title=(
                        f"{dimension_code} {dimension['name']} "
                        f"{_format_score(score_value)} 分"
                    ),
                    content="\n".join(lines),
                    metadata={
                        "page_url": f"/analysis/{run.id}/dimension/{dimension_code}",
                        "codes": [dimension_code],
                        "dimension_code": dimension_code,
                    },
                    rank_boost=0.08,
                )
            )

        for finding in sorted(findings, key=lambda item: item.priority_score, reverse=True):
            metric_help = METRICS.get(finding.metric_code, {})
            dimension_name = DIMENSIONS.get(finding.dimension_code, {}).get("name", "")
            linked_issues = sorted(
                {
                    evidence_issues[value]
                    for value in (finding.evidence_ids_json or [])
                    if value in evidence_issues
                }
            )
            linked_issue_labels = "、".join(
                f"#{value} {_clip(issue_titles.get(value, ''), 80)}".strip()
                for value in linked_issues
            )
            content = "\n".join(
                [
                    f"问题：{finding.title}",
                    f"优先级：{finding.priority_level}，优先级分数 {finding.priority_score:.2f}",
                    f"维度：{finding.dimension_code} {dimension_name}",
                    f"指标：{finding.metric_code} {metric_help.get('name', '')}",
                    f"摘要：{finding.summary}",
                    f"影响：{finding.impact_text}",
                    f"建议：{finding.recommendation}",
                    f"受影响样本：{finding.affected_count}/{finding.sample_size}",
                    f"来源：{'AI 语义分析' if finding.source_type == 'AI' else '确定性规则'}",
                    (
                        "相关 Issue："
                        + linked_issue_labels
                        if linked_issues
                        else "相关 Issue：报告中未绑定具体 Issue 编号"
                    ),
                ]
            )
            chunks.append(
                _chunk(
                    run,
                    source_type="finding",
                    source_key=f"finding-{finding.id}",
                    title=f"{finding.priority_level} {finding.title}",
                    content=content,
                    metadata={
                        "page_url": f"/analysis/{run.id}/findings",
                        "codes": [finding.dimension_code, finding.metric_code],
                        "source_type": finding.source_type,
                        "priority": finding.priority_level,
                    },
                    rank_boost=0.1,
                )
            )
        return chunks

    @staticmethod
    def _issue_chunks(run: AnalysisRun) -> list[AssistantKnowledgeChunk]:
        chunks = []
        for issue in sorted(run.issues, key=lambda item: item.issue_number):
            labels = [
                item.get("name", "") if isinstance(item, dict) else str(item)
                for item in (issue.labels_json or [])
            ]
            linked_prs = (
                ", ".join(f"#{value}" for value in issue.linked_pr_numbers_json)
                if issue.linked_pr_numbers_json
                else "无"
            )
            content = "\n".join(
                [
                    f"Issue #{issue.issue_number}：{issue.title}",
                    f"状态：{issue.state}；作者：{issue.author_login}",
                    f"标签：{', '.join(labels) if labels else '无'}",
                    f"评论数：{issue.comments_count}",
                    f"首次维护者响应：{_format_response_hours(issue.first_maintainer_response_hours)}",
                    f"关联 PR：{linked_prs}",
                    f"GitHub：{issue.html_url}",
                    "正文摘要：",
                    _clip(issue.body_excerpt or "无正文", 1_200),
                ]
            )
            chunks.append(
                _chunk(
                    run,
                    source_type="issue",
                    source_key=f"issue-{issue.issue_number}",
                    title=f"Issue #{issue.issue_number} {issue.title}",
                    content=content,
                    metadata={
                        "page_url": f"/analysis/{run.id}/evidence",
                        "github_url": issue.html_url,
                        "issue_number": issue.issue_number,
                        "codes": [],
                    },
                )
            )
        return chunks

    @staticmethod
    def _ai_chunks(run: AnalysisRun) -> list[AssistantKnowledgeChunk]:
        chunks = []
        rows = db.session.execute(
            db.select(AIAnalysis).where(AIAnalysis.analysis_run_id == run.id)
        ).scalars().all()
        issues = {issue.issue_number: issue for issue in run.issues}
        for row in sorted(rows, key=lambda item: item.issue_number):
            issue = issues.get(row.issue_number)
            action = AI_ACTION_NAMES.get(
                row.recommended_action or "",
                row.recommended_action or "未给出",
            )
            content = "\n".join(
                [
                    f"Issue #{row.issue_number} {issue.title if issue else ''}",
                    f"AI 分类：{row.category}，置信度 {row.category_confidence:.2f}",
                    f"语义信息质量：{_format_score(row.semantic_quality_score)}",
                    f"协作闭环质量：{_format_score(row.closure_quality_score)}",
                    f"建议动作：{action}",
                    f"缺失信息：{', '.join(row.completeness_json or []) or '未发现'}",
                    f"质量标记：{', '.join(row.quality_flags_json or []) or '无'}",
                    f"知识沉淀候选：{'是' if row.knowledge_candidate else '否'}",
                    f"AI 摘要：{row.summary}",
                    f"判断理由：{row.explanation}",
                ]
            )
            chunks.append(
                _chunk(
                    run,
                    source_type="ai_analysis",
                    source_key=f"ai-{row.issue_number}",
                    title=f"Issue #{row.issue_number} AI 分析",
                    content=content,
                    metadata={
                        "page_url": f"/analysis/{run.id}/ai",
                        "github_url": issue.html_url if issue else "",
                        "issue_number": row.issue_number,
                        "codes": [],
                    },
                )
            )
        return chunks

    @staticmethod
    def _evidence_chunks(run: AnalysisRun) -> list[AssistantKnowledgeChunk]:
        rows = db.session.execute(
            db.select(EvidenceItem)
            .where(EvidenceItem.analysis_run_id == run.id)
            .order_by(EvidenceItem.happened_at.desc())
        ).scalars().all()
        def evidence_title(row: EvidenceItem) -> str:
            target = (
                f"Issue #{row.issue_number}"
                if row.issue_number is not None
                else f"PR #{row.pr_number}"
            )
            return f"{target} {row.evidence_type}"

        return [
            _chunk(
                run,
                source_type="evidence",
                source_key=f"evidence-{row.id}",
                title=evidence_title(row),
                content="\n".join(
                    [
                        f"证据类型：{row.evidence_type}",
                        f"操作者：{row.actor_login or '未知'}（{row.actor_association or '未知'}）",
                        f"发生时间：{row.happened_at.isoformat() if row.happened_at else '未知'}",
                        f"来源：{row.source_url}",
                        "摘录：",
                        _clip(row.excerpt or "无摘录", 700),
                    ]
                ),
                metadata={
                    "page_url": f"/analysis/{run.id}/evidence",
                    "github_url": row.source_url,
                    "issue_number": row.issue_number,
                    "codes": [],
                },
            )
            for row in rows
        ]

    @staticmethod
    def _duplicate_chunks(run: AnalysisRun) -> list[AssistantKnowledgeChunk]:
        rows = db.session.execute(
            db.select(DuplicateCandidate)
            .where(DuplicateCandidate.analysis_run_id == run.id)
            .order_by(DuplicateCandidate.similarity.desc())
            .limit(60)
        ).scalars().all()
        if not rows:
            return [
                _chunk(
                    run,
                    source_type="duplicate",
                    source_key="duplicate-summary",
                    title="重复与相似 Issue 摘要",
                    content="本次报告没有生成高相似重复候选。",
                    metadata={
                        "page_url": f"/analysis/{run.id}/ai",
                        "codes": ["D6", "M6.1"],
                    },
                )
            ]
        chunks = []
        for row in rows:
            relation = row.llm_relation or "待 AI 复核或仅本地候选"
            confidence = (
                row.llm_confidence * 100
                if row.llm_confidence is not None
                else None
            )
            chunks.append(
                _chunk(
                    run,
                    source_type="duplicate",
                    source_key=f"duplicate-{row.issue_a}-{row.issue_b}",
                    title=f"Issue #{row.issue_a} 与 #{row.issue_b} 相似度 {row.similarity:.3f}",
                    content="\n".join(
                        [
                            f"相似问题：Issue #{row.issue_a} 与 Issue #{row.issue_b}",
                            f"本地相似度：{row.similarity:.4f}",
                            f"相似模型：{row.embedding_model}",
                            f"关系判断：{relation}",
                            f"AI 置信度：{_format_score(confidence)}",
                            f"判断理由：{row.llm_reason or '尚无'}",
                        ]
                    ),
                    metadata={
                        "page_url": f"/analysis/{run.id}/ai",
                        "codes": ["D6", "M6.1"],
                        "issue_numbers": [row.issue_a, row.issue_b],
                    },
                )
            )
        return chunks

    @staticmethod
    def _governance_chunk(run: AnalysisRun) -> AssistantKnowledgeChunk | None:
        package = db.session.execute(
            db.select(GovernancePackage).where(GovernancePackage.analysis_run_id == run.id)
        ).scalar_one_or_none()
        if package is None:
            return None
        workflow = package.workflow_plan_json or {}
        label_names = ", ".join(
            item.get("name", "") for item in package.labels_plan_json
        )
        content = "\n".join(
            [
                f"治理包版本：{package.version}；状态：{package.status}",
                f"建议文件：{', '.join(package.files_json.keys()) or '无'}",
                f"标签计划：{label_names or '无'}",
                f"动作统计：{workflow.get('action_counts', {})}",
                f"缺少信息统计：{workflow.get('missing_information_counts', {})}",
                f"知识沉淀候选数量：{workflow.get('knowledge_candidate_count', 0)}",
                "所有 GitHub 写入都必须先预览 Diff 并人工确认。",
            ]
        )
        return _chunk(
            run,
            source_type="governance",
            source_key="governance",
            title=f"{run.repository.full_name} 治理方案",
            content=content,
            metadata={
                "page_url": f"/analysis/{run.id}/governance",
                "codes": [],
            },
        )


def _static_chunk(
    *,
    source_type: str,
    source_key: str,
    title: str,
    content: str,
    metadata: dict,
) -> AssistantKnowledgeChunk:
    chunk = AssistantKnowledgeChunk(
        analysis_run_id="__static__",
        source_type=source_type,
        source_key=source_key,
        title=title,
        content=content,
        vector_json={},
        metadata_json=metadata,
        content_hash="",
        rank_boost=0.0,
    )
    return chunk


def _chunk(
    run: AnalysisRun,
    *,
    source_type: str,
    source_key: str,
    title: str,
    content: str,
    metadata: dict,
    rank_boost: float = 0.0,
) -> AssistantKnowledgeChunk:
    clipped = _clip(content, MAX_CHUNK_CONTENT)
    return AssistantKnowledgeChunk(
        analysis_run_id=run.id,
        source_type=source_type,
        source_key=source_key,
        title=_clip(title, 300),
        content=clipped,
        vector_json={},
        metadata_json={**metadata, "source_key": source_key},
        content_hash=hashlib.sha256(clipped.encode("utf-8")).hexdigest(),
        rank_boost=rank_boost,
    )


def _clip(value: str, maximum: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= maximum else text[: maximum - 1].rstrip() + "…"


def _format_score(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "N/A"


def _format_number(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "N/A"


def _format_response_hours(value: float | None) -> str:
    return f"{value:.2f} 小时" if value is not None else "未记录"
