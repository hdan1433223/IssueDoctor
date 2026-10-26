from urllib.parse import parse_qs

import httpx

from issuedoctor.github.client import GitHubClient
from issuedoctor.services.preflight_service import PreflightService


def test_preflight_returns_metadata_counts_and_estimates(app):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/repos/example/project":
            return httpx.Response(
                200,
                json={
                    "id": 1,
                    "name": "project",
                    "full_name": "example/project",
                    "html_url": "https://github.com/example/project",
                    "description": "Example",
                    "default_branch": "main",
                    "language": "Python",
                    "stargazers_count": 42,
                    "forks_count": 3,
                    "archived": False,
                    "has_issues": True,
                    "open_issues_count": 20,
                },
                headers={"X-RateLimit-Limit": "60", "X-RateLimit-Remaining": "57"},
            )
        query = parse_qs(request.url.query.decode())["q"][0]
        total = 16 if "is:issue" in query else 4
        return httpx.Response(
            200,
            json={"total_count": total, "items": []},
            headers={"X-RateLimit-Limit": "10", "X-RateLimit-Remaining": "8"},
        )

    client = GitHubClient(transport=httpx.MockTransport(handler))
    try:
        with app.app_context():
            result = PreflightService(client).run("example/project")
    finally:
        client.close()

    assert result.repository["open_issues"] == 16
    assert result.repository["open_pull_requests"] == 4
    assert result.analysis["estimated_llm_batches"] == 2
    assert result.token_configured is False
    assert result.rate_limit["remaining"] == 8
