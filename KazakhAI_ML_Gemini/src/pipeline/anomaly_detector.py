"""
Stage 1 - Multi-Sensor Anomaly Detection (weekly anomaly masks).

Computes per-grid-cell rolling z-score anomalies independently for SAR (dark
spot / texture) and water-quality channels (chlorophyll-a, turbidity, CDOM),
then fuses them into a weekly anomaly mask with confidence. This is the
unsupervised detection layer that feeds the Stage 2 classifier.

Operates on a deterministic synthetic satellite-aligned baseline (physics-based
seasonal signal + noise), mirroring the rolling-window math that consumes the
pipeline's tiled observations in production. Stdlib only.
"""

from __future__ import annotations

import math
import logging
from typing import Dict, Any, List, Optional

from src.storage.db import CaspianDatabase

logging.basicConfig(level=logging.INFO, format="%(levelname)s: [%(name)s] %(message)s")
logger = logging.getLogger("AnomalyDetector")

# Stage 1 grid over the Caspian basin (lat, lon, name, seeded event_type).
# Cells with an event_type model an active detection and become pollution
# incidents; None cells stay clean and only contribute monitoring masks.
WEEKS = 12  # 12 weeks of archived weekly baseline (rolling window)
WEEK_NAMES = [f"2026-W{w:02d}" for w in range(1, WEEKS + 1)]

GRID = [
    (40.35, 50.05, "BAKU_NEARSHORE", "oil_hydrocarbon"),
    (45.10, 50.80, "SEAL_ISLANDS", "oil_hydrocarbon"),
    (41.80, 51.50, "CENTRAL_BASIN", None),
    (46.10, 49.60, "VOLGA_DELTA", "river_sediment"),
    (43.60, 51.26, "AKTAU_PORT", None),
    (39.00, 52.20, "TURKMEN_SHELF", "oil_hydrocarbon"),
    (38.60, 49.30, "LENKORAN_BLOCK", None),
    (44.60, 50.40, "MANGYSTAU_COAST", "oil_hydrocarbon"),
    (41.90, 49.50, "SUMQAYIT_SHELF", "algal_bloom"),
    (37.60, 52.70, "TURKMENBAY", None),
    (45.60, 51.60, "ZILANTUY_BAY", None),
    (40.30, 50.55, "ABSHERON_EAST", None),
    (46.60, 48.30, "KIZLIAR_FLATS", "river_sediment"),
    (43.20, 50.50, "HASAR_CENTRAL", None),
    (43.90, 50.90, "TUPKARAGAN", "industrial_runoff"),
]

# Per-cell overrides on top of the event-type defaults used to build incidents.
CELL_FACTORS = {
    "BAKU_NEARSHORE": {"coastline_distance_m": 1200.0, "affected_population_density": 2800.0},
    "SEAL_ISLANDS": {"coastline_distance_m": 4500.0, "in_protected_ecosystem_zone": True,
                     "biodiversity_sensitivity_index": 0.98},
    "VOLGA_DELTA": {"coastline_distance_m": 500.0, "affected_population_density": 110.0},
    "AKTAU_PORT": {"coastline_distance_m": 3000.0, "affected_population_density": 900.0},
    "TURKMEN_SHELF": {"coastline_distance_m": 7000.0},
    "LENKORAN_BLOCK": {"coastline_distance_m": 4000.0, "affected_population_density": 300.0},
    "MANGYSTAU_COAST": {"coastline_distance_m": 6500.0},
    "SUMQAYIT_SHELF": {"coastline_distance_m": 1500.0, "affected_population_density": 700.0},
    "TURKMENBAY": {"coastline_distance_m": 8000.0},
    "ZILANTUY_BAY": {"coastline_distance_m": 2000.0, "affected_population_density": 50.0},
    "ABSHERON_EAST": {"coastline_distance_m": 9000.0},
    "KIZLIAR_FLATS": {"coastline_distance_m": 1000.0, "affected_population_density": 80.0},
    "HASAR_CENTRAL": {"coastline_distance_m": 40000.0, "affected_population_density": 5.0},
    "TUPKARAGAN": {"coastline_distance_m": 5500.0, "affected_population_density": 120.0},
    "CENTRAL_BASIN": {"coastline_distance_m": 85000.0},
}

