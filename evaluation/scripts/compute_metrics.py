from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import accuracy_score, precision_recall_fscore_support

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_TRUTH = ROOT / "evaluation" / "annotations" / "ground_truth.csv"
DEFAULT_PREDICTIONS = ROOT / "evaluation" / "annotations" / "predictions.csv"
DEFAULT_OUTPUT = ROOT / "evaluation" / "results"
KEYS = ["task", "item_id"]
ALLOWED_LABELS = {
    "issue_type": {"Bug", "Feature", "Question", "Docs", "Other"},
    "bug_completeness": {"complete", "incomplete"},
    "duplicate_pair": {"duplicate", "distinct"},
    "closure_reason": {"clear", "unclear"},
    "ai_evidence_consistency": {"consistent", "inconsistent"},
}


def calculate_metrics(truth_path: Path, predictions_path: Path) -> tuple[pd.DataFrame, dict]:
    truth = pd.read_csv(truth_path, dtype=str)
    predictions = pd.read_csv(predictions_path, dtype=str)
    _validate(truth, predictions)
    truth = truth.rename(columns={"label": "true_label"})
    predictions = predictions.rename(columns={"label": "predicted_label"})
    merged = truth[KEYS + ["true_label"]].merge(
        predictions[KEYS + ["predicted_label"]],
        on=KEYS,
        how="inner",
        validate="one_to_one",
    )
    rows = []
    for task, frame in merged.groupby("task", sort=True):
        precision, recall, f1, _ = precision_recall_fscore_support(
            frame["true_label"],
            frame["predicted_label"],
            average="macro",
            zero_division=0,
        )
        rows.append(
            {
                "task": task,
                "sample_count": len(frame),
                "accuracy": accuracy_score(frame["true_label"], frame["predicted_label"]),
                "precision_macro": precision,
                "recall_macro": recall,
                "f1_macro": f1,
            }
        )
    table = pd.DataFrame(rows)
    pair_frame = merged.loc[merged["task"].eq("duplicate_pair")]
    pair_precision, pair_recall, pair_f1, _ = precision_recall_fscore_support(
        pair_frame["true_label"].eq("duplicate"),
        pair_frame["predicted_label"].eq("duplicate"),
        average="binary",
        zero_division=0,
    )
    overall = {
        "schema_version": "1.0",
        "sample_count": len(merged),
        "accuracy": float(merged["true_label"].eq(merged["predicted_label"]).mean()),
        "macro_f1_across_tasks": float(table["f1_macro"].mean()),
        "pair_precision": float(pair_precision),
        "pair_recall": float(pair_recall),
        "pair_f1": float(pair_f1),
        "annotator_count": int(truth["annotator"].nunique()),
        "inter_annotator_agreement": None,
        "limitations": "单标注者开发期验收集；结果不代表外部仓库总体性能。",
    }
    return table, overall


def write_results(table: pd.DataFrame, overall: dict, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    table.to_csv(output_dir / "annotation_metrics.csv", index=False, float_format="%.6f")
    payload = {"overall": overall, "by_task": table.to_dict(orient="records")}
    (output_dir / "annotation_metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _validate(truth: pd.DataFrame, predictions: pd.DataFrame) -> None:
    required = {*KEYS, "label", "annotator"}
    for name, frame in (("ground_truth", truth), ("predictions", predictions)):
        missing = required - set(frame.columns)
        if missing:
            raise ValueError(f"{name} 缺少字段: {sorted(missing)}")
        if frame.duplicated(KEYS).any():
            raise ValueError(f"{name} 存在重复 (task, item_id)")
    truth_keys = pd.MultiIndex.from_frame(truth[KEYS])
    prediction_keys = pd.MultiIndex.from_frame(predictions[KEYS])
    if set(truth_keys) != set(prediction_keys):
        raise ValueError("Ground Truth 与预测样本集合不一致")
    unknown_tasks = set(truth["task"]) - set(ALLOWED_LABELS)
    if unknown_tasks:
        raise ValueError(f"存在未知标注任务: {sorted(unknown_tasks)}")
    for name, frame in (("ground_truth", truth), ("predictions", predictions)):
        invalid = frame.loc[
            [
                label not in ALLOWED_LABELS[task]
                for task, label in zip(frame["task"], frame["label"], strict=True)
            ]
        ]
        if not invalid.empty:
            raise ValueError(f"{name} 存在非法标签")


def main() -> None:
    parser = argparse.ArgumentParser(description="计算 IssueDoctor 人工标注指标")
    parser.add_argument("--truth", type=Path, default=DEFAULT_TRUTH)
    parser.add_argument("--predictions", type=Path, default=DEFAULT_PREDICTIONS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    table, overall = calculate_metrics(args.truth, args.predictions)
    write_results(table, overall, args.output)
    print(json.dumps(overall, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
