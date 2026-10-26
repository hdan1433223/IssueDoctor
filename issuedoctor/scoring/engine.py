from issuedoctor.scoring import backlog, collaboration, issue_quality, knowledge, labels, response
from issuedoctor.scoring.interpolation import score_value
from issuedoctor.scoring.types import (
    ScoredDimension,
    ScoredMetric,
    ScoringContext,
    ScoringResult,
)

CALCULATORS = [
    response.calculate,
    backlog.calculate,
    issue_quality.calculate,
    labels.calculate,
    collaboration.calculate,
    knowledge.calculate,
]


class ScoringEngine:
    def __init__(self, scoring_config: dict, labels_config: dict) -> None:
        self.config = scoring_config
        self.labels_config = labels_config

    def calculate(self, context: ScoringContext) -> ScoringResult:
        values = [
            metric
            for calculator in CALCULATORS
            for metric in calculator(context, self.config, self.labels_config)
        ]
        scored_metrics = []
        dimensions = []
        for dimension_code, dimension_config in self.config["dimensions"].items():
            dimension_values = [value for value in values if value.dimension_code == dimension_code]
            applicable = [value for value in dimension_values if value.applicable]
            applicable_weight = sum(
                dimension_config["metrics"][value.metric_code]["weight"] for value in applicable
            )
            dimension_score = 0.0 if applicable else None
            for value in dimension_values:
                metric_config = dimension_config["metrics"][value.metric_code]
                normalized = (
                    score_value(float(value.raw_value), metric_config)
                    if value.applicable and value.raw_value is not None
                    else None
                )
                points = (
                    normalized * metric_config["weight"] / applicable_weight
                    if normalized is not None and applicable_weight
                    else None
                )
                if points is not None:
                    dimension_score += points
                scored_metrics.append(
                    ScoredMetric(
                        value=value,
                        normalized_score=_round(normalized),
                        nominal_weight=float(metric_config["weight"]),
                        weighted_points=_round(points),
                        threshold_snapshot=dict(metric_config),
                    )
                )
            confidence = (
                sum(value.confidence for value in applicable) / len(applicable) if applicable else 0
            )
            dimensions.append(
                ScoredDimension(
                    code=dimension_code,
                    score=_round(dimension_score),
                    nominal_weight=float(dimension_config["weight"]),
                    effective_weight=0,
                    weighted_points=None,
                    applicable_metric_count=len(applicable),
                    confidence=_round(confidence) or 0,
                )
            )

        applicable_dimensions = [
            dimension for dimension in dimensions if dimension.score is not None
        ]
        total_nominal = sum(dimension.nominal_weight for dimension in applicable_dimensions)
        final_dimensions = []
        for dimension in dimensions:
            effective = (
                100 * dimension.nominal_weight / total_nominal
                if dimension.score is not None and total_nominal
                else 0
            )
            points = dimension.score * effective / 100 if dimension.score is not None else None
            final_dimensions.append(
                ScoredDimension(
                    code=dimension.code,
                    score=dimension.score,
                    nominal_weight=dimension.nominal_weight,
                    effective_weight=_round(effective) or 0,
                    weighted_points=_round(points),
                    applicable_metric_count=dimension.applicable_metric_count,
                    confidence=dimension.confidence,
                )
            )
        total_score = (
            sum(dimension.weighted_points or 0 for dimension in final_dimensions)
            if len(applicable_dimensions) >= 3
            else None
        )
        confidence = self._data_confidence(context, scored_metrics)
        return ScoringResult(
            metrics=scored_metrics,
            dimensions=final_dimensions,
            total_score=_round(total_score),
            confidence_score=_round(confidence) or 0,
        )

    def _data_confidence(self, context: ScoringContext, metrics: list[ScoredMetric]) -> float:
        config = self.config["confidence"]
        applicable = [metric for metric in metrics if metric.value.applicable]
        sample = (
            sum(metric.value.confidence for metric in applicable) / len(applicable)
            if applicable
            else 0
        )
        records = [*context.issues, *context.pull_requests]
        key_fields = (
            100
            * sum(
                bool(getattr(record, "title", "")) and record.created_at is not None
                for record in records
            )
            / len(records)
            if records
            else 0
        )
        truncation = 50 if context.is_truncated else 100
        return (
            sample * config["sample_adequacy_weight"]
            + context.api_completeness * config["api_completeness_weight"]
            + truncation * config["truncation_weight"]
            + key_fields * config["key_fields_weight"]
        ) / 100


def _round(value: float | None) -> float | None:
    return round(value, 2) if value is not None else None
