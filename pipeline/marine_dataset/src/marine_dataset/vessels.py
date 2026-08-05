"""Deterministic vessel matching helpers (Step 12)."""

from __future__ import annotations

from datetime import datetime
from math import hypot
from typing import Any, Iterable


def within_window(observed_at: datetime, start: datetime, end: datetime) -> bool:
    if end < start:
        raise ValueError("end must be >= start")
    return start <= observed_at <= end


def reject_speed_jumps(
    points: Iterable[dict[str, Any]], *, max_speed_mps: float = 30.0
) -> tuple[dict[str, Any], ...]:
    if max_speed_mps <= 0:
        raise ValueError("max_speed_mps must be positive")
    ordered = sorted((dict(point) for point in points), key=lambda item: item["observed_at"])
    accepted: list[dict[str, Any]] = []
    for point in ordered:
        if accepted:
            previous = accepted[-1]
            seconds = (point["observed_at"] - previous["observed_at"]).total_seconds()
            distance = hypot(
                float(point["lon"]) - float(previous["lon"]),
                float(point["lat"]) - float(previous["lat"]),
            )
            if seconds <= 0 or distance / seconds > max_speed_mps / 111_000:
                continue
        accepted.append(point)
    return tuple(accepted)


def interpolate_position(
    first: dict[str, Any], second: dict[str, Any], at: datetime
) -> dict[str, Any]:
    start, end = first["observed_at"], second["observed_at"]
    if end <= start or not (start <= at <= end):
        raise ValueError("at must lie between two ordered observations")
    fraction = (at - start).total_seconds() / (end - start).total_seconds()
    return {
        "lon": float(first["lon"]) + fraction * (float(second["lon"]) - float(first["lon"])),
        "lat": float(first["lat"]) + fraction * (float(second["lat"]) - float(first["lat"])),
        "observed_at": at,
        "position_interpolated": True,
        "gap_duration_seconds": int((end - start).total_seconds()),
    }


def grid_density(
    points: Iterable[dict[str, Any]], cell_degrees: float = 0.1
) -> dict[tuple[int, int], int]:
    if cell_degrees <= 0:
        raise ValueError("cell_degrees must be positive")
    density: dict[tuple[int, int], int] = {}
    for point in points:
        key = (int(float(point["lon"]) // cell_degrees), int(float(point["lat"]) // cell_degrees))
        density[key] = density.get(key, 0) + 1
    return dict(sorted(density.items()))
