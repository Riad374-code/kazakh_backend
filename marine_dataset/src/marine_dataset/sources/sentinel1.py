"""Sentinel-1 (GRD, VV/VH) search & download adapter.

Implements Pipeline Step 04: Querying Copernicus Data Space catalog and downloading SAR imagery.
Licence: Copernicus free access + attribution; verify terms before redistribution.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from marine_dataset.logging_config import get_logger
from marine_dataset.sources.copernicus_dataspace import CDSEClient, NotImplementedAdapterError

log = get_logger("sentinel1")

# Default Caspian Sea bounding box (Baku offshore area to Aktau / Mid-Caspian)
DEFAULT_CASPIAN_BBOX = [47.5, 38.0, 55.0, 43.5]  # [min_lon, min_lat, max_lon, max_lat]


def search_sentinel1_scenes(
    start_date: Optional[str] = "2026-08-01",
    end_date: Optional[str] = "2026-08-05",
    bbox: Optional[List[float]] = None,
    max_results: int = 10,
    client: Optional[CDSEClient] = None,
) -> List[Dict[str, Any]]:
    """Search Copernicus Data Space for Sentinel-1 GRD scenes matching geographical and time filters."""
    client = client or CDSEClient()
    search_bbox = bbox if bbox is not None else DEFAULT_CASPIAN_BBOX

    log.info(
        "Searching Sentinel-1 GRD imagery over bbox %s from %s to %s (max_results=%d)...",
        search_bbox,
        start_date,
        end_date,
        max_results,
    )

    products = client.query_products(
        collection="SENTINEL-1",
        product_type="GRD",
        start_date=start_date,
        end_date=end_date,
        bbox=search_bbox,
        max_results=max_results,
    )

    formatted_scenes: List[Dict[str, Any]] = []
    for item in products:
        scene_info = {
            "scene_id": item.get("Name"),
            "uuid": item.get("Id"),
            "acquisition_start": item.get("ContentDate", {}).get("Start"),
            "acquisition_end": item.get("ContentDate", {}).get("End"),
            "content_length_mb": round(int(item.get("ContentLength", 0)) / (1024 * 1024), 2),
            "download_url": f"https://catalogue.dataspace.copernicus.eu/odata/v1/Products('{item.get('Id')}')/$value",
            "geometry": item.get("Footprint"),
            "provenance": "Copernicus Data Space Ecosystem (CDSE) - Sentinel-1 SAR GRD",
        }
        formatted_scenes.append(scene_info)

    log.info("Successfully cataloged %d Sentinel-1 SAR scenes.", len(formatted_scenes))
    return formatted_scenes


def save_scene_manifest(
    scenes: List[Dict[str, Any]], output_path: Path = Path("data/raw/sentinel1/scenes_manifest.json")
) -> Path:
    """Save queried Sentinel-1 scene catalog to local JSON storage."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(scenes, indent=2), encoding="utf-8")
    log.info("Wrote %d scene records to local manifest %s", len(scenes), output_path)
    return output_path


def require_registered() -> CDSEClient:
    """Check that Copernicus registration credentials exist or raise clear exception."""
    try:
        return CDSEClient()
    except Exception as exc:
        raise NotImplementedAdapterError(f"Sentinel-1 acquisition requires registered CDSE account: {exc}") from exc
