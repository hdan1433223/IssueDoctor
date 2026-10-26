from collections import Counter

from issuedoctor.extensions import db
from issuedoctor.models import (
    AIAnalysis,
    AnalysisRun,
    DimensionScore,
    DuplicateCandidate,
    EvidenceItem,
    Finding,
    MetricResult,
)


def analysis_summary(run: AnalysisRun) -> dict:
    dimensions = db.session.execute(
        db.select(DimensionScore)
        .where(DimensionScore.analysis_run_id == run.id)
        .order_by(DimensionScore.dimension_code)
    ).scalars()
    findings = db.session.execute(
        db.select(Finding)
        .where(Finding.analysis_run_id == run.id)
        .order_by(Finding.priority_score.desc())
        .limit(5)
    ).scalars()
    response_hours = [
        issue.first_maintainer_response_hours
        for issue in run.issues
        if issue.first_maintainer_response_hours is not None
    ]
    backlog_bins = Counter()
    for issue in run.issues:
        if issue.state.lower() != "open":
            continue
        window_end = run.window_end.replace(tzinfo=None)
        created_at = issue.created_at.replace(tzinfo=None)
        age = max(0, (window_end - created_at).days)
        if age <= 30:
            bucket = "0–30"
        elif age <= 90:
            bucket = "31–90"
        elif age <= 180:
            bucket = "91–180"
        else:
            bucket = "180+"
        backlog_bins[bucket] += 1
    linked = sum(bool(issue.linked_pr_numbers_json) for issue in run.issues)
    merged_prs = {pr.pr_number for pr in run.pull_requests if pr.merged_at is not None}
    merged = sum(
        bool(set(issue.linked_pr_numbers_json) & merged_prs) for issue in run.issues
    )
    ai_rows = db.session.execute(
        db.select(AIAnalysis).where(AIAnalysis.analysis_run_id == run.id)
    ).scalars().all()
    ai_runtime = (run.analysis_config_json or {}).get("runtime", {})
    eligible_issues = ai_runtime.get("ai_eligible_issues", len(run.issues))
    selected_issues = ai_runtime.get("ai_selected_issues", len(ai_rows))
    analyzed_issues = ai_runtime.get("ai_analyzed_issues", len(ai_rows))
    ai_coverage_percent = (
        100 * analyzed_issues / eligible_issues if eligible_issues else 0
    )
    ai_success_percent = (
        100 * analyzed_issues / selected_issues if selected_issues else 0
    )
    return {
        "id": run.id,
        "repository": run.repository.full_name,
        "repository_url": run.repository.html_url,
        "status": run.status,
        "mode": run.mode,
        "created_at": run.created_at.isoformat(),
        "total_score": run.total_score,
        "ai_semantic_score": run.ai_semantic_score,
        "ai_semantic_confidence": run.ai_semantic_confidence,
        "enhanced_total_score": run.enhanced_total_score,
        "confidence_score": run.confidence_score,
        "ai_coverage_percent": ai_coverage_percent,
        "ai_success_percent": ai_success_percent,
        "is_truncated": run.is_truncated,
        "ai": {
            "enabled": run.mode == "AI_ENHANCED",
            "analysis_count": len(ai_rows),
            "models": sorted({row.model_name for row in ai_rows}),
            "runtime": ai_runtime,
        },
        "counts": {
            "issues": run.issue_count,
            "pull_requests": run.pr_count,
            "comments": run.comment_count,
        },
        "dimensions": [
            {
                "code": item.dimension_code,
                "score": item.score_0_100,
                "nominal_weight": item.nominal_weight,
                "effective_weight": item.effective_weight,
                "confidence": item.confidence,
            }
            for item in dimensions
        ],
        "findings": [finding_dict(item) for item in findings],
        "charts": {
            "response_hours": response_hours,
            "backlog_age": [backlog_bins[key] for key in ("0–30", "31–90", "91–180", "180+")],
            "collaboration": [run.issue_count, linked, merged],
        },
    }


