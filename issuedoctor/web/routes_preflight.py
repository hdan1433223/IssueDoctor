from flask import Blueprint, render_template, request

from issuedoctor.guidance import WORKFLOW_STEPS
from issuedoctor.services.preflight_service import PreflightService

preflight_bp = Blueprint("preflight", __name__)


@preflight_bp.get("/preflight")
def preflight_page():
    repository_url = request.args.get("repository_url", "")
    result = PreflightService().run(repository_url)
    return render_template(
        "preflight.html",
        preflight=result,
        workflow_steps=WORKFLOW_STEPS,
    )
