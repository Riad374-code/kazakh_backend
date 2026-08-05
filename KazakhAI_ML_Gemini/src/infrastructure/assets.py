"""
Caspian Sea oil & gas and renewable energy infrastructure asset catalog.

Dependency-free static catalog of high-value offshore assets around the
Caspian basin. Used by the Oil & Gas risk scoring and the Energy Impact
estimation modules (Stages 5 & 6). Coordinates are approximate operational
centroids of the named fields / terminals / ports / refineries.
"""

from __future__ import annotations

import math
from typing import Dict, Any, List

# asset_id, name, category, subcategory, country, lat, lon, replacement_value_usd
_RAW_ASSETS: List[tuple] = [
    # --- Offshore oil & gas platforms / fields ------------------------------
    ("PLAT_KASHAGAN", "Kashagan Offshore Field (D Island)", "platform", "offshore_field",
     "Kazakhstan", 46.1, 51.6, 48000000000),
    ("PLAT_KA_ACH", "Kalamkas-Aktobe Group", "platform", "offshore_field",
     "Kazakhstan", 45.9, 51.9, 18000000000),
    ("PLAT_KARAZHANBAS", "Karazhanbas Offshore", "platform", "offshore_field",
     "Kazakhstan", 45.7, 51.8, 9000000000),
    ("PLAT_NEET_DASHLARI", "Neft Daslari (Oil Rocks)", "platform", "offshore_field",
     "Azerbaijan", 40.28, 50.35, 15000000000),
    ("PLAT_ARAL_CHIENG", "Azeri-Chirag-Gunashli (ACG)", "platform", "offshore_field",
     "Azerbaijan", 40.0, 50.6, 32000000000),
    ("PLAT_CHIRAG", "Chirag Platform", "platform", "offshore_field",
     "Azerbaijan", 39.9, 50.6, 12000000000),
    ("PLAT_SHAH_DENIZ", "Shah Deniz Gas Field", "platform", "offshore_gas",
     "Azerbaijan", 39.9, 50.3, 26000000000),
    ("PLAT_GGS", "Guneshli (Western)", "platform", "offshore_field",
     "Azerbaijan", 40.05, 50.8, 11000000000),
    # --- Natural gas -------------------------------------------------------------------
    ("PLAT_SANGACHAL", "Sangachal Export Terminal", "terminal", "export_terminal",
     "Azerbaijan", 39.98, 49.5, 42000000000),
    ("PIPE_CPC_CASPIAN", "CPC - Caspian Pipeline Consortium (offshore leg)", "pipeline", "export_pipeline",
     "Kazakhstan", 44.0, 52.2, 25000000000),
    ("PIPE_BAKU_TBILISI", "Baku-Tbilisi-Ceyhan (BTC) start", "pipeline", "export_pipeline",
     "Azerbaijan", 40.05, 49.3, 19000000000),
    ("PIPE_AKTAU_TUBE", "Aktau-Makhachkala pipeline corridor", "pipeline", "export_pipeline",
     "Kazakhstan", 43.6, 52.7, 8000000000),
    # --- Ports -------------------------------------------------------------------------
    ("PORT_AKTAU", "Port of Aktau", "port", "cargo_port", "Kazakhstan", 43.65, 51.26, 2800000000),
    ("PORT_KURYK", "Kuryk Port", "port", "cargo_port", "Kazakhstan", 43.2, 51.7, 1200000000),
    ("PORT_BAKU", "Port of Baku", "port", "cargo_port", "Azerbaijan", 40.36, 49.85, 2000000000),
    ("PORT_TURKMENBASHI", "Turkmenbashi Port", "port", "cargo_port", "Turkmenistan", 39.91, 53.0, 1000000000),
    ("PORT_KAZANKA", "Bandar-e-Anzali port", "port", "cargo_port", "Iran", 37.47, 49.46, 800000000),
    # --- Refineries --------------------------------------------------------------------
    ("REF_CARABERAN", "SOCAR Heydar Aliyev refinery-complex", "refinery", "onshore_processing", "Azerbaijan",
     40.39, 49.9, 12000000000),
    ("REF_MAKHACHKALA", "Makhachkala oil refinery", "refinery", "onshore_processing", "Russia",
     42.98, 47.4, 6000000000),
    ("REF_AKTAU_CRUDE", "Aktau oil/condensate loading terminal", "refinery", "loading_terminal", "Kazakhstan",
     43.66, 51.28, 3500000000),
    # --- Renewable / coastal energy ----------------------------------------------------
    ("SOLAR_MANGYSTAU", "Mangystau solar farm (Aktau region)", "renewable", "solar_farm", "Kazakhstan",
     43.7, 51.9, 900000000),
    ("WIND_KENDERLI", "Kenderli wind corridor", "renewable", "wind_farm", "Kazakhstan", 43.3, 52.2, 1200000000),
    ("COOL_AKTAU_POWER", "Aktau combined-cycle cooling-water intake", "renewable", "cooling_intake", "Kazakhstan",
     43.64, 51.25, 1500000000),
]


def build_asset_catalog() -> List[Dict[str, Any]]:
    catalog = []
    for asset_id, name, category, subcategory, country, lat, lon, value in _RAW_ASSETS:
        catalog.append({
            "asset_id": asset_id,
            "name": name,
            "category": category,
            "subcategory": subcategory,
            "country": country,
            "coordinates_lat": float(lat),
            "coordinates_lon": float(lon),
            "replacement_value_usd": float(value),
            "description": f"{category} asset - {name} ({country})",
        })
    return catalog


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Computes great-circle distance in kilometres (standard-library only)."""
    r = 6371.0088
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = math.sin(d_lat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(d_lon / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def nearest_assets(lat: float, lon: float, limit: int = 10) -> List[Dict[str, Any]]:
    """Returns the `limit` closest infrastructure assets from the catalog with distances in km."""
    scored = []
    for asset in build_asset_catalog():
        dist = haversine_km(lat, lon, asset["coordinates_lat"], asset["coordinates_lon"])
        scored.append({**asset, "distance_km": round(dist, 2)})
    scored.sort(key=lambda a: a["distance_km"])
    return scored[:limit]