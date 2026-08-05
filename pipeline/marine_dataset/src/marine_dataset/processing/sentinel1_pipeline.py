"""Executable, restartable ESA SNAP boundary for Sentinel-1 GRD processing.

This module deliberately delegates every SAR correction to ESA SNAP.  It does
not provide numerical fallbacks for operations whose scientific meaning
depends on the SNAP implementation and auxiliary data.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal
from xml.etree import ElementTree as ET

import numpy as np

from marine_dataset.processing.sentinel1 import derived_channels
from marine_dataset.storage import sha256_file

Executor = Callable[[Sequence[str], float | None], subprocess.CompletedProcess[str]]
Clock = Callable[[], float]


class SnapPipelineError(RuntimeError):
    """An actionable failure at the ESA SNAP process boundary."""


@dataclass(frozen=True)
class SnapPreprocessPlan:
    """Immutable scientific decisions for one Sentinel-1 GRD run."""

    apply_orbit: bool = True
    remove_thermal_noise: bool = True
    remove_border_noise: bool = True
    calibration: Literal["sigma0", "gamma0"] = "sigma0"
    convert_to_db: bool = False
    speckle_filter: str | None = None
    terrain_correct: bool = True
    reproject: bool = False
    dem_name: str = "Copernicus 30m Global DEM"
    pixel_spacing_m: float = 10.0
    target_crs: str = "EPSG:4326"
    resampling: str = "BILINEAR_INTERPOLATION"
    aoi_wkt: str | None = None
    polarisations: tuple[str, ...] = ("VV", "VH")
    output_format: str = "GeoTIFF-BigTIFF"

    def __post_init__(self) -> None:
        if self.pixel_spacing_m <= 0:
            raise ValueError("pixel_spacing_m must be positive")
        if not self.polarisations:
            raise ValueError("at least one polarisation is required")
        invalid = set(self.polarisations) - {"VV", "VH", "HH", "HV"}
        if invalid:
            raise ValueError(f"unsupported polarisations: {sorted(invalid)}")


@dataclass(frozen=True)
class SnapRunResult:
    output_path: Path
    manifest_path: Path
    output_sha256: str
    manifest_sha256: str
    restarted: bool


@dataclass(frozen=True)
class RasterGrid:
    """Georeferencing contract for calibrated, co-registered channel arrays."""

    crs: str
    affine: tuple[float, float, float, float, float, float]
    resolution: tuple[float, float]


@dataclass(frozen=True)
class _SnapRunContext:
    source: Path
    destination: Path
    manifest: Path
    executable: Path
    input_sha256: str
    plan_payload: dict[str, Any]
    plan_sha256: str


def _parameters(node: ET.Element, values: Mapping[str, Any]) -> None:
    parameters = ET.SubElement(
        node, "parameters", {"class": "com.bc.ceres.binding.dom.XppDomElement"}
    )
    for name, value in values.items():
        child = ET.SubElement(parameters, name)
        if isinstance(value, bool):
            child.text = str(value).lower()
        elif isinstance(value, tuple):
            child.text = ",".join(value)
        else:
            child.text = str(value)


def _add_node(
    graph: ET.Element,
    node_id: str,
    operator: str,
    source_id: str | None,
    parameters: Mapping[str, Any],
) -> str:
    node = ET.SubElement(graph, "node", {"id": node_id})
    ET.SubElement(node, "operator").text = operator
    sources = ET.SubElement(node, "sources")
    if source_id is not None:
        ET.SubElement(sources, "sourceProduct", {"refid": source_id})
    _parameters(node, parameters)
    return node_id


def _append_radiometric_nodes(graph: ET.Element, source: str, plan: SnapPreprocessPlan) -> str:
    if plan.apply_orbit:
        source = _add_node(
            graph,
            "orbit",
            "Apply-Orbit-File",
            source,
            {"orbitType": "Sentinel Precise (Auto Download)", "continueOnFail": False},
        )
    if plan.remove_thermal_noise:
        source = _add_node(
            graph,
            "thermal-noise",
            "ThermalNoiseRemoval",
            source,
            {"selectedPolarisations": plan.polarisations, "removeThermalNoise": True},
        )
    if plan.remove_border_noise:
        source = _add_node(graph, "border-noise", "Remove-GRD-Border-Noise", source, {})
    calibration_parameters: dict[str, Any] = {
        "selectedPolarisations": plan.polarisations,
        "outputImageScaleInDb": False,
        "outputSigmaBand": plan.calibration == "sigma0",
        "outputGammaBand": plan.calibration == "gamma0",
    }
    source = _add_node(graph, "calibration", "Calibration", source, calibration_parameters)
    if plan.convert_to_db:
        source = _add_node(graph, "to-db", "LinearToFromdB", source, {})
    if plan.speckle_filter:
        source = _add_node(
            graph,
            "speckle",
            "Speckle-Filter",
            source,
            {"filter": plan.speckle_filter},
        )
    return source


def _append_geometric_nodes(graph: ET.Element, source: str, plan: SnapPreprocessPlan) -> str:
    if plan.terrain_correct:
        source = _add_node(
            graph,
            "terrain-correction",
            "Terrain-Correction",
            source,
            {
                "demName": plan.dem_name,
                "pixelSpacingInMeter": plan.pixel_spacing_m,
                "mapProjection": plan.target_crs,
                "imgResamplingMethod": plan.resampling,
                "nodataValueAtSea": False,
                "saveSelectedSourceBand": True,
            },
        )
    if plan.reproject:
        source = _add_node(
            graph,
            "reproject",
            "Reproject",
            source,
            {"crs": plan.target_crs, "resampling": plan.resampling},
        )
    if plan.aoi_wkt:
        source = _add_node(graph, "aoi-clip", "Subset", source, {"geoRegion": plan.aoi_wkt})
    return source


def build_snap_graph(plan: SnapPreprocessPlan, input_path: Path, output_path: Path) -> str:
    """Return a SNAP GPT XML graph; no operation is emulated or approximated."""
    graph = ET.Element("graph", {"id": "sentinel1-grd-preprocess"})
    ET.SubElement(graph, "version").text = "1.0"
    source = _add_node(
        graph, "read", "Read", None, {"file": input_path, "formatName": "SENTINEL-1"}
    )
    source = _append_radiometric_nodes(graph, source, plan)
    source = _append_geometric_nodes(graph, source, plan)
    _add_node(
        graph,
        "write",
        "Write",
        source,
        {"file": output_path, "formatName": plan.output_format, "deleteOutputOnFailure": True},
    )
    ET.indent(graph, space="  ")
    return ET.tostring(graph, encoding="unicode", xml_declaration=True)


def _canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _plan_payload(plan: SnapPreprocessPlan) -> dict[str, Any]:
    return asdict(plan)


def _publish_file_once(staged: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(staged, destination)
    except FileExistsError as exc:
        raise SnapPipelineError(f"refusing to overwrite processed artifact: {destination}") from exc


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    """Publish JSON once via a unique temporary and an exclusive hard-link."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
        handle.write(_canonical(payload) + b"\n")
        handle.flush()
        os.fsync(handle.fileno())
    try:
        _publish_file_once(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _default_executor(
    args: Sequence[str], timeout: float | None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
        shell=False,
        timeout=timeout,
    )


def validate_snap_executable(executable: Path) -> Path:
    resolved = executable.expanduser().resolve()
    if not resolved.is_file():
        raise SnapPipelineError(
            f"ESA SNAP GPT executable was not found at {resolved}. "
            "Install SNAP and pass the full path to gpt or gpt.exe."
        )
    if not os.access(resolved, os.X_OK):
        raise SnapPipelineError(f"ESA SNAP GPT path is not executable: {resolved}")
    return resolved


def _cached_result(
    output_path: Path,
    manifest_path: Path,
    input_sha256: str,
    plan_sha256: str,
) -> SnapRunResult | None:
    if not output_path.is_file() or not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    output_sha256 = sha256_file(output_path)
    if (
        manifest.get("status") == "success"
        and manifest.get("input", {}).get("sha256") == input_sha256
        and manifest.get("plan_sha256") == plan_sha256
        and manifest.get("output", {}).get("sha256") == output_sha256
    ):
        return SnapRunResult(
            output_path, manifest_path, output_sha256, sha256_file(manifest_path), True
        )
    return None


def _is_raw_destination(destination: Path, raw_root: Path | None) -> bool:
    if raw_root:
        raw = raw_root.resolve()
        return destination == raw or raw in destination.parents
    return any(parent.name.casefold() == "raw" for parent in (destination, *destination.parents))


def _prepare_run(
    input_path: Path,
    output_path: Path,
    manifest_path: Path | None,
    snap_executable: Path,
    plan: SnapPreprocessPlan,
    raw_root: Path | None,
) -> _SnapRunContext:
    source = input_path.resolve()
    destination = output_path.resolve()
    manifest = (
        manifest_path or destination.with_suffix(destination.suffix + ".manifest.json")
    ).resolve()
    if not source.is_file():
        raise SnapPipelineError(f"Sentinel-1 input does not exist: {source}")
    if _is_raw_destination(destination, raw_root):
        raise SnapPipelineError("processed SNAP output must never be written under data/raw")
    input_sha256 = sha256_file(source)
    plan_payload = _plan_payload(plan)
    plan_sha256 = hashlib.sha256(_canonical(plan_payload)).hexdigest()
    return _SnapRunContext(
        source,
        destination,
        manifest,
        validate_snap_executable(snap_executable),
        input_sha256,
        plan_payload,
        plan_sha256,
    )


def _existing_result(context: _SnapRunContext) -> SnapRunResult | None:
    cached = _cached_result(
        context.destination,
        context.manifest,
        context.input_sha256,
        context.plan_sha256,
    )
    if cached:
        return cached
    if context.destination.exists() or context.manifest.exists():
        raise SnapPipelineError(
            "existing output or manifest does not match this input and plan; "
            "choose a new output path instead of overwriting provenance"
        )
    return None


def _claim_run(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    lock = destination.with_suffix(destination.suffix + ".lock")
    try:
        lock.touch(exist_ok=False)
    except FileExistsError as exc:
        raise SnapPipelineError(f"SNAP processing already in progress: {destination}") from exc
    return lock


def _work_files(
    context: _SnapRunContext, interim_dir: Path, plan: SnapPreprocessPlan
) -> tuple[Path, Path, str]:
    prefix = f"snap_{context.input_sha256[:12]}_{context.plan_sha256[:12]}_"
    work_dir = Path(tempfile.mkdtemp(prefix=prefix, dir=interim_dir.resolve()))
    temporary_output = work_dir / context.destination.name
    graph_path = work_dir / "graph.xml"
    graph_path.write_text(
        build_snap_graph(plan, context.source, temporary_output), encoding="utf-8"
    )
    return temporary_output, graph_path, sha256_file(graph_path)


def _base_manifest(
    context: _SnapRunContext, graph_sha256: str, snap_version: str
) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "stage": "sentinel1_snap_preprocess",
        "input": {"path": str(context.source), "sha256": context.input_sha256},
        "plan": context.plan_payload,
        "plan_sha256": context.plan_sha256,
        "graph_sha256": graph_sha256,
        "software": {"name": "ESA SNAP GPT", "version": snap_version},
    }


def _execute_snap(
    context: _SnapRunContext,
    graph_path: Path,
    base_manifest: Mapping[str, Any],
    executor: Executor,
    timeout_seconds: float | None,
    clock: Clock,
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    started = clock()
    try:
        completed = executor((str(context.executable), str(graph_path)), timeout_seconds)
    except (OSError, subprocess.SubprocessError) as exc:
        elapsed = round(clock() - started, 6)
        failure = (
            f"SNAP GPT could not complete: {type(exc).__name__}. "
            "Check executable permissions, timeout, memory, and the interim graph."
        )
        _atomic_json(
            context.manifest,
            {
                **base_manifest,
                "timings": {"elapsed_seconds": elapsed},
                "warnings": (),
                "status": "failed",
                "failure": failure,
            },
        )
        raise SnapPipelineError(failure) from exc
    common = {
        **base_manifest,
        "timings": {"elapsed_seconds": round(clock() - started, 6)},
        "warnings": tuple(line for line in completed.stderr.splitlines() if "warn" in line.lower()),
    }
    return completed, common


def _publish_snap_result(
    context: _SnapRunContext,
    temporary_output: Path,
    completed: subprocess.CompletedProcess[str],
    common_manifest: Mapping[str, Any],
) -> SnapRunResult:
    if completed.returncode != 0 or not temporary_output.is_file():
        failure = (
            f"SNAP GPT exited with code {completed.returncode}. "
            "Inspect SNAP installation, auxiliary-data access, DEM availability, and the interim graph."
        )
        _atomic_json(context.manifest, {**common_manifest, "status": "failed", "failure": failure})
        raise SnapPipelineError(failure)
    _publish_file_once(temporary_output, context.destination)
    output_sha256 = sha256_file(context.destination)
    _atomic_json(
        context.manifest,
        {
            **common_manifest,
            "status": "success",
            "failure": None,
            "output": {"path": str(context.destination), "sha256": output_sha256},
        },
    )
    return SnapRunResult(
        context.destination,
        context.manifest,
        output_sha256,
        sha256_file(context.manifest),
        False,
    )


def run_snap_pipeline(
    *,
    input_path: Path,
    output_path: Path,
    interim_dir: Path,
    snap_executable: Path,
    plan: SnapPreprocessPlan = SnapPreprocessPlan(),
    manifest_path: Path | None = None,
    raw_root: Path | None = None,
    timeout_seconds: float | None = None,
    executor: Executor = _default_executor,
    snap_version: str = "unknown",
    clock: Clock = time.monotonic,
) -> SnapRunResult:
    """Run SNAP once, atomically publish output, and reuse only verified results."""
    context = _prepare_run(input_path, output_path, manifest_path, snap_executable, plan, raw_root)
    cached = _existing_result(context)
    if cached:
        return cached
    lock = _claim_run(context.destination)
    try:
        cached = _existing_result(context)
        if cached:
            return cached
        interim_dir.resolve().mkdir(parents=True, exist_ok=True)
        temporary_output, graph_path, graph_sha256 = _work_files(context, interim_dir, plan)
        base_manifest = _base_manifest(context, graph_sha256, snap_version)
        completed, common = _execute_snap(
            context, graph_path, base_manifest, executor, timeout_seconds, clock
        )
        return _publish_snap_result(context, temporary_output, completed, common)
    finally:
        lock.unlink(missing_ok=True)


def _write_channel_raster(
    destination: Path,
    channels: Mapping[str, np.ndarray],
    grid: RasterGrid,
    shape: tuple[int, ...],
    rasterio: Any,
    affine_type: Any,
) -> tuple[str, ...]:
    names = tuple(channels)
    with tempfile.NamedTemporaryFile(
        prefix=f".{destination.name}.", suffix=".tmp.tif", dir=destination.parent, delete=False
    ) as handle:
        temporary = Path(handle.name)
    try:
        with rasterio.open(
            temporary,
            "w",
            driver="GTiff",
            width=shape[1],
            height=shape[0],
            count=len(names),
            dtype="float32",
            crs=grid.crs,
            transform=affine_type(*grid.affine),
            nodata=np.nan,
            compress="deflate",
        ) as dataset:
            for band, name in enumerate(names, 1):
                dataset.write(channels[name].astype("float32"), band)
                dataset.set_band_description(band, name)
        _publish_file_once(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return names


def _channel_manifest(
    destination: Path,
    names: tuple[str, ...],
    shape: tuple[int, ...],
    grid: RasterGrid,
    calibration: str,
    software: Mapping[str, str] | None,
) -> dict[str, Any]:
    units = dict.fromkeys(("vv", "vh"), "linear power") | {
        "vv_db": "dB",
        "vh_db": "dB",
        "vv_vh_ratio": "unitless",
        "vv_minus_vh_db": "dB",
    }
    formulas = {
        "vv": f"{calibration.upper()}_VV",
        "vh": f"{calibration.upper()}_VH",
        "vv_db": "10*log10(vv)",
        "vh_db": "10*log10(vh)",
        "vv_vh_ratio": "vv/vh",
        "vv_minus_vh_db": "vv_db-vh_db",
    }
    return {
        "schema_version": "1.0",
        "stage": "sentinel1_derived_channels",
        "calibration": calibration,
        "channels": [
            {"band": index, "name": name, "formula": formulas[name], "units": units[name]}
            for index, name in enumerate(names, 1)
        ],
        "raster": {
            "crs": grid.crs,
            "affine": grid.affine,
            "resolution": grid.resolution,
            "width": shape[1],
            "height": shape[0],
            "nodata": "NaN",
        },
        "software": dict(software or {}),
        "output": {"path": str(destination), "sha256": sha256_file(destination)},
    }


def export_calibrated_channels(
    *,
    vv: np.ndarray,
    vh: np.ndarray,
    output_path: Path,
    grid: RasterGrid,
    calibration: Literal["sigma0", "gamma0"] = "sigma0",
    software: Mapping[str, str] | None = None,
    raw_root: Path | None = None,
) -> Path:
    """Export deterministic derived channels from already calibrated VV/VH arrays."""
    try:
        import rasterio
        from affine import Affine
    except ImportError as exc:  # pragma: no cover - exercised without geo extra
        raise SnapPipelineError("install the 'geo' extra to export raster channels") from exc
    destination = output_path.resolve()
    if _is_raw_destination(destination, raw_root):
        raise SnapPipelineError("derived channels must never be written under data/raw")
    manifest_path = destination.with_suffix(destination.suffix + ".manifest.json")
    if destination.exists() or manifest_path.exists():
        raise SnapPipelineError("refusing to overwrite derived channels or provenance")
    channels = derived_channels(vv, vh)
    shape = np.asarray(vv).shape
    if len(shape) != 2:
        raise ValueError("VV and VH must be two-dimensional rasters")
    destination.parent.mkdir(parents=True, exist_ok=True)
    names = _write_channel_raster(destination, channels, grid, shape, rasterio, Affine)
    _atomic_json(
        manifest_path,
        _channel_manifest(destination, names, shape, grid, calibration, software),
    )
    return destination
