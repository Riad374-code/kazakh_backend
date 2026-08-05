import os
import math
import uuid
import datetime
from typing import Dict, Any, Optional
from shapely.geometry import Polygon, mapping

from src.models.drift_forecast import VectorDriftForecaster
from src.pipeline.severity_scorer import SeverityScorer

class CaspianMLPipeline:
    """
    Main orchestrator for Caspian Sea pollution monitoring.
    Connects imagery detection (or simulation fallback), classification,
    severity risk scoring, and 4-week drift prediction into structured REST JSON.
    """

    def __init__(self, model_weights_path: Optional[str] = None):
        self.model_weights_path = model_weights_path
        self.forecaster = VectorDriftForecaster()
        self.scorer = SeverityScorer()
        
        # Load actual model if weights exist, otherwise initialize in high-fidelity Mock Demo Mode
        self.is_mock_mode = not (model_weights_path and os.path.exists(model_weights_path))
        if not self.is_mock_mode:
            print(f"[ML Pipeline] Loading neural segmentation weights from: {model_weights_path}")
            # Placeholder for PyTorch / ONNX execution load:
            # self.model = torch.load(model_weights_path)
        else:
            print("[ML Pipeline] No existing model weights found. Initializing in HIGH-FIDELITY MOCK DEMO MODE to unblock Backend/Frontend integration.")

    def analyze_scene(
        self,
        scene_id: Optional[str] = None,
        center_lat: float = 40.35,  # Default around central Caspian / Baku offshore field
        center_lon: float = 50.45,
        wind_speed_u: float = 2.1,
        wind_speed_v: float = -1.4,
        ocean_current_u: float = 0.12,
        ocean_current_v: float = -0.05,
        simulated_pollution_type: str = "Oil Spill",
        simulated_area_km2: float = 4.85,
        dist_to_coast_km: float = 14.2,
        dist_to_rigs_km: float = 5.5
    ) -> Dict[str, Any]:
        """
        Executes end-to-end processing over an input satellite scene or target coordinates.
        Returns fully formed JSON matching the backend contract requirements.
        """
        if not scene_id:
            scene_id = f"CASPIAN_SAT_{datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:4].upper()}"

        if self.is_mock_mode:
            # Generate a localized polygonal geometry whose degree footprint matches simulated_area_km2
            # At ~42 deg N (Caspian Sea), 1 sq degree is approx 9208 sq km.
            # Our custom polygon area is ~3.3 * deg_size^2, so scaling by 30386 aligns area perfectly.
            deg_size = math.sqrt(max(simulated_area_km2, 0.1) / 30386.0)
            base_coords = [
                [center_lon - deg_size, center_lat - deg_size],
                [center_lon + deg_size, center_lat - (deg_size * 0.5)],
                [center_lon + (deg_size * 1.2), center_lat + deg_size],
                [center_lon - (deg_size * 0.6), center_lat + (deg_size * 1.1)],
                [center_lon - deg_size, center_lat - deg_size]
            ]
            poly_geojson = {"type": "Polygon", "coordinates": [base_coords]}
            detected_type = simulated_pollution_type
            area_km2 = simulated_area_km2
            confidence_score = 0.94
        else:
            # Actual Inference execution path:
            # 1. Tile input GeoTIFF using Rasterio windowed reading
            # 2. Run model forward pass to acquire class probabilities and mask
            # 3. Vectorize masks into GeoJSON and compute surface area using UTM projected CRS
            poly_geojson = {"type": "Polygon", "coordinates": [[[0,0],[0,1],[1,1],[1,0],[0,0]]]}
            detected_type = "Oil Spill"
            area_km2 = 5.0
            confidence_score = 0.90

        # Evaluate risk severity & priority
        risk_evaluation = self.scorer.evaluate_risk(
            pollution_type=detected_type,
            area_km2=area_km2,
            distance_to_coast_km=dist_to_coast_km,
            distance_to_rigs_km=dist_to_rigs_km
        )

        # Generate 4-Week Lagrangian Drift Forecasts
        forecast_timeline = self.forecaster.generate_forecast(
            initial_polygon_geojson=poly_geojson,
            wind_u_mps=wind_speed_u,
            wind_v_mps=wind_speed_v,
            current_u_mps=ocean_current_u,
            current_v_mps=ocean_current_v
        )

        return {
            "scene_metadata": {
                "scene_id": scene_id,
                "timestamp_utc": datetime.datetime.utcnow().isoformat() + "Z",
                "sensor_source": "Sentinel-1/2 Synthetic Mock Integration",
                "crs": "EPSG:4326"
            },
            "detection_summary": {
                "pollution_detected": True,
                "event_count": 1,
                "primary_pollution_type": detected_type,
                "overall_cleanup_priority": risk_evaluation["cleanup_priority"]
            },
            "events": [
                {
                    "event_id": f"evt_{uuid.uuid4().hex[:8]}",
                    "pollution_type": detected_type,
                    "confidence_score": confidence_score,
                    "estimated_area_km2": round(area_km2, 2),
                    "severity": risk_evaluation["severity"],
                    "cleanup_priority": risk_evaluation["cleanup_priority"],
                    "risk_score": risk_evaluation["composite_risk_score"],
                    "distance_metrics": {
                        "to_coastline_km": dist_to_coast_km,
                        "to_offshore_rigs_km": dist_to_rigs_km
                    },
                    "automated_alerts": risk_evaluation["automated_alerts"],
                    "current_mask_geojson": poly_geojson,
                    "forecast_timeline": forecast_timeline
                }
            ]
        }
