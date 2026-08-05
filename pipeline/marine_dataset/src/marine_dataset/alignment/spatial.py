"""Explicit immutable raster grid convention used by imagery, masks, and context."""

from __future__ import annotations

from dataclasses import dataclass

from affine import Affine


@dataclass(frozen=True)
class GridSpec:
    crs: str
    transform: Affine
    width: int
    height: int
    nodata: float | int | None
    axis_order: str = "x,y"
    pixel_origin: str = "upper_left"

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("grid dimensions must be positive")
        if not self.crs:
            raise ValueError("grid CRS is required")

    @property
    def resolution(self) -> tuple[float, float]:
        return abs(self.transform.a), abs(self.transform.e)


def ensure_aligned(left: GridSpec, right: GridSpec) -> None:
    if (left.crs, left.transform, left.width, left.height) != (
        right.crs,
        right.transform,
        right.width,
        right.height,
    ):
        raise ValueError("rasters are not pixel-aligned")
