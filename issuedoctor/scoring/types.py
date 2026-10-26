from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class MetricValue:
    dimension_code: str
    metric_code: str
    raw_value: float | None
    unit: str
    sample_size: int
    applicable: bool
    confidence: float
    affected_count: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DuplicateValue:
    issue_a: int
    issue_b: int
    similarity: float
    cluster_id: str | None = None


@dataclass
class ScoringContext:
    issues: list
    pull_requests: list
    evidence: list
    window_start: datetime
    window_end: datetime
    is_truncated: bool = False
    api_completeness: float = 100.0
    duplicates: list[DuplicateValue] = field(default_factory=list)
    repository_files: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class ScoredMetric:
    value: MetricValue
    normalized_score: float | None
    nominal_weight: float
    weighted_points: float | None
    threshold_snapshot: dict


@dataclass(frozen=True)
class ScoredDimension:
    code: str
    score: float | None
    nominal_weight: float
    effective_weight: float
    weighted_points: float | None
    applicable_metric_count: int
    confidence: float


@dataclass(frozen=True)
class ScoringResult:
    metrics: list[ScoredMetric]
    dimensions: list[ScoredDimension]
    total_score: float | None
    confidence_score: float

