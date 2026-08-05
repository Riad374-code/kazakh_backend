"""Leakage-safe deterministic split assignment."""

from __future__ import annotations

import hashlib
from typing import Any, Iterable


def _bucket(value: str, seed: int) -> float:
    digest = hashlib.sha256(f"{seed}:{value}".encode()).hexdigest()
    return int(digest[:16], 16) / 16**16


def assign_splits(
    rows: Iterable[dict[str, Any]],
    *,
    strategy: str = "group_by_scene",
    seed: int = 42,
    val_fraction: float = 0.2,
    test_fraction: float = 0.2,
) -> tuple[dict[str, Any], ...]:
    if val_fraction < 0 or test_fraction < 0 or val_fraction + test_fraction >= 1:
        raise ValueError("split fractions must be non-negative and sum to < 1")
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
    materialized = [dict(row) for row in rows]
    for row in materialized:
        group_key = strategy.removeprefix("group_by_")
        value = row.get(group_key) or row.get("scene_id") or row.get("tile_id")
        if value is None:
            raise ValueError("each row requires a stable grouping identifier")
        group_id = str(value)
        score = _bucket(group_id, seed)
        split = (
            "test"
            if score < test_fraction
            else "val"
            if score < test_fraction + val_fraction
            else "train"
        )
        row.update(
            {"split": split, "split_strategy": strategy, "split_seed": seed, "group_id": group_id}
        )
    return tuple(materialized)


def leakage_report(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    materialized = [dict(row) for row in rows]
    seen: dict[str, str] = {}
    violations: list[dict[str, str]] = []
    for row in materialized:
        split = str(row.get("split", ""))
        for field in ("scene_id", "incident_id", "product_id", "label_id", "vessel_event_id"):
            value = row.get(field)
            if value is None:
                continue
            key = f"{field}:{value}"
            prior = seen.get(key)
            if prior is not None and prior != split:
                violations.append({"key": key, "first_split": prior, "second_split": split})
            else:
                seen[key] = split
    return {
        "status": "fail" if violations else "pass",
        "violations": tuple(violations),
        "checked_rows": len(materialized),
    }
