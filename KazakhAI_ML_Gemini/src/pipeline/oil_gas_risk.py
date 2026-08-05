"""
Oil & Gas infrastructure risk scoring (Stages 5-6, Backend Task 7).

For every detected pollution incident, computes per-asset risk against offshore
platforms, pipelines, ports, export terminals and refineries around the Caspian
Sea: distance, expected pollution arrival time, threat level, risk score and a
suggested inspection priority. Results are persisted to the SQLite database.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.infrastructure.assets import build_asset_catalog, haversine_km
from src.storage.db import CaspianDatabase

logging.basicConfig(level=logging.INFO, format="%(levelname)s: [%(name)s] %(message)s")
logger = logging.getLogger("OilGasRiskEngine")

# Pollution-type impact multipliers against fixed energy infrastructure.
# Hydrocarbons are the dominant threat to platforms/pipelines/ports.
TYPE_IMPACT = {
    "oil_hydrocarbon": 1.0,
    "industrial_runoff": 0.75,
    "exposed_contaminated_lakebed": 0.55,
    "algal_bloom": 0.4,
    "river_sediment": 0.3,
    "unknown": 0.5,
}

ASSET_CRITICALITY = {
    "platform": 1.0,
    "pipeline": 0.9,
    "terminal": 0.85,
    "port": 0.8,
    "refinery": 0.75,
    "renewable": 0.55,
}

ARRIVAL_SLICE_KM = 40.0  # "reaches asset" threshold in km from a weekly centroid


def _threat_level(score: float) -> str:
    if score >= 70.0:
        return "CRITICAL"
    if score >= 45.0:
        return "HIGH"
    if score >= 20.0:
        return "MODERATE"
    return "LOW"


def _inspection_priority(score: float) -> str:
    if score >= 70.0:
        return "IMMEDIATE"
    if score >= 45.0:
        return "Within 48 hours"
    if score >= 20.0:
        return "Within 7 days"
    return "Routine"


def estimate_arrival_days(
    incident_lat: float,
    incident_lon: float,
    asset_lat: float,
    asset_lon: float,
    forecasts: List[Dict[str, Any]],
) -> float:
    """Estimates how many days until pollution reaches an asset.

    Uses the drift forecast weekly centroids when available; otherwise derives
    a drift speed from the week-1 displacement and projects linearly.
    """
    weekly = sorted([f for f in forecasts if f.get("horizon_week") == f.get("horizon_week")],
                    key=lambda f: f.get("horizon_week", 0))
    # Deduplicate by horizon_week (keep first frame of each week)
    seen: Dict[int, Dict[str, Any]] = {}
    for f in forecasts:
        w = int(f.get("horizon_week", 0))
        if w not in seen:
            seen[w] = f
    weekly = [seen[w] for w in sorted(seen)]

    if weekly:
        for f in weekly:
            dist = haversine_km(asset_lat, asset_lon, float(f.get("centroid_lat", incident_lat)),
                                float(f.get("centroid_lon", incident_lon)))
            day = float(f.get("forecast_day", 0))
            if dist <= ARRIVAL_SLICE_KM and day > 0:
                return max(0.0, round(day - 0.0, 1))
        # Extrapolate using first-week drift speed
        if len(weekly) >= 2:
            f0, f1 = weekly[0], weekly[1]
            speed_km_day = haversine_km(float(f0.get("centroid_lat", incident_lat)),
                                        float(f0.get("centroid_lon", incident_lon)),
                                        float(f1.get("centroid_lat", incident_lat)),
                                        float(f1.get("centroid_lon", incident_lon))) / max(
                1.0, float(f1.get("forecast_day", 1.0)))
            init_dist = haversine_km(incident_lat, incident_lon, asset_lat, asset_lon)
            if speed_km_day > 0.1:
                return round(init_dist / speed_km_day, 1)

    # Fallback: heuristic from current distance
    return round(haversine_km(incident_lat, incident_lon, asset_lat, asset_lon) / 9.0, 1)


class OilGasRiskEngine:
    """Scores every active incident against the full Caspian asset catalog."""

    def __init__(self, db: Optional[CaspianDatabase] = None):
        self.db = db or CaspianDatabase()

    def score_incident(self, incident: Dict[str, Any]) -> List[Dict[str, Any]]:
        lat = float(incident.get("coordinates_lat", 40.0))
        lon = float(incident.get("coordinates_lon", 51.0))
        ptype = incident.get("pollution_type", "unknown")
        type_impact = TYPE_IMPACT.get(ptype, 0.5)
        toxicity = float(incident.get("toxicity_score", 0.5) or 0.5)
        confidence = float(incident.get("detection_confidence", 0.9) or 0.9)
        forecasts = self.db.forecasts_for(incident["incident_id"])

        scored = []
        for asset in build_asset_catalog():
            asset_lat = float(asset["coordinates_lat"])
            asset_lon = float(asset["coordinates_lon"])
            distance_km = haversine_km(lat, lon, asset_lat, asset_lon)
            if distance_km > 300.0:
                continue  # out of operational threat radius

            arrival_days = estimate_arrival_days(lat, lon, asset_lat, asset_lon, forecasts)
            criticality = ASSET_CRITICALITY.get(asset["category"], 0.5)

            # Proximity term: 100 at 0 km decaying to ~15 at 200 km
            proximity = 100.0 * pow(0.985, distance_km)
            urgency = max(0.0, 100.0 - arrival_days * 4.0)  # faster arrival = higher risk
            severity = 100.0 * toxicity

            risk_score = round(
                0.40 * proximity +
                0.20 * (urgency * criticality) +
                0.20 * severity * type_impact +
                0.20 * 100.0 * confidence * criticality,
                2,
            )
            risk_score = round(max(0.0, min(100.0, risk_score)), 2)

            record = {
                "incident_id": incident["incident_id"],
                "asset_id": asset["asset_id"],
                "distance_km": round(distance_km, 2),
                "arrival_days": arrival_days,
                "threat_level": _threat_level(risk_score),
                "risk_score": risk_score,
                "inspection_priority": _inspection_priority(risk_score),
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.db.upsert_risk_score(record)
            scored.append({**record, "asset": asset})

        scored.sort(key=lambda r: r["risk_score"], reverse=True)
        return scored

    def recompute_all(self) -> Dict[str, Any]:
        incidents = self.db.all_incidents()
        total_rows = 0
        for inc in incidents:
            rows = self.score_incident(inc)
            total_rows += len(rows)
            logger.info(f"Scored {len(rows)} assets for {inc['incident_id']}")
        self.db.commit()
        return {"incidents_scored": len(incidents), "risk_rows": total_rows}
