from dataclasses import dataclass
from datetime import datetime

from issuedoctor.github.client import GitHubClient
from issuedoctor.github.schemas import CommentData, IssueData, PullRequestData
from issuedoctor.security.input_validation import RepositoryRef


@dataclass(frozen=True)
class CollectionResult:
    items: list
    truncated: bool


class GitHubCollector:
    def __init__(self, client: GitHubClient, repository: RepositoryRef) -> None:
        self.client = client
        self.repository = repository
        self.base_path = f"/repos/{repository.full_name}"

    def collect_issues(self, window_start: datetime, limit: int) -> CollectionResult:
        raw_items = self.client.paginate(
            f"{self.base_path}/issues",
            params={"state": "all", "since": window_start.isoformat(), "sort": "created"},
        )
        issues = []
        truncated = False
        for raw in raw_items:
            if "pull_request" in raw:
                continue
            issue = IssueData.model_validate(raw)
            if issue.created_at < window_start:
                continue
            if len(issues) >= limit:
                truncated = True
                break
            issues.append(issue)
        return CollectionResult(issues, truncated)

    def collect_pull_requests(self, window_start: datetime, limit: int) -> CollectionResult:
        raw_items = self.client.paginate(
            f"{self.base_path}/pulls",
            params={"state": "all", "sort": "created", "direction": "desc"},
        )
        pull_requests = []
        truncated = False
        for raw in raw_items:
            pull_request = PullRequestData.model_validate(raw)
            if pull_request.created_at < window_start:
                break
            if len(pull_requests) >= limit:
                truncated = True
                break
            pull_requests.append(pull_request)
        return CollectionResult(pull_requests, truncated)

    def collect_comments(self, window_start: datetime) -> CollectionResult:
        raw_items = self.client.paginate(
            f"{self.base_path}/issues/comments",
            params={"since": window_start.isoformat(), "sort": "created", "direction": "asc"},
        )
        comments = [CommentData.model_validate(item) for item in raw_items]
        return CollectionResult(comments, False)

