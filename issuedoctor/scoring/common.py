import statistics
from datetime import datetime

from issuedoctor.compat import UTC


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def percent(numerator: int, denominator: int) -> float:
    return 100.0 * numerator / denominator if denominator else 0.0


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def sample_confidence(sample_size: int, minimum_samples: int) -> float:
    return min(100.0, 100.0 * sample_size / max(minimum_samples, 1))


def metric_config(scoring_config: dict, dimension: str, metric: str) -> dict:
    return scoring_config["dimensions"][dimension]["metrics"][metric]
