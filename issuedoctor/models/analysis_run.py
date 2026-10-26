from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from issuedoctor.extensions import db


class AnalysisRun(db.Model):
    __tablename__ = "analysis_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING", index=True)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="BASIC")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_stage: Mapped[str] = mapped_column(String(50), default="PENDING", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    window_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issue_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    pr_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pr_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    comment_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_truncated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)
    scoring_config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    analysis_config_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    total_score: Mapped[float | None] = mapped_column(Float)
    confidence_score: Mapped[float | None] = mapped_column(Float)
    ai_coverage_percent: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    ai_semantic_score: Mapped[float | None] = mapped_column(Float)
    ai_semantic_confidence: Mapped[float | None] = mapped_column(Float)
    enhanced_total_score: Mapped[float | None] = mapped_column(Float)
    error_code: Mapped[str | None] = mapped_column(String(100))
    error_message: Mapped[str | None] = mapped_column(Text)

    repository = relationship("Repository", back_populates="analysis_runs")
    issues = relationship("IssueSnapshot", cascade="all, delete-orphan", back_populates="run")
    pull_requests = relationship(
        "PullRequestSnapshot", cascade="all, delete-orphan", back_populates="run"
    )
    evidence_items = relationship(
        "EvidenceItem", cascade="all, delete-orphan", back_populates="run"
    )
    events = relationship("TaskEvent", cascade="all, delete-orphan", back_populates="run")
