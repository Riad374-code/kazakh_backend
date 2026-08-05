"""
Weather & rainfall ingestion (Backend Task 1).

Fetches live meteorological observations for a set of Caspian coastal reference
stations from Open-Meteo (wind speed, wind direction, rainfall, air temperature),
then persists them into the SQLite weather_history table.

Standard library only: uses `urllib.request` so no new dependency layer is added.
If the network is unavailable (demo / offline mode), a deterministic synthetic
record set is generated so the trend and forecast pipelines always have data.
"""

from __future__ import annotations

import json
import math
import logging
import urllib.request
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.storage.db import CaspianDatabase

logging.basicConfig(level=logging.INFO, format="%(levelname)s: [%(name)s] %(message)s")
logger = logging.getLogger("WeatherIngest")

# (station, lat, lon) reference points around the Caspian rim.
STATIONS: List[tuple] = [
    ("AKTAU", 43.65, 51.26),
    ("BAKU", 40.36, 49.85),
    ("TURKMENBASHI", 39.91, 53.0),
    ("MAKHACHKALA", 42.98, 47.4),
    ("ANZALI", 37.47, 49.46),
    ("ATYRAU", 47.09, 51.92),
]

API_URL = ("https://api.open-meteo.com/v1/forecast"
           "?latitude={lat}&longitude={lon}"
           "&current=temperature_2m,relative_humidity_2m,wind_speed_10m,wind_direction_10m,precipitation"
           "&timezone=UTC")

# Deterministic synthetic fallback (documented as such in the DB records).
SYNTH_SEED = 2026


def _fetch_station(lat: float, lon: float, timeout: int = 15) -> Optional[Dict[str, Any]]:
    url = API_URL.format(lat=lat, lon=lon)
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        cur = payload.get("current", {})
        return {
            "wind_speed_ms": cur.get("wind_speed_10m"),
            "wind_direction_deg": cur.get("wind_direction_10m"),
            "rainfall_mm": cur.get("precipitation"),
            "sea_surface_temp_c": cur.get("temperature_2m"),
        }
    except Exception as exc:
        logger.info(f"Open-Meteo unavailable for ({lat},{lon}): {exc} - using synthetic fallback.")
        return None


def _synthetic_record(lat: float, lon: float) -> Dict[str, Any]:
    """Deterministic physics-plausible weather for offline demonstrations."""
    t = 15.0 + 8.0 * math.sin(math.radians(lat)) + (math.sin(SYNTH_SEED + lat) * 2.0)
    return {
        "wind_speed_ms": round(4.0 + 3.5 * math.fabs(math.sin(SYNTH_SEED + lon)), 2),
        "wind_direction_deg": round((math.sin(SYNTH_SEED + lat) * 180) % 360, 1),
        "rainfall_mm": round(max(0.0, (math.sin(SYNTH_SEED + lon) + 1.0) * 2.0), 2),
        "sea_surface_temp_c": round(t, 2),
    }


def ingest_weather(db: Optional[CaspianDatabase] = None, *, live: bool = True) -> Dict[str, Any]:
    """Fetches (or synthesizes) and persists weather for all stations."""
    db = db or CaspianDatabase()
    observed_at = datetime.now(timezone.utc).isoformat()
    ingested = 0
    used_live = False

    for station, lat, lon in STATIONS:
        values = None
        if live:
            values = _fetch_station(lat, lon)
        if not values:
            values = _synthetic_record(lat, lon)
        else:
            used_live = True

        db.insert_weather({
            "observed_at": observed_at,
            "coordinates_lat": round(lat, 3),
            "coordinates_lon": round(lon, 3),
            "wind_speed_ms": values.get("wind_speed_ms"),
            "wind_direction_deg": values.get("wind_direction_deg"),
            "rainfall_mm": values.get("rainfall_mm"),
            "sea_surface_temp_c": values.get("sea_surface_temp_c"),
            "source": "open-meteo-live" if (live and values and used_live) else "synthetic-fallback",
        })
        ingested += 1

    db.commit()
    logger.info(f"Ingested {ingested} weather records "
                f"({'live Open-Meteo' if used_live else 'synthetic fallback'}).")
    return {
        "status": "success",
        "stations": ingested,
        "source": "open-meteo-live" if used_live else "synthetic-fallback",
        "observed_at": observed_at,
    }


if __name__ == "__main__":
    print("=== WEATHER & RAINFALL INGESTION ===")
    result = ingest_weather(live=True)
    print(result)
    print("[SUCCESS] Weather history persisted to SQLite.")