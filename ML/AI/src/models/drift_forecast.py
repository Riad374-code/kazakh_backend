import math
import numpy as np
from typing import List, Dict, Any, Tuple
from shapely.geometry import Polygon, mapping
from shapely.affinity import translate, scale

class VectorDriftForecaster:
    """
    Simulates pollution trajectory over time (+1 to +4 weeks) using wind and ocean current vectors.
    
    In open water (like the Caspian Sea):
    - Surface Ocean Currents affect oil/pollutant drift at nearly 100% of current velocity.
    - Surface Winds contribute an additional slippage/leeward drift, typically ~3% of wind speed for oil
      spills and ~1% for submerged suspended particles like algae or sediments.
    
    This simulation applies Lagrangian vector advection for centroid positioning and radial diffusion
    (spreading) to simulate surface dispersion over time.
    """
    
    def __init__(self, wind_slippage_ratio: float = 0.03):
        self.wind_slippage = wind_slippage_ratio
        # Approximate meters per degree latitude near the Caspian Sea (~40-45 degrees N)
        self.meters_per_deg_lat = 111_320.0
        # Average meters per degree longitude at 42 degrees N
        self.meters_per_deg_lon = 111_320.0 * math.cos(math.radians(42.0))

    def _velocity_to_deg_per_week(self, u_mps: float, v_mps: float) -> Tuple[float, float]:
        """
        Converts velocity vectors in meters per second (u=East, v=North) 
        to coordinate degree delta per week (604,800 seconds).
        """
        seconds_per_week = 604_800.0
        dist_x_meters = u_mps * seconds_per_week
        dist_y_meters = v_mps * seconds_per_week
        
        delta_lon = dist_x_meters / self.meters_per_deg_lon
        delta_lat = dist_y_meters / self.meters_per_deg_lat
        return delta_lon, delta_lat

    def generate_forecast(
        self,
        initial_polygon_geojson: Dict[str, Any],
        wind_u_mps: float = 2.5,   # Easterly wind component (m/s)
        wind_v_mps: float = -1.2,  # Southerly wind component (m/s)
        current_u_mps: float = 0.15, # Ocean current East velocity (m/s)
        current_v_mps: float = -0.08,# Ocean current South velocity (m/s)
        diffusion_rate_per_week: float = 1.25 # Area scaling expansion per week due to dispersion
    ) -> List[Dict[str, Any]]:
        """
        Generates a 4-week forecast timeline (+1, +2, +3, +4 weeks) with predicted boundaries and areas.
        """
        try:
            poly = Polygon(initial_polygon_geojson["coordinates"][0])
        except (KeyError, IndexError, ValueError):
            # Fallback polygon if input schema is malformed
            poly = Polygon([[50.0, 40.0], [50.05, 40.0], [50.05, 40.05], [50.0, 40.05], [50.0, 40.0]])

        # Total drift velocity (current + slippage percentage of wind)
        total_u = current_u_mps + (wind_u_mps * self.wind_slippage)
        total_v = current_v_mps + (wind_v_mps * self.wind_slippage)
        
        step_lon, step_lat = self._velocity_to_deg_per_week(total_u, total_v)

        forecasts = []
        current_poly = poly

        for week in range(1, 5):
            # 1. Advection: Translate polygon centroid by vector delta
            # We add slight random turbulence variation per week for realism in demonstrations
            noise_lon = np.random.normal(0, 0.05 * abs(step_lon) + 0.001)
            noise_lat = np.random.normal(0, 0.05 * abs(step_lat) + 0.001)
            shifted_poly = translate(current_poly, xoff=step_lon + noise_lon, yoff=step_lat + noise_lat)
            
            # 2. Diffusion / Spreading: Expand polygon outwards as pollution disperses
            spread_scale = math.sqrt(diffusion_rate_per_week) # Scale linear dimension by sqrt of area growth
            expanded_poly = scale(shifted_poly, xfact=spread_scale, yfact=spread_scale, origin='center')
            
            # Estimate area in sq km based on geographical bounds
            bounds = expanded_poly.bounds  # minx, miny, maxx, maxy
            width_km = ((bounds[2] - bounds[0]) * self.meters_per_deg_lon) / 1000.0
            height_km = ((bounds[3] - bounds[1]) * self.meters_per_deg_lat) / 1000.0
            approx_area_km2 = round(expanded_poly.area * (self.meters_per_deg_lon / 1000.0) * (self.meters_per_deg_lat / 1000.0), 2)

            forecast_entry = {
                "timeline": f"+{week} week{'s' if week > 1 else ''}",
                "predicted_area_km2": max(approx_area_km2, 0.5),
                "centroid_lat": round(expanded_poly.centroid.y, 4),
                "centroid_lon": round(expanded_poly.centroid.x, 4),
                "drift_vector_summary": {
                    "u_velocity_mps": round(total_u, 3),
                    "v_velocity_mps": round(total_v, 3)
                },
                "geometry": mapping(expanded_poly)
            }
            forecasts.append(forecast_entry)
            current_poly = expanded_poly

        return forecasts
