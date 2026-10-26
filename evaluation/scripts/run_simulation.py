from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = ROOT / "evaluation" / "simulation" / "scenarios.csv"
DEFAULT_OUTPUT = ROOT / "evaluation" / "results"
DISCLAIMER = "离线模拟 / controlled simulation；不是该仓库真实部署后的线上结果。"


def calculate_simulation(path: Path) -> tuple[pd.DataFrame, dict]:
    frame = pd.read_csv(path)
    required_columns = {
        "scenario_id",
        "repository_case",
        "ground_truth_type",
        "required_fields",
        "before_captured_fields",
        "after_captured_fields",
        "before_questions",
        "after_questions",
        "before_predicted_type",
        "after_predicted_type",
        "before_minutes",
        "after_minutes",
    }
    missing = required_columns - set(frame.columns)
    if missing:
        raise ValueError(f"模拟数据缺少字段: {sorted(missing)}")
    positive = frame["required_fields"].gt(0)
    if not positive.all():
        raise ValueError("required_fields 必须全部大于 0")
    if frame["scenario_id"].duplicated().any():
        raise ValueError("scenario_id 必须唯一")
    invalid_captured = (
        frame[["before_captured_fields", "after_captured_fields"]].lt(0).any(axis=1)
        | frame["before_captured_fields"].gt(frame["required_fields"])
        | frame["after_captured_fields"].gt(frame["required_fields"])
    )
    if invalid_captured.any():
        raise ValueError("captured_fields 必须位于 0 和 required_fields 之间")
    evaluated = frame.assign(
        before_completeness=frame["before_captured_fields"] / frame["required_fields"],
        after_completeness=frame["after_captured_fields"] / frame["required_fields"],
        before_classification_correct=frame["before_predicted_type"].eq(
            frame["ground_truth_type"]
        ),
        after_classification_correct=frame["after_predicted_type"].eq(
            frame["ground_truth_type"]
        ),
    )
    before = _aggregate(evaluated, "before")
    after = _aggregate(evaluated, "after")
    summary = {
        "schema_version": "1.0",
        "experiment_type": "offline_replay",
        "repository_case": sorted(evaluated["repository_case"].unique().tolist()),
        "scenario_count": len(evaluated),
        "disclaimer": DISCLAIMER,
        "rules": {
            "completeness": "captured_fields / required_fields",
            "follow_up_questions": "缺失的必要信息组数量",
            "classification": "predicted_type == ground_truth_type",
            "time": "预设场景填写计时，单位为分钟",
        },
        "before": before,
        "after": after,
        "delta": {key: after[key] - before[key] for key in before},
        "limitations": [
            "场景为受控离线回放，不是随机对照用户实验。",
            "没有向 pallets/flask 或其他第三方仓库写入任何内容。",
            "结果仅说明预设表单约束在这些场景中的机械差异。",
        ],
    }
    return evaluated, summary


def _aggregate(frame: pd.DataFrame, prefix: str) -> dict[str, float]:
    return {
        "field_completeness": float(frame[f"{prefix}_completeness"].mean()),
        "follow_up_questions": float(frame[f"{prefix}_questions"].mean()),
        "classification_accuracy": float(frame[f"{prefix}_classification_correct"].mean()),
        "completion_minutes": float(frame[f"{prefix}_minutes"].mean()),
    }


def write_results(frame: pd.DataFrame, summary: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    frame.to_csv(output_dir / "simulation_rows.csv", index=False, float_format="%.6f")
    (output_dir / "simulation_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    before, after, delta = summary["before"], summary["after"], summary["delta"]
    metrics_rows = [
        (
            "字段完整率",
            f"{before['field_completeness']:.1%}",
            f"{after['field_completeness']:.1%}",
            f"{delta['field_completeness']:+.1%}",
        ),
        (
            "平均追问数",
            f"{before['follow_up_questions']:.2f}",
            f"{after['follow_up_questions']:.2f}",
            f"{delta['follow_up_questions']:+.2f}",
        ),
        (
            "正确分类率",
            f"{before['classification_accuracy']:.1%}",
            f"{after['classification_accuracy']:.1%}",
            f"{delta['classification_accuracy']:+.1%}",
        ),
        (
            "平均填写时间（分钟）",
            f"{before['completion_minutes']:.2f}",
            f"{after['completion_minutes']:.2f}",
            f"{delta['completion_minutes']:+.2f}",
        ),
    ]
    metrics_table = "\n".join(
        f"| {name} | {old} | {new} | {change} |"
        for name, old, new, change in metrics_rows
    )
    report = f"""# Offline Simulation 报告

> **{DISCLAIMER}**

案例仓库：`pallets/flask`。IssueDoctor 未向该仓库执行任何写操作。

## 方法

采用方案 B 离线回放。对 {summary['scenario_count']} 个预设 Ground Truth 场景，
分别模拟自由文本流程和 IssueDoctor 结构化表单约束。全部数值由脚本从
`scenarios.csv` 计算。

| 指标 | 改进前 | 模拟后 | 差值 |
| --- | ---: | ---: | ---: |
{metrics_table}

## 限制

- 这是受控离线模拟，不是该仓库部署后的线上改善，也不是参与者随机对照实验。
- 场景与计时是固定评测输入，不能外推为所有项目的实际收益。
- 第三方仓库只作为公开流程案例，未被修改。
"""
    (output_dir / "offline_simulation.md").write_text(report, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="运行 IssueDoctor 离线回放模拟")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    frame, summary = calculate_simulation(args.input)
    write_results(frame, summary, args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
