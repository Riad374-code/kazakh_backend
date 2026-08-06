"""
Caspian Sea water/land mask for the Lagrangian drift engine.

Provides a coarse Caspian basin polygon (EPSG:4326) and ray-casting
point-in-polygon tests so drifting particles are beached as soon as they leave
open water, instead of continuing to travel across dry land.

The polygon is an approximation of the Caspian coastline envelope (shallow
northern shelf -> Baku/Absheron -> Iran south coast -> Turkmen/Cheleken ->
Mangystau/Kazakhstan back to the top). It is deliberately coarse: the goal is
to keep predictions inside the sea basin, not to resolve every bay.
"""

from __future__ import annotations

from typing import Sequence, Tuple

import numpy as np

# Coarse Caspian Sea coastline envelope as (lat, lon) vertices, clockwise,
# starting on the Kalmykia coast just below the Volga delta.
CASPIAN_POLYGON: Sequence[Tuple[float, float]] = (
    (46.60, 47.70),
    (46.80, 48.60),
    (46.95, 49.60),
    (47.00, 50.60),
    (46.85, 51.50),
    (46.00, 52.20),
    (45.00, 52.60),
    (44.20, 53.00),
    (43.40, 53.10),
    (42.60, 52.80),
    (41.90, 52.30),
    (41.30, 51.90),
    (40.70, 52.10),
    (40.10, 52.40),
    (39.60, 52.50),
    (39.10, 52.60),
    (38.60, 53.00),
    (38.10, 53.40),
    (37.60, 53.70),
    (37.20, 53.70),
    (36.95, 53.40),
    (36.85, 52.60),
    (36.95, 51.70),
    (37.10, 51.00),
    (37.30, 50.20),
    (37.55, 49.60),
    (37.85, 49.15),
    (38.25, 48.85),
    (38.45, 48.70),
    (39.05, 48.90),
    (39.75, 49.20),
    (40.25, 49.60),
    (40.40, 49.90),
    (40.45, 50.40),
    (40.60, 50.20),
    (40.75, 49.90),
    (41.20, 49.10),
    (41.80, 48.60),
    (42.35, 48.30),
    (43.00, 48.00),
    (43.80, 47.60),
    (44.60, 47.40),
    (45.40, 47.30),
    (46.10, 47.60),
    (46.60, 47.60),
)


def is_water(lat: float, lon: float,
             polygon: Sequence[Tuple[float, float]] = CASPIAN_POLYGON) -> bool:
    """Ray-casting point-in-polygon test: True means the point lies over the Caspian surface."""
    # Polygon vertices are stored as (lat, lon).
    x, y = lon, lat
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        if (yi > y) != (yj > y):
            denom = (yj - yi) or 1e-12
            x_intersect = (xj - xi) * (y - yi) / denom + xi
            if x < x_intersect:
                inside = not inside
        j = i
    return inside


def water_mask(lat: np.ndarray, lon: np.ndarray,
               polygon: Sequence[Tuple[float, float]] = CASPIAN_POLYGON) -> np.ndarray:
    """Vectorized ray-casting mask: True entries lie over the Caspian surface."""
    # Polygon vertices are stored as (lat, lon).
    x = np.asarray(lon, dtype=float)
    y = np.asarray(lat, dtype=float)
    inside = np.zeros(x.shape, dtype=bool)
    n = len(polygon)
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i]
        yj, xj = polygon[j]
        crossing = (yi > y) != (yj > y)
        denom = (yj - yi) or 1e-12
        x_intersect = (xj - xi) * (y - yi) / denom + xi
        inside ^= crossing & (x < x_intersect)
        j = i
    return inside
