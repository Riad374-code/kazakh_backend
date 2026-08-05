"""Stage 2 transparent weak-label classification baseline."""

from __future__ import annotations

from typing import Any

CLASSES = (
    "oil_hydrocarbon",
    "algal_bloom",
    "river_sediment",
    "industrial_runoff",
    "exposed_contaminated_lakebed",
)


def classify(features: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(features, dict):
        raise ValueError("features must be a mapping")
    scores = {name: 0.0 for name in CLASSES}
    if float(features.get("sar_dark_spot", 0) or 0) > 0:
        scores["oil_hydrocarbon"] += 2
    if float(features.get("chlorophyll", 0) or 0) > float(
        features.get("chlorophyll_baseline", 0) or 0
    ):
        scores["algal_bloom"] += 2
    if float(features.get("turbidity", 0) or 0) > float(features.get("turbidity_baseline", 0) or 0):
        scores["river_sediment"] += 1
    if float(features.get("industrial_distance_m", 1e12) or 1e12) < 5000:
        scores["industrial_runoff"] += 1
    if float(features.get("exposed_bed", 0) or 0) > 0:
        scores["exposed_contaminated_lakebed"] += 2
    top = max(scores, key=scores.get)
    total = sum(scores.values())
    confidence = scores[top] / total if total else 0.0
    return {
        "pollution_type": top if confidence >= 0.5 else "unknown",
        "classification_confidence": confidence,
        "severity": min(1.0, scores[top] / 3),
        "scores": scores,
        "model_version": "weak_rules_v1",
    }
