from datetime import datetime

from flask import Blueprint, current_app, jsonify, request

from issuedoctor.compat import UTC
from issuedoctor.errors import IssueDoctorError
from issuedoctor.extensions import db
from issuedoctor.github.branch_pr_writer import BranchPullRequestWriter
from issuedoctor.github.label_writer import LabelDeleteConfirmation, LabelWriter
from issuedoctor.github.write_client import GitHubWriteClient
from issuedoctor.models import GovernanceAction, GovernancePackage
from issuedoctor.repositories.analysis_repo import AnalysisRepository
from issuedoctor.security.redaction import redact_secret
from issuedoctor.security.secrets import GITHUB_TOKEN
from issuedoctor.services.assistant_service import AssistantService
from issuedoctor.services.governance_service import GovernanceService
from issuedoctor.services.settings_service import SettingsService

governance_api_bp = Blueprint("governance_api", __name__, url_prefix="/api")


@governance_api_bp.post("/analyses/<run_id>/governance/generate")
def generate_governance(run_id: str):
    run = AnalysisRepository.get(run_id)
    if run is None:
        raise IssueDoctorError("ANALYSIS_NOT_FOUND", "找不到该分析任务", status_code=404)
    package = GovernanceService().generate(run)
    try:
        AssistantService().rebuild(run)
    except Exception:
        db.session.rollback()
        current_app.logger.exception(
            "Assistant knowledge refresh failed after governance generation for run %s",
            run_id,
        )
    return jsonify({"ok": True, "package_id": package.id})


@governance_api_bp.get("/governance/<int:package_id>/diff")
def governance_diff(package_id: int):
    package = db.session.get(GovernancePackage, package_id)
    if package is None:
        raise IssueDoctorError("GOVERNANCE_NOT_FOUND", "找不到治理包", status_code=404)
    return jsonify({"package_id": package.id, "diff": GovernanceService.diff(package)})


def _package(package_id: int) -> GovernancePackage:
    package = db.session.get(GovernancePackage, package_id)
    if package is None:
        raise IssueDoctorError("GOVERNANCE_NOT_FOUND", "找不到治理包", status_code=404)
    return package


def _client() -> GitHubWriteClient:
    token = SettingsService().secret_store.get(GITHUB_TOKEN)
    return GitHubWriteClient(
        token or "",
        timeout=current_app.config["HTTP_TIMEOUT_SECONDS"],
    )


def _audit(package: GovernancePackage, action_type: str, payload: dict, result: dict) -> None:
    db.session.add(
        GovernanceAction(
            governance_package_id=package.id,
            action_type=action_type,
            request_payload_redacted_json=redact_secret(payload),
            status="SUCCEEDED",
            confirmation_method="explicit_ui_confirmation",
            executed_at=datetime.now(UTC),
            result_json=result,
        )
    )
    db.session.commit()


@governance_api_bp.post("/governance/<int:package_id>/create-pr")
def create_governance_pr(package_id: int):
    package = _package(package_id)
    data = request.get_json(silent=True) or {}
    with _client() as client:
        result = BranchPullRequestWriter(client).create(
            package.analysis_run.repository.full_name,
            package,
            confirmed=data.get("confirmed") is True,
        )
    package.status = "PR_CREATED"
    _audit(package, "CREATE_PR", data, result)
    return jsonify({"ok": True, **result})


@governance_api_bp.post("/governance/<int:package_id>/labels/apply")
def apply_governance_labels(package_id: int):
    package = _package(package_id)
    data = request.get_json(silent=True) or {}
    full_name = package.analysis_run.repository.full_name
    with _client() as client:
        results = LabelWriter(client).apply(
            full_name,
            package.labels_plan_json,
            confirmed=data.get("confirmed") is True,
        )
    result = {"applied_count": len(results)}
    _audit(package, "APPLY_LABELS", data, result)
    return jsonify({"ok": True, **result})


@governance_api_bp.post("/governance/<int:package_id>/labels/delete-impact")
def label_delete_impact(package_id: int):
    package = _package(package_id)
    label_name = str((request.get_json(silent=True) or {}).get("label_name", ""))
    with _client() as client:
        count = client.label_issue_count(package.analysis_run.repository.full_name, label_name)
    return jsonify({"ok": True, "label_name": label_name, "affected_issue_count": count})


@governance_api_bp.post("/governance/<int:package_id>/labels/delete")
def delete_governance_label(package_id: int):
    package = _package(package_id)
    data = request.get_json(silent=True) or {}
    full_name = package.analysis_run.repository.full_name
    confirmation = LabelDeleteConfirmation(
        acknowledged_impact=data.get("acknowledged_impact") is True,
        repository_full_name=str(data.get("repository_full_name", "")),
        confirm_delete=data.get("confirm_delete") is True,
    )
    with _client() as client:
        result = LabelWriter(client).delete(
            full_name,
            str(data.get("label_name", "")),
            confirmation,
        )
    _audit(package, "DELETE_LABEL", data, result)
    return jsonify({"ok": True, **result})
