"""
Orchestrator: builds the SQLite operational database and (re)runs all analysis
stages. Consumes the verified JSON checkpoints and produces the full set of
backend deliverables (detections, forecasts, risk, energy, trends) persisted to
SQLite. Safe to call on every server startup or via the /admin/refresh endpoint.
"""

from __future__ import annotations

import logging
from typing import Dict, Any

from src.storage.db import CaspianDatabase, seed_from_checkpoints
from src.infrastructure.assets import build_asset_catalog
from src.pipeline.oil_gas_risk import OilGasRiskEngine
from src.pipeline.energy_impact import EnergyImpactEngine
from src.pipeline.trend_analysis import TrendAnalysisEngine
from src.pipeline.anomaly_detector import WeeklyAnomalyDetector

logging.basicConfig(level=logging.INFO, format="%(levelname)s: [%(name)s] %(message)s")
logger = logging.getLogger("BootstrapOrchestrator")


def run_full_refresh(db: Optional[CaspianDatabase] = None) -> Dict[str, Any]:
    db = db or CaspianDatabase()

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