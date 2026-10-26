from dataclasses import dataclass

from flask import current_app

from issuedoctor.capabilities import is_available
from issuedoctor.embedding.clustering import assign_clusters
from issuedoctor.embedding.encoder import CachedEncoder, issue_text
from issuedoctor.embedding.model_manager import EmbeddingModelManager
from issuedoctor.embedding.similarity import find_candidates
from issuedoctor.extensions import db
from issuedoctor.models import AnalysisRun, DuplicateCandidate
from issuedoctor.scoring.types import DuplicateValue
from issuedoctor.services.config_service import load_yaml


@dataclass(frozen=True)
class EmbeddingAnalysisResult:
    candidates: list
    scoring_values: list[DuplicateValue]
    mode: str
    warning: str | None = None
    threshold: float = 0.0


def _candidate_threshold(scoring_config: dict, mode: str) -> float:
    """Pick the candidate threshold calibrated for the backend in use.

    The two backends produce similarity scores on different scales, so they must
    not share a threshold. The hashing backend's threshold lives under
    ``candidate_threshold_hashing``; it defaults to the model threshold when a
    custom scoring config omits it.
    """
    metric = scoring_config["dimensions"]["D6"]["metrics"]["M6.1"]
    if mode == "hashing":
        return float(metric.get("candidate_threshold_hashing", metric["candidate_threshold"]))
    return float(metric["candidate_threshold"])


class EmbeddingService:
    """Duplicate-candidate detection.

    Backend selection:

    * ``vector`` capability installed -> local ``sentence-transformers`` model.
    * otherwise -> built-in pure-Python hashing TF-IDF, which needs no
      third-party package and keeps every audit fully reproducible.

    A failure in the model path degrades to the built-in backend rather than
    aborting the audit, because duplicate detection feeds a scored metric.
    """

    def analyze(self, run: AnalysisRun) -> EmbeddingAnalysisResult:
        analysis_config = load_yaml(current_app.config["ANALYSIS_CONFIG_PATH"])
        scoring_config = load_yaml(current_app.config["SCORING_CONFIG_PATH"])
        model_name = analysis_config["embedding_model"]
        issues = sorted(run.issues, key=lambda item: item.issue_number)
        texts = [issue_text(issue, analysis_config["embedding_max_characters"]) for issue in issues]
        numbers = [issue.issue_number for issue in issues]

        prefer_model = is_available("vector")
        mode = "embedding" if prefer_model else "hashing"
        warning = None
        try:
            model_dir = current_app.config["DATA_DIR"] / "models"
            manager = EmbeddingModelManager(model_name, model_dir)
            vectors = CachedEncoder(manager, model_name, prefer_model=prefer_model).encode(texts)
        except Exception as exc:
            db.session.rollback()
            current_app.logger.warning(
                "Embedding unavailable, using built-in hashing TF-IDF: %s",
                type(exc).__name__,
            )
            vectors = CachedEncoder(
                EmbeddingModelManager(model_name, current_app.config["DATA_DIR"] / "models"),
                model_name,
                prefer_model=False,
            ).encode(texts)
            mode = "hashing"
            warning = "本地语义模型不可用，已用内置文本相似度（无需额外依赖）完成分析"

        threshold = _candidate_threshold(scoring_config, mode)
        candidates = assign_clusters(find_candidates(numbers, vectors, threshold))
        self._save(
            run.id,
            candidates,
            model_name if mode == "embedding" else "hashing-tfidf",
            threshold,
        )
        scoring_values = [
            DuplicateValue(
                issue_a=item.issue_a,
                issue_b=item.issue_b,
                similarity=item.similarity,
                cluster_id=item.cluster_id,
            )
            for item in candidates
        ]
        return EmbeddingAnalysisResult(candidates, scoring_values, mode, warning, threshold)

    @staticmethod
    def _save(
        run_id: str,
        candidates: list,
        model_name: str,
        threshold: float,
    ) -> None:
        db.session.execute(
            db.delete(DuplicateCandidate).where(DuplicateCandidate.analysis_run_id == run_id)
        )
        if candidates:
            db.session.add_all(
                DuplicateCandidate(
                    analysis_run_id=run_id,
                    issue_a=item.issue_a,
                    issue_b=item.issue_b,
                    embedding_model=model_name,
                    similarity=item.similarity,
                    candidate_threshold=threshold,
                    cluster_id=item.cluster_id,
                )
                for item in candidates
            )
        db.session.commit()
