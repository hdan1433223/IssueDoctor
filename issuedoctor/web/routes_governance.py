from flask import Blueprint, render_template

from issuedoctor.errors import IssueDoctorError
from issuedoctor.extensions import db
from issuedoctor.guidance import AI_ACTION_NAMES, AI_FIELD_NAMES
from issuedoctor.models import GovernancePackage
from issuedoctor.repositories.analysis_repo import AnalysisRepository
from issuedoctor.services.governance_service import GovernanceService

governance_bp = Blueprint("governance", __name__)


@governance_bp.get("/analysis/<run_id>/governance")
def governance_page(run_id: str):
    run = AnalysisRepository.get(run_id)
    if run is None:
        raise IssueDoctorError("ANALYSIS_NOT_FOUND", "找不到该分析任务", status_code=404)
    package = db.session.execute(
        db.select(GovernancePackage).where(GovernancePackage.analysis_run_id == run_id)
    ).scalar_one_or_none()
    return render_template(
        "analysis/governance.html",
        run=run,
        package=package,
        diff=GovernanceService.diff(package) if package else {},
        action_names=AI_ACTION_NAMES,
        field_names=AI_FIELD_NAMES,
    )
