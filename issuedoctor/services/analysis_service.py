from datetime import datetime
from uuid import uuid4

from flask import current_app

from issuedoctor.ai.budget import effective_ai_budget
from issuedoctor.compat import UTC
from issuedoctor.extensions import db
from issuedoctor.models import AnalysisRun
from issuedoctor.repositories.analysis_repo import AnalysisRepository
from issuedoctor.security.input_validation import parse_github_repository_url
from issuedoctor.security.secrets import LLM_API_KEY
from issuedoctor.services.config_service import load_yaml
from issuedoctor.services.settings_service import SettingsService


def create_analysis_run(
    repository_url: str,
    *,
    window_months: int | None = None,
    issue_limit: int | None = None,
    pr_limit: int | None = None,
    ai_issue_count: int | None = None,
) -> AnalysisRun:
    repository_ref = parse_github_repository_url(repository_url)
    config = load_yaml(current_app.config["ANALYSIS_CONFIG_PATH"])
    months = _bounded(window_months, config["window_months"], 1, 24)
    issues = _bounded(issue_limit, config["issue_limit"], 1, config["max_issue_limit"])
    pull_requests = _bounded(pr_limit, config["pr_limit"], 1, config["max_pr_limit"])
    settings = SettingsService()
    public = settings.get_public()
    recommended_ai_count = effective_ai_budget(
        config,
        public.llm_base_url,
    )["ai_max_issues"]
    selected_ai_count = _bounded(
        ai_issue_count,
        recommended_ai_count,
        1,
        config["ai_max_issues"],
    )
    now = datetime.now(UTC)
    window_start = _subtract_months(now, months)
    repository = AnalysisRepository.get_or_create_repository(
        repository_ref.owner,
        repository_ref.repo,
    )
    llm_configured = bool(settings.secret_store.get(LLM_API_KEY))
    run = AnalysisRun(
        id=str(uuid4()),
        repository_id=repository.id,
        status="PENDING",
        mode="AI_ENHANCED" if llm_configured else "BASIC",
        progress_percent=0,
        current_stage="PENDING",
        created_at=now,
        window_start=window_start,
        window_end=now,
        issue_limit=issues,
        pr_limit=pull_requests,
        scoring_version="1.0",
        scoring_config_json={},
        analysis_config_json={
            **config,
            "window_months": months,
            "ai_requested_issue_count": selected_ai_count,
        },
    )
    db.session.add(run)
    db.session.commit()
    return run


def analysis_status(run: AnalysisRun) -> dict:
    return {
        "id": run.id,
        "repository": run.repository.full_name,
        "status": run.status,
        "mode": run.mode,
        "progress_percent": run.progress_percent,
        "current_stage": run.current_stage,
        "issue_count": run.issue_count,
        "pr_count": run.pr_count,
        "comment_count": run.comment_count,
        "is_truncated": run.is_truncated,
        "error": (
            {"code": run.error_code, "message": run.error_message} if run.error_code else None
        ),
        "events": [
            {
                "stage": event.stage,
                "percent": event.percent,
                "level": event.level,
                "message": event.message,
                "created_at": event.created_at.isoformat(),
            }
            for event in sorted(run.events, key=lambda item: item.id)[-50:]
        ],
    }


def _bounded(value: int | None, default: int, minimum: int, maximum: int) -> int:
    selected = default if value is None else int(value)
    if not minimum <= selected <= maximum:
        from issuedoctor.errors import IssueDoctorError

        raise IssueDoctorError("INVALID_ANALYSIS_CONFIG", "分析范围超出允许值")
    return selected


def _subtract_months(value: datetime, months: int) -> datetime:
    year = value.year
    month = value.month - months
    while month <= 0:
        year -= 1
        month += 12
    return value.replace(year=year, month=month, day=min(value.day, 28))
