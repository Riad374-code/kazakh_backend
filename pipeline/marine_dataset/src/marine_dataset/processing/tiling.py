"""Deterministic array tiling with explicit edge policy."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Iterator, Literal, Sequence

import numpy as np
from affine import Affine

from marine_dataset.alignment.spatial import GridSpec


@dataclass(frozen=True)
class ArrayTile:
    row: int
    col: int
    values: np.ndarray


@dataclass(frozen=True)
class TileThresholds:
    """Quality gates applied before a tile is accepted."""

    minimum_valid_percent: float = 0.0
    minimum_water_percent: float = 0.0
    minimum_positive_pixels: int = 0

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_valid_percent <= 100:
            raise ValueError("minimum_valid_percent must be within [0, 100]")
        if not 0 <= self.minimum_water_percent <= 100:
            raise ValueError("minimum_water_percent must be within [0, 100]")
        if self.minimum_positive_pixels < 0:
            raise ValueError("minimum_positive_pixels must be non-negative")


@dataclass(frozen=True)
class TileContext:
    environmental_record_ids: tuple[str, ...] = ()
    vessel_context_ids: tuple[str, ...] = ()
    infrastructure_context_ids: tuple[str, ...] = ()
    unmatched_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        has_context = any(
            (
                self.environmental_record_ids,
                self.vessel_context_ids,
                self.infrastructure_context_ids,
            )
        )
        if not has_context and not self.unmatched_reasons:
            raise ValueError("context IDs or an explicit unmatched reason are required")


@dataclass(frozen=True)
class GeoTile:
    """An immutable tile plus the geospatial and ML audit metadata it needs."""

    row: int
    col: int
    values: np.ndarray
    bbox: tuple[float, float, float, float]
    footprint_wkt: str
    crs: str
    transform: Affine
    resolution: tuple[float, float]
    channels: tuple[str, ...]
    class_histogram: tuple[tuple[int, int], ...]
    positive_pixel_count: int
    water_percent: float
    land_percent: float
    invalid_pixel_percent: float
    context: TileContext


@dataclass(frozen=True)
class NegativeCandidate:
    """A negative candidate with explicit sampling and leakage dimensions."""

    candidate_id: str
    category: str
    season: str
    sea_state: str
    group_id: str

    @property
    def stratum(self) -> tuple[str, str, str]:
        return self.category, self.season, self.sea_state


def iter_tiles(
    values: np.ndarray,
    *,
    tile_size: int,
    overlap: int = 0,
    edge_policy: Literal["drop", "pad"] = "drop",
    nodata: float = np.nan,
) -> Iterator[ArrayTile]:
    if tile_size <= 0 or overlap < 0 or overlap >= tile_size:
        raise ValueError("require tile_size > 0 and 0 <= overlap < tile_size")
    array = np.asarray(values)
    if array.ndim < 2:
        raise ValueError("tiling requires at least two dimensions")
    stride = tile_size - overlap
    for row in range(0, array.shape[-2], stride):
        for col in range(0, array.shape[-1], stride):
            window = array[..., row : row + tile_size, col : col + tile_size]
            if window.shape[-2:] == (tile_size, tile_size):
                yield ArrayTile(row, col, window.copy())
            elif edge_policy == "pad":
                pad_y = tile_size - window.shape[-2]
                pad_x = tile_size - window.shape[-1]
                pads = [(0, 0)] * window.ndim
                pads[-2] = (0, pad_y)
                pads[-1] = (0, pad_x)
                yield ArrayTile(row, col, np.pad(window, pads, constant_values=nodata))


def iter_geospatial_tiles(
    values: np.ndarray,
    *,
    grid: GridSpec,
    channels: Sequence[str],
    context: TileContext,
    tile_size: int,
    overlap: int = 0,
    edge_policy: Literal["drop", "pad"] = "drop",
    class_mask: np.ndarray | None = None,
    water_mask: np.ndarray | None = None,
    land_mask: np.ndarray | None = None,
    invalid_mask: np.ndarray | None = None,
    thresholds: TileThresholds = TileThresholds(),
    empty_mask_policy: Literal["keep", "drop", "error"] = "keep",
) -> Iterator[GeoTile]:
    """Yield tiles with complete spatial and quality metadata.

    Masks are tiled with the same window and edge policy as imagery. An absent class
    mask is explicit: it is either kept as an empty histogram, dropped, or rejected.
    """
    array = _validated_tile_array(values, grid, channels, empty_mask_policy)
    masks = _validated_masks(
        grid,
        class_mask=class_mask,
        water_mask=water_mask,
        land_mask=land_mask,
        invalid_mask=invalid_mask,
    )
    for tile in iter_tiles(
        array,
        tile_size=tile_size,
        overlap=overlap,
        edge_policy=edge_policy,
    ):
        result = _build_geo_tile(
            tile,
            masks=masks,
            grid=grid,
            channels=channels,
            context=context,
            tile_size=tile_size,
            edge_policy=edge_policy,
            thresholds=thresholds,
            empty_mask_policy=empty_mask_policy,
        )
        if result is not None:
            yield result


def _validated_tile_array(
    values: np.ndarray,
    grid: GridSpec,
    channels: Sequence[str],
    empty_mask_policy: Literal["keep", "drop", "error"],
) -> np.ndarray:
    array = np.asarray(values)
    if array.ndim not in {2, 3}:
        raise ValueError("values must have shape (height, width) or (channels, height, width)")
    if array.shape[-2:] != (grid.height, grid.width):
        raise ValueError("values shape must match grid dimensions")
    channel_count = 1 if array.ndim == 2 else array.shape[0]
    if len(channels) != channel_count:
        raise ValueError("channel names must match the imagery channel dimension")
    if empty_mask_policy not in {"keep", "drop", "error"}:
        raise ValueError("empty_mask_policy must be keep, drop, or error")
    return array


def _build_geo_tile(
    tile: ArrayTile,
    *,
    masks: dict[str, np.ndarray | None],
    grid: GridSpec,
    channels: Sequence[str],
    context: TileContext,
    tile_size: int,
    edge_policy: Literal["drop", "pad"],
    thresholds: TileThresholds,
    empty_mask_policy: Literal["keep", "drop", "error"],
) -> GeoTile | None:
    window_masks = _tile_masks(masks, tile, tile_size, edge_policy)
    class_values = window_masks["class_mask"]
    positive_count = _positive_count(class_values, empty_mask_policy)
    if positive_count is None:
        return None
    invalid = window_masks["invalid_mask"]
    if invalid is None:
        invalid = _invalid_pixels(tile.values)
    metrics = _percentages(window_masks["water_mask"], window_masks["land_mask"], invalid)
    if not _passes_thresholds(metrics, positive_count, thresholds):
        return None
    transform = grid.transform * Affine.translation(tile.col, tile.row)
    bbox = _tile_bbox(transform, tile_size, tile_size)
    return _geo_tile(
        tile, grid, channels, context, class_values, positive_count, metrics, transform, bbox
    )


def _tile_masks(
    masks: dict[str, np.ndarray | None],
    tile: ArrayTile,
    tile_size: int,
    edge_policy: Literal["drop", "pad"],
) -> dict[str, np.ndarray | None]:
    return {
        name: _mask_window(
            mask,
            tile,
            tile_size,
            edge_policy,
            pad_value=1 if name == "invalid_mask" else 0,
        )
        for name, mask in masks.items()
    }


def _positive_count(
    class_values: np.ndarray | None,
    policy: Literal["keep", "drop", "error"],
) -> int | None:
    count = int(np.count_nonzero(class_values > 0)) if class_values is not None else 0
    if count == 0 and policy == "error":
        raise ValueError("empty class mask rejected by empty_mask_policy=error")
    return None if count == 0 and policy == "drop" else count


def _invalid_pixels(values: np.ndarray) -> np.ndarray:
    return np.any(~np.isfinite(values), axis=0) if values.ndim == 3 else ~np.isfinite(values)


def _passes_thresholds(
    metrics: tuple[float, float, float],
    positive_count: int,
    thresholds: TileThresholds,
) -> bool:
    return (
        100.0 - metrics[2] >= thresholds.minimum_valid_percent
        and metrics[0] >= thresholds.minimum_water_percent
        and positive_count >= thresholds.minimum_positive_pixels
    )


def _geo_tile(
    tile: ArrayTile,
    grid: GridSpec,
    channels: Sequence[str],
    context: TileContext,
    class_values: np.ndarray | None,
    positive_count: int,
    metrics: tuple[float, float, float],
    transform: Affine,
    bbox: tuple[float, float, float, float],
) -> GeoTile:
    return GeoTile(
        row=tile.row,
        col=tile.col,
        values=_readonly(tile.values),
        bbox=bbox,
        footprint_wkt=_bbox_wkt(bbox),
        crs=grid.crs,
        transform=transform,
        resolution=grid.resolution,
        channels=tuple(channels),
        class_histogram=_histogram(class_values),
        positive_pixel_count=positive_count,
        water_percent=metrics[0],
        land_percent=metrics[1],
        invalid_pixel_percent=metrics[2],
        context=context,
    )


def stratified_negative_sample(
    candidates: Sequence[NegativeCandidate],
    *,
    maximum_per_stratum: int,
    seed: int,
    positive_group_ids: frozenset[str] = frozenset(),
) -> tuple[NegativeCandidate, ...]:
    """Deterministically sample category/season/sea-state strata.

    Groups already used by positives are excluded, and at most one candidate per
    group is selected. This prevents the sampler from learning a group shortcut.
    """
    if maximum_per_stratum < 0:
        raise ValueError("maximum_per_stratum must be non-negative")
    if maximum_per_stratum == 0:
        return ()
    eligible = [item for item in candidates if item.group_id not in positive_group_ids]
    selected: list[NegativeCandidate] = []
    used_groups: set[str] = set()
    for stratum in sorted({item.stratum for item in eligible}):
        ranked = sorted(
            (item for item in eligible if item.stratum == stratum),
            key=lambda item: (_stable_rank(item.candidate_id, seed), item.candidate_id),
        )
        count = 0
        for item in ranked:
            if item.group_id in used_groups:
                continue
            selected.append(item)
            used_groups.add(item.group_id)
            count += 1
            if count == maximum_per_stratum:
                break
    return tuple(selected)


def _validated_masks(grid: GridSpec, **masks: np.ndarray | None) -> dict[str, np.ndarray | None]:
    result: dict[str, np.ndarray | None] = {}
    for name, raw in masks.items():
        if raw is None:
            result[name] = None
            continue
        mask = np.asarray(raw)
        if mask.shape != (grid.height, grid.width):
            raise ValueError(f"{name} shape must match grid dimensions")
        result[name] = mask
    return result


def _mask_window(
    mask: np.ndarray | None,
    tile: ArrayTile,
    tile_size: int,
    edge_policy: Literal["drop", "pad"],
    pad_value: int,
) -> np.ndarray | None:
    if mask is None:
        return None
    window = mask[tile.row : tile.row + tile_size, tile.col : tile.col + tile_size]
    if window.shape == (tile_size, tile_size) or edge_policy == "drop":
        return window.copy()
    return np.pad(
        window,
        ((0, tile_size - window.shape[0]), (0, tile_size - window.shape[1])),
        constant_values=pad_value,
    )


def _percentages(
    water: np.ndarray | None,
    land: np.ndarray | None,
    invalid: np.ndarray,
) -> tuple[float, float, float]:
    total = invalid.size
    invalid_bool = invalid.astype(bool)
    water_count = int(np.count_nonzero(water)) if water is not None else 0
    land_count = int(np.count_nonzero(land)) if land is not None else 0
    return (
        100.0 * water_count / total,
        100.0 * land_count / total,
        100.0 * int(np.count_nonzero(invalid_bool)) / total,
    )


def _histogram(mask: np.ndarray | None) -> tuple[tuple[int, int], ...]:
    if mask is None:
        return ()
    values, counts = np.unique(mask, return_counts=True)
    return tuple((int(value), int(count)) for value, count in zip(values, counts, strict=True))


def _tile_bbox(transform: Affine, width: int, height: int) -> tuple[float, float, float, float]:
    corners = [transform * point for point in ((0, 0), (width, 0), (width, height), (0, height))]
    xs, ys = zip(*corners, strict=True)
    return min(xs), min(ys), max(xs), max(ys)


def _bbox_wkt(bbox: tuple[float, float, float, float]) -> str:
    left, bottom, right, top = bbox
    return (
        f"POLYGON (({left} {bottom}, {right} {bottom}, {right} {top}, "
        f"{left} {top}, {left} {bottom}))"
    )


def _stable_rank(candidate_id: str, seed: int) -> str:
    return sha256(f"{seed}:{candidate_id}".encode()).hexdigest()


def _readonly(values: np.ndarray) -> np.ndarray:
    result = values.copy()
    result.setflags(write=False)
    return result
