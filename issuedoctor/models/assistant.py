from datetime import datetime

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from issuedoctor.compat import UTC
from issuedoctor.extensions import db


class AssistantKnowledgeBase(db.Model):
    __tablename__ = "assistant_knowledge_bases"

    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id"), primary_key=True
    )
    index_version: Mapped[str] = mapped_column(String(20), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    analysis_run = relationship("AnalysisRun")


class AssistantKnowledgeChunk(db.Model):
    __tablename__ = "assistant_knowledge_chunks"
    __table_args__ = (
        UniqueConstraint(
            "analysis_run_id",
            "source_key",
            name="uq_run_assistant_source_key",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_key: Mapped[str] = mapped_column(String(160), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    vector_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    rank_boost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
