"""Stage 1 deterministic multi-sensor anomaly baseline."""

from __future__ import annotations

from statistics import median
from typing import Iterable


def _robust_z(values: list[float], current: float) -> float | None:
    if len(values) < 2:
        return None
    centre = median(values)
    scale = median([abs(value - centre) for value in values])
    if scale == 0:
        return 0.0 if current == centre else float("inf")
    return 0.6745 * (current - centre) / scale


def weekly_anomalies(
    observations: Iterable[dict],
    *,
    value_key: str = "value",
    window: int = 8,
    threshold: float = 3.5,
) -> tuple[dict, ...]:
    if window < 2 or threshold <= 0:
        raise ValueError("window must be >=2 and threshold must be positive")
    ordered = sorted((dict(item) for item in observations), key=lambda item: item["timestamp"])
    result: list[dict] = []
    history: list[float] = []
    for item in ordered:
        value = item.get(value_key)
        score = _robust_z(history[-window:], float(value)) if value is not None else None
        result.append(
            {
                **item,
                "anomaly_score": score,
                "is_anomaly": bool(score is not None and abs(score) >= threshold),
                "algorithm_version": "robust_rolling_z_v1",
            }
        )
        if value is not None:
            history.append(float(value))
    return tuple(result)
