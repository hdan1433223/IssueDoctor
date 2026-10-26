import httpx
from flask import Blueprint, jsonify, request

from issuedoctor.security.secrets import GITHUB_TOKEN, LLM_API_KEY
from issuedoctor.services.settings_service import (
    SettingsService,
    SettingsValidationError,
    test_github_connection,
    test_llm_connection,
)

settings_api_bp = Blueprint("settings_api", __name__, url_prefix="/api/settings")


def _payload() -> dict:
    return request.get_json(silent=True) or {}


@settings_api_bp.get("")
def get_settings():
    return jsonify(SettingsService().as_public_dict())


@settings_api_bp.post("")
def save_settings():
    data = _payload()
    try:
        settings = SettingsService().save(
            github_token=str(data.get("github_token", "")),
            llm_api_key=str(data.get("llm_api_key", "")),
            llm_base_url=str(data.get("llm_base_url", "")),
            llm_model=str(data.get("llm_model", "")),
        )
    except SettingsValidationError as exc:
        return jsonify({"ok": False, "code": "INVALID_SETTINGS", "message": str(exc)}), 400
    return jsonify(
        {
            "ok": True,
            "message": "设置已保存",
            "settings": settings.__dict__,
        }
    )


@settings_api_bp.post("/test-github")
def test_github():
    store = SettingsService().secret_store
    token = str(_payload().get("github_token", "")).strip() or store.get(GITHUB_TOKEN)
    try:
        return jsonify(test_github_connection(token))
    except httpx.HTTPError:
        error = {"ok": False, "code": "NETWORK_TIMEOUT", "message": "无法连接 GitHub API"}
        return jsonify(error), 502


@settings_api_bp.post("/test-llm")
def test_llm():
    data = _payload()
    service = SettingsService()
    current = service.get_public()
    api_key = str(data.get("llm_api_key", "")).strip() or service.secret_store.get(LLM_API_KEY)
    try:
        return jsonify(
            test_llm_connection(
                str(data.get("llm_base_url", current.llm_base_url)),
                api_key or "",
                str(data.get("llm_model", current.llm_model)),
            )
        )
    except SettingsValidationError as exc:
        return jsonify({"ok": False, "code": "INVALID_SETTINGS", "message": str(exc)}), 400
    except httpx.HTTPError:
        return jsonify({"ok": False, "code": "LLM_TIMEOUT", "message": "无法连接 LLM API"}), 502


@settings_api_bp.post("/delete-github-token")
def delete_github_token():
    SettingsService().delete_github_token()
    return jsonify({"ok": True, "message": "已删除保存的 GitHub Token"})


@settings_api_bp.post("/delete-llm-key")
def delete_llm_key():
    SettingsService().delete_llm_key()
    return jsonify({"ok": True, "message": "已删除保存的 LLM API Key"})
