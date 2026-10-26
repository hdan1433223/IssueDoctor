from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from issuedoctor.compat import UTC
from issuedoctor.extensions import db


class TaskEvent(db.Model):
    __tablename__ = "task_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    stage: Mapped[str] = mapped_column(String(50), nullable=False)
    percent: Mapped[int] = mapped_column(Integer, nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False
    )

    run = relationship("AnalysisRun", back_populates="events")
