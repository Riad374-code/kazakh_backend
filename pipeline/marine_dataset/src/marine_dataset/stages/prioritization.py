"""Stage 4 explainable pollution ranking."""

from __future__ import annotations

from typing import Any, Iterable

DEFAULT_WEIGHTS = {
    "size": 0.2,
    "toxicity": 0.2,
    "coast_distance": 0.1,
    "population": 0.1,
    "protected_ecosystems": 0.1,
    "economic_assets": 0.1,
    "fisheries": 0.05,
    "oil_infrastructure": 0.05,
    "international_spread_probability": 0.05,
    "cleanup_cost": 0.025,
    "forecast_confidence": 0.025,
}


def rank_events(
    events: Iterable[dict[str, Any]], weights: dict[str, float] | None = None
) -> tuple[dict[str, Any], ...]:
    chosen = weights or DEFAULT_WEIGHTS
    ranked = []
    for event in events:
        contributions = {
            key: float(event.get(key, 0) or 0) * value for key, value in chosen.items()
        }
        score = sum(contributions.values())
        ranked.append(
            {
                **event,
                "priority_score": score,
                "priority_band": "high" if score >= 0.66 else "medium" if score >= 0.33 else "low",
                "component_contributions": contributions,
                "forecast_confidence": float(event.get("forecast_confidence", 0) or 0),
            }
        )
    return tuple(
        sorted(ranked, key=lambda item: (-item["priority_score"], str(item.get("event_id", ""))))
    )
