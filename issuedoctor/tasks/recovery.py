from datetime import datetime

from flask import Flask
from sqlalchemy.exc import OperationalError

from issuedoctor.compat import UTC
from issuedoctor.extensions import db
from issuedoctor.models import AnalysisRun


def recover_interrupted_runs(app: Flask) -> int:
    try:
        with app.app_context():
            runs = db.session.execute(
                db.select(AnalysisRun).where(AnalysisRun.status == "RUNNING")
            ).scalars()
            count = 0
            for run in runs:
                run.status = "INTERRUPTED"
                run.current_stage = "INTERRUPTED"
                run.finished_at = datetime.now(UTC)
                run.error_code = "ANALYSIS_INTERRUPTED"
                run.error_message = "应用重启导致分析中断，可以重新发起分析"
                count += 1
            db.session.commit()
            return count
    except OperationalError:
        return 0
