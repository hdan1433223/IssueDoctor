"""Tests for the command line interface.

The CLI is a documented, user-facing entry point that reuses the same services
as the web UI. These tests cover argument parsing, the ``doctor`` self-check,
the summary formatter, and the ``audit`` result handling including its error
paths.
"""

from types import SimpleNamespace

import pytest

from issuedoctor.cli import FORMATS, _build_parser, _fmt, _run_audit, _summary_bytes, main
from issuedoctor.config import Config
from issuedoctor.errors import IssueDoctorError

# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------


def test_no_command_parses_to_none():
    assert _build_parser().parse_args([]).command is None


def test_audit_defaults():
    args = _build_parser().parse_args(["audit", "owner/repo"])
    assert args.command == "audit"
    assert args.repository == "owner/repo"
    assert args.output_format == "markdown"
    assert args.output is None
    assert args.no_ai is False
    assert args.window_months is None
    assert args.issue_limit is None
    assert args.pr_limit is None


def test_audit_accepts_all_flags():
    args = _build_parser().parse_args(
        [
            "audit",
            "https://github.com/owner/repo",
            "--format",
            "json",
            "--output",
            "out.json",
            "--window-months",
            "3",
            "--issue-limit",
            "120",
            "--pr-limit",
            "80",
            "--no-ai",
        ]
    )
    assert args.output_format == "json"
    assert args.output == "out.json"
    assert args.window_months == 3
    assert args.issue_limit == 120
    assert args.pr_limit == 80
    assert args.no_ai is True


def test_every_declared_format_is_accepted():
    parser = _build_parser()
    for name in FORMATS:
        assert parser.parse_args(["audit", "owner/repo", "--format", name]).output_format == name


def test_unknown_format_is_rejected():
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["audit", "owner/repo", "--format", "xml"])


def test_version_flag_exits():
    with pytest.raises(SystemExit):
        _build_parser().parse_args(["--version"])


# --------------------------------------------------------------------------
# main() dispatch
# --------------------------------------------------------------------------


def test_main_without_command_prints_help(capsys):
    assert main([]) == 0
    assert "audit" in capsys.readouterr().out


def test_doctor_reports_core_availability(capsys):
    assert main(["doctor"]) == 0
    captured = capsys.readouterr().out
    assert "能力自检" in captured
    assert "核心诊断" in captured
    assert "插件状态" in captured


def test_doctor_lists_each_capability(capsys):
    main(["doctor"])
    captured = capsys.readouterr().out
    assert "本地语义向量" in captured
    assert "服务端 PDF 导出" in captured


# --------------------------------------------------------------------------
# Summary formatting
# --------------------------------------------------------------------------


def test_fmt_handles_none_and_numbers():
    assert _fmt(None) == "N/A"
    assert _fmt(81.5) == "81.5"
    assert _fmt(0) == "0.0"


def _fake_report(**overrides):
    report = SimpleNamespace(
        repository={"full_name": "example/project"},
        analysis_metadata={"mode": "BASIC", "issue_count": 12, "pr_count": 4},
        scores={
            "total": 81.5,
            "confidence": 92.0,
            "dimensions": [
                {"code": "D1", "score": 88.0, "effective_weight": 20.0},
                {"code": "D6", "score": None, "effective_weight": 10.0},
            ],
        },
        findings=[
            {"priority_level": "HIGH", "title": "D3 指标需要改进"},
            {"priority_level": "MEDIUM", "title": "D6 指标需要改进"},
        ],
    )
    for key, value in overrides.items():
        setattr(report, key, value)
    return report


def test_summary_contains_repository_and_scores():
    text = _summary_bytes(_fake_report()).decode("utf-8")
    assert "example/project" in text
    assert "81.5" in text
    assert "92.0" in text
    assert "D1" in text
    assert "N/A" in text  # the None score for D6


def test_summary_lists_findings():
    text = _summary_bytes(_fake_report()).decode("utf-8")
    assert "HIGH" in text
    assert "D3 指标需要改进" in text


def test_summary_without_findings_omits_section():
    report = _fake_report(findings=[])
    text = _summary_bytes(report).decode("utf-8")
    assert "优先处理的 Findings" not in text


def test_summary_is_utf8_bytes():
    payload = _summary_bytes(_fake_report())
    assert isinstance(payload, bytes)
    payload.decode("utf-8")  # must not raise


# --------------------------------------------------------------------------
# audit execution
# --------------------------------------------------------------------------


@pytest.fixture()
def cli_config(tmp_path, monkeypatch):
    """Point the CLI at a throwaway database and avoid the system keyring."""
    monkeypatch.setattr(Config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        Config,
        "SQLALCHEMY_DATABASE_URI",
        f"sqlite:///{(tmp_path / 'cli.db').as_posix()}",
    )
    # DOCKER_MODE selects the environment-backed secret store, which keeps the
    # CLI test off the real Windows Credential Manager.
    monkeypatch.setattr(Config, "DOCKER_MODE", True)
    return tmp_path


