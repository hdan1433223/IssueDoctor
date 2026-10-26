from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from issuedoctor import create_app  # noqa: E402
from issuedoctor.compat import UTC  # noqa: E402
from issuedoctor.config import Config  # noqa: E402
from issuedoctor.exports.report_builder import build_report  # noqa: E402
from issuedoctor.extensions import db  # noqa: E402
from issuedoctor.security.input_validation import parse_github_repository_url  # noqa: E402
from issuedoctor.services.analysis_service import create_analysis_run  # noqa: E402
from issuedoctor.services.governance_service import GovernanceService  # noqa: E402
from issuedoctor.tasks.analysis_task import run_analysis  # noqa: E402

DEFAULT_MANIFEST = ROOT / "evaluation" / "cases.yml"
DEFAULT_OUTPUT = ROOT / "evaluation" / "results" / "real_cases"


class EvaluationConfig(Config):
    DATA_DIR = ROOT / "evaluation" / ".runtime"
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{(DATA_DIR / 'evaluation.db').as_posix()}"
    DOCKER_MODE = True
    HTTP_TIMEOUT_SECONDS = 30.0
    TASK_MAX_WORKERS = 1


def run_cases(manifest_path: Path, output_dir: Path, selected: set[str]) -> list[dict]:
    manifest = load_manifest(manifest_path)
    shared = manifest["shared_config"]
    cases = [case for case in manifest["cases"] if not selected or case["id"] in selected]
    if not cases:
        raise ValueError("没有匹配的真实仓库案例")

    output_dir.mkdir(parents=True, exist_ok=True)
    app = create_app(EvaluationConfig)
    rows = []
    with app.app_context():
        db.drop_all()
        db.create_all()
        for case in cases:
            started = time.perf_counter()
            run = create_analysis_run(
                case["repository_url"],
                window_months=shared["window_months"],
                issue_limit=shared["issue_limit"],
                pr_limit=shared["pr_limit"],
            )
            run_analysis(run.id)
            db.session.refresh(run)
            if run.status in {"SUCCEEDED", "PARTIAL"}:
                GovernanceService().generate(run)
            elapsed = time.perf_counter() - started
            payload = build_report(run).model_dump(mode="json")
            payload["evaluation"] = {
                "case_id": case["id"],
                "scale": case["scale"],
                "repository_license": case["license"],
                "source_ref": case["source_ref"],
                "manifest_analysis_date": manifest["analysis_date"],
                "executed_at": datetime.now(UTC).isoformat(),
                "elapsed_seconds": round(elapsed, 3),
                "github_api_calls": run.analysis_config_json.get("runtime", {}).get(
                    "github_api_calls", 0
                ),
                "llm_api_calls": run.analysis_config_json.get("runtime", {}).get(
                    "llm_api_calls", 0
                ),
                "llm_config": shared["llm"],
            }
            (output_dir / f"{case['id']}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            rows.append(_summary_row(case, run, elapsed))
    _write_summary(rows, output_dir)
    return rows


def load_manifest(path: Path | str) -> dict:
    path = Path(path)
    manifest = yaml.safe_load(path.read_text(encoding="utf-8"))
    required = {"schema_version", "analysis_date", "shared_config", "cases"}
    if not isinstance(manifest, dict) or required - set(manifest):
        raise ValueError("真实案例清单结构无效")
    cases = manifest["cases"]
    if not isinstance(cases, list) or not 3 <= len(cases) <= 5:
        raise ValueError("真实案例必须包含 3 到 5 个公开仓库")
    ids = [case.get("id") for case in cases]
    if len(set(ids)) != len(ids):
        raise ValueError("真实案例 id 必须唯一")
    for case in cases:
        parse_github_repository_url(case.get("repository_url", ""))
        if not {"scale", "license", "source_ref"} <= set(case):
            raise ValueError("真实案例必须声明规模、许可证和源码版本")
    shared = manifest["shared_config"]
    if "key" in json.dumps(shared, ensure_ascii=False).lower():
        raise ValueError("评测配置不得包含 Key")
    return manifest


def _summary_row(case: dict, run, elapsed: float) -> dict:
    runtime = run.analysis_config_json.get("runtime", {})
    return {
        "case_id": case["id"],
        "repository": run.repository.full_name,
        "scale": case["scale"],
        "status": run.status,
        "total_score": run.total_score,
        "confidence": run.confidence_score,
        "issue_count": run.issue_count,
        "pr_count": run.pr_count,
        "comment_count": run.comment_count,
        "elapsed_seconds": round(elapsed, 3),
        "github_api_calls": runtime.get("github_api_calls", 0),
        "llm_api_calls": runtime.get("llm_api_calls", 0),
        "error_code": run.error_code or "",
    }


def _write_summary(rows: list[dict], output_dir: Path) -> None:
    with (output_dir / "summary.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output_dir / "summary.json").write_text(
        json.dumps({"schema_version": "1.0", "cases": rows}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 IssueDoctor 真实公开仓库案例")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--case", action="append", default=[], help="只运行指定 case id")
    args = parser.parse_args()
    rows = run_cases(args.manifest, args.output, set(args.case))
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
