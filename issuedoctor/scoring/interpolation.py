from collections.abc import Sequence


def _interpolate(value: float, points: Sequence[Sequence[float]]) -> float:
    ordered = sorted((float(x), float(score)) for x, score in points)
    if value <= ordered[0][0]:
        return max(0.0, min(100.0, ordered[0][1]))
    if value >= ordered[-1][0]:
        return max(0.0, min(100.0, ordered[-1][1]))
    for (left_x, left_score), (right_x, right_score) in zip(
        ordered, ordered[1:], strict=False
    ):
        if left_x <= value <= right_x:
            ratio = (value - left_x) / (right_x - left_x)
            score = left_score + ratio * (right_score - left_score)
            return max(0.0, min(100.0, score))
    raise ValueError("评分控制点无效")


def score_lower_is_better(value: float, points: Sequence[Sequence[float]]) -> float:
    return _interpolate(value, points)


def score_higher_is_better(value: float, points: Sequence[Sequence[float]]) -> float:
    return _interpolate(value, points)


def score_value(value: float, config: dict) -> float:
    function = (
        score_lower_is_better
        if config.get("direction") == "lower"
        else score_higher_is_better
    )
    return function(value, config["points"])
