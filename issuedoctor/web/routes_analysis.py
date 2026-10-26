from flask import Blueprint, render_template

from issuedoctor.errors import IssueDoctorError
from issuedoctor.extensions import db
from issuedoctor.guidance import (
    AI_ACTION_NAMES,
    AI_CATEGORY_NAMES,
    AI_FIELD_NAMES,
    DIMENSIONS,
    METRICS,
    WORKFLOW_STEPS,
)
from issuedoctor.models import AnalysisRun, DimensionScore
from issuedoctor.repositories.analysis_repo import AnalysisRepository
from issuedoctor.services.reporting_service import (
    ai_analysis_list,
    analysis_summary,
    duplicate_list,
    evidence_list,
    finding_list,
    metric_list,
)

analysis_bp = Blueprint("analysis", __name__)


@analysis_bp.get("/analysis/<run_id>/progress")
def progress_page(run_id: str):
    run = AnalysisRepository.get(run_id)
    if run is None:
        raise IssueDoctorError("ANALYSIS_NOT_FOUND", "找不到该分析任务", status_code=404)
    return render_template("progress.html", run=run, workflow_steps=WORKFLOW_STEPS)


def _get_run(run_id: str):
    run = AnalysisRepository.get(run_id)
    if run is None:
        raise IssueDoctorError("ANALYSIS_NOT_FOUND", "找不到该分析任务", status_code=404)
    return run


@analysis_bp.get("/analysis/<run_id>")
def overview_page(run_id: str):
    run = _get_run(run_id)
    return render_template(
        "analysis/overview.html",
        run=run,
        summary=analysis_summary(run),
        dimensions=DIMENSIONS,
        metric_help=METRICS,
        workflow_steps=WORKFLOW_STEPS,
    )


@analysis_bp.get("/analysis/<run_id>/ai")
def ai_page(run_id: str):
    run = _get_run(run_id)
    summary = analysis_summary(run)
    return render_template(
        "analysis/ai.html",
        run=run,
        analyses=ai_analysis_list(run),
        category_names=AI_CATEGORY_NAMES,
        field_names=AI_FIELD_NAMES,
        action_names=AI_ACTION_NAMES,
        duplicate_reviews=[
            item for item in duplicate_list(run.id) if item["llm_relation"] is not None
        ],
        summary=summary,
    )


@analysis_bp.get("/analysis/<run_id>/dimension/<code>")
def dimension_page(run_id: str, code: str):
    run = _get_run(run_id)
    dimension = db.session.execute(
        db.select(DimensionScore).where(
            DimensionScore.analysis_run_id == run_id,
            DimensionScore.dimension_code == code.upper(),
        )
    ).scalar_one_or_none()
    if dimension is None:
        raise IssueDoctorError("DIMENSION_NOT_FOUND", "找不到该评分维度", status_code=404)
    findings = [item for item in finding_list(run_id) if item["dimension_code"] == code.upper()]
    return render_template(
        "analysis/dimension.html",
        run=run,
        dimension=dimension,
        metrics=metric_list(run_id, code.upper()),
        findings=findings,
        evidence=evidence_list(run),
        dimension_help=DIMENSIONS[code.upper()],
        metric_help=METRICS,
    )


@analysis_bp.get("/analysis/<run_id>/findings")
def findings_page(run_id: str):
    run = _get_run(run_id)
    return render_template(
        "analysis/findings.html",
        run=run,
        findings=finding_list(run_id),
        evidence=evidence_list(run),
        dimensions=DIMENSIONS,
        metric_help=METRICS,
    )


@analysis_bp.get("/analysis/<run_id>/evidence")
def evidence_page(run_id: str):
    run = _get_run(run_id)
    return render_template("analysis/evidence.html", run=run, evidence=evidence_list(run))


@analysis_bp.get("/history")
def history_page():
    runs = db.session.execute(
        db.select(AnalysisRun).order_by(AnalysisRun.created_at.desc())
    ).scalars()
    return render_template("history.html", runs=list(runs))
