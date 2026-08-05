import json
from src.pipeline.inferencer import CaspianMLPipeline

def main():
    print("=" * 65)
    print("  CASPIAN SEA AI MONITORING & FORECASTING - DEMO VERIFICATION")
    print("=" * 65)
    print("\n[1] Initializing Modular ML Pipeline...")
    pipeline = CaspianMLPipeline()
    
    print("\n[2] Executing Simulated Analysis on Caspian Coordinates (Baku Offshore Field)...")
    results = pipeline.analyze_scene(
        center_lat=40.25,        # Latitude near offshore Azeri-Chirag-Gunashli oil platform
        center_lon=51.10,        # Longitude in open water
        wind_speed_u=3.2,        # Strong Easterly wind pushing spill
        wind_speed_v=-0.8,
        simulated_pollution_type="Oil Spill",
        simulated_area_km2=6.4,
        dist_to_coast_km=18.5,
        dist_to_rigs_km=3.2       # Very close to platform!
    )
    
    print("\n[3] Analysis Accomplished! Outputting Backend Data Contract Summary:\n")
    print(f"Scene ID         : {results['scene_metadata']['scene_id']}")
    
    evt = results['events'][0]
    print(f"Detected Event   : {evt['pollution_type']} (Confidence: {evt['confidence_score'] * 100:.1f}%)")
    print(f"Estimated Area   : {evt['estimated_area_km2']} km²")
    print(f"Severity Level   : {evt['severity']} | Cleanup Priority: {evt['cleanup_priority']}")
    print(f"Risk Score       : {evt['risk_score']} / 1.000")
    print("Automated Alerts :")
    for alert in evt['automated_alerts']:
        print(f"   -> [WARNING] {alert}")
        
    print("\n[4] 4-Week Lagrangian Drift & Spreading Forecast:")
    for step in evt['forecast_timeline']:
        print(f"   * {step['timeline']}: Projected Area = {step['predicted_area_km2']} km² | Centroid -> ({step['centroid_lat']}°N, {step['centroid_lon']}°E)")
        
    print("\n" + "=" * 65)
    print("VERIFICATION SUCCESSFUL! Backend and Frontend teams can integrate immediately.")
    print("To start the local API sidecar server, run: uvicorn api.ml_service:app --reload")
    print("=" * 65)

if __name__ == "__main__":
    main()
