from datetime import datetime

from flask import current_app

from issuedoctor.compat import UTC
from issuedoctor.extensions import db
from issuedoctor.models import AnalysisRun, Repository
from issuedoctor.tasks.manager import TaskManager
from issuedoctor.tasks.recovery import recover_interrupted_runs


def _create_run(status="PENDING"):
    repository = Repository(
        owner="example",
        name="project",
        full_name="example/project",
        html_url="https://github.com/example/project",
    )
    db.session.add(repository)
    db.session.flush()
    now = datetime.now(UTC)
    run = AnalysisRun(
        id="00000000-0000-0000-0000-000000000001",
        repository_id=repository.id,
        status=status,
        mode="BASIC",
        progress_percent=0,
        current_stage=status,
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


def test_task_manager_runs_with_application_context(app):
    manager = TaskManager(app, max_workers=1)

    future = manager.submit("run-id", lambda run_id: (current_app.name, run_id))

    assert future.result(timeout=2) == ("issuedoctor", "run-id")
    manager.shutdown()


def test_recovery_marks_running_analysis_interrupted(app):
    with app.app_context():
        db.create_all()
        run = _create_run("RUNNING")
        run_id = run.id

    assert recover_interrupted_runs(app) == 1

    with app.app_context():
        recovered = db.session.get(AnalysisRun, run_id)
        assert recovered.status == "INTERRUPTED"
        assert recovered.error_code == "ANALYSIS_INTERRUPTED"


def test_create_analysis_returns_id_before_background_work(app, client):
    class FakeTaskManager:
        submitted = []

        def submit(self, run_id):
            self.submitted.append(run_id)

    fake = FakeTaskManager()
    app.extensions["issuedoctor_tasks"] = fake
    with app.app_context():
        db.create_all()

    response = client.post(
        "/api/analyses",
        json={
            "repository_url": "https://github.com/example/project",
            "ai_issue_count": 52,
        },
    )
    payload = response.get_json()

    assert response.status_code == 202
    assert payload["id"] == fake.submitted[0]
    assert payload["status"] == "PENDING"

    with app.app_context():
        run = db.session.get(AnalysisRun, payload["id"])
        assert run.analysis_config_json["ai_requested_issue_count"] == 52

    status = client.get(f"/api/analyses/{payload['id']}/status")
    assert status.status_code == 200
    assert status.get_json()["progress_percent"] == 0
