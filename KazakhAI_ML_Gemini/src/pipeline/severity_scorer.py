from typing import Dict, Any, List

class SeverityScorer:
    """
    Evaluates pollution severity, hazard score (0.0 to 1.0), and cleanup priority.
    Incorporates:
    - Pollutant Toxicity / Type weight (e.g. Oil spills have highest acute hazard).
    - Spatial Extent (Estimated Area in km^2).
    - Geospatial proximity to coastlines, ports, and oil/gas pipelines.
    """

    TOXICITY_WEIGHTS = {
        "Oil Spill": 1.0,
        "Hydrocarbon Pollution": 0.9,
        "Industrial Runoff": 0.7,
        "Algal Bloom": 0.6,
        "River Sediment": 0.25,
        "Exposed Lakebed": 0.3,
        "Unknown Anomaly": 0.5
    }

    def evaluate_risk(
        self,
        pollution_type: str,
        area_km2: float,
        distance_to_coast_km: float = 25.0,
        distance_to_rigs_km: float = 15.0
    ) -> Dict[str, Any]:
        
        toxicity = self.TOXICITY_WEIGHTS.get(pollution_type, 0.5)
        
        # Normalizing area impact (assuming > 15 sq km is severe in short term)
        area_factor = min(area_km2 / 15.0, 1.0)
        
        # Proximity hazard (inversely proportional to distance)
        # Anything closer than 10km to shore or rigs spikes risk
        proximity_hazard = 0.0
        if distance_to_coast_km < 12.0:
            proximity_hazard += (12.0 - distance_to_coast_km) / 12.0 * 0.5
        if distance_to_rigs_km < 8.0:
            proximity_hazard += (8.0 - distance_to_rigs_km) / 8.0 * 0.5
            
        # Weighted composite hazard score (0.0 to 1.0)
        raw_score = (0.45 * toxicity) + (0.35 * area_factor) + (0.20 * min(proximity_hazard, 1.0))
        risk_score = round(min(max(raw_score, 0.05), 0.99), 3)
        
        # Assign categorization & actionable cleanup priorities
        if risk_score >= 0.65 or (pollution_type == "Oil Spill" and area_km2 >= 3.0) or distance_to_coast_km < 5.0:
            severity = "High"
            priority = "High"
        elif risk_score >= 0.35:
            severity = "Medium"
            priority = "Medium"
        else:
            severity = "Low"
            priority = "Low"

        # Generate automated alert reasons for UI Dashboard Notifications
        alerts = []
        if pollution_type in ["Oil Spill", "Hydrocarbon Pollution"]:
            alerts.append("CRITICAL: Acute toxic hydrocarbon spill detected on open water.")
        if distance_to_coast_km <= 8.0:
            alerts.append(f"COASTAL HAZARD: Spill perimeter is only {distance_to_coast_km}km from coastline.")
        if distance_to_rigs_km <= 6.0:
            alerts.append(f"INFRASTRUCTURE RISK: Detected anomaly within {distance_to_rigs_km}km of offshore platform/pipeline.")

        return {
            "severity": severity,
            "cleanup_priority": priority,
            "composite_risk_score": risk_score,
            "automated_alerts": alerts
        }
