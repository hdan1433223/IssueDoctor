from datetime import timedelta

from issuedoctor.scoring.common import as_utc, median, metric_config, percent, sample_confidence
from issuedoctor.scoring.types import MetricValue, ScoringContext


def calculate(context: ScoringContext, config: dict, _labels_config: dict) -> list[MetricValue]:
    dimension = "D1"
    first_response = [
        float(issue.first_maintainer_response_hours)
        for issue in context.issues
        if issue.maintainer_response_found and issue.first_maintainer_response_hours is not None
    ]
    m11 = metric_config(config, dimension, "M1.1")
    response_applicable = len(first_response) >= m11["minimum_samples"]

    sample = len(context.issues)
    no_response = sum(not issue.maintainer_response_found for issue in context.issues)
    m12 = metric_config(config, dimension, "M1.2")

    m13 = metric_config(config, dimension, "M1.3")
    old_open = [
        issue
        for issue in context.issues
        if issue.state.lower() == "open"
        and as_utc(context.window_end) - as_utc(issue.created_at)
        >= timedelta(days=m13["open_age_days"])
    ]
    inactive_cutoff = as_utc(context.window_end) - timedelta(days=m13["inactive_days"])
    inactive = sum(
        issue.last_maintainer_activity_at is None
        or as_utc(issue.last_maintainer_activity_at) < inactive_cutoff
        for issue in old_open
    )

    return [
        MetricValue(
            dimension,
            "M1.1",
            median(first_response) if response_applicable else None,
            m11["unit"],
            len(first_response),
            response_applicable,
            sample_confidence(len(first_response), m11["minimum_samples"]),
        ),
        MetricValue(
            dimension,
            "M1.2",
            percent(no_response, sample) if sample else None,
            m12["unit"],
            sample,
            sample >= m12["minimum_samples"],
            sample_confidence(sample, m12["minimum_samples"]),
            affected_count=no_response,
        ),
        MetricValue(
            dimension,
            "M1.3",
            percent(inactive, len(old_open)) if old_open else None,
            m13["unit"],
            len(old_open),
            len(old_open) >= m13["minimum_samples"],
            sample_confidence(len(old_open), m13["minimum_samples"]),
            affected_count=inactive,
        ),
    ]

