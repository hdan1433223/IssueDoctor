import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime

from flask import current_app
from sqlalchemy import inspect

from issuedoctor.ai.budget import effective_ai_budget
from issuedoctor.compat import UTC
from issuedoctor.errors import IssueDoctorError
from issuedoctor.extensions import db
from issuedoctor.github.client import GitHubClient
from issuedoctor.github.schemas import RepositoryData
from issuedoctor.security.input_validation import RepositoryRef, parse_github_repository_url
from issuedoctor.security.secrets import GITHUB_TOKEN
from issuedoctor.services.config_service import load_yaml
from issuedoctor.services.settings_service import DEFAULT_LLM_BASE_URL, SettingsService


@dataclass(frozen=True)
class PreflightResult:
    repository: dict
    token_configured: bool
    rate_limit: dict
    analysis: dict

    def as_dict(self) -> dict:
        return asdict(self)


class PreflightService:
    def __init__(self, client: GitHubClient | None = None) -> None:
        self.client = client

    def run(
        self,
        repository_url: str,
        *,
        window_months: int | None = None,
        issue_limit: int | None = None,
        pr_limit: int | None = None,
    ) -> PreflightResult:
        repository_ref = parse_github_repository_url(repository_url)
        config = load_yaml(current_app.config["ANALYSIS_CONFIG_PATH"])
        window_months = _bounded(window_months, config["window_months"], 1, 24)
        issue_limit = _bounded(issue_limit, config["issue_limit"], 1, config["max_issue_limit"])
        pr_limit = _bounded(pr_limit, config["pr_limit"], 1, config["max_pr_limit"])
        window_start = _subtract_months(datetime.now(UTC), window_months)

        settings = SettingsService()
        token = settings.secret_store.get(GITHUB_TOKEN)
        base_url = (
            settings.get_public().llm_base_url
            if inspect(db.engine).has_table("app_settings")
            else os.environ.get("ISSUEDOCTOR_LLM_BASE_URL", DEFAULT_LLM_BASE_URL)
        )
        budget = effective_ai_budget(config, base_url)
        owns_client = self.client is None
        client = self.client or GitHubClient(
            token,
            timeout=current_app.config["HTTP_TIMEOUT_SECONDS"],
        )
        try:
            result = self._fetch(
                client,
                repository_ref,
                window_start,
                issue_limit,
                pr_limit,
                budget,
            )
        finally:
            if owns_client:
                client.close()
        return result

    @staticmethod
    def _fetch(
        client: GitHubClient,
        repository_ref: RepositoryRef,
        window_start: datetime,
        issue_limit: int,
        pr_limit: int,
        budget: dict,
    ) -> PreflightResult:
        repo = RepositoryData.model_validate(
            client.get_json(f"/repos/{repository_ref.full_name}")
        )
        if not repo.has_issues:
            raise IssueDoctorError("ISSUES_DISABLED", "该仓库未启用 Issues", status_code=422)

        date_value = window_start.date().isoformat()
        issue_count = _search_count(
            client,
            f"repo:{repository_ref.full_name} is:issue is:open created:>={date_value}",
        )
        pr_count = _search_count(
            client,
            f"repo:{repository_ref.full_name} is:pr is:open created:>={date_value}",
        )
        estimated_issues = min(issue_count, issue_limit)
        estimated_prs = min(pr_count, pr_limit)
        estimated_llm_items = min(estimated_issues, budget["ai_max_issues"])
        estimated_llm_batches = min(
            budget["ai_max_batches"],
            math.ceil(estimated_llm_items / budget["llm_batch_issue_count"]),
        )
        return PreflightResult(
            repository={
                "owner": repository_ref.owner,
                "name": repo.name,
                "full_name": repo.full_name,
                "html_url": repo.html_url,
                "description": repo.description,
                "stars": repo.stargazers_count,
                "language": repo.language,
                "default_branch": repo.default_branch,
                "archived": repo.archived,
                "issues_enabled": repo.has_issues,
                "open_issues": issue_count,
                "open_pull_requests": pr_count,
            },
            token_configured=client.authenticated,
            rate_limit=client.rate_limit.as_dict(),
            analysis={
                "window_start": window_start.isoformat(),
                "issue_limit": issue_limit,
                "pr_limit": pr_limit,
                "estimated_issues": estimated_issues,
                "estimated_pull_requests": estimated_prs,
                "estimated_llm_items": estimated_llm_items,
                "ai_recommended_issue_count": estimated_llm_items,
                "ai_max_issue_count": budget["user_max_issues"],
                "ai_batch_issue_count": budget["llm_batch_issue_count"],
                "ai_max_batches": budget["user_max_batches"],
                "estimated_llm_batches": estimated_llm_batches,
                "ai_max_total_characters": budget["ai_max_total_characters"],
                "ai_duplicate_pair_limit": budget["ai_duplicate_pair_limit"],
                "ai_budget_profile": budget["profile"],
                "will_truncate": issue_count > issue_limit or pr_count > pr_limit,
            },
        )


def _search_count(client: GitHubClient, query: str) -> int:
    payload = client.get_json("/search/issues", params={"q": query, "per_page": 1})
    return int(payload.get("total_count", 0))


def _bounded(value: int | None, default: int, minimum: int, maximum: int) -> int:
    selected = default if value is None else int(value)
    if not minimum <= selected <= maximum:
        raise IssueDoctorError("INVALID_ANALYSIS_CONFIG", "分析范围超出允许值")
    return selected


def _subtract_months(value: datetime, months: int) -> datetime:
    year = value.year
    month = value.month - months
    while month <= 0:
        year -= 1
        month += 12
    day = min(value.day, 28)
    return value.replace(year=year, month=month, day=day)
