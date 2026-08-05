"""Sentinel-3 collection selection, native-grid extraction and co-registration."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

import numpy as np
import xarray as xr
from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry


class Sentinel3Variable(str, Enum):
    chlorophyll = "chlorophyll"
    cdom_proxy = "cdom_proxy"
    turbidity_proxy = "turbidity_proxy"
    sst = "sst"


VARIABLE_CANDIDATES = {
    Sentinel3Variable.chlorophyll: ("CHL_OC4ME", "CHL_NN", "chl_oc4me", "chlor_a"),
    Sentinel3Variable.cdom_proxy: ("ADG443_NN", "adg_443_nn"),
    Sentinel3Variable.turbidity_proxy: ("TSM_NN", "tsm_nn"),
    Sentinel3Variable.sst: ("sea_surface_temperature", "SST", "sea_surface_temperature_skin"),
}

STAC_COLLECTIONS = {
    "olci_wfr_ntc": "sentinel-3-olci-2-wfr-ntc",
    "olci_wfr_nrt": "sentinel-3-olci-2-wfr-nrt",
    "slstr_wst_ntc": "sentinel-3-sl-2-wst-ntc",
    "slstr_wst_nrt": "sentinel-3-sl-2-wst-nrt",
}


@dataclass(frozen=True)
class ExtractedVariable:
    variable: Sentinel3Variable
    source_name: str
    values: np.ndarray
    units: str | None
    native_shape: tuple[int, ...]
    native_resolution_m: float | None
    processing_baseline: str | None
    is_proxy: bool
    retrieval_algorithm: str | None
    product_version: str | None
    uncertainty: np.ndarray | None
    valid_mask: np.ndarray


@dataclass(frozen=True)
class Sentinel3SceneMetadata:
    product_id: str
    platform: str
    footprint_wkt: str | None
    acquisition_start: datetime
    acquisition_end: datetime
    processing_level: str | None
    native_resolution_m: float | None
    processing_baseline: str | None
    cloud_or_quality_assets: tuple[str, ...]


@dataclass(frozen=True)
class CoregistrationRecord:
    coverage_fraction: float
    time_delta_minutes: float
    native_resolution_m: float
    interpolation_method: str | None


def extract_sentinel3_variable(
    dataset: xr.Dataset,
    variable: Sentinel3Variable,
    *,
    cloud_mask: np.ndarray | None = None,
    valid_mask: np.ndarray | None = None,
    uncertainty_variable: str | None = None,
) -> ExtractedVariable:
    source_name = next((name for name in VARIABLE_CANDIDATES[variable] if name in dataset), None)
    if source_name is None:
        raise ValueError(f"Sentinel-3 variable unavailable: {variable.value}")
    data = dataset[source_name]
    values = np.asarray(data.values, dtype=float)
    fill = data.attrs.get("_FillValue")
    if fill is not None:
        values = np.where(values == float(fill), np.nan, values)
    values = np.where(np.isfinite(values), values, np.nan)
    mask = quality_mask(values, cloud_mask=cloud_mask, valid_mask=valid_mask)
    values = np.where(mask, values, np.nan)
    uncertainty = None
    if uncertainty_variable:
        if uncertainty_variable not in dataset:
            raise ValueError(f"uncertainty variable unavailable: {uncertainty_variable}")
        uncertainty = np.asarray(dataset[uncertainty_variable].values, dtype=float)
        if uncertainty.shape != values.shape:
            raise ValueError("uncertainty and data arrays must share the native grid")
        uncertainty = np.where(mask, uncertainty, np.nan)
    return ExtractedVariable(
        variable,
        source_name,
        values,
        data.attrs.get("units"),
        tuple(values.shape),
        dataset.attrs.get("spatial_resolution_m"),
        dataset.attrs.get("processing_baseline"),
        variable in {Sentinel3Variable.cdom_proxy, Sentinel3Variable.turbidity_proxy},
        data.attrs.get("algorithm") or data.attrs.get("retrieval_algorithm"),
        dataset.attrs.get("product_version"),
        uncertainty,
        mask,
    )


def decode_quality_bits(
    flags: np.ndarray,
    *,
    invalid_bits: tuple[int, ...],
    cloud_bits: tuple[int, ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Decode caller-supplied documented bit positions; no product bits are guessed."""
    values = np.asarray(flags)
    if not np.issubdtype(values.dtype, np.integer):
        raise ValueError("quality flags must use an integer dtype")
    for bit in (*invalid_bits, *cloud_bits):
        if bit < 0 or bit >= values.dtype.itemsize * 8:
            raise ValueError("quality flag bit is outside the source dtype")
    invalid = np.zeros(values.shape, dtype=bool)
    cloud = np.zeros(values.shape, dtype=bool)
    for bit in invalid_bits:
        invalid |= (values & (1 << bit)) != 0
    for bit in cloud_bits:
        cloud |= (values & (1 << bit)) != 0
    return ~invalid, cloud


def assert_resolution_claim(
    native_resolution_m: float,
    target_resolution_m: float,
    *,
    allow_derived_upsampling: bool = False,
) -> None:
    if native_resolution_m <= 0 or target_resolution_m <= 0:
        raise ValueError("resolutions must be positive")
    if target_resolution_m < native_resolution_m and not allow_derived_upsampling:
        raise ValueError(
            "target grid is finer than Sentinel-3 native resolution; "
            "mark it as derived upsampling or retain the native grid"
        )


