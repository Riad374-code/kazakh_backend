"""
Orchestrator: builds the SQLite operational database and (re)runs all analysis
stages. Consumes the verified JSON checkpoints and produces the full set of
backend deliverables (detections, forecasts, risk, energy, trends) persisted to
SQLite. Safe to call on every server startup or via the /admin/refresh endpoint.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from src.storage.db import CaspianDatabase, seed_from_checkpoints
from src.infrastructure.assets import build_asset_catalog
from src.pipeline.oil_gas_risk import OilGasRiskEngine
from src.pipeline.energy_impact import EnergyImpactEngine
from src.pipeline.trend_analysis import TrendAnalysisEngine
from src.pipeline.priority_engine import CaspianPriorityEngine
from src.pipeline.anomaly_detector import WeeklyAnomalyDetector

logging.basicConfig(level=logging.INFO, format="%(levelname)s: [%(name)s] %(message)s")
logger = logging.getLogger("BootstrapOrchestrator")


def run_full_refresh(db: Optional[CaspianDatabase] = None) -> Dict[str, Any]:
    db = db or CaspianDatabase()

    # Serialize the entire refresh cycle: the background scheduler and the
    # /admin/refresh endpoint share the same SQLite connection, and concurrent
    # multi-statement writes surface as sqlite3 SQLITE_MISUSE errors.
    with db.locked():
        return _run_full_refresh_locked(db)


def _run_full_refresh_locked(db: CaspianDatabase) -> Dict[str, Any]:
    # 1. Seed checkpoints into SQLite (idempotent unless force)
    seed_from_checkpoints(db)
    db.commit()

    # 2. Ingest the Caspian energy/industrial asset catalog.
    for asset in build_asset_catalog():
        db.upsert_infrastructure(asset)
    db.commit()

    # 3. Oil & Gas per-asset risk scoring for every incident.
    risk_engine = OilGasRiskEngine(db)
    risk_result = risk_engine.recompute_all()

    # 4. Energy impact estimation for every incident.
    energy_engine = EnergyImpactEngine(db)
    energy_summaries = energy_engine.recompute_all()

    # 5. Caspian trend analysis (sea level, exposed areas, pollution stats).
    trend_engine = TrendAnalysisEngine(db)
    trend_result = trend_engine.recompute_all()

    # 6. Stage 1 weekly anomaly masks (regenerate clean on each refresh).
    db.conn.execute("DELETE FROM anomaly_masks")
    db.conn.commit()
    anomaly_engine = WeeklyAnomalyDetector(db)
    anomaly_count = len(anomaly_engine.recompute_weeks())

    # 7. Derive live pollution incidents from the anomaly grid so the incident
    #    list grows automatically as detections are made (not just the static
    #    checkpoint seed). Idempotent per incident_id.
    priority = CaspianPriorityEngine()
    now = datetime.now(timezone.utc).isoformat()
    incident_count = 0
    for draft in anomaly_engine.grid_incidents():
        db.upsert_incident(_incident_from_scored(priority.compute_incident_priority(draft), draft, now))
        incident_count += 1
    db.commit()

    stats = db.stats()

    logger.info(
        f"Refresh complete: {stats['incidents']} incidents, {stats['infrastructure_assets']} assets, "
        f"{stats['risk_scores']} risk scores, {stats['energy_impacts']} energy impacts, "
        f"{anomaly_count} anomaly masks."
    )
    return {
        "status": "success",
        "stats": stats,
        "risk": risk_result,
        "energy_impact_summaries": energy_summaries,
        "trends": {
            "sea_level": trend_result["sea_level"],
            "projections": trend_result["future_exposure"],
        },
        "anomaly_masks_computed": anomaly_count,
        "incidents_derived_from_grid": incident_count,
    }


def _incident_from_scored(scored: Dict[str, Any], draft: Dict[str, Any], now: str) -> Dict[str, Any]:
    """Maps a priority-engine scored incident back onto the SQLite incidents schema."""
    b = scored.get("factor_breakdown", {})
    coords = scored.get("coordinates", [0.0, 0.0])
    return {
        "incident_id": scored.get("incident_id"),
        "location_name": scored.get("location_name"),
        "coordinates_lat": coords[0] if isinstance(coords, list) and len(coords) > 0 else None,
        "coordinates_lon": coords[1] if isinstance(coords, list) and len(coords) > 1 else None,
        "pollution_type": draft.get("pollution_type"),
        "size_km2": b.get("pollution_size_km2"),
        "toxicity_score": b.get("toxicity_index"),
        "detection_confidence": None if b.get("ai_detection_confidence") is None
        else round(float(b.get("ai_detection_confidence", 0)) / 100.0, 4),
        "priority_score": scored.get("priority_score"),
        "urgency_classification": scored.get("urgency_classification"),
        "coastline_distance_m": b.get("coastline_distance_m"),
        "population_density_sqkm": b.get("population_density_sqkm"),
        "in_protected_ecosystem_zone": int(bool(b.get("protected_ecosystem_zone"))),
        "economic_impact_estimate_usd": b.get("economic_loss_usd"),
        "forecast_spread_rate_km2_day": b.get("forecast_spread_km2_day"),
        "status": draft.get("status", "active"),
        "detected_at": now,
    }


if __name__ == "__main__":
    print("=== CASPIAN AI LOGIC API - SQLite DATABASE BOOTSTRAP & FULL REFRESH ===")
    result = run_full_refresh()
    s = result["stats"]
    print(f"Incidents seeded: {s['incidents']}")
    print(f"Infrastructure assets: {s['infrastructure_assets']}")
    print(f"Risk scores: {s['risk_scores']}")
    print(f"Energy impacts: {s['energy_impacts']}")
    print(f"Anomaly masks: {result['anomaly_masks_computed']}")
    print(f"Total maintenance savings (USD): ${s['total_maintenance_savings_usd']:,.0f}")
    print(f"Total disruption avoided (USD):  ${s['total_disruption_avoided_usd']:,.0f}")
    print("Top energy impact summary:")
    for summary in result["energy_impact_summaries"][:3]:
        print(f"  - {summary['location_name']}: score {summary['energy_impact_score']} "
              f"| savings ${summary['total_maintenance_savings_usd']:,.0f} | "
              f"disruption avoided ${summary['total_disruption_avoided_usd']:,.0f}")
    print("[SUCCESS] SQLite database operational and fully populated.")