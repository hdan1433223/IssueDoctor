from typing import Any

from pydantic import BaseModel, ConfigDict


class ReportDTO(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    repository: dict[str, Any]
    analysis_metadata: dict[str, Any]
    analysis_config: dict[str, Any]
    scoring_config: dict[str, Any]
    scores: dict[str, Any]
    metrics: list[dict[str, Any]]
    findings: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    duplicate_summary: list[dict[str, Any]]
    governance_summary: dict[str, Any]
    ai_metadata: dict[str, Any]

