from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from issuedoctor.compat import UTC
from issuedoctor.extensions import db


class AIAnalysis(db.Model):
    __tablename__ = "ai_issue_analyses"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "issue_number", name="uq_run_ai_issue"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    input_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    category_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    completeness_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    quality_flags_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    semantic_quality_score: Mapped[float | None] = mapped_column(Float)
    closure_quality_score: Mapped[float | None] = mapped_column(Float)
    semantic_confidence: Mapped[float | None] = mapped_column(Float)
    knowledge_candidate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recommended_action: Mapped[str | None] = mapped_column(String(50))
    evidence_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_response_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
