from datetime import datetime

from flask import current_app

from issuedoctor.compat import UTC
from issuedoctor.errors import IssueDoctorError
from issuedoctor.extensions import db
from issuedoctor.github.client import GitHubClient
from issuedoctor.github.collector import GitHubCollector
from issuedoctor.github.pr_linker import link_issues_and_pull_requests
from issuedoctor.github.schemas import RepositoryData
from issuedoctor.models import AnalysisRun
from issuedoctor.repositories.analysis_repo import AnalysisRepository
from issuedoctor.repositories.snapshot_repo import SnapshotRepository
from issuedoctor.security.input_validation import RepositoryRef
from issuedoctor.security.secrets import GITHUB_TOKEN
from issuedoctor.services.ai_service import AIService
from issuedoctor.services.assistant_service import AssistantService
from issuedoctor.services.embedding_service import EmbeddingService
from issuedoctor.services.scoring_service import ScoringService
from issuedoctor.services.settings_service import SettingsService
from issuedoctor.tasks.progress import report_progress


def run_analysis(run_id: str) -> None:
    run = db.session.get(AnalysisRun, run_id)
    if run is None:
        return
    run.status = "RUNNING"
    run.started_at = datetime.now(UTC)
    db.session.commit()
    try:
        _collect(run)
    except IssueDoctorError as exc:
        db.session.rollback()
        run = db.session.get(AnalysisRun, run_id)
        if run is None:
            return
        AnalysisRepository.mark_failed(run, exc.code, exc.message)
    except Exception:
        db.session.rollback()
        run = db.session.get(AnalysisRun, run_id)
        current_app.logger.exception("Analysis task failed for run %s", run_id)
        if run is None:
            return
        AnalysisRepository.mark_failed(run, "ANALYSIS_INTERNAL_ERROR", "分析任务发生内部错误")


def _collect(run: AnalysisRun) -> None:
    repository_ref = RepositoryRef(run.repository.owner, run.repository.name)
    token = SettingsService().secret_store.get(GITHUB_TOKEN)
    report_progress(run, "VALIDATING_REPOSITORY", 2, "正在验证仓库")
    with GitHubClient(token, timeout=current_app.config["HTTP_TIMEOUT_SECONDS"]) as client:
        metadata = RepositoryData.model_validate(
            client.get_json(f"/repos/{repository_ref.full_name}")
        )
        _update_repository(run, metadata)
        report_progress(run, "FETCHING_REPOSITORY", 10, "仓库信息已读取")

        collector = GitHubCollector(client, repository_ref)
        window_start = _as_utc(run.window_start)
        issues = collector.collect_issues(window_start, run.issue_limit)
        run.issue_count = len(issues.items)
        report_progress(run, "FETCHING_ISSUES", 25, f"已抓取 {run.issue_count} 个 Issues")

        comments = collector.collect_comments(window_start)
        run.comment_count = len(comments.items)
        report_progress(run, "FETCHING_COMMENTS", 35, f"已抓取 {run.comment_count} 条评论")

        pull_requests = collector.collect_pull_requests(window_start, run.pr_limit)
        run.pr_count = len(pull_requests.items)
        run.is_truncated = issues.truncated or pull_requests.truncated
        report_progress(run, "FETCHING_PULL_REQUESTS", 45, f"已抓取 {run.pr_count} 个 PRs")

        relations = link_issues_and_pull_requests(issues.items, pull_requests.items)
        report_progress(run, "BUILDING_RELATIONS", 52, "Issue 与 PR 关联已构建")
        SnapshotRepository.replace(
            run.id,
            issues.items,
            pull_requests.items,
            comments.items,
            issue_links=relations.issue_to_prs,
            pr_links=relations.pr_to_issues,
            link_methods=relations.methods_by_pr,
        )
        ScoringService().calculate_and_save(run)
        report_progress(run, "CALCULATING_METRICS", 65, "六维确定性评分已完成")
        embedding_result = EmbeddingService().analyze(run)
        report_progress(
            run,
            "EMBEDDING_ANALYSIS",
            75,
            embedding_result.warning or "本地语义相似度分析已完成",
            level="WARNING" if embedding_result.warning else "INFO",
        )
        ScoringService().calculate_and_save(run, duplicates=embedding_result.scoring_values)
        ai_result = AIService().analyze(run)
        run.analysis_config_json = {
            **run.analysis_config_json,
            "runtime": {
                "github_api_calls": client.request_count,
                "llm_api_calls": ai_result.api_call_count,
                "ai_eligible_issues": ai_result.eligible_count,
                "ai_requested_issues": (run.analysis_config_json or {}).get(
                    "ai_requested_issue_count"
                ),
                "ai_selected_issues": ai_result.selected_count,
                "ai_analyzed_issues": ai_result.analyzed_count,
                "ai_skipped_issues": ai_result.skipped_count,
                "ai_duplicate_reviews": ai_result.duplicate_review_count,
                "ai_failure_reasons": list(ai_result.failure_reasons),
                "ai_budget_profile": ai_result.budget_profile,
                "embedding_mode": embedding_result.mode,
            },
        }
        db.session.commit()
        report_progress(
            run,
            "AI_SEMANTIC_ANALYSIS",
            87,
            (
                "AI 语义分析完成 "
                f"{ai_result.analyzed_count}/{ai_result.selected_count}，"
                f"重复候选复核 {ai_result.duplicate_review_count} 对"
                + (
                    f"；失败类型 {', '.join(ai_result.failure_reasons)}"
                    if ai_result.failure_reasons
                    else ""
                )
                if ai_result.configured
                else "未配置 LLM，已跳过 AI 增强并保留基础诊断"
            ),
            level="WARNING" if ai_result.failed_batches else "INFO",
        )
        report_progress(run, "SAVING_REPORT_DATA", 97, "快照已写入本地数据库")

    run.status = "PARTIAL" if ai_result.failed_batches else "SUCCEEDED"
    run.progress_percent = 100
    run.current_stage = "COMPLETED"
    run.finished_at = datetime.now(UTC)
    failed_run_id = run.id
    try:
        AssistantService().rebuild(run)
    except Exception:
        db.session.rollback()
        run = db.session.get(AnalysisRun, failed_run_id)
        if run is not None:
            run.status = "PARTIAL" if ai_result.failed_batches else "SUCCEEDED"
            run.progress_percent = 100
            run.current_stage = "COMPLETED"
            run.finished_at = datetime.now(UTC)
            db.session.commit()
        current_app.logger.exception(
            "Assistant knowledge indexing failed for run %s; report remains available",
            failed_run_id,
        )
    if run is None:
        return
    report_progress(run, "COMPLETED", 100, "基础数据采集完成")


def _update_repository(run: AnalysisRun, metadata: RepositoryData) -> None:
    repository = run.repository
    repository.html_url = metadata.html_url
    repository.default_branch = metadata.default_branch
    repository.primary_language = metadata.language
    repository.stars_count = metadata.stargazers_count
    repository.forks_count = metadata.forks_count
    repository.archived = metadata.archived
    repository.issues_enabled = metadata.has_issues
    repository.last_preflight_at = datetime.now(UTC)
    db.session.commit()


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
