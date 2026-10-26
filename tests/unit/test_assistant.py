import re
from datetime import datetime

from issuedoctor.ai.schemas import AssistantAnswer
from issuedoctor.compat import UTC
from issuedoctor.extensions import db
from issuedoctor.models import (
    AnalysisRun,
    DimensionScore,
    EvidenceItem,
    Finding,
    IssueSnapshot,
    MetricResult,
    Repository,
)
from issuedoctor.models.assistant import AssistantKnowledgeBase, AssistantKnowledgeChunk
from issuedoctor.rag.retrieval import build_context
from issuedoctor.services.assistant_service import AssistantService


def _create_completed_run() -> AnalysisRun:
    now = datetime.now(UTC)
    repository = Repository(
        owner="example",
        name="assistant",
        full_name="example/assistant",
        html_url="https://github.com/example/assistant",
    )
    db.session.add(repository)
    db.session.flush()
    run = AnalysisRun(
        id="00000000-0000-0000-0000-000000000018",
        repository_id=repository.id,
        status="SUCCEEDED",
        mode="AI_ENHANCED",
        progress_percent=100,
        current_stage="COMPLETED",
        created_at=now,
        started_at=now,
        finished_at=now,
        window_start=now,
        window_end=now,
        issue_limit=20,
        pr_limit=20,
        issue_count=1,
        ai_coverage_percent=100,
        total_score=52,
        confidence_score=90,
        scoring_config_json={},
        analysis_config_json={"window_months": 6, "runtime": {"embedding_mode": "hashing"}},
    )
    db.session.add(run)
    db.session.flush()
    db.session.add(
        IssueSnapshot(
            analysis_run_id=run.id,
            issue_number=7,
            title="登录后页面崩溃",
            body_excerpt="在 Windows 上打开设置页并点击保存后崩溃，没有错误日志。",
            body_hash="7" * 64,
            state="closed",
            html_url="https://github.com/example/assistant/issues/7",
            author_login="reporter",
            author_association="NONE",
            created_at=now,
            updated_at=now,
            closed_at=now,
            comments_count=2,
            labels_json=[{"name": "bug"}],
            maintainer_response_found=False,
            linked_pr_numbers_json=[],
        )
    )
    db.session.add(
        MetricResult(
            analysis_run_id=run.id,
            dimension_code="D5",
            metric_code="M5.1",
            raw_value=12.5,
            unit="percent",
            normalized_score=15.0,
            metric_weight=5,
            weighted_points=0.75,
            sample_size=10,
            applicable=True,
            confidence=100,
            threshold_snapshot_json={"points": []},
            explanation_template_key="response",
        )
    )
    db.session.add(
        DimensionScore(
            analysis_run_id=run.id,
            dimension_code="D5",
            score_0_100=26.6,
            nominal_weight=15,
            effective_weight=15,
            weighted_points=4,
            applicable_metric_count=1,
            confidence=100,
        )
    )
    db.session.add(
        Finding(
            analysis_run_id=run.id,
            dimension_code="D5",
            finding_code="LOW_M5.1",
            severity_score=85,
            priority_score=90,
            priority_level="HIGH",
            title="关闭依据不清晰",
            summary="大多数关闭的 Issue 没有可识别的解决依据。",
            impact_text="贡献者无法判断问题是否已经修复。",
            recommendation="关联解决 PR，并在关闭时说明 fixed、duplicate 或 wontfix。",
            source_type="RULE",
            metric_code="M5.1",
            affected_count=8,
            sample_size=10,
            evidence_ids_json=[],
        )
    )
    db.session.add(
        EvidenceItem(
            analysis_run_id=run.id,
            issue_number=7,
            evidence_type="CLOSED_WITHOUT_REASON",
            excerpt="Issue 被关闭，但没有关联 PR 或关闭说明。",
            source_url="https://github.com/example/assistant/issues/7",
            actor_login="maintainer",
            actor_association="MEMBER",
            happened_at=now,
            metadata_json={},
        )
    )
    db.session.commit()
    return run


def test_knowledge_index_is_complete_and_idempotent(app):
    with app.app_context():
        db.create_all()
        run = _create_completed_run()
        service = AssistantService()

        first = service.rebuild(run)
        first_count = db.session.execute(db.select(AssistantKnowledgeChunk)).scalars().all()
        second = service.rebuild(run)
        second_count = db.session.execute(db.select(AssistantKnowledgeChunk)).scalars().all()

        assert first.chunk_count == len(first_count)
        assert second.chunk_count == len(second_count)
        assert len(first_count) == len(second_count)
        assert {
            chunk.source_type for chunk in second_count
        } >= {"overview", "dimension", "finding", "issue", "evidence", "guide"}
        assert db.session.get(AssistantKnowledgeBase, run.id) is not None


def test_extractive_answer_retrieves_report_evidence_without_llm(app):
    with app.app_context():
        db.create_all()
        run = _create_completed_run()

        result = AssistantService().answer(run, "为什么 D5 协作闭环分数低？")

        assert result["mode"] == "extractive"
        assert result["scope"] == "本次报告"
        assert result["sources"]
        assert any(
            source["source_type"] in {"dimension", "finding"}
            for source in result["sources"]
        )
        assert all(
            source["page_url"].startswith(f"/analysis/{run.id}")
            or source["page_url"].startswith("/guide")
            for source in result["sources"]
        )


def test_assistant_refuses_off_topic_questions_without_report_evidence(app):
    with app.app_context():
        db.create_all()
        run = _create_completed_run()

        result = AssistantService().answer(run, "今天天气怎么样？")

        assert result["mode"] == "extractive"
        assert result["sources"] == []
        assert "没有检索到" in result["answer"]


