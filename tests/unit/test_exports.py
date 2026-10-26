import json
from datetime import datetime

from issuedoctor.compat import UTC
from issuedoctor.errors import IssueDoctorError
from issuedoctor.exports.json_exporter import export_json
from issuedoctor.exports.markdown_exporter import export_markdown
from issuedoctor.exports.pdf_exporter import export_pdf
from issuedoctor.exports.report_builder import build_report
from issuedoctor.extensions import db
from issuedoctor.models import AnalysisRun, Repository
from issuedoctor.security.secrets import GITHUB_TOKEN, LLM_API_KEY
from issuedoctor.services.settings_service import SettingsService


def _create_run():
    now = datetime.now(UTC)
    repository = Repository(
        owner="example",
        name="export",
        full_name="example/export",
        html_url="https://github.com/example/export",
        default_branch="main",
        primary_language="Python",
    )
    db.session.add(repository)
    db.session.flush()
    run = AnalysisRun(
        id="00000000-0000-0000-0000-000000000007",
        repository_id=repository.id,
        status="SUCCEEDED",
        mode="BASIC",
        progress_percent=100,
        current_stage="COMPLETED",
        created_at=now,
        started_at=now,
        finished_at=now,
        window_start=now,
        window_end=now,
        issue_limit=500,
        pr_limit=500,
        issue_count=10,
        pr_count=2,
        comment_count=5,
        scoring_version="1.0",
        scoring_config_json={"version": "1.0"},
        analysis_config_json={"window_months": 6},
        total_score=81.5,
        confidence_score=92,
        ai_coverage_percent=0,
    )
    db.session.add(run)
    db.session.commit()
    return run


def test_json_and_markdown_share_the_same_report_data_and_no_secrets(app):
    github_secret = "github-export-secret"
    llm_secret = "llm-export-secret"
    with app.app_context():
        db.create_all()
        settings = SettingsService()
        settings.secret_store.set(GITHUB_TOKEN, github_secret)
        settings.secret_store.set(LLM_API_KEY, llm_secret)
        report = build_report(_create_run())
        json_bytes = export_json(report)
        markdown_bytes = export_markdown(report)

    payload = json.loads(json_bytes)
    markdown = markdown_bytes.decode("utf-8")
    combined = json_bytes + markdown_bytes
    assert payload["scores"]["total"] == 81.5
    assert "综合健康度：81.5" in markdown
    assert github_secret.encode() not in combined
    assert llm_secret.encode() not in combined


def test_pdf_renderer_receives_chinese_report_and_returns_pdf_bytes():
    captured = []

    def renderer(html):
        captured.append(html)
        return b"%PDF-1.7\nmock"

    result = export_pdf("<h1>中文报告</h1>", renderer=renderer)

    assert result.startswith(b"%PDF")
    assert captured == ["<h1>中文报告</h1>"]


def test_pdf_availability_reflects_capability_probe():
    from issuedoctor.capabilities import is_available
    from issuedoctor.exports.pdf_exporter import pdf_available

    assert pdf_available() == is_available("pdf")


def test_export_pdf_degrades_with_actionable_error_when_capability_missing():
    """A missing Playwright must yield a clear 503, not an opaque crash."""
    import issuedoctor.exports.pdf_exporter as exporter
    from issuedoctor.capabilities import OptionalDependencyError

    def renderer_requiring_capability(_html):
        raise OptionalDependencyError("pdf")

    try:
        export_pdf("<h1>x</h1>", renderer=renderer_requiring_capability)
    except IssueDoctorError as exc:
        assert exc.code == "PDF_CAPABILITY_MISSING"
        assert exc.status_code == 503
        assert "Playwright" in exc.message
        assert "打印" in exc.message
    else:  # pragma: no cover
        raise AssertionError("expected IssueDoctorError")

    assert exporter.INSTALL_HINTS["pdf"].startswith("pip install")


def test_export_pdf_wraps_unexpected_renderer_failure():
    def broken_renderer(_html):
        raise RuntimeError("browser crashed")

    try:
        export_pdf("<h1>x</h1>", renderer=broken_renderer)
    except IssueDoctorError as exc:
        assert exc.code == "PDF_RENDER_FAILED"
        assert exc.status_code == 500
    else:  # pragma: no cover
        raise AssertionError("expected IssueDoctorError")


def test_export_pdf_passes_through_existing_issue_doctor_error():
    def renderer(_html):
        raise IssueDoctorError("CUSTOM_CODE", "自定义错误", status_code=418)

    try:
        export_pdf("<h1>x</h1>", renderer=renderer)
    except IssueDoctorError as exc:
        assert exc.code == "CUSTOM_CODE"
        assert exc.status_code == 418
    else:  # pragma: no cover
        raise AssertionError("expected IssueDoctorError")


def test_playwright_renderer_raises_optional_dependency_error_when_absent(monkeypatch):
    """The internal renderer must fail fast with the capability error."""
    from issuedoctor.capabilities import OptionalDependencyError
    from issuedoctor.exports.pdf_exporter import _playwright_renderer

    monkeypatch.setattr("issuedoctor.exports.pdf_exporter.is_available", lambda _name: False)
    try:
        _playwright_renderer("<h1>x</h1>")
    except OptionalDependencyError as exc:
        assert exc.capability == "pdf"
    else:  # pragma: no cover
        raise AssertionError("expected OptionalDependencyError")


def test_export_endpoints_use_report_dto(app, client):
    with app.app_context():
        db.create_all()
        run_id = _create_run().id

    response = client.get(f"/api/analyses/{run_id}/export/json")
    print_page = client.get(f"/analysis/{run_id}/report")

    assert response.status_code == 200
    assert response.get_json()["repository"]["full_name"] == "example/export"
    assert print_page.status_code == 200
    assert "执行摘要" in print_page.get_data(as_text=True)
