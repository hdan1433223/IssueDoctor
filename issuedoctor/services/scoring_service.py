from flask import current_app

from issuedoctor.extensions import db
from issuedoctor.models import (
    AnalysisRun,
    DimensionScore,
    EvidenceItem,
    Finding,
    MetricResult,
)
from issuedoctor.scoring.engine import ScoringEngine
from issuedoctor.scoring.types import ScoringContext
from issuedoctor.services.config_service import load_yaml


class ScoringService:
    def calculate_and_save(
        self,
        run: AnalysisRun,
        *,
        repository_files: set[str] | None = None,
        duplicates: list | None = None,
    ):
        scoring_config = load_yaml(current_app.config["SCORING_CONFIG_PATH"])
        labels_config = load_yaml(current_app.config["LABELS_CONFIG_PATH"])
        context = ScoringContext(
            issues=list(run.issues),
            pull_requests=list(run.pull_requests),
            evidence=list(run.evidence_items),
            window_start=run.window_start,
            window_end=run.window_end,
            is_truncated=run.is_truncated,
            duplicates=duplicates or [],
            repository_files=repository_files or set(),
        )
        result = ScoringEngine(scoring_config, labels_config).calculate(context)
        self._replace_results(run, result, scoring_config)
        run.scoring_version = str(scoring_config["version"])
        run.scoring_config_json = scoring_config
        run.total_score = result.total_score
        run.confidence_score = result.confidence_score
        db.session.commit()
        return result

    @staticmethod
    def _replace_results(run: AnalysisRun, result, scoring_config: dict) -> None:
        for model in (MetricResult, DimensionScore, Finding):
            db.session.execute(db.delete(model).where(model.analysis_run_id == run.id))
        for metric in result.metrics:
            value = metric.value
            db.session.add(
                MetricResult(
                    analysis_run_id=run.id,
                    dimension_code=value.dimension_code,
                    metric_code=value.metric_code,
                    raw_value=value.raw_value,
                    unit=value.unit,
                    normalized_score=metric.normalized_score,
                    metric_weight=metric.nominal_weight,
                    weighted_points=metric.weighted_points,
                    sample_size=value.sample_size,
                    applicable=value.applicable,
                    confidence=value.confidence,
                    threshold_snapshot_json=metric.threshold_snapshot,
                    explanation_template_key=f"metric.{value.metric_code}.explanation",
                )
            )
            if value.applicable and metric.normalized_score is not None:
                healthy = scoring_config["finding_healthy_score"]
                if metric.normalized_score < healthy:
                    db.session.add(_build_finding(run, metric))
        for dimension in result.dimensions:
            db.session.add(
                DimensionScore(
                    analysis_run_id=run.id,
                    dimension_code=dimension.code,
                    score_0_100=dimension.score,
                    nominal_weight=dimension.nominal_weight,
                    effective_weight=dimension.effective_weight,
                    weighted_points=dimension.weighted_points,
                    applicable_metric_count=dimension.applicable_metric_count,
                    confidence=dimension.confidence,
                )
            )


def _build_finding(run: AnalysisRun, metric) -> Finding:
    value = metric.value
    severity = 100 - metric.normalized_score
    affected_rate = 100 * value.affected_count / max(value.sample_size, 1)
    impact = min(100.0, 0.5 * metric.nominal_weight * 10 + 0.5 * affected_rate)
    priority = 0.45 * severity + 0.35 * impact + 0.20 * value.confidence
    level = "HIGH" if priority >= 75 else "MEDIUM" if priority >= 45 else "LOW"
    evidence_ids = [
        item.id
        for item in db.session.execute(
            db.select(EvidenceItem)
            .where(EvidenceItem.analysis_run_id == run.id)
            .limit(20)
        ).scalars()
    ]
    return Finding(
        analysis_run_id=run.id,
        dimension_code=value.dimension_code,
        finding_code=f"LOW_{value.metric_code}",
        severity_score=round(severity, 2),
        priority_score=round(priority, 2),
        priority_level=level,
        title=f"{value.metric_code} 指标需要改进",
        summary=f"该指标得分为 {metric.normalized_score:.2f}，低于健康阈值。",
        impact_text=f"影响 {value.affected_count}/{value.sample_size} 个样本。",
        recommendation="查看证据并按治理页建议完善 Issue 流程。",
        source_type="RULE",
        metric_code=value.metric_code,
        affected_count=value.affected_count,
        sample_size=value.sample_size,
        evidence_ids_json=evidence_ids,
        status="OPEN",
    )

