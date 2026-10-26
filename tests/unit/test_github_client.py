import json

import httpx
import pytest

from issuedoctor.errors import IssueDoctorError
from issuedoctor.github.client import GitHubClient


def test_pagination_follows_only_github_api_links():
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        if page == "1":
            return httpx.Response(
                200,
                json=[{"number": 1}],
                headers={
                    "Link": '<https://api.github.com/repos/a/b/issues?page=2>; rel="next"'
                },
            )
        return httpx.Response(200, json=[{"number": 2}])

    with GitHubClient(transport=httpx.MockTransport(handler)) as client:
        assert [item["number"] for item in client.paginate("/repos/a/b/issues")] == [1, 2]


def test_client_rejects_non_github_pagination_target():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json=[{"number": 1}],
            headers={"Link": '<https://evil.example/items?page=2>; rel="next"'},
        )

    with GitHubClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IssueDoctorError, match="非 GitHub"):
            list(client.paginate("/repos/a/b/issues"))


def test_rate_limit_error_is_clear():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            content=json.dumps({"message": "rate limit"}),
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "123"},
        )

    with GitHubClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(IssueDoctorError) as error:
            client.get_json("/repos/a/b")

    assert error.value.code == "GITHUB_RATE_LIMITED"
    assert "额度" in error.value.message


@pytest.mark.parametrize("token", [None, "secret-token"])
def test_client_supports_anonymous_and_authenticated_requests(token):
    def handler(request: httpx.Request) -> httpx.Response:
        expected = f"Bearer {token}" if token else None
        assert request.headers.get("Authorization") == expected
        return httpx.Response(200, json={"ok": True})

    with GitHubClient(token, transport=httpx.MockTransport(handler)) as client:
        assert client.get_json("/repos/a/b") == {"ok": True}


def test_pagination_honors_item_limit_and_skips_non_objects():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["invalid", {"number": 1}, {"number": 2}])

    with GitHubClient(transport=httpx.MockTransport(handler)) as client:
        result = list(client.paginate("/repos/a/b/issues", item_limit=1))

    assert result == [{"number": 1}]
    assert client.request_count == 1


def test_pagination_rejects_non_list_response():
    with GitHubClient(
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={"items": []}))
    ) as client:
        with pytest.raises(IssueDoctorError) as error:
            list(client.paginate("/repos/a/b/issues"))

    assert error.value.code == "GITHUB_INVALID_RESPONSE"


@pytest.mark.parametrize(
    ("status", "headers", "code"),
    [
        (401, {}, "GITHUB_TOKEN_INVALID"),
        (404, {}, "REPOSITORY_NOT_FOUND"),
        (403, {"X-RateLimit-Remaining": "3"}, "REPOSITORY_PRIVATE_OR_FORBIDDEN"),
        (500, {}, "GITHUB_UNAVAILABLE"),
        (422, {}, "GITHUB_API_ERROR"),
    ],
)
def test_http_errors_map_to_stable_codes(status, headers, code):
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(status, headers=headers, json={"message": "error"})
    )
    with GitHubClient(transport=transport) as client:
        with pytest.raises(IssueDoctorError) as error:
            client.get_json("/repos/a/b")

    assert error.value.code == code


def test_network_failures_map_to_stable_codes():
    def timeout(request: httpx.Request):
        raise httpx.ReadTimeout("late", request=request)

    with GitHubClient(transport=httpx.MockTransport(timeout)) as client:
        with pytest.raises(IssueDoctorError) as error:
            client.get_json("/repos/a/b")
    assert error.value.code == "NETWORK_TIMEOUT"

    def broken(request: httpx.Request):
        raise httpx.ConnectError("broken", request=request)

    with GitHubClient(transport=httpx.MockTransport(broken)) as client:
        with pytest.raises(IssueDoctorError) as error:
            client.get_json("/repos/a/b")
    assert error.value.code == "NETWORK_ERROR"


@pytest.mark.parametrize(
    "path",
    [
        "repos/a/b",
        "http://api.github.com/repos/a/b",
        "https://evil.example/repos/a/b",
    ],
)
def test_client_rejects_unsafe_api_paths(path):
    transport = httpx.MockTransport(lambda _request: httpx.Response(200))
    with GitHubClient(transport=transport) as client:
        with pytest.raises(IssueDoctorError) as error:
            client.get_json(path)

    assert error.value.code == "UNSAFE_GITHUB_URL"
