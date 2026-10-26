from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from issuedoctor.extensions import db


class PullRequestSnapshot(db.Model):
    __tablename__ = "pr_snapshots"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "pr_number", name="uq_run_pr_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    pr_number: Mapped[int] = mapped_column(Integer, nullable=False)
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
    merged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    labels_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    linked_issue_numbers_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    link_method_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    run = relationship("AnalysisRun", back_populates="pull_requests")

