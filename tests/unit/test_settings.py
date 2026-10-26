import httpx

from issuedoctor.extensions import db
from issuedoctor.models import AppSetting
from issuedoctor.security.secrets import GITHUB_TOKEN, LLM_API_KEY
from issuedoctor.services.settings_service import (
    SettingsService,
    SettingsValidationError,
    normalize_llm_base_url,
)
from issuedoctor.services.settings_service import (
    test_github_connection as check_github_connection,
)
from issuedoctor.services.settings_service import (
    test_llm_connection as check_llm_connection,
)


def test_settings_never_store_plaintext_secrets(app):
    github_secret = "github-plain-secret"
    llm_secret = "llm-plain-secret"

    with app.app_context():
        db.create_all()
        service = SettingsService()
        service.save(
            github_token=github_secret,
            llm_api_key=llm_secret,
            llm_base_url="https://llm.example.test/v1/",
            llm_model="model-a",
        )
        stored_values = [row.value for row in db.session.execute(db.select(AppSetting)).scalars()]

        assert github_secret not in stored_values
        assert llm_secret not in stored_values
        assert service.secret_store.get(GITHUB_TOKEN) == github_secret
        assert service.secret_store.get(LLM_API_KEY) == llm_secret


def test_settings_secret_delete(app):
    with app.app_context():
        db.create_all()
        service = SettingsService()
        service.secret_store.set(GITHUB_TOKEN, "secret")
        service.delete_github_token()

        assert service.secret_store.get(GITHUB_TOKEN) is None


def test_settings_use_environment_fallback_for_docker_llm_config(app, monkeypatch):
    monkeypatch.setenv("ISSUEDOCTOR_LLM_BASE_URL", "https://llm.container.test/v1")
    monkeypatch.setenv("ISSUEDOCTOR_LLM_MODEL", "container-model")
    with app.app_context():
        db.create_all()
        public = SettingsService().get_public()

    assert public.llm_base_url == "https://llm.container.test/v1"
    assert public.llm_model == "container-model"


def test_normalize_llm_url_rejects_credentials():
    try:
        normalize_llm_base_url("https://user:password@example.test/v1")
    except SettingsValidationError:
        pass
    else:
        raise AssertionError("URL credentials must be rejected")


def test_github_connection_uses_optional_token(app):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-token"
        return httpx.Response(
            200,
            json={"resources": {"core": {"limit": 5000, "remaining": 4999, "reset": 1}}},
        )

    with app.app_context():
        result = check_github_connection("test-token", transport=httpx.MockTransport(handler))

    assert result["ok"] is True
    assert result["authenticated"] is True
    assert result["rate_limit"]["remaining"] == 4999


def test_llm_connection_checks_configured_model(app):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "model-a"}]})
        assert request.url.path.endswith("/chat/completions")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    with app.app_context():
        result = check_llm_connection(
            "https://llm.example.test/v1",
            "test-key",
            "model-a",
            transport=httpx.MockTransport(handler),
        )

    assert result["ok"] is True
    assert result["model_available"] is True
    assert result["message"] == "LLM 连接成功，模型 model-a 已完成对话测试"


def test_settings_api_save_read_delete_without_secret_disclosure(app, client):
    with app.app_context():
        db.create_all()

    response = client.post(
        "/api/settings",
        json={
            "github_token": "api-github-secret",
            "llm_api_key": "api-llm-secret",
            "llm_base_url": "https://llm.example.test/v1",
            "llm_model": "model-a",
        },
    )
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "api-github-secret" not in body
    assert "api-llm-secret" not in body
    assert response.get_json()["message"] == "设置已保存"
    assert client.get("/api/settings").get_json()["github_token_saved"] is True

    assert client.post("/api/settings/delete-github-token").status_code == 200
    assert client.post("/api/settings/delete-llm-key").status_code == 200
    public = client.get("/api/settings").get_json()
    assert public["github_token_saved"] is False
    assert public["llm_api_key_saved"] is False


def test_settings_page_shows_local_feedback_and_guide_link(app, client):
    with app.app_context():
        db.create_all()

    body = client.get("/settings").get_data(as_text=True)

    assert 'id="github-status"' in body
    assert 'id="llm-status"' in body
    assert "第一次使用" not in body
    assert 'href="/guide#ai"' in body
    assert "保存后，密码框会按安全规则清空" in body
