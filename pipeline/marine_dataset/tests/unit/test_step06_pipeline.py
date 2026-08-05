"""Step 06 executable Sentinel-1 SNAP pipeline contract tests."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np
import pytest

from marine_dataset.processing.sentinel1_pipeline import (
    RasterGrid,
    SnapPipelineError,
    SnapPreprocessPlan,
    build_snap_graph,
    export_calibrated_channels,
    run_snap_pipeline,
)


def _executable(tmp_path: Path) -> Path:
    executable = tmp_path / ("gpt.exe" if os.name == "nt" else "gpt")
    executable.write_text("mock", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def _write_output_executor(calls: list[tuple[str, ...]]):
    def execute(args, timeout):
        calls.append(tuple(args))
        graph = ET.parse(args[1]).getroot()
        write_node = next(node for node in graph.findall("node") if node.get("id") == "write")
        target = Path(write_node.findtext("parameters/file", default=""))
        target.write_bytes(b"processed-sar")
        return subprocess.CompletedProcess(args, 0, stdout="done", stderr="WARNING auxiliary")

    return execute


def test_snap_graph_encodes_full_scientific_plan(tmp_path: Path):
    plan = SnapPreprocessPlan(
        calibration="gamma0",
        convert_to_db=True,
        speckle_filter="Lee Sigma",
        reproject=True,
        aoi_wkt="POLYGON ((50 40, 51 40, 51 41, 50 40))",
    )
    root = ET.fromstring(build_snap_graph(plan, tmp_path / "in.zip", tmp_path / "out.tif"))
    operators = [node.findtext("operator") for node in root.findall("node")]

    assert operators == [
        "Read",
        "Apply-Orbit-File",
        "ThermalNoiseRemoval",
        "Remove-GRD-Border-Noise",
        "Calibration",
        "LinearToFromdB",
        "Speckle-Filter",
        "Terrain-Correction",
        "Reproject",
        "Subset",
        "Write",
    ]
    calibration = next(node for node in root.findall("node") if node.get("id") == "calibration")
    assert calibration.findtext("parameters/outputSigmaBand") == "false"
    assert calibration.findtext("parameters/outputGammaBand") == "true"
    assert root.find(".//node[@id='aoi-clip']/parameters/geoRegion").text == plan.aoi_wkt


def test_snap_run_is_atomic_restartable_and_manifest_is_stable(tmp_path: Path):
    source = tmp_path / "raw" / "scene.zip"
    source.parent.mkdir()
    source.write_bytes(b"raw-safe")
    output = tmp_path / "processed" / "scene.tif"
    calls: list[tuple[str, ...]] = []
    ticks = iter((10.0, 12.5))

    first = run_snap_pipeline(
        input_path=source,
        output_path=output,
        interim_dir=tmp_path / "interim",
        snap_executable=_executable(tmp_path),
        raw_root=tmp_path / "raw",
        executor=_write_output_executor(calls),
        snap_version="12.0.0",
        clock=lambda: next(ticks),
    )
    manifest_before = first.manifest_path.read_bytes()
    second = run_snap_pipeline(
        input_path=source,
        output_path=output,
        interim_dir=tmp_path / "interim",
        snap_executable=_executable(tmp_path),
        raw_root=tmp_path / "raw",
        executor=_write_output_executor(calls),
        snap_version="12.0.0",
    )

    assert first.restarted is False
    assert second.restarted is True
    assert len(calls) == 1
    assert second.manifest_path.read_bytes() == manifest_before
    payload = json.loads(manifest_before)
    assert payload["output"]["sha256"] == second.output_sha256
    assert first.manifest_sha256 == second.manifest_sha256
    assert payload["software"] == {"name": "ESA SNAP GPT", "version": "12.0.0"}
    assert payload["timings"] == {"elapsed_seconds": 2.5}
    assert not list(output.parent.glob("*.part*"))


def test_snap_failure_has_actionable_manifest_and_does_not_publish(tmp_path: Path):
    source = tmp_path / "scene.zip"
    source.write_bytes(b"raw")
    output = tmp_path / "processed" / "scene.tif"

    def fail(args, timeout):
        return subprocess.CompletedProcess(args, 7, stdout="", stderr="ERROR DEM unavailable")

    ticks = iter((1.0, 2.0))
    with pytest.raises(SnapPipelineError, match="auxiliary-data access, DEM availability"):
        run_snap_pipeline(
            input_path=source,
            output_path=output,
            interim_dir=tmp_path / "interim",
            snap_executable=_executable(tmp_path),
            executor=fail,
            clock=lambda: next(ticks),
        )

    assert not output.exists()
    payload = json.loads((output.with_suffix(".tif.manifest.json")).read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failure"].startswith("SNAP GPT exited with code 7")


def test_snap_rejects_missing_executable_and_raw_output(tmp_path: Path):
    source = tmp_path / "raw" / "scene.zip"
    source.parent.mkdir()
    source.write_bytes(b"raw")
    with pytest.raises(SnapPipelineError, match="was not found"):
        run_snap_pipeline(
            input_path=source,
            output_path=tmp_path / "processed" / "scene.tif",
            interim_dir=tmp_path / "interim",
            snap_executable=tmp_path / "missing-gpt",
        )
    with pytest.raises(SnapPipelineError, match="never be written under data/raw"):
        run_snap_pipeline(
            input_path=source,
            output_path=tmp_path / "raw" / "derived.tif",
            interim_dir=tmp_path / "interim",
            snap_executable=_executable(tmp_path),
            raw_root=tmp_path / "raw",
        )


def test_derived_channel_export_records_geospatial_contract(tmp_path: Path, monkeypatch):
    rasterio = pytest.importorskip("rasterio")
    monkeypatch.setenv("PROJ_LIB", str(Path(rasterio.__file__).parent / "proj_data"))
    monkeypatch.setenv("GDAL_DATA", str(Path(rasterio.__file__).parent / "gdal_data"))
    output = export_calibrated_channels(
        vv=np.array([[2.0, 4.0], [8.0, 16.0]]),
        vh=np.array([[1.0, 2.0], [4.0, 8.0]]),
        output_path=tmp_path / "processed" / "channels.tif",
        grid=RasterGrid(
            crs="EPSG:4326",
            affine=(0.1, 0.0, 50.0, 0.0, -0.1, 45.0),
            resolution=(0.1, 0.1),
        ),
        software={"marine-dataset": "0.1.0"},
    )

    payload = json.loads(output.with_suffix(".tif.manifest.json").read_text(encoding="utf-8"))
    assert output.is_file()
    assert [item["name"] for item in payload["channels"]] == [
        "vv",
        "vh",
        "vv_db",
        "vh_db",
        "vv_vh_ratio",
        "vv_minus_vh_db",
    ]
    assert payload["raster"]["width"] == 2
    assert payload["raster"]["crs"] == "EPSG:4326"
    assert payload["output"]["sha256"]
