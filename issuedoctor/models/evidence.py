from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from issuedoctor.extensions import db


class EvidenceItem(db.Model):
    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    issue_number: Mapped[int | None] = mapped_column(Integer)
    pr_number: Mapped[int | None] = mapped_column(Integer)
    evidence_type: Mapped[str] = mapped_column(String(100), nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source_url: Mapped[str] = mapped_column(String(500), nullable=False)
    actor_login: Mapped[str | None] = mapped_column(String(255))
    actor_association: Mapped[str | None] = mapped_column(String(50))
    happened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    run = relationship("AnalysisRun", back_populates="evidence_items")

