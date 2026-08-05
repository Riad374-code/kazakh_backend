"""Small, licence-aware context helpers used by Steps 11 and 12.

The module intentionally accepts plain mappings so it is useful with OSM,
EMODnet and national registry exports without forcing a geospatial dependency.
"""

from __future__ import annotations

import math
from typing import Any, Iterable


def normalize_context(record: dict[str, Any], *, source_name: str) -> dict[str, Any]:
    """Return a stable context record while preserving all original tags."""
    if not isinstance(record, dict) or not source_name.strip():
        raise ValueError("record must be a mapping and source_name must be non-empty")
    tags = dict(record.get("tags") or {})
    identifier = str(record.get("id") or record.get("source_record_id") or "").strip()
    if not identifier:
        raise ValueError("context record requires a source identifier")
    return {
        "context_id": f"{source_name}:{identifier}",
        "source_name": source_name,
        "source_record_id": identifier,
        "geometry": record.get("geometry"),
        "tags": tags,
        "source_authority": record.get("source_authority", source_name),
        "licence": record.get("licence"),
        "location_method": record.get("location_method", "verified"),
        "location_confidence": record.get("location_confidence"),
        "geometry_accuracy": record.get("geometry_accuracy", "verified"),
        "last_verified_at": record.get("last_verified_at"),
        "operating_status": record.get("operating_status"),
    }


def merge_context(records: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Merge by source-specific ID without discarding disagreements."""
    merged: dict[str, dict[str, Any]] = {}
    for raw in records:
        item = dict(raw)
        key = str(item.get("context_id") or item.get("source_record_id") or "")
        if not key:
            raise ValueError("context record requires context_id or source_record_id")
        prior = merged.get(key)
        if prior is None:
            merged[key] = item
            continue
        if prior.get("geometry") != item.get("geometry"):
            conflicts = list(prior.get("geometry_conflicts", []))
            conflicts.append(item.get("geometry"))
            merged[key] = {**prior, "geometry_conflicts": conflicts, "location_method": "inferred"}
    return tuple(merged[key] for key in sorted(merged))


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Distance in metres for EPSG:4326 points."""
    for value in (lon1, lat1, lon2, lat2):
        if not math.isfinite(value):
            raise ValueError("coordinates must be finite")
    radius = 6_371_008.8
    lon_a, lat_a, lon_b, lat_b = map(math.radians, (lon1, lat1, lon2, lat2))
    a = (
        math.sin((lat_b - lat_a) / 2) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin((lon_b - lon_a) / 2) ** 2
    )
    return radius * 2 * math.asin(math.sqrt(min(1.0, a)))
