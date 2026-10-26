from datetime import datetime

import httpx

from issuedoctor.compat import UTC
from issuedoctor.github.client import GitHubClient
from issuedoctor.github.collector import GitHubCollector
from issuedoctor.security.input_validation import RepositoryRef


def _item(number, *, pull_request=False):
    item = {
        "number": number,
        "title": f"Item {number}",
        "body": "body",
        "state": "open",
        "html_url": f"https://github.com/a/b/issues/{number}",
        "user": {"login": "author"},
        "author_association": "NONE",
        "created_at": "2026-09-01T00:00:00Z",
        "updated_at": "2026-09-01T00:00:00Z",
        "comments": 0,
        "labels": [],
    }
    if pull_request:
        item["pull_request"] = {"url": "https://api.github.com/repos/a/b/pulls/2"}
    return item


def test_issue_collector_filters_pull_requests_from_issues_endpoint():
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[_item(1), _item(2, pull_request=True)])

    with GitHubClient(transport=httpx.MockTransport(handler)) as client:
        result = GitHubCollector(client, RepositoryRef("a", "b")).collect_issues(
            datetime(2026, 1, 1, tzinfo=UTC),
            500,
        )

    assert [issue.number for issue in result.items] == [1]
    assert result.truncated is False


class StubClient:
    def __init__(self, items_by_path):
        self.items_by_path = items_by_path

    def paginate(self, path, **_kwargs):
        return iter(self.items_by_path[path])


def _pull_request(number, created_at="2026-09-01T00:00:00Z"):
    item = _item(number)
    item["created_at"] = created_at
    item["merged_at"] = None
    return item


def _comment(comment_id, issue_number):
    return {
        "id": comment_id,
        "issue_url": f"https://api.github.com/repos/a/b/issues/{issue_number}",
        "html_url": f"https://github.com/a/b/issues/{issue_number}#issuecomment-{comment_id}",
        "body": "maintainer response",
        "user": {"login": "maintainer"},
        "author_association": "MEMBER",
        "created_at": "2026-09-02T00:00:00Z",
        "updated_at": "2026-09-02T00:00:00Z",
    }


def test_issue_collector_applies_window_and_limit():
    old = _item(1)
    old["created_at"] = "2025-01-01T00:00:00Z"
    client = StubClient({"/repos/a/b/issues": [old, _item(2), _item(3)]})
    collector = GitHubCollector(client, RepositoryRef("a", "b"))

    result = collector.collect_issues(datetime(2026, 1, 1, tzinfo=UTC), limit=1)

    assert [item.number for item in result.items] == [2]
    assert result.truncated is True


def test_pull_request_collector_stops_at_window_and_marks_truncation():
    client = StubClient(
        {
            "/repos/a/b/pulls": [
                _pull_request(3),
                _pull_request(2),
                _pull_request(1, "2025-01-01T00:00:00Z"),
            ]
        }
    )
    collector = GitHubCollector(client, RepositoryRef("a", "b"))

    result = collector.collect_pull_requests(datetime(2026, 1, 1, tzinfo=UTC), limit=1)

    assert [item.number for item in result.items] == [3]
    assert result.truncated is True


def test_pull_request_collector_breaks_on_old_item_without_truncating():
    client = StubClient(
        {"/repos/a/b/pulls": [_pull_request(1, "2025-01-01T00:00:00Z")]}
    )

    result = GitHubCollector(client, RepositoryRef("a", "b")).collect_pull_requests(
        datetime(2026, 1, 1, tzinfo=UTC), limit=5
    )

    assert result.items == []
    assert result.truncated is False


def test_comment_collector_validates_items_and_exposes_issue_number():
    client = StubClient({"/repos/a/b/issues/comments": [_comment(10, 42)]})

    result = GitHubCollector(client, RepositoryRef("a", "b")).collect_comments(
        datetime(2026, 1, 1, tzinfo=UTC)
    )

    assert result.items[0].issue_number == 42
    assert result.truncated is False