def test_audit_rejects_invalid_repository(cli_config, capsys):
    args = _build_parser().parse_args(["audit", "not-a-repository"])
    assert _run_audit(args) == 2
    assert "错误" in capsys.readouterr().err


def test_audit_writes_markdown_report(cli_config, monkeypatch, capsys):
    _mock_successful_pipeline(monkeypatch, status="SUCCEEDED")
    target = cli_config / "report.md"

    args = _build_parser().parse_args(
        ["audit", "owner/repo", "--format", "markdown", "--output", str(target)]
    )
    assert _run_audit(args) == 0
    assert target.exists()
    assert "报告已写入" in capsys.readouterr().out


def test_audit_prints_to_stdout_when_no_output_file(cli_config, monkeypatch, capsys):
    _mock_successful_pipeline(monkeypatch, status="SUCCEEDED")
    args = _build_parser().parse_args(["audit", "owner/repo", "--format", "summary"])

    assert _run_audit(args) == 0
    assert "审计摘要" in capsys.readouterr().out


def test_audit_supports_json_format(cli_config, monkeypatch, capsys):
    _mock_successful_pipeline(monkeypatch, status="SUCCEEDED")
    target = cli_config / "report.json"
    args = _build_parser().parse_args(
        ["audit", "owner/repo", "--format", "json", "--output", str(target)]
    )

    assert _run_audit(args) == 0
    import json

    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["repository"]["full_name"] == "owner/repo"


def test_audit_returns_one_when_analysis_failed(cli_config, monkeypatch, capsys):
    _mock_successful_pipeline(monkeypatch, status="FAILED")
    args = _build_parser().parse_args(["audit", "owner/repo"])

    assert _run_audit(args) == 1
    assert "分析失败" in capsys.readouterr().err


def test_audit_no_ai_disables_ai_budget(cli_config, monkeypatch):
    """--no-ai must pass an explicit zero AI count through to the run record."""
    captured = {}
    _mock_successful_pipeline(monkeypatch, status="SUCCEEDED", captured=captured)

    args = _build_parser().parse_args(["audit", "owner/repo", "--no-ai"])
    _run_audit(args)

    assert captured["ai_issue_count"] == 0


def test_audit_passes_limits_through(cli_config, monkeypatch):
    captured = {}
    _mock_successful_pipeline(monkeypatch, status="SUCCEEDED", captured=captured)

    args = _build_parser().parse_args(
        ["audit", "owner/repo", "--issue-limit", "33", "--pr-limit", "44", "--window-months", "3"]
    )
    _run_audit(args)

    assert captured["issue_limit"] == 33
    assert captured["pr_limit"] == 44
    assert captured["window_months"] == 3


def _mock_successful_pipeline(monkeypatch, *, status: str, captured: dict | None = None):
    """Stub the network and background stages, keeping the real DB flow."""
    from issuedoctor.extensions import db
    from issuedoctor.models import AnalysisRun
    from issuedoctor.services import analysis_service
    from issuedoctor.tasks import analysis_task

    captured = captured if captured is not None else {}
    real_create = analysis_service.create_analysis_run

    def create_stub(repository_url, **kwargs):
        captured.update(kwargs)
        captured["repository_url"] = repository_url
        return real_create(repository_url, **kwargs)

    monkeypatch.setattr(analysis_service, "create_analysis_run", create_stub)

    def run_stub(run_id):
        run = db.session.get(AnalysisRun, run_id)
        run.status = status
        run.progress_percent = 100
        run.current_stage = "COMPLETED"
        run.total_score = 81.5
        run.confidence_score = 92.0
        if status == "FAILED":
            run.error_code = "GITHUB_REPO_NOT_FOUND"
            run.error_message = "仓库不存在"
        db.session.commit()

    monkeypatch.setattr(analysis_task, "run_analysis", run_stub)


def test_run_audit_handles_missing_run_record(cli_config, monkeypatch, capsys):
    """A vanished run record must be reported, not crash."""
    from issuedoctor.services import analysis_service

    monkeypatch.setattr(
        analysis_service,
        "create_analysis_run",
        lambda *_a, **_k: SimpleNamespace(id="does-not-exist"),
    )
    from issuedoctor.tasks import analysis_task

    monkeypatch.setattr(analysis_task, "run_analysis", lambda _id: None)

    args = _build_parser().parse_args(["audit", "owner/repo"])
    assert _run_audit(args) == 2
    assert "丢失" in capsys.readouterr().err


def test_run_audit_reports_service_error(cli_config, monkeypatch, capsys):
    from issuedoctor.services import analysis_service

    def boom(*_a, **_k):
        raise IssueDoctorError("INVALID_ANALYSIS_CONFIG", "分析范围超出允许值")

    monkeypatch.setattr(analysis_service, "create_analysis_run", boom)

    args = _build_parser().parse_args(["audit", "owner/repo"])
    assert _run_audit(args) == 2
    assert "分析范围超出允许值" in capsys.readouterr().err
