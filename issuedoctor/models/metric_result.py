from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from issuedoctor.extensions import db


class MetricResult(db.Model):
    __tablename__ = "metric_results"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "metric_code", name="uq_run_metric_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    dimension_code: Mapped[str] = mapped_column(String(10), nullable=False)
    metric_code: Mapped[str] = mapped_column(String(20), nullable=False)
    raw_value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(50), nullable=False)
    normalized_score: Mapped[float | None] = mapped_column(Float)
    metric_weight: Mapped[float] = mapped_column(Float, nullable=False)
    weighted_points: Mapped[float | None] = mapped_column(Float)
    sample_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    applicable: Mapped[bool] = mapped_column(Boolean, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    threshold_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    explanation_template_key: Mapped[str] = mapped_column(String(100), nullable=False)


class DimensionScore(db.Model):
    __tablename__ = "dimension_scores"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "dimension_code", name="uq_run_dimension_code"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    dimension_code: Mapped[str] = mapped_column(String(10), nullable=False)
    score_0_100: Mapped[float | None] = mapped_column(Float)
    nominal_weight: Mapped[float] = mapped_column(Float, nullable=False)
    effective_weight: Mapped[float] = mapped_column(Float, nullable=False)
    weighted_points: Mapped[float | None] = mapped_column(Float)
    applicable_metric_count: Mapped[int] = mapped_column(Integer, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)

