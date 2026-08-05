"""Copernicus Marine Toolbox adapter and ocean-vector derivations."""

from __future__ import annotations

import importlib
import itertools
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import numpy as np
import xarray as xr

from marine_dataset.sources.copernicus_dataspace import publish_staged_file, write_raw_once

COVERAGE_CHUNK_ELEMENTS = 1_000_000


@dataclass(frozen=True)
class MarineSubsetRequest:
    dataset_id: str
    variables: tuple[str, ...]
    bbox: tuple[float, float, float, float]
    start_datetime: str
    end_datetime: str
    output_filename: str
    observation_type: Literal["observation", "analysis", "reanalysis", "forecast"]
    dataset_version: str | None = None
    minimum_depth: float = 0.0
    maximum_depth: float = 1.0

    def __post_init__(self) -> None:
        if not self.dataset_id or not self.variables:
            raise ValueError(
                "dataset_id and variables must be selected from `copernicusmarine describe`"
            )
        filename = Path(self.output_filename)
        if filename.name != self.output_filename or filename.suffix.lower() != ".nc":
            raise ValueError("output_filename must be a .nc basename")
        _validate_bbox(self.bbox)
        start = _parse_request_datetime(self.start_datetime, "start_datetime")
        end = _parse_request_datetime(self.end_datetime, "end_datetime")
        if end < start:
            raise ValueError("end_datetime must not be earlier than start_datetime")


@dataclass(frozen=True)
class MarineVariableMetadata:
    name: str
    units: str | None
    horizontal_resolution: str | None
    vertical_level: str | None
    temporal_resolution: str | None
    quality_attributes: dict[str, str]


@dataclass(frozen=True)
class MarineSubsetResult:
    path: Path
    metadata_path: Path
    dataset_id: str
    dataset_version: str | None
    observation_type: str
    observation_type_source: str
    retrieved_at: datetime
    variables: tuple[MarineVariableMetadata, ...]


