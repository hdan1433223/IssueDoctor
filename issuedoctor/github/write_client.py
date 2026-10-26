import base64
from typing import Any
from urllib.parse import quote

import httpx

from issuedoctor.errors import IssueDoctorError
from issuedoctor.github.client import GITHUB_API_URL


class GitHubWriteClient:
    def __init__(
        self,
        token: str,
        *,
        timeout: float = 15.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not token:
            raise IssueDoctorError(
                "GITHUB_PERMISSION_INSUFFICIENT",
                "GitHub 写操作需要具备相应权限的 Token",
                status_code=403,
            )
        self._client = httpx.Client(
            base_url=GITHUB_API_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "IssueDoctor/0.1",
            },
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()

    def close(self) -> None:
        self._client.close()

    def get(self, path: str, *, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def post(self, path: str, payload: dict) -> Any:
        return self._request("POST", path, json=payload)

    def patch(self, path: str, payload: dict) -> Any:
        return self._request("PATCH", path, json=payload)

    def delete(self, path: str) -> None:
        self._request("DELETE", path)

    def get_repository(self, full_name: str) -> dict:
        return self.get(f"/repos/{full_name}")

    def get_file(self, full_name: str, path: str, reference: str) -> str:
        encoded_path = quote(path, safe="")
        try:
            payload = self.get(
                f"/repos/{full_name}/contents/{encoded_path}",
                params={"ref": reference},
            )
        except IssueDoctorError as exc:
            if exc.code == "REPOSITORY_NOT_FOUND":
                return ""
            raise
        if payload.get("type") != "file" or payload.get("encoding") != "base64":
            raise IssueDoctorError("GITHUB_WRITE_CONFLICT", "目标治理文件状态无效", status_code=409)
        return base64.b64decode(payload.get("content", "")).decode("utf-8")

    def get_reference(self, full_name: str, branch: str) -> dict:
        return self.get(f"/repos/{full_name}/git/ref/heads/{quote(branch, safe='')}")

    def get_commit(self, full_name: str, sha: str) -> dict:
        return self.get(f"/repos/{full_name}/git/commits/{sha}")

    def create_reference(self, full_name: str, branch: str, sha: str) -> dict:
        return self.post(
            f"/repos/{full_name}/git/refs",
            {"ref": f"refs/heads/{branch}", "sha": sha},
        )

    def create_tree(self, full_name: str, base_tree: str, entries: list[dict]) -> dict:
        return self.post(
            f"/repos/{full_name}/git/trees",
            {"base_tree": base_tree, "tree": entries},
        )

    def create_commit(
        self,
        full_name: str,
        message: str,
        tree_sha: str,
        parent_sha: str,
    ) -> dict:
        return self.post(
            f"/repos/{full_name}/git/commits",
            {"message": message, "tree": tree_sha, "parents": [parent_sha]},
        )

    def update_reference(self, full_name: str, branch: str, sha: str) -> dict:
        return self.patch(
            f"/repos/{full_name}/git/refs/heads/{quote(branch, safe='')}",
            {"sha": sha, "force": False},
        )

    def create_pull_request(
        self,
        full_name: str,
        title: str,
        body: str,
        head: str,
        base: str,
    ) -> dict:
        return self.post(
            f"/repos/{full_name}/pulls",
            {"title": title, "body": body, "head": head, "base": base},
        )

    def list_labels(self, full_name: str) -> list[dict]:
        return self.get(f"/repos/{full_name}/labels", params={"per_page": 100})

    def create_label(self, full_name: str, payload: dict) -> dict:
        return self.post(f"/repos/{full_name}/labels", payload)

    def update_label(self, full_name: str, current_name: str, payload: dict) -> dict:
        name = quote(current_name, safe="")
        return self.patch(f"/repos/{full_name}/labels/{name}", payload)

    def delete_label(self, full_name: str, name: str) -> None:
        self.delete(f"/repos/{full_name}/labels/{quote(name, safe='')}")

    def label_issue_count(self, full_name: str, name: str) -> int:
        query = f'repo:{full_name} label:"{name}"'
        result = self.get("/search/issues", params={"q": query, "per_page": 1})
        return int(result.get("total_count", 0))

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.TimeoutException as exc:
            raise IssueDoctorError("NETWORK_TIMEOUT", "GitHub 写操作超时", status_code=504) from exc
        except httpx.HTTPError as exc:
            raise IssueDoctorError("NETWORK_ERROR", "无法连接 GitHub API", status_code=502) from exc
        if response.status_code in {401, 403}:
            raise IssueDoctorError(
                "GITHUB_PERMISSION_INSUFFICIENT",
                "GitHub Token 无效或缺少写权限",
                status_code=403,
            )
        if response.status_code in {409, 422}:
            raise IssueDoctorError(
                "GITHUB_WRITE_CONFLICT",
                "仓库状态已变化或写入内容冲突，请刷新预览后重试",
                status_code=409,
            )
        if response.status_code == 404:
            raise IssueDoctorError("REPOSITORY_NOT_FOUND", "GitHub 资源不存在", status_code=404)
        if response.is_error:
            raise IssueDoctorError("GITHUB_API_ERROR", "GitHub 写操作失败", status_code=502)
        return response.json() if response.content else None
