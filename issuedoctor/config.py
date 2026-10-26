import os
from pathlib import Path
from typing import Any


def _default_data_dir() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "IssueDoctor"
    return Path.home() / ".local" / "share" / "IssueDoctor"


class Config:
    SECRET_KEY = os.environ.get("ISSUEDOCTOR_SECRET_KEY", "issuedoctor-local-development")
    DATA_DIR = Path(os.environ.get("ISSUEDOCTOR_DATA_DIR", _default_data_dir()))
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "ISSUEDOCTOR_DATABASE_URL",
        f"sqlite:///{(DATA_DIR / 'issuedoctor.db').as_posix()}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_AS_ASCII = False
    WTF_CSRF_TIME_LIMIT = None
    TEMPLATES_AUTO_RELOAD = True
    DOCKER_MODE = os.environ.get("ISSUEDOCTOR_DOCKER", "").lower() in {"1", "true", "yes"}
    GITHUB_API_URL = "https://api.github.com"
    HTTP_TIMEOUT_SECONDS = 10.0
    ANALYSIS_CONFIG_PATH = Path(__file__).parent.parent / "config" / "analysis.default.yml"
    SCORING_CONFIG_PATH = Path(__file__).parent.parent / "config" / "scoring.default.yml"
    LABELS_CONFIG_PATH = Path(__file__).parent.parent / "config" / "labels.default.yml"
    TASK_MAX_WORKERS = 1

    @staticmethod
    def ensure_runtime_directories(config: dict[str, Any]) -> None:
        data_dir = Path(config["DATA_DIR"])
        for name in ("logs", "cache", "models", "reports", "exports"):
            (data_dir / name).mkdir(parents=True, exist_ok=True)
