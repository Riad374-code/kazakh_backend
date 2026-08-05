"""
Energy Impact Estimation (Backend Task 8, Product Stage 5).

Quantifies how cleaning a pollution event protects the national energy sector:
- Infrastructure protection (fraction of replacement value shielded from damage)
- Maintenance savings (USD) from avoiding fouling / corrosion
- Operational disruption avoided (downtime hours + lost production USD)
- Environmental benefit and carbon impact of early intervention

Purely additive math over the SQLite risk scores - no external dependencies.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

from src.storage.db import CaspianDatabase

logging.basicConfig(level=logging.INFO, format="%(levelname)s: [%(name)s] %(message)s")
logger = logging.getLogger("EnergyImpactEngine")

# Industry-style unit economics for Caspian offshore assets.
DAILY_PRODUCTION_VALUE_USD = {
    "platform": 4_000_000.0,
    "pipeline": 3_200_000.0,
    "terminal": 2_500_000.0,
    "port": 1_800_000.0,
    "refinery": 2_200_000.0,
    "renewable": 600_000.0,
}

MAINTENANCE_BURDEN_PCT = {
    "platform": 0.025,   # 2.5% of replacement value per year at risk
    "pipeline": 0.020,
    "terminal": 0.018,
    "port": 0.015,
    "refinery": 0.022,
    "renewable": 0.012,
}

FOULING_SAVINGS_PCT = {
    "renewable": 0.18,    # cooling/solar fouling cost reduction
    "port": 0.10,
    "refinery": 0.08,
    "terminal": 0.06,
    "platform": 0.05,
    "pipeline": 0.04,
}

DOWNTIME_AVOIDED_HOURS_CAP = 96.0


def _benefit_label(score: float) -> str:
    if score >= 80.0:
        return "MAJOR - protects core national energy infrastructure"
    if score >= 55.0:
        return "HIGH - meaningful protection of regional energy assets"
    if score >= 30.0:
        return "MODERATE - localised energy sector benefit"
    return "MINOR - limited energy sector exposure"


class EnergyImpactEngine:
    """Estimates the economic/energy benefit of prioritizing each cleanup action."""

    def __init__(self, db: Optional[CaspianDatabase] = None):
        self.db = db or CaspianDatabase()

    def estimate_for_incident(self, incident_id: str) -> Dict[str, Any]:
        incident = self.db.incident_by_id(incident_id)
        if not incident:
            raise KeyError(f"Incident {incident_id} not found in database.")
        risk_rows = self.db.risk_scores(incident_id)
        assets = {a["asset_id"]: a for a in self.db.all_assets()}
        toxicity = float(incident.get("toxicity_score", 0.5) or 0.5)

        rows = []
        for risk in risk_rows:
            asset = assets.get(risk["asset_id"])
            if not asset:
                continue
            risk_score = float(risk["risk_score"])
            replacement = float(asset.get("replacement_value_usd", 0.0) or 0.0)
            category = asset.get("category", "platform")
            arrival_days = float(risk.get("arrival_days", 30.0) or 30.0)

            # Infrastructure protection: share of replacement value shielded.
            # Faster arrival + higher risk = more value protected by early cleanup.
            protection = round(min(100.0, risk_score * 0.85 + max(0.0, 30.0 - arrival_days)), 2)
            protected_value_usd = replacement * (protection / 100.0)

            # Maintenance savings from avoided fouling / corrosion.
            maintenance_burden = replacement * MAINTENANCE_BURDEN_PCT.get(category, 0.015)
            maintenance_savings = maintenance_burden * FOULING_SAVINGS_PCT.get(category, 0.05) \
                * (protection / 100.0)

            # Operational disruption avoided (downtime hours capped).
            avoided_hours = round(DOWNTIME_AVOIDED_HOURS_CAP * (protection / 100.0), 1)
            daily_value = DAILY_PRODUCTION_VALUE_USD.get(category, 1_000_000.0)
            disruption_avoided_usd = round(avoided_hours / 24.0 * daily_value, 0)

            # Carbon impact: early intervention shortens cleanup voyage distances.
            carbon_tons = round((daily_value / 1000.0) * (protection / 100.0) * 0.02, 2)

            # Environmental benefit: protected ecosystems nearby & severity of pollutant.
            environmental_benefit = round(
                min(100.0, protection * 0.6 + toxicity * 30.0 +
                    (100.0 if incident.get("in_protected_ecosystem_zone") else 0.0) * 0.15),
                2,
            )

            # Composite energy impact score (0-100).
            energy_score = round(
                0.35 * protection +
                0.30 * min(100.0, protected_value_usd / 1e7) +
                0.20 * min(100.0, disruption_avoided_usd / 5e5) +
                0.15 * environmental_benefit,
                2,
            )

            record = {
                "incident_id": incident_id,
                "asset_id": asset["asset_id"],
                "infrastructure_protection": protection,
                "maintenance_savings_usd": round(maintenance_savings, 0),
                "avoided_downtime_hours": avoided_hours,
                "operational_disruption_avoided_usd": disruption_avoided_usd,
                "environmental_benefit": environmental_benefit,
                "carbon_impact_tons_co2e": carbon_tons,
                "energy_impact_score": energy_score,
                "computed_at": datetime.now(timezone.utc).isoformat(),
            }
            self.db.upsert_energy_impact(record)
            rows.append({
                **record,
                "asset": asset,
                "protected_value_usd": round(protected_value_usd, 0),
            })

        rows.sort(key=lambda r: r["energy_impact_score"], reverse=True)

        summary = self._summarize(incident, rows)
        return {"incident": incident, "assets": rows, "summary": summary}

    def _summarize(self, incident: Dict[str, Any], rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        top = rows[0] if rows else {}
        total_savings = sum(r["maintenance_savings_usd"] for r in rows)
        total_disruption = sum(r["operational_disruption_avoided_usd"] for r in rows)
        total_carbon = sum(r["carbon_impact_tons_co2e"] for r in rows)
        avg_protection = round(sum(r["infrastructure_protection"] for r in rows) / len(rows), 2) if rows else 0.0
        energy_score = round(sum(r["energy_impact_score"] for r in rows) / len(rows), 2) if rows else 0.0
        top_asset = top.get("asset", {}).get("name") if top else None
        return {
            "incident_id": incident["incident_id"],
            "location_name": incident.get("location_name"),
            "pollution_type": incident.get("pollution_type"),
            "priority_score": incident.get("priority_score"),
            "assets_assessed": len(rows),
            "top_protected_asset": top_asset,
            "average_infrastructure_protection": avg_protection,
            "total_maintenance_savings_usd": round(total_savings, 0),
            "total_disruption_avoided_usd": round(total_disruption, 0),
            "total_carbon_avoided_tons_co2e": round(total_carbon, 2),
            "energy_impact_score": energy_score,
            "benefit_classification": _benefit_label(energy_score),
        }

    def recompute_all(self) -> List[Dict[str, Any]]:
        summaries = []
        for inc in self.db.all_incidents():
            try:
                result = self.estimate_for_incident(inc["incident_id"])
                summaries.append(result["summary"])
                logger.info(f"Energy impact computed for {inc['incident_id']} "
                            f"(score {result['summary']['energy_impact_score']}).")
            except KeyError as exc:
                logger.warning(f"Skipping {inc['incident_id']}: {exc}")
        self.db.commit()
        return summaries