def ai_analysis_list(run: AnalysisRun) -> list[dict]:
    issues = {issue.issue_number: issue for issue in run.issues}
    rows = db.session.execute(
        db.select(AIAnalysis)
        .where(AIAnalysis.analysis_run_id == run.id)
        .order_by(AIAnalysis.issue_number)
    ).scalars()
    return [
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
            "category": row.category,
            "category_confidence": row.category_confidence,
            "missing_information": row.completeness_json,
            "quality_flags": row.quality_flags_json,
            "semantic_quality_score": row.semantic_quality_score,
            "closure_quality_score": row.closure_quality_score,
            "semantic_confidence": row.semantic_confidence,
            "knowledge_candidate": row.knowledge_candidate,
            "recommended_action": row.recommended_action,
            "evidence_quotes": row.evidence_json,
            "summary": row.summary,
            "explanation": row.explanation,
            "model": row.model_name,
            "prompt_version": row.prompt_version,
        }
        for row in rows
    ]


def metric_list(run_id: str, dimension_code: str | None = None) -> list[dict]:
    query = db.select(MetricResult).where(MetricResult.analysis_run_id == run_id)
    if dimension_code:
        query = query.where(MetricResult.dimension_code == dimension_code)
    rows = db.session.execute(query.order_by(MetricResult.metric_code)).scalars()
    return [
        {
            "dimension_code": row.dimension_code,
            "metric_code": row.metric_code,
            "raw_value": row.raw_value,
            "unit": row.unit,
            "normalized_score": row.normalized_score,
            "nominal_weight": row.metric_weight,
            "sample_size": row.sample_size,
            "applicable": row.applicable,
            "confidence": row.confidence,
            "thresholds": row.threshold_snapshot_json,
        }
        for row in rows
    ]


def finding_list(run_id: str) -> list[dict]:
    rows = db.session.execute(
        db.select(Finding)
        .where(Finding.analysis_run_id == run_id)
        .order_by(Finding.priority_score.desc())
    ).scalars()
    return [finding_dict(row) for row in rows]


def finding_dict(row: Finding) -> dict:
    return {
        "id": row.id,
        "dimension_code": row.dimension_code,
        "finding_code": row.finding_code,
        "priority_score": row.priority_score,
        "priority_level": row.priority_level,
        "title": row.title,
        "summary": row.summary,
        "impact_text": row.impact_text,
        "recommendation": row.recommendation,
        "metric_code": row.metric_code,
        "affected_count": row.affected_count,
        "sample_size": row.sample_size,
        "source_type": row.source_type,
        "evidence_ids": row.evidence_ids_json,
    }


def evidence_list(run: AnalysisRun) -> list[dict]:
    issue_urls = {issue.issue_number: issue.html_url for issue in run.issues}
    rows = db.session.execute(
        db.select(EvidenceItem)
        .where(EvidenceItem.analysis_run_id == run.id)
        .order_by(EvidenceItem.happened_at.desc())
    ).scalars()
    return [
        {
            "id": row.id,
            "issue_number": row.issue_number,
            "pr_number": row.pr_number,
            "type": row.evidence_type,
            "excerpt": row.excerpt,
            "source_url": row.source_url,
            "github_url": issue_urls.get(row.issue_number, row.source_url),
            "actor_login": row.actor_login,
            "actor_association": row.actor_association,
            "happened_at": row.happened_at.isoformat() if row.happened_at else None,
        }
        for row in rows
    ]


def duplicate_list(run_id: str) -> list[dict]:
    rows = db.session.execute(
        db.select(DuplicateCandidate)
        .where(DuplicateCandidate.analysis_run_id == run_id)
        .order_by(DuplicateCandidate.similarity.desc())
    ).scalars()
    return [
        {
            "issue_a": row.issue_a,
            "issue_b": row.issue_b,
            "similarity": row.similarity,
            "cluster_id": row.cluster_id,
            "model": row.embedding_model,
            "llm_relation": row.llm_relation,
            "llm_confidence": row.llm_confidence,
            "llm_reason": row.llm_reason,
        }
        for row in rows
    ]
