from issuedoctor.scoring.common import metric_config, percent, sample_confidence
from issuedoctor.scoring.types import MetricValue, ScoringContext


def calculate(context: ScoringContext, config: dict, _labels_config: dict) -> list[MetricValue]:
    dimension = "D6"
    m61 = metric_config(config, dimension, "M6.1")
    high_pairs = [
        pair
        for pair in context.duplicates
        if pair.similarity >= m61["candidate_threshold"]
    ]
    involved = {number for pair in high_pairs for number in (pair.issue_a, pair.issue_b)}
    issue_count = len(context.issues)
    duplicate_applicable = issue_count >= m61["minimum_samples"] and bool(context.duplicates)

    m62 = metric_config(config, dimension, "M6.2")
    clusters: dict[str, set[int]] = {}
    for pair in high_pairs:
        if pair.cluster_id:
            clusters.setdefault(pair.cluster_id, set()).update((pair.issue_a, pair.issue_b))
    clustered = {
        number
        for values in clusters.values()
        if len(values) >= m62["minimum_cluster_size"]
        for number in values
    }
    cluster_applicable = issue_count >= m62["minimum_samples"] and bool(context.duplicates)

    m63 = metric_config(config, dimension, "M6.3")
    infrastructure = infrastructure_score(context.repository_files, m63["infrastructure_points"])

    return [
        MetricValue(
            dimension,
            "M6.1",
            percent(len(involved), issue_count) if duplicate_applicable else None,
            m61["unit"],
            issue_count,
            duplicate_applicable,
            sample_confidence(issue_count, m61["minimum_samples"]) if context.duplicates else 0,
            affected_count=len(involved),
        ),
        MetricValue(
            dimension,
            "M6.2",
            percent(len(clustered), issue_count) if cluster_applicable else None,
            m62["unit"],
            issue_count,
            cluster_applicable,
            sample_confidence(issue_count, m62["minimum_samples"]) if context.duplicates else 0,
            affected_count=len(clustered),
        ),
        MetricValue(
            dimension,
            "M6.3",
            infrastructure,
            m63["unit"],
            1,
            True,
            100,
            affected_count=int(infrastructure < m63["maximum_points"]),
        ),
    ]


def infrastructure_score(files: set[str], points: dict) -> float:
    normalized = {path.replace("\\", "/").lower() for path in files}
    issue_template = any(path.startswith(".github/issue_template/") for path in normalized)
    contributing = any(
        path in {"contributing.md", ".github/contributing.md", "docs/contributing.md"}
        for path in normalized
    )
    issue_config = ".github/issue_template/config.yml" in normalized
    support_or_faq = any("support" in path or "faq" in path for path in normalized)
    triage_docs = any("triage" in path or "issue_guide" in path for path in normalized)
    return sum(
        score
        for present, score in [
            (issue_template, points["issue_template"]),
            (contributing, points["contributing"]),
            (issue_config, points["issue_config"]),
            (support_or_faq, points["support_or_faq"]),
            (triage_docs, points["triage_docs"]),
        ]
        if present
    )
