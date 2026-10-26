from issuedoctor.models import AnalysisRun
from issuedoctor.repositories.analysis_repo import AnalysisRepository


def report_progress(
    run: AnalysisRun,
    stage: str,
    percent: int,
    message: str,
    *,
    level: str = "INFO",
) -> None:
    AnalysisRepository.add_event(run, stage, max(0, min(percent, 100)), level, message)

