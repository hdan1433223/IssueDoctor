import re
from itertools import combinations

from issuedoctor.scoring.common import metric_config, percent, sample_confidence
from issuedoctor.scoring.types import MetricValue, ScoringContext


def calculate(context: ScoringContext, config: dict, labels_config: dict) -> list[MetricValue]:
    dimension = "D4"
    issue_count = len(context.issues)
    issue_label_names = [
        {_label_name(label) for label in issue.labels_json} for issue in context.issues
    ]
    labeled = sum(bool(names) for names in issue_label_names)

    type_names = {
        _normalize(name)
        for group in labels_config["type_groups"].values()
        for name in group
    }
    type_labeled = sum(
        bool({_normalize(name) for name in names} & type_names) for names in issue_label_names
    )

    unique_labels = _unique_labels(context.issues)
    conflicts = _conflicting_labels(set(unique_labels), labels_config["synonym_groups"])
    involved = {name for pair in conflicts for name in pair}
    described = sum(bool(data.get("description")) for data in unique_labels.values())

    values = [
        (
            "M4.1",
            percent(labeled, issue_count) if issue_count else None,
            issue_count,
            issue_count - labeled,
        ),
        (
            "M4.2",
            percent(type_labeled, issue_count) if issue_count else None,
            issue_count,
            issue_count - type_labeled,
        ),
        (
            "M4.3",
            percent(len(involved), len(unique_labels)) if unique_labels else None,
            len(unique_labels),
            len(involved),
        ),
        (
            "M4.4",
            percent(described, len(unique_labels)) if unique_labels else None,
            len(unique_labels),
            len(unique_labels) - described,
        ),
    ]
    metrics = []
    for code, raw, sample, affected in values:
        metric = metric_config(config, dimension, code)
        metrics.append(
            MetricValue(
                dimension,
                code,
                raw,
                metric["unit"],
                sample,
                raw is not None and sample >= metric["minimum_samples"],
                sample_confidence(sample, metric["minimum_samples"]),
                affected_count=affected,
                details={"conflicts": conflicts} if code == "M4.3" else {},
            )
        )
    return metrics


def _unique_labels(issues: list) -> dict[str, dict]:
    result = {}
    for issue in issues:
        for label in issue.labels_json:
            data = label if isinstance(label, dict) else {"name": str(label), "description": None}
            name = str(data.get("name", ""))
            if name:
                result[name] = data
    return result


def _conflicting_labels(names: set[str], synonym_groups: list[list[str]]) -> list[tuple[str, str]]:
    by_normalized: dict[str, list[str]] = {}
    for name in names:
        by_normalized.setdefault(_normalize(name), []).append(name)
    conflicts = {
        tuple(sorted(pair))
        for values in by_normalized.values()
        for pair in combinations(values, 2)
    }
    for group in synonym_groups:
        normalized_group = {_normalize(item) for item in group}
        matches = [name for name in names if _normalize(name) in normalized_group]
        conflicts.update(tuple(sorted(pair)) for pair in combinations(matches, 2))
    return sorted(conflicts)


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]", "", value.lower())


def _label_name(label: dict | str) -> str:
    return str(label.get("name", "")) if isinstance(label, dict) else str(label)