# Event-type defaults merged with the per-cell overrides when building incidents.
EVENT_FACTORS = {
    "oil_hydrocarbon": {"pollution_size_km2": 8.0, "toxicity_score": 1.0,
                        "economic_impact_estimate_usd": 900000.0,
                        "forecast_spread_rate_km2_day": 2.2, "detection_confidence": 0.93},
    "river_sediment": {"pollution_size_km2": 28.0, "toxicity_score": 0.15,
                       "economic_impact_estimate_usd": 8000.0,
                       "forecast_spread_rate_km2_day": 0.4, "detection_confidence": 0.82},
    "algal_bloom": {"pollution_size_km2": 15.0, "toxicity_score": 0.05,
                    "economic_impact_estimate_usd": 5000.0,
                    "forecast_spread_rate_km2_day": 0.6, "detection_confidence": 0.78},
    "industrial_runoff": {"pollution_size_km2": 5.0, "toxicity_score": 0.8,
                          "economic_impact_estimate_usd": 250000.0,
                          "forecast_spread_rate_km2_day": 1.1, "detection_confidence": 0.85},
}


def _sim_series(base: float, amp: float, seed: float, drift: float = 0.0,
                spiked_weeks: Optional[Dict[int, float]] = None) -> List[float]:
    """Deterministic physics-labelled seasonal signal with controllable spikes."""
    series = []
    for w in range(WEEKS):
        seasonal = base + amp * math.sin(2.0 * math.pi * (w % 12) / 12.0 + seed)
        noise = (math.sin(seed * 12.9898 + w * 78.233) * 43758.5453)
        noise = (noise - math.floor(noise)) - 0.5
        val = seasonal + noise * amp * 0.35 + drift * w
        if spiked_weeks and w in spiked_weeks:
            val += spiked_weeks[w]
        series.append(round(val, 3))
    return series


def _z_value(x: float, series: List[float]) -> float:
    mu = sum(series) / len(series)
    var = sum((v - mu) ** 2 for v in series) / len(series)
    std = var ** 0.5 or 1e-9
    return (x - mu) / std


