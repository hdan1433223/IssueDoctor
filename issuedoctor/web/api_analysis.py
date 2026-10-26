from flask import Blueprint, current_app, jsonify, request

from issuedoctor.errors import IssueDoctorError
from issuedoctor.repositories.analysis_repo import AnalysisRepository
from issuedoctor.services.analysis_service import analysis_status, create_analysis_run
from issuedoctor.services.reporting_service import (
    analysis_summary,
    duplicate_list,
    finding_list,
    metric_list,
)

analysis_api_bp = Blueprint("analysis_api", __name__, url_prefix="/api/analyses")


@analysis_api_bp.post("")
def create_analysis():
    data = request.get_json(silent=True) or {}
    run = create_analysis_run(
        str(data.get("repository_url", "")),
        window_months=data.get("window_months"),
        issue_limit=data.get("issue_limit"),
        pr_limit=data.get("pr_limit"),
        ai_issue_count=data.get("ai_issue_count"),
    )
    current_app.extensions["issuedoctor_tasks"].submit(run.id)
    return jsonify({"id": run.id, "status": run.status}), 202


@analysis_api_bp.get("/<run_id>/status")
def get_analysis_status(run_id: str):
    run = AnalysisRepository.get(run_id)
    if run is None:
        raise IssueDoctorError("ANALYSIS_NOT_FOUND", "找不到该分析任务", status_code=404)
    return jsonify(analysis_status(run))


def _get_run(run_id: str):
    run = AnalysisRepository.get(run_id)
    if run is None:
        raise IssueDoctorError("ANALYSIS_NOT_FOUND", "找不到该分析任务", status_code=404)
    return run


@analysis_api_bp.get("/<run_id>/summary")
def get_analysis_summary(run_id: str):
    return jsonify(analysis_summary(_get_run(run_id)))


@analysis_api_bp.get("/<run_id>/metrics")
def get_analysis_metrics(run_id: str):
    _get_run(run_id)
    return jsonify(metric_list(run_id))


@analysis_api_bp.get("/<run_id>/findings")
def get_analysis_findings(run_id: str):
    _get_run(run_id)
    return jsonify(finding_list(run_id))


@analysis_api_bp.get("/<run_id>/duplicates")
def get_analysis_duplicates(run_id: str):
    _get_run(run_id)
    return jsonify(duplicate_list(run_id))
