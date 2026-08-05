"""Versioned, explainable weak-label rules for pollution-type bootstrapping."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WeakLabelEvidence:
    sar_dark: bool = False
    chlorophyll_z: float | None = None
    turbidity_z: float | None = None
    cdom_z: float | None = None
    river_distance_km: float | None = None
    industrial_distance_km: float | None = None
    exposed_lakebed: bool = False


@dataclass(frozen=True)
class WeakLabelResult:
    pollution_type: str
    segmentation_class_id: int | None
    rule_id: str
    rule_version: str
    evidence: tuple[str, ...]
    uncertainty: str
    is_weak_label: bool = True
    is_machine_generated: bool = True
    verification_status: str = "unverified"


def classify_weak_label(evidence: WeakLabelEvidence, *, rule_version: str) -> WeakLabelResult:
    rules = (
        (
            evidence.exposed_lakebed,
            "exposed_contaminated_lakebed",
            "lakebed_exposure",
            ("exposed_lakebed",),
        ),
        (
            (evidence.chlorophyll_z or 0) >= 2.0,
            "algal_bloom",
            "chlorophyll_anomaly",
            ("chlorophyll_z>=2",),
        ),
        (
            (evidence.turbidity_z or 0) >= 2.0
            and _distance_within(evidence.river_distance_km, 10.0),
            "river_sediment",
            "turbidity_near_river",
            ("turbidity_z>=2", "river_distance_km<=10"),
        ),
        (
            max(evidence.turbidity_z or 0, evidence.cdom_z or 0) >= 2.0
            and _distance_within(evidence.industrial_distance_km, 10.0),
            "industrial_runoff",
            "water_quality_near_industry",
            ("water_quality_z>=2", "industrial_distance_km<=10"),
        ),
        (evidence.sar_dark, "oil_or_hydrocarbon", "sar_dark_candidate", ("sar_dark",)),
    )
    for matched, pollution_type, rule_id, signals in rules:
        if matched:
            segmentation_id = {"oil_or_hydrocarbon": 2, "algal_bloom": 5}.get(pollution_type)
            return WeakLabelResult(
                pollution_type, segmentation_id, rule_id, rule_version, signals, "low"
            )
    return WeakLabelResult("unknown", None, "no_rule_match", rule_version, (), "unknown")


def _distance_within(distance_km: float | None, threshold_km: float) -> bool:
    return distance_km is not None and distance_km <= threshold_km