def parse_sentinel3_item(item: dict[str, Any]) -> Sentinel3SceneMetadata:
    props = item.get("properties", {})
    start_text = props.get("start_datetime") or props.get("datetime")
    end_text = props.get("end_datetime") or props.get("datetime")
    if not start_text or not end_text:
        raise ValueError("Sentinel-3 STAC item is missing acquisition time")
    asset_names = tuple(
        sorted(
            name
            for name in item.get("assets", {})
            if any(token in name.lower() for token in ("quality", "flag", "cloud"))
        )
    )
    return Sentinel3SceneMetadata(
        product_id=str(item["id"]),
        platform=str(props.get("platform", "unknown")),
        footprint_wkt=shape(item["geometry"]).wkt if item.get("geometry") else None,
        acquisition_start=_parse_utc(start_text),
        acquisition_end=_parse_utc(end_text),
        processing_level=props.get("processing:level"),
        native_resolution_m=props.get("gsd"),
        processing_baseline=props.get("processing:baseline"),
        cloud_or_quality_assets=asset_names,
    )


def _parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _quality_masks(
    dataset: xr.Dataset,
    quality_variable: str | None,
    invalid_bits: tuple[int, ...],
    cloud_bits: tuple[int, ...],
) -> tuple[np.ndarray | None, np.ndarray | None]:
    if not quality_variable:
        return None, None
    if quality_variable not in dataset:
        raise ValueError(f"quality variable unavailable: {quality_variable}")
    return decode_quality_bits(
        np.asarray(dataset[quality_variable].values),
        invalid_bits=invalid_bits,
        cloud_bits=cloud_bits,
    )


def _processed_dataset(
    dataset: xr.Dataset,
    variable: Sentinel3Variable,
    extracted: ExtractedVariable,
) -> xr.Dataset:
    source = dataset[extracted.source_name]
    coordinates = {name: dataset.coords[name] for name in source.dims if name in dataset.coords}
    attributes = {
        "source_variable": extracted.source_name,
        "native_resolution_m": extracted.native_resolution_m,
        "processing_baseline": extracted.processing_baseline,
        "retrieval_algorithm": extracted.retrieval_algorithm,
        "product_version": extracted.product_version,
        "is_proxy": int(extracted.is_proxy),
        "grid_status": "native",
    }
    output = xr.Dataset(
        {
            variable.value: (source.dims, extracted.values),
            f"{variable.value}_valid": (source.dims, extracted.valid_mask),
        },
        coords=coordinates,
        attrs={key: value for key, value in attributes.items() if value is not None},
    )
    output[variable.value].attrs["units"] = extracted.units or "unknown"
    if extracted.uncertainty is not None:
        output[f"{variable.value}_uncertainty"] = (source.dims, extracted.uncertainty)
    return output


def _write_netcdf_once(output: xr.Dataset, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{output_path.name}.", suffix=".tmp.nc", dir=output_path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        output.to_netcdf(temporary)
        os.link(temporary, output_path)
    finally:
        temporary.unlink(missing_ok=True)


def process_sentinel3_file(
    input_path: Path,
    output_path: Path,
    variable: Sentinel3Variable,
    *,
    quality_variable: str | None = None,
    invalid_bits: tuple[int, ...] = (),
    cloud_bits: tuple[int, ...] = (),
    uncertainty_variable: str | None = None,
    target_resolution_m: float | None = None,
    allow_derived_upsampling: bool = False,
) -> ExtractedVariable:
    """Extract one native-grid variable and persist values plus an explicit valid mask."""
    if output_path.exists():
        raise FileExistsError(f"refusing to overwrite processed Sentinel-3 output: {output_path}")
    with xr.open_dataset(input_path) as dataset:
        valid_mask, cloud_mask = _quality_masks(dataset, quality_variable, invalid_bits, cloud_bits)
        extracted = extract_sentinel3_variable(
            dataset,
            variable,
            cloud_mask=cloud_mask,
            valid_mask=valid_mask,
            uncertainty_variable=uncertainty_variable,
        )
        if extracted.native_resolution_m and target_resolution_m:
            assert_resolution_claim(
                extracted.native_resolution_m,
                target_resolution_m,
                allow_derived_upsampling=allow_derived_upsampling,
            )
        _write_netcdf_once(_processed_dataset(dataset, variable, extracted), output_path)
    return extracted


def quality_mask(
    values: np.ndarray,
    *,
    cloud_mask: np.ndarray | None = None,
    valid_mask: np.ndarray | None = None,
) -> np.ndarray:
    result = np.isfinite(np.asarray(values, dtype=float))
    if cloud_mask is not None:
        result &= ~np.asarray(cloud_mask, dtype=bool)
    if valid_mask is not None:
        result &= np.asarray(valid_mask, dtype=bool)
    return result


def coregistration_record(
    satellite1_footprint: BaseGeometry,
    sentinel3_footprint: BaseGeometry,
    time_delta_minutes: float,
    native_resolution_m: float,
    interpolation_method: str | None = None,
) -> CoregistrationRecord:
    if satellite1_footprint.is_empty or satellite1_footprint.area == 0:
        raise ValueError("Sentinel-1 footprint must have positive area")
    intersection = satellite1_footprint.intersection(sentinel3_footprint)
    coverage = intersection.area / satellite1_footprint.area
    return CoregistrationRecord(
        coverage, abs(time_delta_minutes), native_resolution_m, interpolation_method
    )


def validate_collection(collection_id: str, available_collection_ids: set[str]) -> None:
    if collection_id not in available_collection_ids:
        raise ValueError(
            "configured Sentinel-3 collection is not present in the current CDSE catalogue"
        )


def require_registered() -> None:
    from marine_dataset.sources.copernicus_dataspace import require_registered as require_cdse

    require_cdse()
