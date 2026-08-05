"""Stage 6 asset-risk aggregation without rendering dependencies."""

from __future__ import annotations

from typing import Any, Iterable


def risk_heatmap(
    cells: Iterable[dict[str, Any]], events: Iterable[dict[str, Any]]
) -> tuple[dict[str, Any], ...]:
    event_rows = tuple(dict(event) for event in events)
    result = []
    for cell in cells:
        score = sum(
            float(event.get("severity", 0) or 0) * float(event.get("probability", 0) or 0)
            for event in event_rows
        )
        result.append(
            {
                **cell,
                "risk": score,
                "threat_band": "high" if score >= 0.66 else "medium" if score >= 0.33 else "low",
                "contributing_event_ids": tuple(
                    event.get("event_id")
                    for event in event_rows
                    if event.get("event_id") is not None
                ),
                "risk_version": "weighted_event_v1",
            }
        )
    return tuple(result)
