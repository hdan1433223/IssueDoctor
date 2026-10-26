from datetime import datetime

import pytest

from issuedoctor.ai.batching import BatchItem, build_batches
from issuedoctor.ai.budget import effective_ai_budget
from issuedoctor.ai.client import OpenAICompatibleClient
from issuedoctor.ai.parser import parse_json_response, parse_list_response
from issuedoctor.ai.schemas import (
    DuplicateReviewItem,
    DuplicateReviewResult,
    IssueAnalysisItem,
    IssueBatchResult,
)
from issuedoctor.compat import UTC
from issuedoctor.errors import IssueDoctorError
from issuedoctor.extensions import db
from issuedoctor.models import (
    AIAnalysis,
    AnalysisRun,
    DuplicateCandidate,
    Finding,
    IssueSnapshot,
    Repository,
)
from issuedoctor.security.secrets import LLM_API_KEY
from issuedoctor.services.ai_service import AIService
from issuedoctor.services.config_service import load_yaml
from issuedoctor.services.settings_service import SettingsService

VALID_RESULT = {
    "items": [
        {
            "issue_number": 1,
            "category": "bug",
            "category_confidence": 0.9,
            "missing_information": ["version"],
            "quality_flags": [],
            "semantic_quality_score": 72,
            "closure_quality_score": 65,
            "semantic_confidence": 0.88,
            "knowledge_candidate": 0,
            "recommended_action": "request_more_information",
            "evidence_quotes": ["It crashes immediately."],
            "semantic_summary": "Crash on startup",
            "reason": "The report describes a crash.",
        }
    ]
}


def _create_run_with_issue():
    now = datetime.now(UTC)
    repository = Repository(
        owner="example",
        name="ai",
        full_name="example/ai",
        html_url="https://github.com/example/ai",
    )
    db.session.add(repository)
    db.session.flush()
    run = AnalysisRun(
        id="00000000-0000-0000-0000-000000000004",
        repository_id=repository.id,
        status="RUNNING",
        mode="AI_ENHANCED",
        progress_percent=75,
        current_stage="EMBEDDING_ANALYSIS",
        created_at=now,
        window_start=now,
        window_end=now,
        issue_limit=500,
        pr_limit=500,
        scoring_config_json={},
        analysis_config_json={},
    )
    db.session.add(run)
    db.session.add(
        IssueSnapshot(
            analysis_run_id=run.id,
            issue_number=1,
            title="Bug: startup crash",
            body_excerpt="It crashes immediately.",
            body_hash="1" * 64,
            state="open",
            html_url="https://github.com/example/ai/issues/1",
            author_login="user",
            author_association="NONE",
            created_at=now,
            updated_at=now,
            comments_count=0,
            labels_json=[{"name": "bug"}],
            maintainer_response_found=False,
            linked_pr_numbers_json=[],
        )
    )
    db.session.commit()
    return run


def _add_second_issue(run):
    first = run.issues[0]
    db.session.add(
        IssueSnapshot(
            analysis_run_id=run.id,
            issue_number=2,
            title="Feature request",
            body_excerpt="Please add another option.",
            body_hash="2" * 64,
            state="open",
            html_url="https://github.com/example/ai/issues/2",
            author_login="user2",
            author_association="NONE",
            created_at=first.created_at,
            updated_at=first.updated_at,
            comments_count=0,
            labels_json=[],
            maintainer_response_found=False,
            linked_pr_numbers_json=[],
        )
    )


def test_parser_repairs_fenced_json_and_trailing_commas():
    content = "```json\n" + str(VALID_RESULT).replace("'", '"').replace("}]", "},]") + "\n```"

    result = parse_json_response(content, IssueBatchResult)

    assert result.items[0].issue_number == 1


def test_parser_salvages_complete_items_from_truncated_batch():
    first = __import__("json").dumps(VALID_RESULT["items"][0])
    content = f'{{"items":[{first},{{"issue_number":2,"category":"bug"'

    result = parse_list_response(
        content,
        IssueBatchResult,
        IssueAnalysisItem,
        "items",
    )

    assert [item.issue_number for item in result.items] == [1]


def test_parser_accepts_legacy_item_without_new_optional_fields():
    content = '{"items":[{"issue_number":3,"category":"bug","semantic_summary":"x"}]}'

    result = parse_list_response(
        content,
        IssueBatchResult,
        IssueAnalysisItem,
        "items",
    )

    assert result.items[0].semantic_quality_score is None


def test_client_retries_at_most_configured_limit_and_recovers():
    responses = iter(["not-json", "still not-json", __import__("json").dumps(VALID_RESULT)])
    calls = []

    def requester(messages):
        calls.append(messages)
        return next(responses)

    client = OpenAICompatibleClient("key", "https://example.test/v1", "model", requester=requester)
    result = client.analyze_issue_batch(
        [BatchItem(1, "title", "body")],
        "system",
        "{{ISSUES_JSON}}",
        max_retries=2,
    )

    assert result.items[0].category == "bug"
    assert len(calls) == 3


