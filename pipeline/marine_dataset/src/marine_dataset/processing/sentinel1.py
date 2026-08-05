"""Safe numerical Sentinel-1 channels and explicit scientific boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np


class ScientificCapabilityError(RuntimeError):
    """A scientifically required external operation is unavailable."""


def linear_to_db(values: np.ndarray) -> np.ndarray:
    """Convert positive linear backscatter to dB; nonpositive/nodata become NaN."""
    array = np.asarray(values, dtype=float)
    valid = np.isfinite(array) & (array > 0)
    result = np.full(array.shape, np.nan, dtype=float)
    result[valid] = 10.0 * np.log10(array[valid])
    return result


def derived_channels(vv: np.ndarray, vh: np.ndarray) -> dict[str, np.ndarray]:
    vv_array = np.asarray(vv, dtype=float)
    vh_array = np.asarray(vh, dtype=float)
    if vv_array.shape != vh_array.shape:
        raise ValueError("VV and VH arrays must have identical shapes")
    ratio = np.divide(
        vv_array,
        vh_array,
        out=np.full(vv_array.shape, np.nan),
        where=np.isfinite(vv_array) & np.isfinite(vh_array) & (vh_array != 0),
    )
    vv_db = linear_to_db(vv_array)
    vh_db = linear_to_db(vh_array)
    return {
        "vv": vv_array.copy(),
        "vh": vh_array.copy(),
        "vv_db": vv_db,
        "vh_db": vh_db,
        "vv_vh_ratio": ratio,
        "vv_minus_vh_db": vv_db - vh_db,
    }


def local_texture(values: np.ndarray, window_size: int = 3) -> np.ndarray:
    if window_size < 1 or window_size % 2 == 0:
        raise ValueError("window_size must be a positive odd integer")
    array = np.asarray(values, dtype=float)
    pad = window_size // 2
    padded = np.pad(array, pad, mode="constant", constant_values=np.nan)
    result = np.full(array.shape, np.nan)
    for row in range(array.shape[0]):
        for col in range(array.shape[1]):
            window = padded[row : row + window_size, col : col + window_size]
            result[row, col] = np.nanstd(window) if np.isfinite(window).any() else np.nan
    return result


@dataclass(frozen=True)
class PreprocessPlan:
    apply_orbit: bool = True
    remove_thermal_noise: bool = True
    calibrate: bool = True
    terrain_correct: bool = True
    speckle_filter: bool = False


def validate_scientific_capabilities(
    plan: PreprocessPlan, capabilities: Mapping[str, bool]
) -> None:
    required = {
        "precise_orbit": plan.apply_orbit,
        "thermal_noise": plan.remove_thermal_noise,
        "calibration": plan.calibrate,
        "terrain_correction": plan.terrain_correct,
    }
    missing = [
        name for name, enabled in required.items() if enabled and not capabilities.get(name, False)
    ]
    if missing:
        raise ScientificCapabilityError(
            "required SAR operations unavailable: "
            + ", ".join(missing)
            + "; install/configure ESA SNAP"
        )