def test_llm_answer_returns_only_cited_sources(app):
    class AnswerClient:
        def __init__(self):
            self.context = ""

        def answer_report_question(
            self,
            _question,
            context,
            _history,
            _system_prompt,
            *,
            max_retries,
        ):
            assert max_retries == 1
            self.context = context
            return AssistantAnswer(
                answer="D5 偏低主要因为关闭依据不足 [K1]。",
                key_points=["优先关联 PR 并补充关闭原因"],
                source_ids=["K1"],
                limitations="回答仅基于本次采集样本。",
            )

    with app.app_context():
        db.create_all()
        run = _create_completed_run()
        client = AnswerClient()

        result = AssistantService(client=client).answer(run, "D5 为什么低？")

        assert result["mode"] == "enhanced"
        assert len(result["sources"]) == 1
        assert result["sources"][0]["label"] == "K1"
        assert "report_context" not in client.context
        assert "[K1]" in client.context


def test_llm_failure_falls_back_to_report_citations(app):
    class FailingClient:
        def answer_report_question(self, *_args, **_kwargs):
            raise RuntimeError("provider unavailable")

    with app.app_context():
        db.create_all()
        run = _create_completed_run()

        result = AssistantService(client=FailingClient()).answer(run, "D5 为什么低？")

        assert result["mode"] == "extractive"
        assert result["sources"]
        assert result["llm_error"]["code"] == "ASSISTANT_LLM_FAILED"
        assert "模型调用失败" in result["limitations"]


def test_action_question_returns_specific_metric_guidance(app):
    with app.app_context():
        db.create_all()
        run = _create_completed_run()

        result = AssistantService().answer(run, "这些问题我要怎么解决？")

        assert result["mode"] == "extractive"
        assert "关闭 Issue 时写明" in "\n".join(result["key_points"])
        assert result["limitations"].startswith("当前没有可用的 LLM 配置")


def test_assistant_limits_context_and_history_for_rate_limited_providers(app):
    with app.app_context():
        db.create_all()
        run = _create_completed_run()
        service = AssistantService()
        service.rebuild(run)
        chunks = db.session.execute(
            db.select(AssistantKnowledgeChunk).where(
                AssistantKnowledgeChunk.analysis_run_id == run.id
            )
        ).scalars().all()
        from issuedoctor.rag.retrieval import retrieve_chunks

        results = retrieve_chunks("列出所有问题", list(chunks), limit=20)
        history = service._normalise_history(
            [{"role": "user", "content": "问" * 2_000} for _ in range(8)]
        )

        assert len(build_context(results)) <= 3_400
        assert len(history) <= 4
        assert all(len(item["content"]) <= 500 for item in history)


def test_assistant_api_validates_scope_and_question(app, client):
    with app.app_context():
        db.create_all()
        run = _create_completed_run()
        run_id = run.id

    response = client.post(
        f"/api/analyses/{run_id}/assistant/query",
        json={"question": "最该先处理什么？", "history": []},
    )
    too_long = client.post(
        f"/api/analyses/{run_id}/assistant/query",
        json={"question": "问" * 2001},
    )

    assert response.status_code == 200
    assert response.get_json()["scope"] == "本次报告"
    assert too_long.status_code == 422
    assert too_long.get_json()["code"] == "ASSISTANT_QUESTION_TOO_LONG"

    with app.app_context():
        run = db.session.get(AnalysisRun, run_id)
        run.status = "RUNNING"
        db.session.commit()
    not_ready = client.post(
        f"/api/analyses/{run_id}/assistant/query",
        json={"question": "总结一下"},
    )
    assert not_ready.status_code == 409
    assert not_ready.get_json()["code"] == "ASSISTANT_REPORT_NOT_READY"


def test_assistant_floats_only_on_completed_report_pages(app, client):
    with app.app_context():
        db.create_all()
        run_id = _create_completed_run().id

    overview = client.get(f"/analysis/{run_id}")
    dimension = client.get(f"/analysis/{run_id}/dimension/D5")
    findings = client.get(f"/analysis/{run_id}/findings")
    evidence = client.get(f"/analysis/{run_id}/evidence")
    ai = client.get(f"/analysis/{run_id}/ai")
    governance = client.get(f"/analysis/{run_id}/governance")
    home = client.get("/")
    progress = client.get(f"/analysis/{run_id}/progress")

    assert 'data-assistant-root' in overview.get_data(as_text=True)
    assert 'data-assistant-panel' in overview.get_data(as_text=True)
    assert 'assistant.js?v=20261023-6' in overview.get_data(as_text=True)
    for response in (dimension, findings, evidence, ai, governance):
        assert response.status_code == 200
        assert 'data-assistant-root' in response.get_data(as_text=True)
        assert 'data-assistant-panel' in response.get_data(as_text=True)
    assert 'data-assistant-root' not in home.get_data(as_text=True)
    assert 'data-assistant-root' not in progress.get_data(as_text=True)


def test_assistant_query_requires_csrf_when_enabled(app, client):
    app.config["WTF_CSRF_ENABLED"] = True
    with app.app_context():
        db.create_all()
        run_id = _create_completed_run().id

    page = client.get(f"/analysis/{run_id}")
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', page.get_data(as_text=True))
    assert match is not None
    rejected = client.post(
        f"/api/analyses/{run_id}/assistant/query",
        json={"question": "D5 为什么低？"},
    )
    accepted = client.post(
        f"/api/analyses/{run_id}/assistant/query",
        json={"question": "D5 为什么低？"},
        headers={"X-CSRFToken": match.group(1)},
    )

    assert rejected.status_code == 400
    assert accepted.status_code == 200