def derive_current_vectors(u: np.ndarray, v: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return speed and direction-to degrees clockwise from north."""
    u_array = np.asarray(u, dtype=float)
    v_array = np.asarray(v, dtype=float)
    speed = np.hypot(u_array, v_array)
    direction = (np.degrees(np.arctan2(u_array, v_array)) + 360.0) % 360.0
    invalid = np.isnan(u_array) | np.isnan(v_array)
    return np.where(invalid, np.nan, speed), np.where(invalid, np.nan, direction)


def ensure_coverage(values: np.ndarray) -> None:
    if not np.isfinite(np.asarray(values, dtype=float)).any():
        raise ValueError(
            "no valid ocean coverage at requested coordinates; record modality as unavailable"
        )


def _validate_bbox(bbox: tuple[float, float, float, float]) -> None:
    min_lon, min_lat, max_lon, max_lat = bbox
    if not all(np.isfinite(value) for value in bbox):
        raise ValueError("bbox coordinates must be finite")
    if not (-180 <= min_lon < max_lon <= 180):
        raise ValueError("bbox longitude must be ordered within EPSG:4326 bounds")
    if not (-90 <= min_lat < max_lat <= 90):
        raise ValueError("bbox latitude must be ordered within EPSG:4326 bounds")


def _parse_request_datetime(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field} must include a timezone offset")
    return parsed.astimezone(timezone.utc)


class CopernicusMarineClient:
    """Injectable wrapper around the official optional ``copernicusmarine`` package."""

    def __init__(self, toolbox: Any | None = None) -> None:
        self.toolbox = toolbox

    def subset(
        self, request: MarineSubsetRequest, output_directory: Path, *, allow_forecast: bool = False
    ) -> MarineSubsetResult:
        if request.observation_type == "forecast" and not allow_forecast:
            raise ValueError("forecast products are disabled for historical training")
        root = output_directory.resolve()
        destination = (root / request.output_filename).resolve()
        if destination.parent != root:
            raise ValueError("ocean output must remain inside output_directory")
        root.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            return self._existing_result(request, destination)
        toolbox = self.toolbox or importlib.import_module("copernicusmarine")
        self._download_subset(toolbox, request, root, destination)
        return self._existing_result(request, destination)

    def _existing_result(
        self, request: MarineSubsetRequest, destination: Path
    ) -> MarineSubsetResult:
        metadata_path = destination.with_suffix(".metadata.json")
        result = self._read_result(request, destination, metadata_path)
        if not metadata_path.exists():
            write_raw_once(metadata_path, _metadata_bytes(result))
        return result

    def _download_subset(
        self, toolbox: Any, request: MarineSubsetRequest, root: Path, destination: Path
    ) -> None:
        min_lon, min_lat, max_lon, max_lat = request.bbox
        staging_root = _subset_staging_root(root)
        staging_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="marine-subset-", dir=staging_root) as temporary:
            temporary_path = Path(temporary)
            toolbox.subset(
                dataset_id=request.dataset_id,
                dataset_version=request.dataset_version,
                variables=list(request.variables),
                minimum_longitude=min_lon,
                maximum_longitude=max_lon,
                minimum_latitude=min_lat,
                maximum_latitude=max_lat,
                start_datetime=request.start_datetime,
                end_datetime=request.end_datetime,
                minimum_depth=request.minimum_depth,
                maximum_depth=request.maximum_depth,
                output_directory=temporary_path,
                output_filename=request.output_filename,
                disable_progress_bar=True,
            )
            staged = temporary_path / request.output_filename
            if not staged.is_file():
                raise RuntimeError("Copernicus Marine toolbox did not produce the requested NetCDF")
            _validate_subset(staged, request.variables)
            publish_staged_file(destination, staged)

    def _read_result(
        self, request: MarineSubsetRequest, destination: Path, metadata_path: Path
    ) -> MarineSubsetResult:
        with xr.open_dataset(destination) as dataset:
            provider_type = str(
                dataset.attrs.get("observation_type") or dataset.attrs.get("product_type") or ""
            ).lower()
            if provider_type and request.observation_type not in provider_type:
                raise ValueError("provider product type contradicts configured observation type")
            variables = tuple(_variable_metadata(dataset, name) for name in request.variables)
            version = request.dataset_version or dataset.attrs.get("dataset_version")
        return MarineSubsetResult(
            destination,
            metadata_path,
            request.dataset_id,
            str(version) if version is not None else None,
            request.observation_type,
            "provider_metadata" if provider_type else "explicit_configuration_unverified",
            datetime.now(timezone.utc),
            variables,
        )


def _subset_staging_root(root: Path) -> Path:
    if root.parent.name.lower() == "raw":
        return root.parents[1] / "interim" / "ocean"
    return root.parent / "interim" / "ocean"


def _validate_subset(path: Path, variables: tuple[str, ...]) -> None:
    with xr.open_dataset(path) as dataset:
        for name in variables:
            if name not in dataset:
                raise ValueError(f"Copernicus Marine subset omitted requested variable: {name}")
            if not _has_finite_coverage(dataset[name]):
                ensure_coverage(np.array([], dtype=float))


def _coverage_chunk_shape(shape: tuple[int, ...]) -> tuple[int, ...]:
    remaining = COVERAGE_CHUNK_ELEMENTS
    reversed_chunks = []
    for size in reversed(shape):
        chunk = max(1, min(size, max(1, remaining)))
        reversed_chunks.append(chunk)
        remaining = max(1, remaining // max(1, chunk))
    return tuple(reversed(reversed_chunks))


def _has_finite_coverage(data: xr.DataArray) -> bool:
    shape = tuple(int(size) for size in data.shape)
    if not shape:
        return bool(np.isfinite(np.asarray(data.values, dtype=float)).any())
    chunks = _coverage_chunk_shape(shape)
    starts = (range(0, size, chunk) for size, chunk in zip(shape, chunks, strict=True))
    for offsets in itertools.product(*starts):
        indexers = {
            dim: slice(start, min(start + chunk, size))
            for dim, start, chunk, size in zip(data.dims, offsets, chunks, shape, strict=True)
        }
        values = np.asarray(data.isel(indexers).values, dtype=float)
        if np.isfinite(values).any():
            return True
    return False


def _variable_metadata(dataset: xr.Dataset, name: str) -> MarineVariableMetadata:
    data = dataset[name]
    quality = {
        key: str(value)
        for key, value in data.attrs.items()
        if "quality" in key.lower() or "flag" in key.lower()
    }
    return MarineVariableMetadata(
        name=name,
        units=data.attrs.get("units"),
        horizontal_resolution=dataset.attrs.get("horizontal_resolution"),
        vertical_level=str(data.coords.get("depth", "surface")),
        temporal_resolution=dataset.attrs.get("temporal_resolution"),
        quality_attributes=quality,
    )


def _metadata_bytes(result: MarineSubsetResult) -> bytes:
    payload = {
        "dataset_id": result.dataset_id,
        "dataset_version": result.dataset_version,
        "observation_type": result.observation_type,
        "observation_type_source": result.observation_type_source,
        "retrieved_at": result.retrieved_at.isoformat(),
        "variables": [item.__dict__ for item in result.variables],
        "licence": "Copernicus Marine terms; verify source registry before redistribution",
        "citation": "Record the dataset-specific citation returned by Copernicus Marine describe",
    }
    return (json.dumps(payload, sort_keys=True, indent=2) + "\n").encode()


def require_registered() -> None:
    if not os.getenv("COPERNICUSMARINE_SERVICE_USERNAME") or not os.getenv(
        "COPERNICUSMARINE_SERVICE_PASSWORD"
    ):
        raise RuntimeError(
            "Copernicus Marine credentials are required; run `copernicusmarine login`"
        )
