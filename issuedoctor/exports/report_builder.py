from issuedoctor.exports.schemas import ReportDTO
from issuedoctor.extensions import db
from issuedoctor.models import AIAnalysis, AnalysisRun, GovernancePackage
from issuedoctor.services.reporting_service import (
    analysis_summary,
    duplicate_list,
    evidence_list,
    finding_list,
    metric_list,
)


def build_report(run: AnalysisRun) -> ReportDTO:
    summary = analysis_summary(run)
    package = db.session.execute(
        db.select(GovernancePackage).where(GovernancePackage.analysis_run_id == run.id)
    ).scalar_one_or_none()
    ai_rows = db.session.execute(
        db.select(AIAnalysis).where(AIAnalysis.analysis_run_id == run.id)
    ).scalars().all()
    return ReportDTO(
        schema_version="1.0",
        repository={
            "full_name": run.repository.full_name,
            "html_url": run.repository.html_url,
            "default_branch": run.repository.default_branch,
            "primary_language": run.repository.primary_language,
            "stars_count": run.repository.stars_count,
        },
        analysis_metadata={
            "id": run.id,
            "status": run.status,
            "mode": run.mode,
            "created_at": run.created_at.isoformat(),
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at else None,
            "window_start": run.window_start.isoformat(),
            "window_end": run.window_end.isoformat(),
            "issue_count": run.issue_count,
            "pr_count": run.pr_count,
            "comment_count": run.comment_count,
            "is_truncated": run.is_truncated,
        },
        analysis_config=run.analysis_config_json,
        scoring_config=run.scoring_config_json,
        scores={
            "total": run.total_score,
            "ai_semantic": run.ai_semantic_score,
            "ai_semantic_confidence": run.ai_semantic_confidence,
            "enhanced_total": run.enhanced_total_score,
            "confidence": run.confidence_score,
            "ai_coverage_percent": summary["ai_coverage_percent"],
            "ai_success_percent": summary["ai_success_percent"],
            "dimensions": summary["dimensions"],
        },
        metrics=metric_list(run.id),
        findings=finding_list(run.id),
        evidence=evidence_list(run),
        duplicate_summary=duplicate_list(run.id),
        governance_summary=(
            {
                "package_id": package.id,
                "version": package.version,
                "status": package.status,
                "files": list(package.files_json),
                "labels": package.labels_plan_json,
                "workflow": package.workflow_plan_json,
            }
            if package
            else {}
        ),
        ai_metadata={
            "enabled": run.mode == "AI_ENHANCED",
            "coverage_percent": summary["ai_coverage_percent"],
            "success_percent": summary["ai_success_percent"],
            "models": sorted({row.model_name for row in ai_rows}),
            "prompt_versions": sorted({row.prompt_version for row in ai_rows}),
            "analysis_count": len(ai_rows),
            "runtime": (run.analysis_config_json or {}).get("runtime", {}),
        },
    )
