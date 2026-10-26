from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from issuedoctor.compat import UTC
from issuedoctor.extensions import db


class GovernancePackage(db.Model):
    __tablename__ = "governance_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    files_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    labels_plan_json: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    workflow_plan_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
    analysis_run = relationship("AnalysisRun")


class GovernanceAction(db.Model):
    __tablename__ = "governance_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    governance_package_id: Mapped[int] = mapped_column(
        ForeignKey("governance_packages.id"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)
    request_payload_redacted_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    confirmation_method: Mapped[str | None] = mapped_column(String(100))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
