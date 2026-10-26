from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evaluation" / "results"


def main() -> None:
    required = [
        RESULTS / "annotation_metrics.csv",
        RESULTS / "annotation_metrics.json",
        RESULTS / "simulation_rows.csv",
        RESULTS / "simulation_summary.json",
        RESULTS / "offline_simulation.md",
        RESULTS / "real_cases" / "summary.csv",
        RESULTS / "real_cases" / "summary.json",
    ]
    missing = [str(path.relative_to(ROOT)) for path in required if not path.is_file()]
    if missing:
        raise SystemExit(f"评测结果缺失: {missing}")
    simulation = json.loads((RESULTS / "simulation_summary.json").read_text(encoding="utf-8"))
    disclaimer = simulation.get("disclaimer", "")
    if "不是该仓库真实部署后的线上结果" not in disclaimer:
        raise SystemExit("离线模拟缺少强制非线上结果声明")
    cases = json.loads((RESULTS / "real_cases" / "summary.json").read_text(encoding="utf-8"))[
        "cases"
    ]
    if len(cases) < 3 or any(case["status"] not in {"SUCCEEDED", "PARTIAL"} for case in cases):
        raise SystemExit("真实仓库案例不足 3 个或存在未成功案例")
    print("evaluation results: OK")


if __name__ == "__main__":
    main()
