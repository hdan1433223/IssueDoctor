from typing import Literal

from pydantic import BaseModel, Field, field_validator


class IssueAnalysisItem(BaseModel):
    issue_number: int
    category: Literal["bug", "feature", "question", "docs", "support", "other"]
    category_confidence: float = Field(default=0.5, ge=0, le=1)
    missing_information: list[str] = Field(default_factory=list)
    quality_flags: list[str] = Field(default_factory=list)
    semantic_quality_score: float | None = Field(default=None, ge=0, le=100)
    closure_quality_score: float | None = Field(default=None, ge=0, le=100)
    semantic_confidence: float | None = Field(default=None, ge=0, le=1)
    knowledge_candidate: bool = False
    recommended_action: Literal[
        "none",
        "request_more_information",
        "add_or_fix_label",
        "link_pull_request",
        "review_as_duplicate",
        "document_or_faq",
        "review_closure",
    ] = "none"
    evidence_quotes: list[str] = Field(default_factory=list)
    semantic_summary: str = Field(default="", max_length=1000)
    reason: str = Field(default="", max_length=2000)

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, value: str) -> str:
        candidate = str(value).strip().lower()
        aliases = {
            "documentation": "docs",
            "doc": "docs",
            "enhancement": "feature",
            "help": "support",
        }
        normalized = aliases.get(candidate, candidate)
        allowed = {"bug", "feature", "question", "docs", "support"}
        return normalized if normalized in allowed else "other"

    @field_validator("recommended_action", mode="before")
    @classmethod
    def normalize_action(cls, value: str | None) -> str:
        candidate = str(value or "none").strip().lower()
        allowed = {
            "none",
            "request_more_information",
            "add_or_fix_label",
            "link_pull_request",
            "review_as_duplicate",
            "document_or_faq",
            "review_closure",
        }
        return candidate if candidate in allowed else "none"

    @field_validator(
        "missing_information",
        "quality_flags",
        "evidence_quotes",
        mode="before",
    )
    @classmethod
    def normalize_lists(cls, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [str(item)[:300] for item in value[:20]]


class IssueBatchResult(BaseModel):
    items: list[IssueAnalysisItem]


class DuplicateReviewItem(BaseModel):
    issue_a: int
    issue_b: int
    relation: Literal["duplicate", "strongly_related", "related", "unrelated"]
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(max_length=2000)


class DuplicateReviewResult(BaseModel):
    pairs: list[DuplicateReviewItem]


class AssistantAnswer(BaseModel):
    answer: str = Field(min_length=1, max_length=6000)
    key_points: list[str] = Field(default_factory=list, max_length=8)
    source_ids: list[str] = Field(default_factory=list, max_length=12)
    limitations: str = Field(default="", max_length=1000)

    @field_validator("key_points", "source_ids", mode="before")
    @classmethod
    def normalize_string_list(cls, value) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = [value]
        if not isinstance(value, list):
            return []
        return [str(item).strip()[:500] for item in value if str(item).strip()][:12]
