from io import BytesIO

from flask import Blueprint, Response, send_file

from issuedoctor.errors import IssueDoctorError
from issuedoctor.repositories.analysis_repo import AnalysisRepository
from issuedoctor.services.export_service import ExportService

export_bp = Blueprint("export", __name__)


def _run(run_id: str):
    run = AnalysisRepository.get(run_id)
    if run is None:
        raise IssueDoctorError("ANALYSIS_NOT_FOUND", "找不到该分析任务", status_code=404)
    return run


def _filename(run, extension: str) -> str:
    repository = run.repository.full_name.replace("/", "-")
    return f"issuedoctor-{repository}-{run.id[:8]}.{extension}"


@export_bp.get("/api/analyses/<run_id>/export/json")
def export_analysis_json(run_id: str):
    run = _run(run_id)
    return send_file(
        BytesIO(ExportService.json(run)),
        mimetype="application/json",
        as_attachment=True,
        download_name=_filename(run, "json"),
    )


@export_bp.get("/api/analyses/<run_id>/export/markdown")
def export_analysis_markdown(run_id: str):
    run = _run(run_id)
    return send_file(
        BytesIO(ExportService.markdown(run)),
        mimetype="text/markdown; charset=utf-8",
        as_attachment=True,
        download_name=_filename(run, "md"),
    )


@export_bp.get("/api/analyses/<run_id>/export/pdf")
def export_analysis_pdf(run_id: str):
    run = _run(run_id)
    return send_file(
        BytesIO(ExportService.pdf(run)),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=_filename(run, "pdf"),
    )


@export_bp.get("/analysis/<run_id>/report")
def print_report(run_id: str):
    return Response(ExportService.print_html(_run(run_id)), mimetype="text/html")

