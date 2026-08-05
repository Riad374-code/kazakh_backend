"""Deterministic geometry validation, clipping, and categorical rasterization."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import rasterio
from affine import Affine
from pyproj import Transformer
from rasterio.features import rasterize
from shapely.geometry.base import BaseGeometry
from shapely.ops import transform as transform_geometry
from shapely.validation import make_valid


@dataclass(frozen=True)
class RasterizeOptions:
    all_touched: bool = False
    fill: int = 0
    dtype: str = "uint8"
    overlap_rule: str = "last_wins"
    class_priority: tuple[int, ...] = ()


@dataclass(frozen=True)
class LabelShape:
    geometry: BaseGeometry
    class_id: int
    crs: str


@dataclass(frozen=True)
class RasterizationMetadata:
    target_crs: str
    resolution: tuple[float, float]
    all_touched: bool
    overlap_rule: str
    class_priority: tuple[int, ...]
    clipped_geometry_count: int


def rasterize_labels(
    labels: Iterable[tuple[BaseGeometry, int]],
    *,
    out_shape: tuple[int, int],
    transform: Affine,
    options: RasterizeOptions = RasterizeOptions(),
) -> np.ndarray:
    result, _ = rasterize_label_shapes(
        (LabelShape(geometry, class_id, "") for geometry, class_id in labels),
        out_shape=out_shape,
        transform=transform,
        target_crs="",
        options=options,
    )
    return result


def rasterize_label_shapes(
    labels: Iterable[LabelShape],
    *,
    out_shape: tuple[int, int],
    transform: Affine,
    target_crs: str,
    footprint: BaseGeometry | None = None,
    options: RasterizeOptions = RasterizeOptions(),
) -> tuple[np.ndarray, RasterizationMetadata]:
    _validate_options(options)
    prepared, clipped_count = _prepare_shapes(labels, target_crs, footprint)
    prepared = _ordered_shapes(prepared, options.class_priority)
    mask = rasterize(
        prepared,
        out_shape=out_shape,
        transform=transform,
        fill=options.fill,
        all_touched=options.all_touched,
        dtype=options.dtype,
    )
    return mask, RasterizationMetadata(
        target_crs=target_crs,
        resolution=(abs(transform.a), abs(transform.e)),
        all_touched=options.all_touched,
        overlap_rule=options.overlap_rule,
        class_priority=options.class_priority,
        clipped_geometry_count=clipped_count,
    )


def _validate_options(options: RasterizeOptions) -> None:
    if options.overlap_rule != "last_wins":
        raise ValueError("only the explicit 'last_wins' overlap rule is supported")
    if len(set(options.class_priority)) != len(options.class_priority):
        raise ValueError("class_priority cannot contain duplicates")


def _prepare_shapes(
    labels: Iterable[LabelShape],
    target_crs: str,
    footprint: BaseGeometry | None,
) -> tuple[list[tuple[BaseGeometry, int]], int]:
    prepared: list[tuple[BaseGeometry, int]] = []
    clipped_count = 0
    for label in labels:
        result = _prepare_shape(label, target_crs, footprint)
        if result is None:
            continue
        geometry, was_clipped = result
        prepared.append((geometry, label.class_id))
        clipped_count += int(was_clipped)
    return prepared, clipped_count


def _prepare_shape(
    label: LabelShape,
    target_crs: str,
    footprint: BaseGeometry | None,
) -> tuple[BaseGeometry, bool] | None:
    geometry = _reproject_shape(label, target_crs)
    valid = geometry if geometry.is_valid else make_valid(geometry)
    if valid.is_empty or not valid.is_valid:
        raise ValueError("label geometry is not safely repairable")
    if footprint is None:
        return valid, False
    clipped = valid.intersection(footprint)
    if clipped.is_empty:
        return None
    return clipped, not clipped.equals(valid)


def _reproject_shape(label: LabelShape, target_crs: str) -> BaseGeometry:
    if not label.crs or not target_crs or label.crs == target_crs:
        return label.geometry
    transformer = Transformer.from_crs(label.crs, target_crs, always_xy=True)
    return transform_geometry(transformer.transform, label.geometry)


def _ordered_shapes(
    shapes: list[tuple[BaseGeometry, int]],
    priorities: tuple[int, ...],
) -> list[tuple[BaseGeometry, int]]:
    if not priorities:
        return shapes
    order = {class_id: index for index, class_id in enumerate(priorities)}
    return sorted(shapes, key=lambda item: order.get(item[1], -1))


def write_mask_geotiff(path, mask: np.ndarray, *, transform: Affine, crs: str, nodata: int = 255):
    from pathlib import Path

    target = Path(path)
    if target.suffix.lower() in {".jpg", ".jpeg"}:
        raise ValueError("JPEG is forbidden for categorical masks")
    target.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(
        target,
        "w",
        driver="GTiff",
        height=mask.shape[0],
        width=mask.shape[1],
        count=1,
        dtype=mask.dtype,
        crs=crs,
        transform=transform,
        nodata=nodata,
        compress="DEFLATE",
    ) as dataset:
        dataset.write(mask, 1)
    return target