def test_client_never_exceeds_two_extra_attempts():
    calls = 0

    def requester(_messages):
        nonlocal calls
        calls += 1
        return "invalid"

    client = OpenAICompatibleClient("key", "https://example.test/v1", "model", requester=requester)
    with pytest.raises(IssueDoctorError) as error:
        client.analyze_issue_batch(
            [BatchItem(1, "title", "body")],
            "system",
            "{{ISSUES_JSON}}",
            max_retries=99,
        )

    assert error.value.code == "LLM_RETRY_EXHAUSTED"
    assert calls == 3


def test_client_honors_retry_after_for_rate_limit(monkeypatch):
    class Response:
        status_code = 429
        headers = {"retry-after": "2"}

    class RateLimitError(Exception):
        status_code = 429
        response = Response()

    responses = iter([RateLimitError("limited"), __import__("json").dumps(VALID_RESULT)])
    waits = []

    def requester(_messages):
        result = next(responses)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr("issuedoctor.ai.client.time.sleep", waits.append)
    client = OpenAICompatibleClient("key", "https://example.test/v1", "model", requester=requester)

    result = client.analyze_issue_batch(
        [BatchItem(1, "title", "body")],
        "system",
        "{{ISSUES_JSON}}",
        max_retries=1,
    )

    assert result.items[0].issue_number == 1
    assert waits == [2]


def test_assistant_client_sends_explicit_answer_schema_and_token_limit():
    captured = {}

    def requester(messages, **options):
        captured["messages"] = messages
        captured["options"] = options
        return (
            '{"answer":"模型回答 [K1]","key_points":["要点"],'
            '"source_ids":["K1"],"limitations":""}'
        )

    client = OpenAICompatibleClient(
        "key",
        "https://example.test/v1",
        "model",
        requester=requester,
    )
    result = client.answer_report_question(
        "问题",
        "[K1] 上下文",
        [],
        "system",
        max_retries=0,
    )

    prompt = captured["messages"][-1]["content"]
    assert result.answer == "模型回答 [K1]"
    assert '"answer"' in prompt
    assert '"source_ids"' in prompt
    assert captured["options"] == {"max_tokens": 1_000}


def test_batching_honors_item_and_character_limits():
    items = [BatchItem(number, "t", "x" * 8) for number in range(5)]

    batches = build_batches(items, maximum_items=2, maximum_characters=18)

    assert [len(batch) for batch in batches] == [2, 2, 1]


def test_groq_budget_profile_stays_within_free_tier_guardrails(app):
    with app.app_context():
        config = load_yaml(app.config["ANALYSIS_CONFIG_PATH"])

    budget = effective_ai_budget(config, "https://api.groq.com/openai/v1")

    assert budget["profile"] == "groq-free-safe"
    assert budget["ai_max_issues"] == 30
    assert budget["ai_max_batches"] == 5
    assert budget["max_llm_retries"] == 1

    user_budget = effective_ai_budget(
        config,
        "https://api.groq.com/openai/v1",
        requested_issues=52,
    )
    assert user_budget["ai_max_issues"] == 52
    assert user_budget["ai_max_batches"] == 8


def test_ai_service_skips_cleanly_without_key(app):
    with app.app_context():
        db.create_all()
        run = _create_run_with_issue()

        result = AIService().analyze(run)

        assert result.configured is False
        assert run.ai_coverage_percent == 0


def test_ai_failure_degrades_and_rule_run_survives(app):
    class FailingClient:
        def analyze_issue_batch(self, *_args, **_kwargs):
            raise IssueDoctorError("LLM_TIMEOUT", "timeout")

    with app.app_context():
        db.create_all()
        run = _create_run_with_issue()
        settings = SettingsService()
        settings.secret_store.set(LLM_API_KEY, "secret")
        settings.save(llm_base_url="https://example.test/v1", llm_model="model-a")

        result = AIService(FailingClient()).analyze(run)

        assert result.failed_batches == 1
        assert result.failure_reasons == ("LLM_TIMEOUT",)
        assert result.analyzed_count == 0
        assert run.total_score is None


def test_ai_coverage_uses_all_candidates_as_denominator(app):
    class SuccessfulClient:
        def analyze_issue_batch(self, items, *_args, **_kwargs):
            return IssueBatchResult(
                items=[
                    IssueAnalysisItem.model_validate(
                        {**VALID_RESULT["items"][0], "issue_number": item.issue_number}
                    )
                    for item in items
                ]
            )

    with app.app_context():
        db.create_all()
        run = _create_run_with_issue()
        _add_second_issue(run)
        run.analysis_config_json = {"ai_requested_issue_count": 1}
        settings = SettingsService()
        settings.secret_store.set(LLM_API_KEY, "secret")
        settings.save(llm_base_url="https://example.test/v1", llm_model="model-a")
        db.session.commit()

        result = AIService(SuccessfulClient()).analyze(run)

        assert result.selected_count == 1
        assert result.analyzed_count == 1
        assert run.ai_coverage_percent == 50


