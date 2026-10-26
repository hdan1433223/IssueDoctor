from collections.abc import Iterator
from typing import Any
from urllib.parse import urlsplit

import httpx

from issuedoctor.errors import IssueDoctorError
from issuedoctor.github.rate_limit import RateLimit

GITHUB_API_URL = "https://api.github.com"


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "IssueDoctor/0.1",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self.authenticated = bool(token)
        self.request_count = 0
        self.rate_limit = RateLimit()
        self._client = httpx.Client(
            base_url=GITHUB_API_URL,
            headers=headers,
            timeout=timeout,
            follow_redirects=False,
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_json(self, path: str, *, params: dict[str, Any] | None = None) -> Any:
        response = self._request(path, params=params)
        return response.json()

    def paginate(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        item_limit: int | None = None,
    ) -> Iterator[dict]:
        next_path: str | None = path
        next_params = {**(params or {}), "per_page": 100}
        yielded = 0
        while next_path:
            response = self._request(next_path, params=next_params)
            payload = response.json()
            if not isinstance(payload, list):
                raise IssueDoctorError(
                    "GITHUB_INVALID_RESPONSE",
                    "GitHub 分页响应格式无效",
                    status_code=502,
                )
            for item in payload:
                if not isinstance(item, dict):
                    continue
                yield item
                yielded += 1
                if item_limit is not None and yielded >= item_limit:
                    return
            next_path = response.links.get("next", {}).get("url")
            next_params = None

    def _request(self, path: str, *, params: dict[str, Any] | None = None) -> httpx.Response:
        self._assert_safe_api_path(path)
        self.request_count += 1
        try:
            response = self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise IssueDoctorError(
                "NETWORK_TIMEOUT",
                "连接 GitHub API 超时",
                status_code=504,
            ) from exc
        except httpx.HTTPError as exc:
            raise IssueDoctorError("NETWORK_ERROR", "无法连接 GitHub API", status_code=502) from exc

        self.rate_limit = RateLimit.from_headers(response.headers)
        if response.status_code == 401:
            raise IssueDoctorError("GITHUB_TOKEN_INVALID", "GitHub Token 无效", status_code=401)
        if response.status_code == 404:
            raise IssueDoctorError(
                "REPOSITORY_NOT_FOUND",
                "仓库不存在，或当前凭据无权访问",
                status_code=404,
            )
        if response.status_code == 403:
            rate_limited = self.rate_limit.remaining == 0
            code = (
                "GITHUB_RATE_LIMITED" if rate_limited else "REPOSITORY_PRIVATE_OR_FORBIDDEN"
            )
            message = (
                "GitHub API 额度已用尽，请等待重置或配置 Token"
                if rate_limited
                else "GitHub 拒绝访问该资源"
            )
            raise IssueDoctorError(code, message, status_code=403)
        if response.status_code >= 500:
            raise IssueDoctorError("GITHUB_UNAVAILABLE", "GitHub API 暂时不可用", status_code=502)
        if response.is_error:
            raise IssueDoctorError("GITHUB_API_ERROR", "GitHub API 请求失败", status_code=502)
        return response

    @staticmethod
    def _assert_safe_api_path(path: str) -> None:
        parts = urlsplit(path)
        if parts.scheme or parts.netloc:
            if parts.scheme != "https" or parts.hostname != "api.github.com":
                raise IssueDoctorError("UNSAFE_GITHUB_URL", "拒绝访问非 GitHub API 地址")
        elif not path.startswith("/"):
            raise IssueDoctorError("UNSAFE_GITHUB_URL", "GitHub API 路径必须是绝对路径")
