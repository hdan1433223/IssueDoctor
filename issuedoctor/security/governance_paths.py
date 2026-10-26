from pathlib import PurePosixPath

from issuedoctor.errors import IssueDoctorError

EXACT_PATHS = {
    "CONTRIBUTING.md",
    ".github/ISSUE_TRIAGE.md",
    "docs/ISSUE_TRIAGE.md",
    "docs/ISSUE_GUIDE.md",
    ".github/ISSUE_TEMPLATE/config.yml",
}


def validate_governance_path(value: str) -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if path.is_absolute() or ".." in path.parts or normalized != str(path):
        raise IssueDoctorError("GOVERNANCE_PATH_FORBIDDEN", "治理文件路径不在允许范围内")
    issue_form = (
        len(path.parts) == 3
        and path.parts[:2] == (".github", "ISSUE_TEMPLATE")
        and path.suffix.lower() in {".yml", ".yaml", ".md"}
    )
    if normalized not in EXACT_PATHS and not issue_form:
        raise IssueDoctorError("GOVERNANCE_PATH_FORBIDDEN", "治理文件路径不在允许范围内")
    return normalized

