from issuedoctor.exports.schemas import ReportDTO


def export_json(report: ReportDTO) -> bytes:
    return report.model_dump_json(indent=2).encode("utf-8")

