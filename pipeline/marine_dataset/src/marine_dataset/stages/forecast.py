"""Stage 3 persistence/advection forecast baseline."""

from __future__ import annotations

from math import cos, radians, sin


def advection_forecast(
    start: dict,
    *,
    wind_speed_mps: float = 0.0,
    wind_direction_deg: float = 0.0,
    current_u_mps: float = 0.0,
    current_v_mps: float = 0.0,
    horizons_days: tuple[int, ...] = (7, 14, 30),
) -> dict:
    if not horizons_days or any(day <= 0 for day in horizons_days):
        raise ValueError("horizons_days must contain positive values")
    direction = radians(wind_direction_deg)
    east = current_u_mps + wind_speed_mps * sin(direction)
    north = current_v_mps + wind_speed_mps * cos(direction)
    lat = float(start["lat"])
    lon = float(start["lon"])
    paths = []
    for day in horizons_days:
        seconds = day * 86_400
        paths.append(
            {
                "horizon_days": day,
                "lon": lon + east * seconds / (111_320 * max(cos(radians(lat)), 0.1)),
                "lat": lat + north * seconds / 110_540,
                "spread_probability": min(1.0, 0.5 + 0.01 * day),
                "confidence": 0.5,
                "model_version": "persistence_advection_v1",
            }
        )
    return {
        "origin": {"lon": lon, "lat": lat},
        "paths": tuple(paths),
        "inputs_complete": all(
            value is not None
            for value in (wind_speed_mps, wind_direction_deg, current_u_mps, current_v_mps)
        ),
    }
