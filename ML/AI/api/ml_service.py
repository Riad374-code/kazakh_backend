from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

from src.pipeline.inferencer import CaspianMLPipeline

app = FastAPI(
    title="Caspian Sea AI Environmental Monitoring API",
    description="Machine Learning service for real-time marine pollution detection, classification, and 4-week drift forecasting.",
    version="1.0.0-hackathon"
)

# Initialize global pipeline engine
pipeline = CaspianMLPipeline()

class SceneAnalysisRequest(BaseModel):
    scene_id: Optional[str] = Field(default=None, description="Optional satellite scene identifier")
    center_lat: float = Field(default=40.35, description="Latitude target in the Caspian Sea")
    center_lon: float = Field(default=50.45, description="Longitude target in the Caspian Sea")
    wind_u: float = Field(default=2.5, description="Wind Easterly velocity vector (m/s)")
    wind_v: float = Field(default=-1.2, description="Wind Southerly velocity vector (m/s)")
    current_u: float = Field(default=0.15, description="Surface ocean current Easterly velocity (m/s)")
    current_v: float = Field(default=-0.08, description="Surface ocean current Southerly velocity (m/s)")
    pollution_type_simulation: str = Field(
        default="Oil Spill", 
        description="Simulated event type (Oil Spill, Algal Bloom, Industrial Runoff, River Sediment)"
    )
    simulated_area_km2: float = Field(default=4.8, description="Estimated initial surface area in sq km")
    dist_coast_km: float = Field(default=14.0, description="Distance from spill perimeter to nearest coast (km)")
    dist_rig_km: float = Field(default=5.5, description="Distance to nearest oil rig/pipeline (km)")

@app.get("/health", tags=["System"])
def health_check():
    return {
        "status": "online",
        "service": "Caspian Sea ML Engine",
        "mode": "Mock Integration Demo Mode" if pipeline.is_mock_mode else "Active Inference Mode",
        "ready_for_requests": True
    }

@app.post("/api/v1/predict/scene", tags=["Inference & Forecasting"])
def analyze_scene(request: SceneAnalysisRequest):
    """
    Executes deep learning pollution evaluation, severity assessment, and generates a 4-week 
    spatial drift projection suitable for map visualizations.
    """
    try:
        result = pipeline.analyze_scene(
            scene_id=request.scene_id,
            center_lat=request.center_lat,
            center_lon=request.center_lon,
            wind_speed_u=request.wind_u,
            wind_speed_v=request.wind_v,
            ocean_current_u=request.current_u,
            ocean_current_v=request.current_v,
            simulated_pollution_type=request.pollution_type_simulation,
            simulated_area_km2=request.simulated_area_km2,
            dist_to_coast_km=request.dist_coast_km,
            dist_to_rigs_km=request.dist_rig_km
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference pipeline execution error: {str(e)}")

@app.get("/api/v1/supported-pollutants", tags=["Metadata"])
def get_supported_pollutants():
    return {
        "classes": [
            {"id": 0, "name": "Clean Water / Background", "color_hex": "#0044ff"},
            {"id": 1, "name": "Oil Spill", "color_hex": "#ff2200", "toxicity_weight": 1.0},
            {"id": 2, "name": "Algal Bloom", "color_hex": "#00dd44", "toxicity_weight": 0.6},
            {"id": 3, "name": "Industrial Runoff", "color_hex": "#ffbb00", "toxicity_weight": 0.7},
            {"id": 4, "name": "River Sediment", "color_hex": "#00bbff", "toxicity_weight": 0.25},
            {"id": 5, "name": "Exposed Lakebed", "color_hex": "#8811ee", "toxicity_weight": 0.3}
        ]
    }
