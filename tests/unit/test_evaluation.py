"""Evaluation-harness tests.

These exercise the evaluation measurement scripts, which depend on the
``dev`` extra (pandas + scikit-learn). They are skipped when that tooling is
absent so the core suite still runs in a minimal installation.
"""

import json

import pytest

pd = pytest.importorskip("pandas", reason="评估脚本需要 dev 依赖（pandas）")
pytest.importorskip("sklearn", reason="评估脚本需要 dev 依赖（scikit-learn）")

from evaluation.scripts.compute_metrics import (  # noqa: E402
    calculate_metrics,
)
from evaluation.scripts.compute_metrics import write_results as write_metric_results  # noqa: E402
from evaluation.scripts.run_real_cases import load_manifest  # noqa: E402
from evaluation.scripts.run_simulation import (  # noqa: E402
    DISCLAIMER,
    calculate_simulation,
)
from evaluation.scripts.run_simulation import (  # noqa: E402
    write_results as write_simulation_results,
)


def test_annotation_metrics_are_generated_from_matching_samples(tmp_path):
    truth = tmp_path / "truth.csv"
    predictions = tmp_path / "predictions.csv"
    pd.DataFrame(
        [
            {"task": "duplicate_pair", "item_id": "1|2", "label": "duplicate", "annotator": "A1"},
            {"task": "duplicate_pair", "item_id": "2|3", "label": "distinct", "annotator": "A1"},
        ]
    ).to_csv(truth, index=False)
    pd.DataFrame(
        [
            {
                "task": "duplicate_pair",
                "item_id": "1|2",
                "label": "duplicate",
                "annotator": "system",
            },
            {
                "task": "duplicate_pair",
                "item_id": "2|3",
                "label": "distinct",
                "annotator": "system",
            },
        ]
    ).to_csv(predictions, index=False)

    table, overall = calculate_metrics(truth, predictions)
    write_metric_results(table, overall, tmp_path)

    assert overall["accuracy"] == 1.0
    assert overall["pair_recall"] == 1.0
    content = (tmp_path / "annotation_metrics.json").read_text(encoding="utf-8")
    assert json.loads(content)["overall"]["sample_count"] == 2


def test_simulation_outputs_disclaimer_and_calculated_deltas(tmp_path):
    source = tmp_path / "simulation.csv"
    pd.DataFrame(
        [
            {
                "scenario_id": "S1",
                "repository_case": "example/repo",
                "ground_truth_type": "Bug",
                "required_fields": 4,
                "before_captured_fields": 2,
                "after_captured_fields": 4,
                "before_questions": 2,
                "after_questions": 0,
                "before_predicted_type": "Other",
                "after_predicted_type": "Bug",
                "before_minutes": 4,
                "after_minutes": 6,
            }
        ]
    ).to_csv(source, index=False)

    frame, summary = calculate_simulation(source)
    write_simulation_results(frame, summary, tmp_path)

    assert summary["delta"]["field_completeness"] == 0.5
    assert DISCLAIMER in (tmp_path / "offline_simulation.md").read_text(encoding="utf-8")


def test_real_case_manifest_has_three_to_five_valid_public_repositories():
    manifest = load_manifest("evaluation/cases.yml")

    assert len(manifest["cases"]) == 3
    assert all(
        case["repository_url"].startswith("https://github.com/")
        for case in manifest["cases"]
    )
