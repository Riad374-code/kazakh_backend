"""Compact offline implementations for Steps 11-24.

These functions consume JSON-like records and never invent provider data.
External downloads remain explicit commands from Steps 04-05.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from statistics import median
from typing import Any, Iterable


def normalize_context(record: dict[str, Any], source: str) -> dict[str, Any]:
    record_id = str(record.get("id") or record.get("source_record_id") or "").strip()
    if not record_id or not source.strip():
        raise ValueError("context records need a source and identifier")
    return {
        "context_id": f"{source}:{record_id}",
        "source": source,
        "source_record_id": record_id,
        "geometry": record.get("geometry"),
        "tags": dict(record.get("tags") or {}),
        "location_confidence": record.get("location_confidence"),
        "licence": record.get("licence"),
        "status": record.get("status", "unknown"),
    }


def filter_vessels(
    rows: Iterable[dict[str, Any]], start: str | None = None, end: str | None = None
) -> tuple[dict[str, Any], ...]:
    result = []
    for row in rows:
        item = dict(row)
        if start and str(item.get("observed_at", "")) < start:
            continue
        if end and str(item.get("observed_at", "")) > end:
            continue
        result.append(item)
    return tuple(result)


def _stable_bucket(value: str, seed: int) -> float:
    return int(hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()[:12], 16) / 16**12


def assign_splits(
    rows: Iterable[dict[str, Any]], strategy: str = "group_by_scene", seed: int = 42
) -> tuple[dict[str, Any], ...]:
    allowed = {
        "group_by_scene",
        "group_by_incident",
        "spatial_holdout",
        "temporal_holdout",
        "region_holdout",
        "combined_spatiotemporal_holdout",
    }
    if strategy not in allowed:
        raise ValueError(f"unsupported split strategy: {strategy}")
    result = []
    for row in rows:
        item = dict(row)
        key = strategy.removeprefix("group_by_")
        group = str(item.get(key) or item.get("scene_id") or item.get("tile_id") or "")
        if not group:
            raise ValueError("each row needs a stable group identifier")
        bucket = _stable_bucket(group, seed)
        item.update(
            {
                "group_id": group,
                "split_strategy": strategy,
                "split": "test" if bucket < 0.2 else "val" if bucket < 0.4 else "train",
            }
        )
        result.append(item)
    return tuple(result)


def leakage_report(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    seen: dict[tuple[str, str], str] = {}
    violations = []
    materialized = list(rows)
    for row in materialized:
        for field in ("scene_id", "incident_id", "product_id", "label_id"):
            value = row.get(field)
            if value is None:
                continue
            key = (field, str(value))
            prior = seen.get(key)
            if prior and prior != row.get("split"):
                violations.append({"field": field, "value": str(value)})
            seen[key] = str(row.get("split"))
    return {
        "status": "fail" if violations else "pass",
        "rows": len(materialized),
        "violations": violations,
    }


def quality_report(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = list(rows)
    checks = {
        "rows_present": bool(materialized),
        "stable_ids": all(row.get("scene_id") or row.get("tile_id") for row in materialized),
        "relative_paths": all(
            not str(row.get("path", "")).startswith(("/", "\\")) for row in materialized
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "status": "fail" if failed else "pass",
        "checks": checks,
        "failed": failed,
        "rows": len(materialized),
    }


def anomalies(
    rows: Iterable[dict[str, Any]],
    value_key: str = "value",
    window: int = 8,
    threshold: float = 3.5,
) -> tuple[dict[str, Any], ...]:
    if window < 2 or threshold <= 0:
        raise ValueError("window must be >=2 and threshold must be positive")
    history: list[float] = []
    result = []
    for row in sorted((dict(item) for item in rows), key=lambda item: item.get("timestamp", "")):
        value = row.get(value_key)
        score = None
        if value is not None and len(history) >= 2:
            centre = median(history[-window:])
            scale = median(abs(item - centre) for item in history[-window:])
            score = (
                0.0
                if scale == 0 and float(value) == centre
                else (float("inf") if scale == 0 else 0.6745 * (float(value) - centre) / scale)
            )
        result.append(
            {
                **row,
                "anomaly_score": score,
                "is_anomaly": score is not None and abs(score) >= threshold,
            }
        )
        if value is not None:
            history.append(float(value))
    return tuple(result)


def classify(features: dict[str, Any]) -> dict[str, Any]:
    scores = {
        name: 0.0
        for name in (
            "oil_hydrocarbon",
            "algal_bloom",
            "river_sediment",
            "industrial_runoff",
            "exposed_contaminated_lakebed",
        )
    }
    if features.get("sar_dark_spot"):
        scores["oil_hydrocarbon"] += 2
    if float(features.get("chlorophyll", 0) or 0) > float(
        features.get("chlorophyll_baseline", 0) or 0
    ):
        scores["algal_bloom"] += 2
    if float(features.get("turbidity", 0) or 0) > float(features.get("turbidity_baseline", 0) or 0):
        scores["river_sediment"] += 1
    if float(features.get("industrial_distance_m", math.inf)) < 5000:
        scores["industrial_runoff"] += 1
    if features.get("exposed_bed"):
        scores["exposed_contaminated_lakebed"] += 2
    label = max(scores, key=scores.get)
    confidence = scores[label] / sum(scores.values()) if sum(scores.values()) else 0.0
    return {
        "pollution_type": label if confidence >= 0.5 else "unknown",
        "confidence": confidence,
        "severity": min(1.0, scores[label] / 3),
        "scores": scores,
    }


def forecast(
    start: dict[str, float],
    wind_u: float = 0.0,
    wind_v: float = 0.0,
    days: tuple[int, ...] = (7, 14, 30),
) -> dict[str, Any]:
    paths = []
    for day in days:
        seconds = day * 86400
        paths.append(
            {
                "days": day,
                "lon": start["lon"] + wind_u * seconds / 111320,
                "lat": start["lat"] + wind_v * seconds / 110540,
                "probability": min(1.0, 0.5 + day / 100),
            }
        )
    return {"origin": start, "paths": paths, "model": "persistence_advection_v1"}


def prioritize(events: Iterable[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    fields = (
        "size",
        "toxicity",
        "population",
        "protected_ecosystems",
        "economic_assets",
        "international_spread_probability",
        "forecast_confidence",
    )
    result = []
    for event in events:
        score = sum(float(event.get(field, 0) or 0) for field in fields) / len(fields)
        result.append(
            {
                **event,
                "priority_score": score,
                "priority": "high" if score >= 0.66 else "medium" if score >= 0.33 else "low",
            }
        )
    return tuple(
        sorted(result, key=lambda item: (-item["priority_score"], str(item.get("event_id", ""))))
    )


def energy_impact(event: dict[str, Any], cost_per_unit: float | None = None) -> dict[str, Any]:
    if cost_per_unit is None:
        return {
            "status": "not_estimated",
            "event_id": event.get("event_id"),
            "missing": ["verified_coefficient"],
        }
    exposure = float(event.get("severity", 0) or 0) * float(event.get("asset_exposure", 0) or 0)
    return {
        "status": "scenario",
        "event_id": event.get("event_id"),
        "energy_impact_score": min(1.0, exposure),
        "estimated_cost": exposure * cost_per_unit,
    }


def risk_heatmap(
    cells: Iterable[dict[str, Any]], events: Iterable[dict[str, Any]]
) -> tuple[dict[str, Any], ...]:
    total = sum(
        float(event.get("severity", 0) or 0) * float(event.get("probability", 0) or 0)
        for event in events
    )
    return tuple(
        {
            **cell,
            "risk": total,
            "threat": "high" if total >= 0.66 else "medium" if total >= 0.33 else "low",
        }
        for cell in cells
    )


def api_response(data: Any, version: str = "1", missing: tuple[str, ...] = ()) -> dict[str, Any]:
    return {
        "contract_version": version,
        "data": data,
        "missing_inputs": missing,
        "limitations": ["predictions are not observations"],
    }


def dataset_card(path: Path, version: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"# Marine dataset\n\nVersion: `{version}`\n\nSAR dark regions are not automatically oil. Predictions and weak labels require human review.\n",
        encoding="utf-8",
    )
    return path


def acceptance_report(root: Path) -> dict[str, Any]:
    files = sorted(str(path.relative_to(root)) for path in root.rglob("*") if path.is_file())
    return {
        "status": "pass" if files else "blocked",
        "files": files,
        "bytes": sum((root / name).stat().st_size for name in files),
    }


def read_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("rows", payload.get("items", []))
    if not isinstance(rows, list):
        raise ValueError("JSON must be a list or contain rows/items")
    return [dict(row) for row in rows]
