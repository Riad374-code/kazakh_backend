"""Raster reprojection with complete source/target grid metadata."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import rasterio
from rasterio.enums import Resampling
from rasterio.warp import calculate_default_transform, reproject


@dataclass(frozen=True)
class ResamplingRecord:
    source_crs: str
    target_crs: str
    source_resolution: tuple[float, float]
    target_resolution: tuple[float, float]
    source_dimensions: tuple[int, int]
    target_dimensions: tuple[int, int]
    method: str


def reproject_raster(
    source: Path, target: Path, target_crs: str, *, categorical: bool = False
) -> ResamplingRecord:
    method = Resampling.nearest if categorical else Resampling.bilinear
    with rasterio.open(source) as src:
        transform, width, height = calculate_default_transform(
            src.crs, target_crs, src.width, src.height, *src.bounds
        )
        profile = {
            **src.profile,
            "crs": target_crs,
            "transform": transform,
            "width": width,
            "height": height,
        }
        target.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(target, "w", **profile) as dst:
            for band in range(1, src.count + 1):
                reproject(
                    source=rasterio.band(src, band),
                    destination=rasterio.band(dst, band),
                    src_transform=src.transform,
                    src_crs=src.crs,
                    dst_transform=transform,
                    dst_crs=target_crs,
                    resampling=method,
                )
        return ResamplingRecord(
            str(src.crs),
            target_crs,
            tuple(abs(value) for value in src.res),
            (abs(transform.a), abs(transform.e)),
            (src.height, src.width),
            (height, width),
            method.name,
        )
