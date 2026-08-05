"""Offline command tests for operational Steps 04-10 CLI boundaries."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from typer.testing import CliRunner

from marine_dataset.cli import _weather_raw_path, app
from marine_dataset.config import load_config

RUNNER = CliRunner()
SHIPPED_CONFIG = Path("configs/default.yaml").resolve()


def test_preprocess_dry_run_emits_snap_plan() -> None:
    result = RUNNER.invoke(
        app,
        ["preprocess", "--config", str(SHIPPED_CONFIG), "--dry-run"],
    )

    assert result.exit_code == 0, result.output
    assert '"calibration": "sigma0"' in result.output
    assert '"dry_run": true' in result.output


def test_weather_cache_path_hashes_full_request_parameters() -> None:
    config = load_config(SHIPPED_CONFIG)
    region = config.regions[0]
    wind = {"latitude": 44.5, "longitude": 52.0, "hourly": "wind_speed_10m"}
    rain = {**wind, "hourly": "precipitation"}

    first = _weather_raw_path(config, region, wind)
    repeated = _weather_raw_path(config, region, wind)
    changed = _weather_raw_path(config, region, rain)

    assert first == repeated
    assert first != changed


def test_align_writes_auditable_weather_and_ocean_matches(tmp_path: Path) -> None:
    source = tmp_path / "alignment.json"
    output = tmp_path / "aligned.json"
    source.write_text(
        json.dumps(
            {
                "acquisition_start": "2025-01-01T00:00:00Z",
                "acquisition_end": "2025-01-01T00:20:00Z",
                "weather": [
                    {
                        "observed_at": "2025-01-01T00:10:00Z",
                        "value": 4.5,
                        "record_id": "weather:1",
                    }
                ],
                "ocean": [
                    {
                        "observed_at": "2025-01-01T00:10:00Z",
                        "value": 0.25,
                        "record_id": "ocean:1",
                    }
                ],
                "ocean_temporal_semantics": "daily_mean",
                "ocean_coverage_fraction": 0.95,
            }
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(app, ["align", "--input", str(source), "--output", str(output)])

    assert result.exit_code == 0, result.output
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["weather"]["source_record_ids"] == ["weather:1"]
    assert payload["ocean"]["temporal_semantics"] == "daily_mean"
    assert payload["ocean"]["represents_acquisition_instant"] is False


def test_tile_uses_grid_quality_policy_and_persists_masks_and_metadata(tmp_path: Path) -> None:
    input_path = tmp_path / "scene.npz"
    grid_path = tmp_path / "grid.json"
    output_dir = tmp_path / "tiles"
    np.savez_compressed(
        input_path,
        values=np.ones((1, 2, 2), dtype=np.float32),
        class_mask=np.array([[0, 2], [2, 0]], dtype=np.uint8),
        water_mask=np.ones((2, 2), dtype=np.uint8),
        invalid_mask=np.zeros((2, 2), dtype=np.uint8),
    )
    grid_path.write_text(
        json.dumps(
            {
                "crs": "EPSG:32639",
                "affine": [10, 0, 100, 0, -10, 200],
                "channels": ["vv_db"],
                "temporal_semantics": "instantaneous",
                "empty_mask_policy": "error",
                "thresholds": {
                    "minimum_valid_percent": 100,
                    "minimum_water_percent": 100,
                    "minimum_positive_pixels": 2,
                },
                "context": {"environmental_record_ids": ["weather:1"]},
            }
        ),
        encoding="utf-8",
    )

    result = RUNNER.invoke(
        app,
        [
            "tile",
            "--input",
            str(input_path),
            "--grid-json",
            str(grid_path),
            "--output-dir",
            str(output_dir),
            "--tile-size",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    with np.load(output_dir / "tile_r0_c0.npz") as tile:
        assert tile["class_mask"].tolist() == [[0, 2], [2, 0]]
    index = json.loads((output_dir / "tile_index.json").read_text(encoding="utf-8"))
    assert index[0]["transform"] == [10.0, 0.0, 100.0, 0.0, -10.0, 200.0]
    assert index[0]["context"]["environmental_record_ids"] == ["weather:1"]
    assert index[0]["temporal_semantics"] == "instantaneous"


def test_build_manifest_creates_schema_bundle_offline(tmp_path: Path) -> None:
    output_dir = tmp_path / "manifest"

    result = RUNNER.invoke(
        app,
        ["build-manifest", "--output-dir", str(output_dir), "--allow-empty"],
    )

    assert result.exit_code == 0, result.output
    assert (output_dir / "dataset_manifest.parquet").is_file()
    assert (output_dir / "ml_export_contract.json").is_file()
    assert (output_dir / "checksums.sha256").is_file()


def test_tile_rejects_invalid_edge_and_temporal_policies(tmp_path: Path) -> None:
    source = tmp_path / "scene.npy"
    grid = tmp_path / "grid.json"
    np.save(source, np.ones((2, 2), dtype=np.float32))
    grid.write_text(
        json.dumps(
            {
                "crs": "EPSG:4326",
                "affine": [1, 0, 0, 0, -1, 2],
                "channels": ["vv"],
                "temporal_semantics": "forecast_guess",
                "context": {"unmatched_reasons": ["not_available"]},
            }
        ),
        encoding="utf-8",
    )

    temporal = RUNNER.invoke(
        app,
        [
            "tile",
            "--input",
            str(source),
            "--grid-json",
            str(grid),
            "--output-dir",
            str(tmp_path / "out"),
        ],
    )
    edge = RUNNER.invoke(app, ["tile", "--edge-policy", "truncate", "--dry-run"])

    assert temporal.exit_code != 0
    assert "temporal_semantics" in temporal.output
    assert edge.exit_code != 0
    assert "edge_policy" in edge.output