def test_ai_service_retries_items_missing_from_partial_batch(app):
    class PartialThenCompleteClient:
        calls = 0

        def analyze_issue_batch(self, items, *_args, **_kwargs):
            self.calls += 1
            returned = items[:1] if self.calls == 1 else items
            return IssueBatchResult(
                items=[
                    IssueAnalysisItem.model_validate(
                        {**VALID_RESULT["items"][0], "issue_number": item.issue_number}
                    )
                    for item in returned
                ]
            )

    with app.app_context():
        db.create_all()
        run = _create_run_with_issue()
        _add_second_issue(run)
        run.analysis_config_json = {"ai_requested_issue_count": 2}
        settings = SettingsService()
        settings.secret_store.set(LLM_API_KEY, "secret")
        settings.save(llm_base_url="https://example.test/v1", llm_model="model-a")
        client = PartialThenCompleteClient()
        db.session.commit()

        result = AIService(client).analyze(run)

        assert client.calls == 2
        assert result.analyzed_count == 2
        assert result.failure_reasons == ()
        assert run.ai_coverage_percent == 100


def test_ai_cache_prevents_repeat_request(app):
    class SuccessfulClient:
        calls = 0

        def analyze_issue_batch(self, *_args, **_kwargs):
            self.calls += 1
            return IssueBatchResult(
                items=[IssueAnalysisItem.model_validate(VALID_RESULT["items"][0])]
            )

    with app.app_context():
        db.create_all()
        run = _create_run_with_issue()
        settings = SettingsService()
        settings.secret_store.set(LLM_API_KEY, "secret")
        settings.save(llm_base_url="https://example.test/v1", llm_model="model-a")
        client = SuccessfulClient()
        run.total_score = 80
        db.session.commit()

        first = AIService(client).analyze(run)
        second = AIService(client).analyze(run)
        analyses = db.session.execute(db.select(AIAnalysis)).scalars().all()

        assert first.analyzed_count == second.analyzed_count == 1
        assert client.calls == 1
        assert len(analyses) == 1
        assert run.ai_semantic_score == 69.38
        assert run.enhanced_total_score == 77.88
        assert {
            finding.metric_code
            for finding in db.session.execute(db.select(Finding)).scalars()
        } == {"AI3.1", "AI5.1"}


def test_ai_reviews_only_prefiltered_duplicate_candidates(app):
    class SuccessfulClient:
        def analyze_issue_batch(self, items, *_args, **_kwargs):
            return IssueBatchResult(
                items=[
                    IssueAnalysisItem.model_validate(
                        {**VALID_RESULT["items"][0], "issue_number": item.issue_number}
                    )
                    for item in items
                ]
            )

        def review_duplicate_batch(self, *_args, **_kwargs):
            return DuplicateReviewResult(
                pairs=[
                    DuplicateReviewItem(
                        issue_a=1,
                        issue_b=2,
                        relation="duplicate",
                        confidence=0.91,
                        reason="问题与期望结果一致。",
                    )
                ]
            )

    with app.app_context():
        db.create_all()
        run = _create_run_with_issue()
        first = run.issues[0]
        db.session.add(
            IssueSnapshot(
                analysis_run_id=run.id,
                issue_number=2,
                title="Bug: startup still crashes",
                body_excerpt="It crashes immediately after launch.",
                body_hash="2" * 64,
                state="open",
                html_url="https://github.com/example/ai/issues/2",
                author_login="user2",
                author_association="NONE",
                created_at=first.created_at,
                updated_at=first.updated_at,
                comments_count=0,
                labels_json=[{"name": "bug"}],
                maintainer_response_found=False,
                linked_pr_numbers_json=[],
            )
        )
        db.session.add(
            DuplicateCandidate(
                analysis_run_id=run.id,
                issue_a=1,
                issue_b=2,
                embedding_model="local-test",
                similarity=0.95,
                candidate_threshold=0.82,
            )
        )
        settings = SettingsService()
        settings.secret_store.set(LLM_API_KEY, "secret")
        settings.save(llm_base_url="https://example.test/v1", llm_model="model-a")
        db.session.commit()

        result = AIService(SuccessfulClient()).analyze(run)
        candidate = db.session.execute(db.select(DuplicateCandidate)).scalar_one()
        ai_duplicate_finding = db.session.execute(
            db.select(Finding).where(Finding.metric_code == "AI6.1")
        ).scalar_one()

        assert result.api_call_count == 2
        assert result.duplicate_review_count == 1
        assert candidate.llm_relation == "duplicate"
        assert ai_duplicate_finding.source_type == "AI"
