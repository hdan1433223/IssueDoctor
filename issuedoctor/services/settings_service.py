import os
from dataclasses import asdict, dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx
from flask import current_app

from issuedoctor.extensions import db
from issuedoctor.models import AppSetting
from issuedoctor.security.secrets import GITHUB_TOKEN, LLM_API_KEY, SecretStore

LLM_BASE_URL = "llm_base_url"
LLM_MODEL = "llm_model"
DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"


class SettingsValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PublicSettings:
    github_token_saved: bool
    llm_api_key_saved: bool
    llm_base_url: str
    llm_model: str
    secret_storage: str


class SettingsService:
    def __init__(self, secret_store: SecretStore | None = None) -> None:
        self.secret_store = secret_store or current_app.extensions["issuedoctor_secrets"]

    def get_public(self) -> PublicSettings:
        values = {
            row.key: row.value
            for row in db.session.execute(db.select(AppSetting)).scalars().all()
        }
        return PublicSettings(
            github_token_saved=bool(self.secret_store.get(GITHUB_TOKEN)),
            llm_api_key_saved=bool(self.secret_store.get(LLM_API_KEY)),
            llm_base_url=values.get(LLM_BASE_URL)
            or os.environ.get("ISSUEDOCTOR_LLM_BASE_URL", DEFAULT_LLM_BASE_URL),
            llm_model=values.get(LLM_MODEL) or os.environ.get("ISSUEDOCTOR_LLM_MODEL", ""),
            secret_storage="persistent" if self.secret_store.persistent else "process",
        )

    def as_public_dict(self) -> dict:
        return asdict(self.get_public())

    def save(
        self,
        *,
        github_token: str = "",
        llm_api_key: str = "",
        llm_base_url: str = DEFAULT_LLM_BASE_URL,
        llm_model: str = "",
    ) -> PublicSettings:
        normalized_url = normalize_llm_base_url(llm_base_url)
        self._upsert(LLM_BASE_URL, normalized_url)
        self._upsert(LLM_MODEL, llm_model.strip())
        if github_token.strip():
            self.secret_store.set(GITHUB_TOKEN, github_token.strip())
        if llm_api_key.strip():
            self.secret_store.set(LLM_API_KEY, llm_api_key.strip())
        db.session.commit()
        return self.get_public()

    def delete_github_token(self) -> None:
        self.secret_store.delete(GITHUB_TOKEN)

    def delete_llm_key(self) -> None:
        self.secret_store.delete(LLM_API_KEY)

    @staticmethod
    def _upsert(key: str, value: str) -> None:
        setting = db.session.get(AppSetting, key)
        if setting is None:
            db.session.add(AppSetting(key=key, value=value))
        else:
            setting.value = value


def normalize_llm_base_url(value: str) -> str:
    candidate = value.strip().rstrip("/")
    parts = urlsplit(candidate)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise SettingsValidationError("LLM Base URL 必须是有效的 HTTP(S) 地址")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise SettingsValidationError("LLM Base URL 不得包含凭据、查询参数或片段")
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))


def test_github_connection(
    token: str | None,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "IssueDoctor/0.1",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    with httpx.Client(
        base_url=current_app.config["GITHUB_API_URL"],
        headers=headers,
        timeout=current_app.config["HTTP_TIMEOUT_SECONDS"],
        transport=transport,
    ) as client:
        response = client.get("/rate_limit")
    if response.status_code == 401:
        return {"ok": False, "code": "GITHUB_TOKEN_INVALID", "message": "GitHub Token 无效"}
    if response.status_code == 403:
        return {
            "ok": False,
            "code": "GITHUB_RATE_LIMITED",
            "message": "GitHub API 拒绝访问或已限流",
        }
    response.raise_for_status()
    rate = response.json().get("resources", {}).get("core", {})
    authenticated = bool(token)
    remaining = rate.get("remaining")
    mode = "Token 认证" if authenticated else "匿名访问"
    quota = f"，剩余 API 额度 {remaining}" if remaining is not None else ""
    return {
        "ok": True,
        "authenticated": authenticated,
        "message": f"GitHub 连接成功（{mode}{quota}）",
        "rate_limit": {key: rate.get(key) for key in ("limit", "remaining", "reset")},
    }


def test_llm_connection(
    base_url: str,
    api_key: str,
    model: str,
    *,
    transport: httpx.BaseTransport | None = None,
) -> dict:
    if not api_key:
        return {"ok": False, "code": "LLM_NOT_CONFIGURED", "message": "尚未配置 LLM API Key"}
    normalized_url = normalize_llm_base_url(base_url)
    with httpx.Client(
        base_url=normalized_url,
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=current_app.config["HTTP_TIMEOUT_SECONDS"],
        transport=transport,
    ) as client:
        response = client.get("models")
        if response.status_code in {401, 403}:
            return {"ok": False, "code": "LLM_AUTH_FAILED", "message": "LLM API Key 无效或无权限"}
        response.raise_for_status()
        models = response.json().get("data", [])
        model_ids = {item.get("id") for item in models if isinstance(item, dict)}
        model_available = not model or model in model_ids
        if model and not model_available:
            return {
                "ok": False,
                "code": "LLM_MODEL_NOT_FOUND",
                "model_available": False,
                "message": f"API 可以连接，但模型列表中未找到 {model}；请检查模型名称",
            }
        chat = client.post(
            f"{normalized_url}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": 'Reply with JSON: {"ok": true}'}],
                "max_tokens": 16,
            },
        )
        if chat.status_code in {401, 403}:
            return {"ok": False, "code": "LLM_AUTH_FAILED", "message": "LLM API Key 无效或无权限"}
        if chat.status_code == 429:
            retry_after = chat.headers.get("retry-after", "")
            delay = f"，建议等待 {retry_after} 秒" if retry_after else "，请稍后重试"
            return {
                "ok": False,
                "code": "LLM_RATE_LIMITED",
                "message": f"模型可识别，但聊天接口当前被限流{delay}",
            }
        if chat.status_code >= 400:
            return {
                "ok": False,
                "code": "LLM_CHAT_TEST_FAILED",
                "message": f"模型可识别，但聊天接口返回 HTTP {chat.status_code}",
            }
    message = f"LLM 连接成功，模型 {model} 已完成对话测试" if model else "LLM 对话测试成功"
    return {"ok": True, "model_available": model_available, "message": message}
