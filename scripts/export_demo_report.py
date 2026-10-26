from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from issuedoctor import create_app  # noqa: E402
from issuedoctor.extensions import db  # noqa: E402
from issuedoctor.models import AnalysisRun  # noqa: E402
from issuedoctor.services.export_service import ExportService  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="导出最近一次成功分析的演示报告")
    parser.add_argument("--run-id", help="指定分析任务 ID；默认选择最近成功任务")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "exports")
    args = parser.parse_args()
    app = create_app()
    with app.app_context():
        query = db.select(AnalysisRun)
        if args.run_id:
            query = query.where(AnalysisRun.id == args.run_id)
        else:
            query = query.where(AnalysisRun.status.in_(["SUCCEEDED", "PARTIAL"]))
            query = query.order_by(AnalysisRun.created_at.desc()).limit(1)
        run = db.session.execute(query).scalar_one_or_none()
        if run is None:
            raise SystemExit("没有可导出的分析任务")
        args.output.mkdir(parents=True, exist_ok=True)
        stem = f"issuedoctor-{run.repository.full_name.replace('/', '-')}-{run.id[:8]}"
        outputs = {
            args.output / f"{stem}.json": ExportService.json(run),
            args.output / f"{stem}.md": ExportService.markdown(run),
            args.output / f"{stem}.html": ExportService.print_html(run).encode("utf-8"),
            args.output / f"{stem}.pdf": ExportService.pdf(run),
        }
        for path, content in outputs.items():
            path.write_bytes(content)
            print(path)


if __name__ == "__main__":
    main()
