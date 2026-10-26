from datetime import datetime

from issuedoctor.compat import UTC
from issuedoctor.extensions import db
from issuedoctor.models import AIAnalysis, AnalysisRun, EvidenceItem, Finding, Repository


def _create_completed_run():
    now = datetime.now(UTC)
    repository = Repository(
        owner="example",
        name="ui",
        full_name="example/ui",
        html_url="https://github.com/example/ui",
    )
    db.session.add(repository)
    db.session.flush()
    run = AnalysisRun(
        id="00000000-0000-0000-0000-000000000005",
        repository_id=repository.id,
        status="SUCCEEDED",
        mode="BASIC",
        progress_percent=100,
        current_stage="COMPLETED",
        created_at=now,
        window_start=now,
        window_end=now,
        issue_limit=500,
        pr_limit=500,
        issue_count=0,
        pr_count=0,
        comment_count=0,
        scoring_config_json={},
        analysis_config_json={},
        confidence_score=75,
        ai_coverage_percent=0,
    )
    db.session.add(run)
    db.session.add(
        EvidenceItem(
            analysis_run_id=run.id,
            issue_number=1,
            evidence_type="MAINTAINER_COMMENT",
            excerpt='<script>alert("xss")</script>',
            source_url="https://github.com/example/ui/issues/1#issuecomment-1",
            actor_login="maintainer",
            actor_association="MEMBER",
            happened_at=now,
            metadata_json={},
        )
    )
    db.session.commit()
    return run.id


def test_overview_history_and_evidence_pages_render_safely(app, client):
    with app.app_context():
        db.create_all()
        run_id = _create_completed_run()

    overview = client.get(f"/analysis/{run_id}")
    history = client.get("/history")
    evidence = client.get(f"/analysis/{run_id}/evidence")

    assert overview.status_code == history.status_code == evidence.status_code == 200
    assert "基础诊断模式" in overview.get_data(as_text=True)
    assert "example/ui" in history.get_data(as_text=True)
    evidence_html = evidence.get_data(as_text=True)
    assert "&lt;script&gt;" in evidence_html
    assert '<script>alert("xss")</script>' not in evidence_html


def test_ai_page_explains_and_displays_structured_results(app, client):
    with app.app_context():
        db.create_all()
        run_id = _create_completed_run()
        run = db.session.get(AnalysisRun, run_id)
        run.mode = "AI_ENHANCED"
        run.ai_coverage_percent = 100
        db.session.add(
            AIAnalysis(
                analysis_run_id=run_id,
                issue_number=7,
                input_hash="1" * 64,
                prompt_version="issue-batch-v1",
                model_name="model-a",
                category="bug",
                category_confidence=0.92,
                completeness_json=["version"],
                quality_flags_json=["missing_reproduction"],
                summary="启动时发生崩溃",
                explanation="正文描述了可重复出现的启动错误。",
                status="SUCCEEDED",
                raw_response_hash="2" * 64,
            )
        )
        db.session.commit()

    response = client.get(f"/analysis/{run_id}/ai")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AI 在硬预算内抽取有代表性的 Issue" in body
    assert "启动时发生崩溃" in body
    assert "缺陷 · 置信度 92%" in body
    assert "版本信息" in body
    assert "正文描述了可重复出现的启动错误" in body


def test_findings_page_shows_dimension_and_metric_names(app, client):
    with app.app_context():
        db.create_all()
        run_id = _create_completed_run()
        db.session.add(
            Finding(
                analysis_run_id=run_id,
                dimension_code="D1",
                finding_code="LOW_M1.1",
                severity_score=60,
                priority_score=72,
                priority_level="HIGH",
                title="M1.1 指标需要改进",
                summary="响应较慢",
                impact_text="贡献者需要等待。",
                recommendation="缩短首次响应时间。",
                source_type="RULE",
                metric_code="M1.1",
                affected_count=3,
                sample_size=10,
                evidence_ids_json=[],
            )
        )
        db.session.commit()

    body = client.get(f"/analysis/{run_id}/findings").get_data(as_text=True)

    assert "D1 响应效率" in body
    assert "M1.1 首次维护者响应中位时间" in body
