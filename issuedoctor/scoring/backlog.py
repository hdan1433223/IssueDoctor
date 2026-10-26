from datetime import timedelta

from issuedoctor.scoring.common import as_utc, median, metric_config, percent, sample_confidence
from issuedoctor.scoring.types import MetricValue, ScoringContext


def calculate(context: ScoringContext, config: dict, _labels_config: dict) -> list[MetricValue]:
    dimension = "D2"
    closed = [issue for issue in context.issues if issue.closed_at is not None]
    close_days = [
        (as_utc(issue.closed_at) - as_utc(issue.created_at)).total_seconds() / 86400
        for issue in closed
    ]
    m21 = metric_config(config, dimension, "M2.1")
    m21_applicable = len(close_days) >= m21["minimum_samples"]

    open_issues = [issue for issue in context.issues if issue.state.lower() == "open"]
    m22 = metric_config(config, dimension, "M2.2")
    long_open = sum(
        as_utc(context.window_end) - as_utc(issue.created_at)
        > timedelta(days=m22["long_open_days"])
        for issue in open_issues
    )

    m23 = metric_config(config, dimension, "M2.3")
    opened_in_window = [
        issue
        for issue in context.issues
        if as_utc(issue.created_at) >= as_utc(context.window_start)
    ]
    closed_in_window = [
        issue
        for issue in context.issues
        if issue.closed_at is not None
        and as_utc(issue.closed_at) >= as_utc(context.window_start)
        and as_utc(issue.closed_at) <= as_utc(context.window_end)
    ]
    window_days = (as_utc(context.window_end) - as_utc(context.window_start)).days
    balance_applicable = (
        window_days >= m23["minimum_window_days"]
        and len(opened_in_window) >= m23["minimum_samples"]
    )
    closure_ratio = len(closed_in_window) / max(len(opened_in_window), 1)

    return [
        MetricValue(
            dimension,
            "M2.1",
            median(close_days) if m21_applicable else None,
            m21["unit"],
            len(close_days),
            m21_applicable,
            sample_confidence(len(close_days), m21["minimum_samples"]),
        ),
        MetricValue(
            dimension,
            "M2.2",
            percent(long_open, len(open_issues)) if open_issues else None,
            m22["unit"],
            len(open_issues),
            len(open_issues) >= m22["minimum_samples"],
            sample_confidence(len(open_issues), m22["minimum_samples"]),
            affected_count=long_open,
        ),
        MetricValue(
            dimension,
            "M2.3",
            closure_ratio if balance_applicable else None,
            m23["unit"],
            len(opened_in_window),
            balance_applicable,
            sample_confidence(len(opened_in_window), m23["minimum_samples"]),
            affected_count=max(len(opened_in_window) - len(closed_in_window), 0),
        ),
    ]
