"""Small QA and reliability scorer for manifest rows (Step 14)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

QUALITY_FIELDS = (
    "satellite_quality_score",
    "label_quality_score",
    "weather_match_score",
    "ocean_match_score",
    "vessel_data_quality_score",
    "infrastructure_quality_score",
)


@dataclass(frozen=True)
class Check:
    name: str
    severity: str
    passed: bool
    evidence: str
    remediation: str


def score_row(row: dict[str, Any], *, weights: dict[str, float] | None = None) -> dict[str, Any]:
    chosen = {field: float(row[field]) for field in QUALITY_FIELDS if row.get(field) is not None}
    if any(value < 0 or value > 1 for value in chosen.values()):
        raise ValueError("quality scores must be between 0 and 1")
    effective = weights or {field: 1.0 for field in QUALITY_FIELDS}
    numerator = sum(chosen[field] * effective.get(field, 0.0) for field in chosen)
    denominator = sum(effective.get(field, 0.0) for field in chosen)
    overall = numerator / denominator if denominator else None
    return {
        **row,
        "overall_sample_quality_score": overall,
        "quality_formula": "weighted_available_modalities_v1",
        "quality_missing": tuple(field for field in QUALITY_FIELDS if field not in chosen),
    }


def validate_rows(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(row) for row in rows]
    checks: list[Check] = []
    checks.append(
        Check(
            "rows_present",
            "critical",
            bool(materialized),
            str(len(materialized)),
            "provide at least one row",
        )
    )
    checks.append(
        Check(
            "relative_paths",
            "critical",
            all(not str(row.get("path", "")).startswith(("/", "\\")) for row in materialized),
            "path policy",
            "use relative artifact paths",
        )
    )
    checks.append(
        Check(
            "stable_ids",
            "critical",
            all(row.get("tile_id") or row.get("scene_id") for row in materialized),
            "identifier presence",
            "add stable scene/tile IDs",
        )
    )
    failures = [check for check in checks if not check.passed]
    return {
        "status": "fail" if any(check.severity == "critical" for check in failures) else "pass",
        "checks": tuple(check.__dict__ for check in checks),
        "failed_count": len(failures),
        "denominator": len(materialized),
    }
