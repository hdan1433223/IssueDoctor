from flask import Blueprint, jsonify, request

from issuedoctor.services.preflight_service import PreflightService

preflight_api_bp = Blueprint("preflight_api", __name__, url_prefix="/api")


@preflight_api_bp.post("/preflight")
def preflight():
    data = request.get_json(silent=True) or {}
    result = PreflightService().run(
        str(data.get("repository_url", "")),
        window_months=data.get("window_months"),
        issue_limit=data.get("issue_limit"),
        pr_limit=data.get("pr_limit"),
    )
    return jsonify(result.as_dict())

