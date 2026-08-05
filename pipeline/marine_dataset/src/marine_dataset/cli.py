"""Command-line interface for the marine-dataset pipeline.

Registers every command from pipeline_inst.md section 13. Commands that are not
yet implemented fail clearly (non-zero exit) and never report success.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import typer

from marine_dataset.config import Config, default_config, dump_config, load_config
from marine_dataset.logging_config import get_logger, setup_logging

app = typer.Typer(
    name="marine-data",
    help="Build a reproducible marine pollution / oil-spill detection dataset.",
    no_args_is_help=True,
)

log = get_logger("cli")

# Commands without an input artifact keep the old non-zero behavior. This is
# useful for callers that accidentally run a network/data step with no inputs.


def _load_config_or_default(config_path: Optional[Path]) -> Config:
    if config_path is not None:
        return load_config(config_path)
    return default_config()


def _not_implemented(command: str) -> None:
    message = (
        f"ERROR: command '{command}' is registered but not implemented "
        "in this build step. It will never report success. Implement it "
        "before use."
    )
    log.error(message)
    typer.secho(message, err=True)
    raise typer.Exit(code=2)


@app.command()
def init_config(
    config_path: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    output_config: Optional[Path] = typer.Option(None, "--output-config"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    base_dir: Path = typer.Option(Path("data"), "--base-dir"),
    create_dirs: bool = typer.Option(True, "--create-dirs/--no-create-dirs"),
) -> None:
    """Validate configuration and initialise the storage tree."""
    config = _load_config_or_default(config_path)
    resolved = config.paths.resolve_all(base_dir)

    if dry_run:
        print(dump_config(config))
        print(
            f"\n[init-config --dry-run] validated {config_path}; "
            f"would create dirs under {resolved.base}."
        )
        return

    if output_config is not None:
        _write_validated_config(config, config_path, output_config)
    if create_dirs:
        _create_storage_tree(config, base_dir)
        log.info("created storage tree under %s", resolved.base)


def _first_region(config: Config):
    if not config.regions:
        raise typer.BadParameter("configuration must contain at least one region")
    return config.regions[0]


def _emit_or_write(payload, output: Optional[Path]) -> None:
    text = json.dumps(payload, indent=2, default=str)
    if output is None:
        print(text)
        return
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(text + "\n", encoding="utf-8")


def _canonical_json_bytes(payload) -> bytes:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return (text + "\n").encode()


def _create_storage_tree(config: Config, base_dir: Path) -> None:
    resolved = config.paths.resolve_all(base_dir)
    for path in (
        resolved.raw,
        resolved.interim,
        resolved.processed,
        resolved.manifests,
        resolved.reports,
        resolved.cache,
        resolved.quarantine,
    ):
        path.mkdir(parents=True, exist_ok=True)
    for subdir in (
        "sentinel1",
        "sentinel3",
        "weather",
        "ocean",
        "vessels",
        "infrastructure",
        "labels",
    ):
        (resolved.raw / subdir).mkdir(parents=True, exist_ok=True)
    for subdir in ("scenes", "tiles", "masks", "environmental_grids"):
        (resolved.processed / subdir).mkdir(parents=True, exist_ok=True)


def _write_validated_config(config: Config, source: Path, output: Path) -> None:
    if output.exists() and output.resolve() == source.resolve():
        raise typer.BadParameter(
            "--output-config must differ from --config; refusing to overwrite the source."
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(dump_config(config), encoding="utf-8")
    log.info("wrote validated config to %s", output)


def _sentinel1_bodies(config: Config, region: Any) -> list[dict[str, Any]]:
    from marine_dataset.sources.sentinel1 import Sentinel1Query

    requested: set[str] = set()
    for item in config.scene_search.polarizations:
        requested.update(("VV", "VH") if item.value == "VV+VH" else (item.value,))
    directions = [item.value for item in config.scene_search.orbit_directions] or [None]
    relative_orbits = config.scene_search.relative_orbits or [None]
    return [
        Sentinel1Query(
            bbox=(region.min_lon, region.min_lat, region.max_lon, region.max_lat),
            start=f"{config.date_start.isoformat()}T00:00:00Z",
            end=f"{config.date_end.isoformat()}T23:59:59Z",
            polarizations=tuple(sorted(requested)) or ("VV",),
            orbit_direction=direction,
            relative_orbit=relative_orbit,
            platform=config.scene_search.platform,
            limit=min(config.scene_search.max_results, 1000),
        ).to_stac_body()
        for direction in directions
        for relative_orbit in relative_orbits
    ]


def _search_with_raw_pages(client: Any, bodies: list[dict[str, Any]], limit: int):
    pages: list[dict[str, Any]] = []
    found: dict[str, dict[str, Any]] = {}
    for query_index, body in enumerate(bodies):

        def preserve(page_number: int, payload: dict[str, Any], index: int = query_index):
            pages.append({"query_index": index, "page_number": page_number, "response": payload})

        for item in client.search(body, max_items=limit, on_page=preserve):
            found.setdefault(str(item["id"]), item)
    return pages, tuple(found.values())[:limit]


@app.command("search-sentinel1")
def search_sentinel1(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    """Search current CDSE STAC for Sentinel-1 IW GRD scenes."""
    from marine_dataset.sources.copernicus_dataspace import CDSEClient, write_raw_once
    from marine_dataset.sources.sentinel1 import parse_sentinel1_item

    cfg = load_config(config)
    region = _first_region(cfg)
    bodies = _sentinel1_bodies(cfg, region)
    if dry_run:
        _emit_or_write({"dry_run": True, "requests": bodies}, output)
        return
    client = CDSEClient(timeout=cfg.retry.http_timeout_seconds, max_attempts=cfg.retry.max_attempts)
    pages, items = _search_with_raw_pages(client, bodies, cfg.scene_search.max_results)
    raw_root = cfg.paths.resolve_all().raw / "sentinel1"
    search_id = hashlib.sha256(_canonical_json_bytes(bodies)).hexdigest()[:16]
    raw_result = write_raw_once(
        raw_root / f"catalogue_{search_id}.json", _canonical_json_bytes({"pages": pages})
    )
    scenes = [
        parse_sentinel1_item(item, cfg.dataset_version).model_dump(mode="json") for item in items
    ]
    _emit_or_write({"raw_response": str(raw_result.path), "scenes": scenes}, output)


def _download_cdse(
    product_id: str, output: Path, expected_sha256: Optional[str], dry_run: bool
) -> None:
    if dry_run:
        _emit_or_write({"dry_run": True, "product_id": product_id, "output": str(output)}, None)
        return
    from marine_dataset.sources.copernicus_dataspace import CDSEClient

    try:
        result = CDSEClient().download_product(product_id, output, expected_sha256=expected_sha256)
    except Exception as exc:
        retry_path = Path("data/interim/retry") / f"{product_id}.json"
        _emit_or_write(
            {"product_id": product_id, "output": str(output), "error_type": type(exc).__name__},
            retry_path,
        )
        raise
    _emit_or_write(
        {"path": str(result.path), "sha256": result.sha256, "created": result.created}, None
    )


@app.command("download-sentinel1")
def download_sentinel1(
    product_id: str = typer.Option(..., "--product-id"),
    output: Path = typer.Option(..., "--output"),
    expected_sha256: Optional[str] = typer.Option(None, "--expected-sha256"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Download one authenticated Sentinel-1 product through CDSE OData."""
    _download_cdse(product_id, output, expected_sha256, dry_run)


