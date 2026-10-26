from issuedoctor.scoring.common import as_utc, median, metric_config, percent, sample_confidence
from issuedoctor.scoring.types import MetricValue, ScoringContext

CLEAR_LABELS = {
    "duplicate": "DUPLICATE_LABEL_OR_COMMENT",
    "invalid": "INVALID",
    "wontfix": "WONTFIX",
    "won't fix": "WONTFIX",
    "stale": "STALE",
}
RESOLUTION_WORDS = ("fixed", "resolved", "implemented", "已修复", "已解决", "完成")


def calculate(context: ScoringContext, config: dict, _labels_config: dict) -> list[MetricValue]:
    dimension = "D5"
    prs = {pr.pr_number: pr for pr in context.pull_requests}
    closed = [issue for issue in context.issues if issue.closed_at is not None]
    reasons = {issue.issue_number: closure_reason(issue, prs, context.evidence) for issue in closed}
    clear = sum(reason != "NO_CLEAR_EVIDENCE" for reason in reasons.values())
    unclear = len(closed) - clear

    linked = [issue for issue in context.issues if issue.linked_pr_numbers_json]
    linked_merged = sum(
        any(
            prs.get(number) and prs[number].merged_at is not None
            for number in issue.linked_pr_numbers_json
        )
        for issue in linked
    )
    merge_days = []
    for issue in context.issues:
        merged_dates = [
            prs[number].merged_at
            for number in issue.linked_pr_numbers_json
            if number in prs and prs[number].merged_at is not None
        ]
        if merged_dates:
            first_merge = min(as_utc(value) for value in merged_dates)
            merge_days.append(
                (first_merge - as_utc(issue.created_at)).total_seconds() / 86400
            )

    source = [
        ("M5.1", percent(clear, len(closed)) if closed else None, len(closed), len(closed) - clear),
        (
            "M5.2",
            percent(linked_merged, len(linked)) if linked else None,
            len(linked),
            len(linked) - linked_merged,
        ),
        ("M5.3", percent(unclear, len(closed)) if closed else None, len(closed), unclear),
    ]
    values = []
    for code, raw, sample, affected in source:
        metric = metric_config(config, dimension, code)
        values.append(
            MetricValue(
                dimension,
                code,
                raw,
                metric["unit"],
                sample,
                raw is not None and sample >= metric["minimum_samples"],
                sample_confidence(sample, metric["minimum_samples"]),
                affected_count=affected,
                details={"reasons": reasons} if code == "M5.3" else {},
            )
        )
    m54 = metric_config(config, dimension, "M5.4")
    applicable = len(merge_days) >= m54["minimum_samples"]
    values.append(
        MetricValue(
            dimension,
            "M5.4",
            median(merge_days) if applicable else None,
            m54["unit"],
            len(merge_days),
            applicable,
            sample_confidence(len(merge_days), m54["minimum_samples"]),
        )
    )
    return values


def closure_reason(issue, pull_requests: dict, evidence: list) -> str:
    for number in issue.linked_pr_numbers_json:
        pr = pull_requests.get(number)
        if pr and pr.merged_at is not None:
            return "MERGED_PR"
    if issue.linked_pr_numbers_json:
        return "LINKED_PR_NOT_MERGED"
    names = {_label_name(label).lower() for label in issue.labels_json}
    for label, reason in CLEAR_LABELS.items():
        if label in names:
            return reason
    related = [item for item in evidence if item.issue_number == issue.issue_number]
    for item in related:
        text = item.excerpt.lower()
        if "duplicate" in text or "重复" in text:
            return "DUPLICATE_LABEL_OR_COMMENT"
        if any(word in text for word in RESOLUTION_WORDS):
            return "MAINTAINER_RESOLUTION_COMMENT"
    return "NO_CLEAR_EVIDENCE"


def _label_name(label: dict | str) -> str:
    return str(label.get("name", "")) if isinstance(label, dict) else str(label)
