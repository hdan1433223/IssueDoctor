import re

from issuedoctor.scoring.common import metric_config, percent, sample_confidence
from issuedoctor.scoring.types import MetricValue, ScoringContext

HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
MARKDOWN_IMAGE = re.compile(r"!\[[^]]*]\([^)]+\)")
HEADING = re.compile(r"(?m)^#{1,6}\s+\S+")


def calculate(context: ScoringContext, config: dict, labels_config: dict) -> list[MetricValue]:
    dimension = "D3"
    bug_issues = [issue for issue in context.issues if is_bug(issue, labels_config)]
    completeness = [bug_completeness(issue.body_excerpt, labels_config) for issue in bug_issues]
    m31 = metric_config(config, dimension, "M3.1")
    m31_applicable = len(bug_issues) >= m31["minimum_samples"]

    m32 = metric_config(config, dimension, "M3.2")
    low_information = sum(
        is_low_information(issue.body_excerpt, m32["low_information_characters"])
        for issue in context.issues
    )

    m33 = metric_config(config, dimension, "M3.3")
    structured = sum(
        uses_structured_template(issue.body_excerpt, m33["minimum_headings"])
        for issue in context.issues
    )
    issue_count = len(context.issues)

    return [
        MetricValue(
            dimension,
            "M3.1",
            sum(completeness) / len(completeness) if m31_applicable else None,
            m31["unit"],
            len(bug_issues),
            m31_applicable,
            sample_confidence(len(bug_issues), m31["minimum_samples"]),
            affected_count=sum(value < 70 for value in completeness),
        ),
        MetricValue(
            dimension,
            "M3.2",
            percent(low_information, issue_count) if issue_count else None,
            m32["unit"],
            issue_count,
            issue_count >= m32["minimum_samples"],
            sample_confidence(issue_count, m32["minimum_samples"]),
            affected_count=low_information,
        ),
        MetricValue(
            dimension,
            "M3.3",
            percent(structured, issue_count) if issue_count else None,
            m33["unit"],
            issue_count,
            issue_count >= m33["minimum_samples"],
            sample_confidence(issue_count, m33["minimum_samples"]),
            affected_count=issue_count - structured,
        ),
    ]


def is_bug(issue, labels_config: dict) -> bool:
    labels = {_label_name(label).lower() for label in issue.labels_json}
    bug_labels = {value.lower() for value in labels_config["type_groups"]["bug"]}
    title = issue.title.lower()
    return bool(labels & bug_labels) or any(
        keyword.lower() in title for keyword in labels_config["bug_title_keywords"]
    )


def bug_completeness(body: str, labels_config: dict) -> float:
    total = 0.0
    lowered = HTML_COMMENT.sub("", body or "").lower()
    for field in labels_config["bug_fields"].values():
        aliases = [alias.lower() for alias in field["aliases"]]
        if any(_field_has_content(lowered, alias) for alias in aliases):
            total += float(field["weight"])
    return total


def _field_has_content(body: str, alias: str) -> bool:
    escaped = re.escape(alias)
    heading = re.search(rf"(?im)^#{{1,6}}\s*{escaped}\s*:?[ \t]*\n+([^#\n].*)", body)
    inline = re.search(rf"(?im)^{escaped}\s*:\s*(\S.+)$", body)
    return bool(heading or inline)


def is_low_information(body: str, minimum_characters: int) -> bool:
    cleaned = HTML_COMMENT.sub("", body or "")
    cleaned = MARKDOWN_IMAGE.sub("", cleaned)
    cleaned = re.sub(r"[`#>*_\-\s]", "", cleaned)
    return len(cleaned) < minimum_characters


def uses_structured_template(body: str, minimum_headings: int) -> bool:
    cleaned = HTML_COMMENT.sub("", body or "")
    return len(HEADING.findall(cleaned)) >= minimum_headings


def _label_name(label: dict | str) -> str:
    return str(label.get("name", "")) if isinstance(label, dict) else str(label)

