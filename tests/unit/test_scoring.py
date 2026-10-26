from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest

from issuedoctor.compat import UTC
from issuedoctor.github.pr_linker import link_issues_and_pull_requests
from issuedoctor.scoring.collaboration import closure_reason
from issuedoctor.scoring.engine import ScoringEngine
from issuedoctor.scoring.interpolation import score_value
from issuedoctor.scoring.types import DuplicateValue, ScoringContext
from issuedoctor.services.config_service import load_yaml


def _configs(app):
    return (
        load_yaml(app.config["SCORING_CONFIG_PATH"]),
        load_yaml(app.config["LABELS_CONFIG_PATH"]),
    )


@pytest.mark.parametrize("boundary", ["first", "last"])
def test_every_metric_honors_configured_boundary_points(app, boundary):
    scoring, _ = _configs(app)
    for dimension in scoring["dimensions"].values():
        for metric in dimension["metrics"].values():
            point = metric["points"][0 if boundary == "first" else -1]
            assert score_value(point[0], metric) == point[1]


def test_engine_calculates_all_six_dimensions_deterministically(app):
    scoring, labels = _configs(app)
    now = datetime(2026, 9, 25, tzinfo=UTC)
    body = """### Version
1.0
### Environment
Windows 11
### Steps to reproduce
Run the command
### Expected behavior
It succeeds
### Actual behavior
It crashes
### Logs
Traceback details
### Additional context
Minimal example attached
"""
    issues = []
    pull_requests = []
    for number in range(1, 11):
        created = now - timedelta(days=20 + number)
        closed = created + timedelta(days=5) if number <= 5 else None
        issues.append(
            SimpleNamespace(
                issue_number=number,
                number=number,
                title=f"Bug: crash {number}",
                body=body,
                body_excerpt=body,
                state="closed" if closed else "open",
                html_url=f"https://github.com/a/b/issues/{number}",
                labels_json=[{"name": "bug", "description": "Bug report"}],
                created_at=created,
                updated_at=now,
                closed_at=closed,
                maintainer_response_found=True,
                first_maintainer_response_hours=12,
                last_maintainer_activity_at=now - timedelta(days=2),
                linked_pr_numbers_json=[number] if number <= 5 else [],
            )
        )
        if number <= 5:
            pull_requests.append(
                SimpleNamespace(
                    pr_number=number,
                    number=number,
                    title=f"Fix {number}",
                    body=f"Fixes #{number}",
                    created_at=created + timedelta(days=1),
                    merged_at=created + timedelta(days=4),
                )
            )
    context = ScoringContext(
        issues=issues,
        pull_requests=pull_requests,
        evidence=[],
        window_start=now - timedelta(days=180),
        window_end=now,
        duplicates=[
            DuplicateValue(1, 6, 0.91, "cluster-a"),
            DuplicateValue(2, 6, 0.90, "cluster-a"),
        ],
        repository_files={
            ".github/ISSUE_TEMPLATE/bug.yml",
            ".github/ISSUE_TEMPLATE/config.yml",
            "CONTRIBUTING.md",
            "SUPPORT.md",
            "docs/ISSUE_TRIAGE.md",
        },
    )
    engine = ScoringEngine(scoring, labels)

    first = engine.calculate(context)
    second = engine.calculate(context)

    assert first == second
    assert {item.code for item in first.dimensions} == {f"D{number}" for number in range(1, 7)}
    assert len(first.metrics) == 20
    assert all(item.score is not None for item in first.dimensions)
    assert first.total_score is not None
    assert 0 <= first.total_score <= 100
    assert 0 <= first.confidence_score <= 100


def test_engine_uses_na_and_refuses_total_when_fewer_than_three_dimensions(app):
    scoring, labels = _configs(app)
    now = datetime(2026, 9, 25, tzinfo=UTC)
    result = ScoringEngine(scoring, labels).calculate(
        ScoringContext(
            issues=[],
            pull_requests=[],
            evidence=[],
            window_start=now - timedelta(days=30),
            window_end=now,
        )
    )

    assert result.total_score is None
    assert sum(item.score is not None for item in result.dimensions) < 3
    assert any(not item.value.applicable for item in result.metrics)


def test_pr_linker_records_method_confidence_and_bidirectional_relation():
    issue = SimpleNamespace(number=12, body="Implemented by https://github.com/a/b/pull/4")
    pull_request = SimpleNamespace(number=4, body="Fixes #12")

    result = link_issues_and_pull_requests([issue], [pull_request])

    assert result.issue_to_prs[12] == [4]
    assert result.pr_to_issues[4] == [12]
    assert result.methods_by_pr[4][0] == {
        "issue_number": 12,
        "link_method": "PR_CLOSING_KEYWORD",
        "confidence": 1.0,
    }


@pytest.mark.parametrize(
    ("labels", "linked", "merged", "expected"),
    [
        ([], [1], True, "MERGED_PR"),
        ([], [1], False, "LINKED_PR_NOT_MERGED"),
        ([{"name": "duplicate"}], [], False, "DUPLICATE_LABEL_OR_COMMENT"),
        ([], [], False, "NO_CLEAR_EVIDENCE"),
    ],
)
def test_closure_reason_rules(labels, linked, merged, expected):
    issue = SimpleNamespace(issue_number=2, labels_json=labels, linked_pr_numbers_json=linked)
    pull_requests = {1: SimpleNamespace(merged_at=datetime.now(UTC) if merged else None)}

    assert closure_reason(issue, pull_requests, []) == expected
