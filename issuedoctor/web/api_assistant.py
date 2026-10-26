from flask import Blueprint, jsonify, request

from issuedoctor.errors import IssueDoctorError
from issuedoctor.repositories.analysis_repo import AnalysisRepository
from issuedoctor.services.assistant_service import AssistantService

assistant_api_bp = Blueprint("assistant_api", __name__, url_prefix="/api/analyses")


@assistant_api_bp.post("/<run_id>/assistant/query")
def query_assistant(run_id: str):
    run = AnalysisRepository.get(run_id)
    if run is None:
        raise IssueDoctorError("ANALYSIS_NOT_FOUND", "找不到该分析任务", status_code=404)
    data = request.get_json(silent=True) or {}
    question = data.get("question")
    history = data.get("history", [])
    if not isinstance(question, str):
        raise IssueDoctorError(
            "ASSISTANT_QUESTION_REQUIRED",
            "请提供需要回答的问题",
            status_code=422,
        )
    if not isinstance(history, list):
        raise IssueDoctorError(
            "ASSISTANT_HISTORY_INVALID",
            "对话历史格式无效",
            status_code=422,
        )
    return jsonify(AssistantService().answer(run, question, history))