class WeeklyAnomalyDetector:
    """Rolling z-score anomaly detector producing weekly SAR + water masks."""

    def __init__(self, db: Optional[CaspianDatabase] = None):
        self.db = db or CaspianDatabase()
        self.z_threshold = 2.0

    def _generate_channels(self, lat: float, lon: float, seed: float,
                           event_type: Optional[str]) -> Dict[str, Any]:
        """Builds aligned SAR + optical time series for a grid cell."""
        spiked = event_type
        sar_spikes: Dict[int, float] = {}
        chloro_spikes: Dict[int, float] = {}
        turbid_spikes: Dict[int, float] = {}
        cdom_spikes: Dict[int, float] = {}

        if spiked == "oil_hydrocarbon":
            sar_spikes = {WEEKS - 1: 4.5}
        elif spiked == "algal_bloom":
            chloro_spikes = {WEEKS - 1: 3.5}
        elif spiked == "river_sediment":
            turbid_spikes = {WEEKS - 1: 2.8}
            cdom_spikes = {WEEKS - 1: 1.6}
        elif spiked == "industrial_runoff":
            turbid_spikes = {WEEKS - 1: 2.2}
            cdom_spikes = {WEEKS - 1: 2.6}

        sar = _sim_series(base=0.22, amp=0.06, seed=seed, spiked_weeks=sar_spikes)
        chloro = _sim_series(base=1.4, amp=0.5, seed=seed * 1.3, spiked_weeks=chloro_spikes)
        turbidity = _sim_series(base=2.0, amp=0.4, seed=seed * 2.1, spiked_weeks=turbid_spikes)
        cdom = _sim_series(base=0.9, amp=0.2, seed=seed * 3.3, spiked_weeks=cdom_spikes)

        return {
            "sar": sar, "chlorophyll": chloro, "turbidity": turbidity, "cdom": cdom,
        }

    def detect_week(self, week_index: int, lat: float, lon: float,
                    event_type: Optional[str] = None) -> Dict[str, Any]:
        """Computes the anomaly mask for one cell at the latest week."""
        seed = round(lat * 100 + lon * 100)
        channels = self._generate_channels(lat, lon, seed, event_type)
        series = {
            "sar": channels["sar"],
            "chlorophyll": channels["chlorophyll"],
            "turbidity": channels["turbidity"],
            "cdom": channels["cdom"],
        }

        history = {k: v[:week_index + 1] for k, v in series.items()}
        full = dict(series)

        sar_z = _z_value(full["sar"][week_index], history["sar"])
        chloro_z = _z_value(full["chlorophyll"][week_index], history["chlorophyll"])
        turb_z = _z_value(full["turbidity"][week_index], history["turbidity"])
        cdom_z = _z_value(full["cdom"][week_index], history["cdom"])
        wq_z = max(chloro_z, turb_z, cdom_z)

        sar_anom = abs(sar_z) >= self.z_threshold
        wq_anom = abs(wq_z) >= self.z_threshold

        # Fusion confidence: stronger multi-sensor corroboration -> higher confidence
        n_signals = int(sar_anom) + sum(1 for z in (chloro_z, turb_z, cdom_z) if abs(z) >= self.z_threshold)
        confidence = round(min(0.99, 0.2 + n_signals * 0.25 + min(abs(wq_z), 3.0) * 0.05), 3)
        predicted = "clean"
        if sar_anom and not wq_anom:
            predicted = "oil_hydrocarbon"
        elif wq_anom and sar_anom:
            predicted = "oil_hydrocarbon_or_bloom"
        elif wq_anom and turb_z >= 2.0 and cdom_z >= 2.0:
            predicted = "industrial_runoff"
        elif wq_anom and chloro_z >= 2.0:
            predicted = "algal_bloom"
        elif wq_anom and turb_z >= 2.0:
            predicted = "river_sediment"

        return {
            "week_start": WEEK_NAMES[week_index],
            "coordinates_lat": lat,
            "coordinates_lon": lon,
            "sar_z_score": round(sar_z, 3),
            "water_quality_z_score": round(wq_z, 3),
            "chlorophyll": full["chlorophyll"][week_index],
            "turbidity": full["turbidity"][week_index],
            "cdom": full["cdom"][week_index],
            "sar_anomaly": sar_anom,
            "water_quality_anomaly": wq_anom,
            "confidence": confidence,
            "predicted_type": predicted,
        }

    def recompute_weeks(self, weeks_back: int = 4) -> List[Dict[str, Any]]:
        """Recomputes and persists the most recent anomaly masks for the grid."""
        rows = []
        # Cells with a seeded event produce a demonstrable detection at the latest week.
        for lat, lon, name, event in GRID:
            for w in range(WEEKS - weeks_back, WEEKS):
                rec = self.detect_week(w, lat, lon, event_type=event if w == WEEKS - 1 else None)
                self.db.insert_anomaly(rec)
                rows.append(rec)
        self.db.commit()
        logger.info(f"Recomputed {len(rows)} weekly anomaly masks across the grid.")
        return rows

    def grid_incidents(self) -> List[Dict[str, Any]]:
        """
        Derives pollution incident drafts from the grid cells that show an active
        detection at the latest week (i.e. seeded event type). Each draft carries
        the 8 priority-engine factors plus the detection confidence from the mask.

        Returns raw incident factor dicts; the priority engine / bootstrap layer
        computes the weighted scores and persists them to the operational store.
        """
        incidents: List[Dict[str, Any]] = []
        for idx, (lat, lon, name, event) in enumerate(GRID, start=1):
            if not event:
                continue
            rec = self.detect_week(WEEKS - 1, lat, lon, event_type=event)
            factors = dict(EVENT_FACTORS[event])
            factors.update(CELL_FACTORS.get(name, {}))
            factors["detection_confidence"] = min(0.99, max(0.6, rec.get("confidence", 0.9)))
            location = name.replace("_", " ").title()
            incidents.append({
                "incident_id": f"DET_2026_{idx:03d}_{name}",
                "location_name": f"{location} (Satellite Detection)",
                "coordinates": [lat, lon],
                "pollution_type": event,
                "status": "active",
                **factors,
            })
        logger.info(f"Derived {len(incidents)} pollution incidents from the Stage 1 grid.")
        return incidents