@app.command("search-sentinel3")
def search_sentinel3(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    collection: Optional[str] = typer.Option(None, "--collection"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    """Search a configured Sentinel-3 OLCI/SLSTR STAC collection."""
    from marine_dataset.sources.copernicus_dataspace import CDSEClient, write_raw_once
    from marine_dataset.sources.sentinel3 import parse_sentinel3_item, validate_collection

    cfg = load_config(config)
    region = _first_region(cfg)
    selected = collection or cfg.sentinel3_collections[0]
    body = {
        "collections": [selected],
        "bbox": [region.min_lon, region.min_lat, region.max_lon, region.max_lat],
        "datetime": f"{cfg.date_start.isoformat()}T00:00:00Z/{cfg.date_end.isoformat()}T23:59:59Z",
        "limit": min(cfg.scene_search.max_results, 1000),
    }
    if dry_run:
        _emit_or_write({"dry_run": True, "request": body}, output)
        return
    client = CDSEClient(timeout=cfg.retry.http_timeout_seconds, max_attempts=cfg.retry.max_attempts)
    validate_collection(selected, client.collection_ids())
    pages = []
    items = client.search(
        body,
        max_items=cfg.scene_search.max_results,
        on_page=lambda page_number, payload: pages.append(
            {"page_number": page_number, "response": payload}
        ),
    )
    raw_root = cfg.paths.resolve_all().raw / "sentinel3"
    search_id = hashlib.sha256(_canonical_json_bytes(body)).hexdigest()[:16]
    raw_result = write_raw_once(
        raw_root / f"catalogue_{search_id}.json", _canonical_json_bytes({"pages": pages})
    )
    _emit_or_write(
        {
            "raw_response": str(raw_result.path),
            "scenes": [parse_sentinel3_item(item).__dict__ for item in items],
        },
        output,
    )


@app.command("download-sentinel3")
def download_sentinel3(
    product_id: str = typer.Option(..., "--product-id"),
    output: Path = typer.Option(..., "--output"),
    expected_sha256: Optional[str] = typer.Option(None, "--expected-sha256"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Download one authenticated original Sentinel-3 product."""
    _download_cdse(product_id, output, expected_sha256, dry_run)


def _weather_raw_path(config: Config, region: Any, params: dict[str, Any]) -> Path:
    request_hash = hashlib.sha256(_canonical_json_bytes(params)).hexdigest()[:16]
    filename = (
        f"{region.name}_{config.date_start.isoformat()}_{config.date_end.isoformat()}_"
        f"{config.weather_model}_{request_hash}.json"
    )
    return config.paths.resolve_all().raw / "weather" / filename


def _sentinel3_request(
    input_path: Path,
    output: Path,
    variable: str,
    quality_variable: Optional[str],
    invalid_bits: Optional[list[int]],
    cloud_bits: Optional[list[int]],
    uncertainty_variable: Optional[str],
):
    from marine_dataset.sources.sentinel3 import Sentinel3Variable

    try:
        selected = Sentinel3Variable(variable)
    except ValueError as exc:
        raise typer.BadParameter(f"unsupported Sentinel-3 variable: {variable}") from exc
    if (invalid_bits or cloud_bits) and not quality_variable:
        raise typer.BadParameter("quality bit positions require --quality-variable")
    request = {
        "input": str(input_path),
        "output": str(output),
        "variable": selected.value,
        "quality_variable": quality_variable,
        "invalid_bits": invalid_bits or [],
        "cloud_bits": cloud_bits or [],
        "uncertainty_variable": uncertainty_variable,
        "grid_status": "native",
    }
    return selected, request


@app.command("process-sentinel3")
def process_sentinel3(
    input_path: Path = typer.Option(..., "--input"),
    output: Path = typer.Option(..., "--output"),
    variable: str = typer.Option(..., "--variable"),
    quality_variable: Optional[str] = typer.Option(None, "--quality-variable"),
    invalid_bits: Optional[list[int]] = typer.Option(None, "--invalid-bit"),
    cloud_bits: Optional[list[int]] = typer.Option(None, "--cloud-bit"),
    uncertainty_variable: Optional[str] = typer.Option(None, "--uncertainty-variable"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Extract a documented Sentinel-3 variable while retaining its native grid."""
    from marine_dataset.sources.sentinel3 import process_sentinel3_file

    selected, request = _sentinel3_request(
        input_path,
        output,
        variable,
        quality_variable,
        invalid_bits,
        cloud_bits,
        uncertainty_variable,
    )
    if dry_run:
        _emit_or_write({"dry_run": True, **request}, None)
        return
    extracted = process_sentinel3_file(
        input_path,
        output,
        selected,
        quality_variable=quality_variable,
        invalid_bits=tuple(invalid_bits or ()),
        cloud_bits=tuple(cloud_bits or ()),
        uncertainty_variable=uncertainty_variable,
    )
    _emit_or_write(
        {
            **request,
            "native_shape": extracted.native_shape,
            "native_resolution_m": extracted.native_resolution_m,
            "units": extracted.units,
            "is_proxy": extracted.is_proxy,
        },
        None,
    )


@app.command("collect-weather")
def collect_weather(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    output: Optional[Path] = typer.Option(None, "--output"),
) -> None:
    """Collect explicit-model historical weather for the first configured region."""
    from marine_dataset.sources.open_meteo import OpenMeteoClient, WeatherRequest

    cfg = load_config(config)
    region = _first_region(cfg)
    variables = tuple(cfg.weather_variables)
    if not variables:
        raise typer.BadParameter("weather_variables must be configured")
    request = WeatherRequest(
        (region.min_lat + region.max_lat) / 2,
        (region.min_lon + region.max_lon) / 2,
        cfg.date_start.isoformat(),
        cfg.date_end.isoformat(),
        variables,
        cfg.weather_model,
    )
    if dry_run:
        _emit_or_write({"dry_run": True, "params": request.params()}, output)
        return
    raw_output = output or _weather_raw_path(cfg, region, request.params())
    dataset = OpenMeteoClient(
        timeout=cfg.retry.http_timeout_seconds,
        max_attempts=cfg.retry.max_attempts,
        requests_per_minute=cfg.rate_limit.requests_per_minute,
    ).collect(request, raw_path=raw_output)
    _emit_or_write(
        {
            "model": dataset.model,
            "records": [item.__dict__ for item in dataset.records],
            "missing_variables": dataset.missing_variables,
            "raw_response": str(raw_output),
            "attribution": dataset.attribution,
            "licence_note": dataset.licence_note,
        },
        None,
    )


@app.command("collect-ocean")
def collect_ocean(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    output_dir: Path = typer.Option(Path("data/raw/ocean"), "--output-dir"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Subset a user-selected Copernicus Marine dataset; never guesses IDs."""
    from marine_dataset.sources.copernicus_marine import CopernicusMarineClient, MarineSubsetRequest

    cfg = load_config(config)
    if not cfg.ocean_dataset_id or not cfg.ocean_variables:
        raise typer.BadParameter(
            "configure ocean_dataset_id and ocean_variables from `copernicusmarine describe`"
        )
    region = _first_region(cfg)
    request = MarineSubsetRequest(
        cfg.ocean_dataset_id,
        tuple(cfg.ocean_variables),
        (region.min_lon, region.min_lat, region.max_lon, region.max_lat),
        f"{cfg.date_start.isoformat()}T00:00:00Z",
        f"{cfg.date_end.isoformat()}T23:59:59Z",
        "ocean_subset.nc",
        cfg.observations[0].value,
    )
    if dry_run:
        _emit_or_write({"dry_run": True, "request": request.__dict__}, None)
        return
    result = CopernicusMarineClient().subset(
        request,
        output_dir,
        allow_forecast=request.observation_type == "forecast"
        and any(item.value == "forecast" for item in cfg.observations),
    )
    _emit_or_write(
        {
            "dataset_id": request.dataset_id,
            "observation_type": request.observation_type,
            "path": str(result.path),
            "metadata_path": str(result.metadata_path),
            "observation_type_source": result.observation_type_source,
        },
        None,
    )


@app.command("import-labels")
def import_labels(
    input_path: Optional[Path] = typer.Option(None, "--input"),
    scene_id: str = typer.Option("dry-run-scene", "--scene-id"),
    licence: str = typer.Option("unresolved", "--licence"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Validate ontology or import GeoJSON labels."""
    from marine_dataset.labels.importers import import_geojson_labels
    from marine_dataset.labels.ontology import load_ontology

    ontology = load_ontology(Path("configs/label_ontology.yaml"))
    if dry_run:
        _emit_or_write({"dry_run": True, "ontology_classes": len(ontology.classes)}, None)
        return
    if input_path is None:
        raise typer.BadParameter("--input is required unless --dry-run")
    labels = import_geojson_labels(
        input_path,
        scene_id=scene_id,
        dataset_version="0.1.0",
        label_source=input_path.name,
        licence=licence,
        ontology={entry.class_id: entry.name for entry in ontology.classes},
    )
    _emit_or_write([item.model_dump(mode="json") for item in labels], None)


def _snap_plan(config: Config):
    from marine_dataset.processing.sentinel1_pipeline import SnapPreprocessPlan

    return SnapPreprocessPlan(
        apply_orbit=config.preprocessing.apply_precise_orbit,
        remove_thermal_noise=config.preprocessing.remove_thermal_noise,
        calibration="sigma0",
        convert_to_db=config.preprocessing.convert_to_db,
        speckle_filter="Lee" if config.preprocessing.speckle_filter else None,
        terrain_correct=config.preprocessing.terrain_correct,
        target_crs=config.tile.target_crs,
        pixel_spacing_m=config.tile.target_resolution_m or 10.0,
    )


def _snap_executable(option: Optional[Path]) -> Optional[Path]:
    configured = os.getenv("SNAP_GPT")
    return option or (Path(configured) if configured else None)


@app.command("preprocess")
def preprocess(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    snap_executable: Optional[Path] = typer.Option(None, "--snap-executable"),
    manifest: Optional[Path] = typer.Option(None, "--manifest"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run the restartable ESA SNAP Sentinel-1 scientific preprocessing graph."""
    from marine_dataset.processing.sentinel1_pipeline import run_snap_pipeline

    cfg = load_config(config)
    plan = _snap_plan(cfg)
    if dry_run:
        _emit_or_write({"dry_run": True, "plan": plan.__dict__}, None)
        return
    executable = _snap_executable(snap_executable)
    if input_path is None or output is None or executable is None:
        raise typer.BadParameter(
            "--input, --output and --snap-executable (or SNAP_GPT) are required"
        )
    result = run_snap_pipeline(
        input_path=input_path,
        output_path=output,
        interim_dir=cfg.paths.resolve_all().interim,
        snap_executable=executable,
        plan=plan,
        manifest_path=manifest,
        raw_root=cfg.paths.resolve_all().raw,
        timeout_seconds=cfg.retry.http_timeout_seconds * 100,
    )
    _emit_or_write(
        {
            "output": str(result.output_path),
            "manifest": str(result.manifest_path),
            "sha256": result.output_sha256,
            "restarted": result.restarted,
        },
        None,
    )


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _timed_values(items: list[dict[str, Any]]):
    from marine_dataset.alignment.pipeline import TimedValue

    return tuple(
        TimedValue(_parse_time(item["observed_at"]), float(item["value"]), str(item["record_id"]))
        for item in items
    )


def _align_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from marine_dataset.alignment.pipeline import (
        align_ocean_value,
        align_weather_value,
        scene_midpoint,
    )

    midpoint = scene_midpoint(
        _parse_time(payload["acquisition_start"]), _parse_time(payload["acquisition_end"])
    )
    weather = align_weather_value(
        midpoint,
        _timed_values(payload.get("weather", [])),
        preferred_minutes=float(payload.get("weather_preferred_minutes", 30)),
        acceptable_minutes=float(payload.get("weather_acceptable_minutes", 90)),
        interpolate=bool(payload.get("weather_interpolate", False)),
    )
    ocean = align_ocean_value(
        midpoint,
        _timed_values(payload.get("ocean", [])),
        acceptable_minutes=float(payload.get("ocean_acceptable_minutes", 90)),
        temporal_semantics=payload.get("ocean_temporal_semantics", "instantaneous"),
        spatial_coverage_fraction=float(payload.get("ocean_coverage_fraction", 0)),
        minimum_coverage_fraction=float(payload.get("minimum_ocean_coverage_fraction", 0.8)),
    )
    return {
        "scene_midpoint_utc": midpoint.isoformat(),
        "weather": asdict(weather),
        "ocean": asdict(ocean),
    }


@app.command("align")
def align(
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Align JSON weather/ocean records to a scene acquisition midpoint."""
    if dry_run:
        _emit_or_write(
            {
                "dry_run": True,
                "input_contract": "scene start/end plus weather/ocean timed values",
                "weather_preferred_minutes": 30,
                "weather_acceptable_minutes": 90,
            },
            output,
        )
        return
    if input_path is None or output is None:
        raise typer.BadParameter("--input and --output are required unless --dry-run")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    _emit_or_write(_align_payload(payload), output)


EDGE_POLICIES = frozenset({"drop", "pad"})
TEMPORAL_SEMANTICS = frozenset(
    {"unspecified", "instantaneous", "daily_mean", "period_mean", "scene_interval", "static"}
)


def _validate_tile_options(tile_size: int, overlap: int, edge_policy: str) -> None:
    if tile_size <= 0 or overlap < 0 or overlap >= tile_size:
        raise typer.BadParameter("require tile_size > 0 and 0 <= overlap < tile_size")
    if edge_policy not in EDGE_POLICIES:
        raise typer.BadParameter("edge_policy must be drop or pad")


def _load_tile_arrays(path: Path):
    import numpy as np

    loaded = np.load(path, allow_pickle=False)
    if not isinstance(loaded, np.lib.npyio.NpzFile):
        return np.asarray(loaded).copy(), {}
    try:
        if "values" not in loaded.files:
            raise ValueError("NPZ input must contain a values array")
        masks = {
            name: np.asarray(loaded[name]).copy()
            for name in ("class_mask", "water_mask", "land_mask", "invalid_mask")
            if name in loaded.files
        }
        return np.asarray(loaded["values"]).copy(), masks
    finally:
        loaded.close()


def _tile_settings(spec: dict[str, Any], values: Any):
    from affine import Affine

    from marine_dataset.alignment.spatial import GridSpec
    from marine_dataset.processing.tiling import TileContext, TileThresholds

    temporal = str(spec.get("temporal_semantics", "unspecified"))
    if temporal not in TEMPORAL_SEMANTICS:
        raise typer.BadParameter("temporal_semantics is unsupported")
    context_payload = spec.get("context", {})
    context = TileContext(
        tuple(context_payload.get("environmental_record_ids", [])),
        tuple(context_payload.get("vessel_context_ids", [])),
        tuple(context_payload.get("infrastructure_context_ids", [])),
        tuple(context_payload.get("unmatched_reasons", [])),
    )
    thresholds = TileThresholds(**spec.get("thresholds", {}))
    empty_policy = str(spec.get("empty_mask_policy", "keep"))
    if empty_policy not in {"keep", "drop", "error"}:
        raise typer.BadParameter("empty_mask_policy must be keep, drop, or error")
    grid = GridSpec(
        str(spec["crs"]),
        Affine(*spec["affine"]),
        values.shape[-1],
        values.shape[-2],
        spec.get("nodata"),
    )
    return grid, context, thresholds, empty_policy, temporal


def _mask_tiles(class_mask: Any, tile_size: int, overlap: int, edge_policy: str):
    from marine_dataset.processing.tiling import iter_tiles

    if class_mask is None:
        return {}
    return {
        (item.row, item.col): item.values
        for item in iter_tiles(
            class_mask,
            tile_size=tile_size,
            overlap=overlap,
            edge_policy=edge_policy,
            nodata=0,
        )
    }


def _tile_record(item: Any, target: Path, temporal: str) -> dict[str, Any]:
    return {
        "row": item.row,
        "col": item.col,
        "path": str(target),
        "bbox": item.bbox,
        "footprint_wkt": item.footprint_wkt,
        "crs": item.crs,
        "transform": list(tuple(item.transform)[:6]),
        "resolution": item.resolution,
        "channels": item.channels,
        "class_histogram": item.class_histogram,
        "positive_pixel_count": item.positive_pixel_count,
        "water_percent": item.water_percent,
        "land_percent": item.land_percent,
        "invalid_pixel_percent": item.invalid_pixel_percent,
        "context": asdict(item.context),
        "temporal_semantics": temporal,
    }


def _write_tile_outputs(tiles: tuple[Any, ...], masks: dict[Any, Any], root: Path, temporal: str):
    import numpy as np

    targets = tuple(root / f"tile_r{item.row}_c{item.col}.npz" for item in tiles)
    index_path = root / "tile_index.json"
    existing = tuple(path for path in (*targets, index_path) if path.exists())
    if existing:
        raise FileExistsError(f"refusing to overwrite tile artifact: {existing[0]}")
    root.mkdir(parents=True, exist_ok=True)
    records = []
    for item, target in zip(tiles, targets, strict=True):
        class_mask = masks.get((item.row, item.col))
        arrays = {"values": item.values}
        if class_mask is not None:
            arrays = {**arrays, "class_mask": class_mask}
        np.savez_compressed(target, **arrays)
        records.append(_tile_record(item, target, temporal))
    _emit_or_write(records, index_path)


@app.command("tile")
def tile(
    input_path: Optional[Path] = typer.Option(None, "--input"),
    grid_json: Optional[Path] = typer.Option(None, "--grid-json"),
    output_dir: Optional[Path] = typer.Option(None, "--output-dir"),
    tile_size: int = typer.Option(256, "--tile-size"),
    overlap: int = typer.Option(0, "--overlap"),
    edge_policy: str = typer.Option("drop", "--edge-policy"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Create deterministic geospatial NPZ tiles and a JSON tile index."""
    from marine_dataset.processing.tiling import iter_geospatial_tiles

    _validate_tile_options(tile_size, overlap, edge_policy)
    if dry_run:
        _emit_or_write(
            {
                "dry_run": True,
                "tile_size": tile_size,
                "overlap": overlap,
                "edge_policy": edge_policy,
            },
            None,
        )
        return
    if input_path is None or grid_json is None or output_dir is None:
        raise typer.BadParameter("--input, --grid-json and --output-dir are required")
    spec = json.loads(grid_json.read_text(encoding="utf-8"))
    values, masks = _load_tile_arrays(input_path)
    grid, context, thresholds, empty_policy, temporal = _tile_settings(spec, values)
    tiles = tuple(
        iter_geospatial_tiles(
            values,
            grid=grid,
            channels=tuple(spec["channels"]),
            context=context,
            tile_size=tile_size,
            overlap=overlap,
            edge_policy=edge_policy,
            thresholds=thresholds,
            empty_mask_policy=empty_policy,
            **masks,
        )
    )
    class_tiles = _mask_tiles(masks.get("class_mask"), tile_size, overlap, edge_policy)
    _write_tile_outputs(tiles, class_tiles, output_dir, temporal)


@app.command("build-manifest")
def build_manifest(
    output_dir: Path = typer.Option(Path("data/manifests"), "--output-dir"),
    tables_json: Optional[Path] = typer.Option(None, "--tables-json"),
    allow_empty: bool = typer.Option(False, "--allow-empty"),
) -> None:
    """Validate rows and build the complete Step-09 artifact and ML-contract bundle."""
    from marine_dataset.manifests.dataset import DatasetTables, build_dataset_artifacts

    if tables_json is None and not allow_empty:
        raise typer.BadParameter(
            "--tables-json is required; use --allow-empty for a schema-only bundle"
        )
    payload = json.loads(tables_json.read_text(encoding="utf-8")) if tables_json else {}
    outputs = build_dataset_artifacts(
        output_dir,
        DatasetTables(
            tables=payload.get("tables", {}),
            dataset_version=payload.get("dataset_version", "0.1.0"),
            ml_export_contract=payload.get("ml_export_contract", {}),
        ),
        source_registry=Path("metadata/source_registry.yaml"),
        label_ontology=Path("configs/label_ontology.yaml"),
    )
    _emit_or_write({name: str(path) for name, path in outputs.items()}, None)


def _json_rows(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(row) for row in payload]
    if isinstance(payload, dict):
        rows = payload.get("rows", payload.get("items", []))
        if isinstance(rows, list):
            return [dict(row) for row in rows]
    raise typer.BadParameter("input JSON must be a list or an object with rows/items")


def _input_or_placeholder(command: str, input_path: Optional[Path], dry_run: bool) -> None:
    if input_path is None and not dry_run:
        _not_implemented(command)


@app.command("collect-vessels")
def collect_vessels(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Normalize an authorised vessel fixture; live GFW access is opt-in."""
    _ = load_config(config)
    _input_or_placeholder("collect-vessels", input_path, dry_run)
    if dry_run:
        _emit_or_write(
            {"dry_run": True, "status": "unavailable_without_authorised_gfw_access"}, output
        )
        return
    from marine_dataset.vessels import reject_speed_jumps

    rows = reject_speed_jumps(_json_rows(input_path))
    _emit_or_write({"rows": rows, "status": "fixture"}, output)


@app.command("collect-infrastructure")
def collect_infrastructure(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Normalize an OSM/registry fixture while preserving source IDs."""
    _ = load_config(config)
    _input_or_placeholder("collect-infrastructure", input_path, dry_run)
    if dry_run:
        _emit_or_write({"dry_run": True, "status": "no_authoritative_source_queried"}, output)
        return
    from marine_dataset.context import merge_context, normalize_context

    rows = _json_rows(input_path)
    normalized = merge_context(
        normalize_context(row, source_name=str(row.get("source_name", "fixture"))) for row in rows
    )
    _emit_or_write({"rows": normalized, "status": "fixture"}, output)


@app.command("split")
def split_data(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Assign deterministic grouped train/validation/test splits."""
    cfg = load_config(config)
    _input_or_placeholder("split", input_path, dry_run)
    from marine_dataset.splitting import assign_splits

    if dry_run:
        _emit_or_write({"dry_run": True, "strategy": cfg.split_strategy, "seed": cfg.seed}, output)
        return
    _emit_or_write(
        {
            "rows": assign_splits(
                _json_rows(input_path),
                strategy=cfg.split_strategy,
                seed=cfg.seed,
                val_fraction=cfg.split_val_holdout,
                test_fraction=cfg.split_test_holdout,
            )
        },
        output,
    )


@app.command("validate")
def validate(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run deterministic manifest quality checks."""
    _ = load_config(config)
    _input_or_placeholder("validate", input_path, dry_run)
    from marine_dataset.validation import validate_rows

    if dry_run:
        _emit_or_write({"dry_run": True, "status": "not_run"}, output)
        return
    report = validate_rows(_json_rows(input_path))
    _emit_or_write(report, output)
    if report["status"] == "fail":
        raise typer.Exit(code=1)


@app.command("build-dataset-card")
def build_card(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    output_dir: Path = typer.Option(Path("data/reports"), "--output-dir"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Write a minimal reproducibility card and known-issues file."""
    cfg = load_config(config)
    from marine_dataset.dataset_card import build_dataset_card

    if dry_run:
        _emit_or_write({"dry_run": True, "output_dir": str(output_dir)}, None)
        return
    card, issues = build_dataset_card(output_dir, dataset_version=cfg.dataset_version)
    _emit_or_write({"dataset_card": str(card), "known_issues": str(issues)}, None)


@app.command("run-all")
def run_all(
    config: Path = typer.Option(Path("configs/default.yaml"), "--config"),
    output_dir: Path = typer.Option(Path("data/reports"), "--output-dir"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    """Run the offline-safe stages and record a durable checkpoint."""
    cfg = load_config(config)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = output_dir / "run_all_checkpoint.json"
    payload = {
        "config_version": cfg.dataset_version,
        "status": "dry_run" if dry_run else "completed",
        "steps": ["init-config", "validate", "build-dataset-card"],
    }
    if not dry_run:
        from marine_dataset.dataset_card import build_dataset_card

        build_dataset_card(output_dir, dataset_version=cfg.dataset_version)
    _emit_or_write(payload, checkpoint)


def _run_stage(
    command: str, function: Any, input_path: Optional[Path], output: Optional[Path], dry_run: bool
) -> None:
    if dry_run:
        _emit_or_write({"dry_run": True, "stage": command}, output)
        return
    if input_path is None:
        raise typer.BadParameter("--input is required")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    if function.__name__ == "weekly_anomalies":
        payload = payload.get("rows", payload) if isinstance(payload, dict) else payload
    elif function.__name__ == "rank_events":
        payload = payload.get("rows", payload) if isinstance(payload, dict) else payload
    if function.__name__ == "risk_heatmap":
        result = function(payload.get("cells", []), payload.get("events", []))
    elif (
        function.__name__ == "advection_forecast"
        and isinstance(payload, dict)
        and "start" in payload
    ):
        result = function(
            **{
                key: value
                for key, value in payload.items()
                if key
                in {
                    "start",
                    "wind_speed_mps",
                    "wind_direction_deg",
                    "current_u_mps",
                    "current_v_mps",
                    "horizons_days",
                }
            }
        )
    else:
        result = function(payload)
    _emit_or_write(result, output)


@app.command("detect")
def detect(
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    from marine_dataset.stages import weekly_anomalies

    _run_stage("stage1-anomaly", weekly_anomalies, input_path, output, dry_run)


@app.command("classify")
def classify_stage(
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    from marine_dataset.stages import classify

    _run_stage("stage2-classification", classify, input_path, output, dry_run)


@app.command("forecast")
def forecast_stage(
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    from marine_dataset.stages import advection_forecast

    _run_stage("stage3-forecast", advection_forecast, input_path, output, dry_run)


@app.command("prioritize")
def prioritize_stage(
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    from marine_dataset.stages import rank_events

    _run_stage("stage4-prioritization", rank_events, input_path, output, dry_run)


@app.command("energy-impact")
def energy_impact_stage(
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    from marine_dataset.stages.impact import energy_impact

    _run_stage("stage5-energy-impact", energy_impact, input_path, output, dry_run)


@app.command("risk-heatmap")
def risk_heatmap_stage(
    input_path: Optional[Path] = typer.Option(None, "--input"),
    output: Optional[Path] = typer.Option(None, "--output"),
    dry_run: bool = typer.Option(False, "--dry-run"),
) -> None:
    from marine_dataset.stages.heatmap import risk_heatmap

    _run_stage("stage6-risk-heatmap", risk_heatmap, input_path, output, dry_run)


@app.command("version")
def version() -> None:
    """Print the package version."""
    from marine_dataset import __version__

    print(f"marine-data {__version__}")


if __name__ == "__main__":
    setup_logging("INFO")
    app()
