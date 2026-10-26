from datetime import datetime

from issuedoctor.compat import UTC
from issuedoctor.extensions import db
from issuedoctor.models import AnalysisRun, Repository, TaskEvent


class AnalysisRepository:
    @staticmethod
    def get(run_id: str) -> AnalysisRun | None:
        return db.session.get(AnalysisRun, run_id)

    @staticmethod
    def get_or_create_repository(owner: str, name: str) -> Repository:
        full_name = f"{owner}/{name}"
        repository = db.session.execute(
            db.select(Repository).where(Repository.full_name == full_name)
        ).scalar_one_or_none()
        if repository is None:
            repository = Repository(
                owner=owner,
                name=name,
                full_name=full_name,
                html_url=f"https://github.com/{full_name}",
            )
            db.session.add(repository)
            db.session.flush()
        return repository

    @staticmethod
    def add_event(run: AnalysisRun, stage: str, percent: int, level: str, message: str) -> None:
        run.current_stage = stage
        run.progress_percent = percent
        db.session.add(
            TaskEvent(
                analysis_run_id=run.id,
                stage=stage,
                percent=percent,
                level=level,
                message=message,
            )
        )
        db.session.commit()

    @staticmethod
    def mark_failed(run: AnalysisRun, code: str, message: str) -> None:
        run.status = "FAILED"
        run.finished_at = datetime.now(UTC)
        run.error_code = code
        run.error_message = message
        run.current_stage = "FAILED"
        db.session.commit()
