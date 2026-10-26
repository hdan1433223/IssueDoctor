from datetime import datetime, timedelta

from issuedoctor.compat import UTC
from issuedoctor.extensions import db
from issuedoctor.github.schemas import CommentData, IssueData
from issuedoctor.models import AnalysisRun, EvidenceItem, IssueSnapshot, Repository
from issuedoctor.repositories.snapshot_repo import SnapshotRepository


def _create_run(now):
    repository = Repository(
        owner="example",
        name="project",
        full_name="example/project",
        html_url="https://github.com/example/project",
    )
    db.session.add(repository)
    db.session.flush()
    run = AnalysisRun(
        id="00000000-0000-0000-0000-000000000002",
        repository_id=repository.id,
        status="PENDING",
        mode="BASIC",
        progress_percent=0,
        current_stage="PENDING",
        created_at=now,
        window_start=now,
        window_end=now,
        issue_limit=500,
        pr_limit=500,
        scoring_config_json={},
        analysis_config_json={},
    )
    db.session.add(run)
    db.session.commit()
    return run


def test_snapshot_computes_first_maintainer_response_and_keeps_only_evidence(app):
    created_at = datetime(2026, 9, 1, tzinfo=UTC)
    issue = IssueData.model_validate(
        {
            "number": 7,
            "title": "Failure",
            "body": "A" * 7000,
            "state": "open",
            "html_url": "https://github.com/example/project/issues/7",
            "user": {"login": "reporter"},
            "author_association": "NONE",
            "created_at": created_at,
            "updated_at": created_at,
            "comments": 2,
            "labels": [],
        }
    )
    comments = [
        CommentData.model_validate(
            {
                "id": index,
                "issue_url": "https://api.github.com/repos/example/project/issues/7",
                "html_url": f"https://github.com/example/project/issues/7#issuecomment-{index}",
                "body": body,
                "user": {"login": actor},
                "author_association": association,
                "created_at": created_at + timedelta(hours=hours),
                "updated_at": created_at + timedelta(hours=hours),
            }
        )
        for index, actor, association, hours, body in [
            (1, "visitor", "CONTRIBUTOR", 1, "me too"),
            (2, "maintainer", "MEMBER", 4, "Thanks, we are investigating"),
        ]
    ]

    with app.app_context():
        db.create_all()
        run = _create_run(created_at)
        SnapshotRepository.replace(run.id, [issue], [], comments)
        snapshot = db.session.execute(db.select(IssueSnapshot)).scalar_one()
        evidence = db.session.execute(db.select(EvidenceItem)).scalars().all()

        assert snapshot.first_maintainer_response_hours == 4
        assert snapshot.maintainer_response_found is True
        assert len(snapshot.body_excerpt) == 6000
        assert [item.actor_login for item in evidence] == ["maintainer"]
