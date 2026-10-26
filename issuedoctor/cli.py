"""IssueDoctor command line interface.

Provides a dependency-light way to audit a repository and emit a report without
starting the web server::

    issuedoctor audit owner/repo --format markdown
    issuedoctor audit owner/repo --format json --output report.json
    issuedoctor doctor        # show optional-capability and plugin status

The CLI drives exactly the same collection and scoring services as the web UI,
so results are identical; only the presentation differs.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from issuedoctor.capabilities import capability_report
from issuedoctor.errors import IssueDoctorError
from issuedoctor.plugins import summary as plugin_summary

#: formats accepted by ``audit --format``.
FORMATS = ("markdown", "json", "summary")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="issuedoctor",
        description="GitHub Issue 流程健康度审计与治理工具",
    )
    parser.add_argument("--version", action="version", version="IssueDoctor 0.1.0")
    subparsers = parser.add_subparsers(dest="command")

    audit = subparsers.add_parser("audit", help="审计一个公开 GitHub 仓库")
    audit.add_argument("repository", help="仓库地址或 owner/repo")
    audit.add_argument(
        "--format",
        dest="output_format",
        choices=FORMATS,
        default="markdown",
        help="输出格式（默认 markdown）",
    )
    audit.add_argument("--output", "-o", help="写入文件；省略则打印到标准输出")
    audit.add_argument("--window-months", type=int, help="分析窗口月数")
    audit.add_argument("--issue-limit", type=int, help="最多采集的 Issue 数")
    audit.add_argument("--pr-limit", type=int, help="最多采集的 PR 数")
    audit.add_argument(
        "--no-ai",
        action="store_true",
        help="跳过 LLM 语义增强，仅运行确定性规则评分",
    )

    subparsers.add_parser("doctor", help="显示可选能力与插件状态")
    return parser


def _run_audit(args: argparse.Namespace) -> int:
    from issuedoctor import create_app
    from issuedoctor.services.analysis_service import create_analysis_run
    from issuedoctor.tasks.analysis_task import run_analysis

    app = create_app()
    with app.app_context():
        from issuedoctor.extensions import db

        db.create_all()
        try:
            run = create_analysis_run(
                args.repository,
                window_months=args.window_months,
                issue_limit=args.issue_limit,
                pr_limit=args.pr_limit,
                ai_issue_count=0 if args.no_ai else None,
            )
        except IssueDoctorError as exc:
            print(f"错误：{exc.message}", file=sys.stderr)
            return 2

        run_analysis(run.id)

        from issuedoctor.exports.json_exporter import export_json
        from issuedoctor.exports.markdown_exporter import export_markdown
        from issuedoctor.exports.report_builder import build_report
        from issuedoctor.models import AnalysisRun

        refreshed = db.session.get(AnalysisRun, run.id)
        if refreshed is None:
            print("错误：分析记录丢失", file=sys.stderr)
            return 2
        if refreshed.status == "FAILED":
            print(
                f"分析失败：{refreshed.error_code} {refreshed.error_message}",
                file=sys.stderr,
            )
            return 1

        report = build_report(refreshed)
        if args.output_format == "json":
            payload = export_json(report)
        elif args.output_format == "summary":
            payload = _summary_bytes(report)
        else:
            payload = export_markdown(report)

    text = payload.decode("utf-8")
    if args.output:
        target = Path(args.output)
        target.write_text(text, encoding="utf-8")
        print(f"报告已写入 {target}")
    else:
        print(text)
    return 0


def _summary_bytes(report) -> bytes:
    """Compact one-screen summary for terminal use."""
    repository = report.repository["full_name"]
    scores = report.scores
    lines = [
        f"IssueDoctor 审计摘要：{repository}",
        f"综合健康度：{_fmt(scores['total'])}   数据置信度：{_fmt(scores['confidence'])}",
        f"分析模式：{report.analysis_metadata['mode']}   "
        f"Issue {report.analysis_metadata['issue_count']} / "
        f"PR {report.analysis_metadata['pr_count']}",
        "",
        "六维评分：",
    ]
    for item in scores["dimensions"]:
        lines.append(
            f"  {item['code']}  {_fmt(item['score']):>6}   "
            f"(权重 {item['effective_weight']:.1f}%)"
        )
    if report.findings:
        lines.extend(["", "优先处理的 Findings："])
        for finding in report.findings[:5]:
            lines.append(f"  [{finding['priority_level']}] {finding['title']}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def _fmt(value) -> str:
    return "N/A" if value is None else f"{value:.1f}"


def _run_doctor() -> int:
    print("IssueDoctor 能力自检")
    print("=" * 46)
    capabilities = capability_report()
    for item in capabilities:
        mark = "可用" if item["available"] else "未启用"
        print(f"[{mark}] {item['label']}（{item['name']}）")
        if not item["available"]:
            print(f"        缺少：{'、'.join(item['missing'])}")
            print(f"        启用：{item['install_hint']}")
    print()
    print("插件状态")
    print("-" * 46)
    for item in plugin_summary():
        mark = "可用" if item["available"] else "未启用"
        print(f"[{mark}] {item['label']}（{item['name']}）")
        if item.get("description"):
            print(f"        {item['description']}")
        if not item["available"] and item.get("install_hint"):
            print(f"        启用：{item['install_hint']}")
    print()
    print("核心诊断（采集 / 六维评分 / 报告 / Web 界面）始终可用。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "doctor":
        return _run_doctor()
    if args.command == "audit":
        return _run_audit(args)
    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
