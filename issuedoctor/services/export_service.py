from flask import render_template

from issuedoctor.exports.json_exporter import export_json
from issuedoctor.exports.markdown_exporter import export_markdown
from issuedoctor.exports.pdf_exporter import export_pdf
from issuedoctor.exports.report_builder import build_report
from issuedoctor.models import AnalysisRun


class ExportService:
    @staticmethod
    def json(run: AnalysisRun) -> bytes:
        return export_json(build_report(run))

    @staticmethod
    def markdown(run: AnalysisRun) -> bytes:
        return export_markdown(build_report(run))

    @staticmethod
    def print_html(run: AnalysisRun) -> str:
        return render_template("exports/report_print.html", report=build_report(run))

    @classmethod
    def pdf(cls, run: AnalysisRun) -> bytes:
        return export_pdf(cls.print_html(run))

