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
from sqlalchemy.orm import Mapped, mapped_column, relationship

from issuedoctor.extensions import db


class IssueSnapshot(db.Model):
    __tablename__ = "issue_snapshots"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "issue_number", name="uq_run_issue_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    issue_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body_excerpt: Mapped[str] = mapped_column(Text, default="", nullable=False)
    body_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    html_url: Mapped[str] = mapped_column(String(500), nullable=False)
    author_login: Mapped[str] = mapped_column(String(255), nullable=False)
    author_association: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    comments_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    labels_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    first_maintainer_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_maintainer_response_hours: Mapped[float | None] = mapped_column(Float)
    maintainer_response_found: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_maintainer_activity_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    likely_type_rule: Mapped[str | None] = mapped_column(String(50))
    linked_pr_numbers_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    run = relationship("AnalysisRun", back_populates="issues")
