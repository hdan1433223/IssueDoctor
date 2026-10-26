from sqlalchemy import Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from issuedoctor.extensions import db


class DuplicateCandidate(db.Model):
    __tablename__ = "duplicate_candidates"
    __table_args__ = (
        UniqueConstraint("analysis_run_id", "issue_a", "issue_b", name="uq_run_duplicate_pair"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    analysis_run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id"), nullable=False)
    issue_a: Mapped[int] = mapped_column(Integer, nullable=False)
    issue_b: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(255), nullable=False)
    similarity: Mapped[float] = mapped_column(Float, nullable=False)
    candidate_threshold: Mapped[float] = mapped_column(Float, nullable=False)
    cluster_id: Mapped[str | None] = mapped_column(String(100))
    llm_relation: Mapped[str | None] = mapped_column(String(30))
    llm_confidence: Mapped[float | None] = mapped_column(Float)
    llm_reason: Mapped[str | None] = mapped_column(Text)

