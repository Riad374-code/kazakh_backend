"""Focused integrity checks for source boundaries and atomic publishing."""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from marine_dataset.processing.sentinel1_pipeline import SnapPipelineError, run_snap_pipeline
from marine_dataset.sources.copernicus_marine import MarineSubsetRequest


def _executable(tmp_path: Path) -> Path:
    executable = tmp_path / ("gpt.exe" if os.name == "nt" else "gpt")
    executable.write_text("mock", encoding="utf-8")
    executable.chmod(0o755)
    return executable


def test_snap_publish_conflict_never_overwrites_competing_output(tmp_path: Path):
    source = tmp_path / "raw" / "scene.zip"
    source.parent.mkdir()
    source.write_bytes(b"raw")
    destination = tmp_path / "processed" / "scene.tif"

    def race_executor(args, timeout):
        graph = ET.parse(args[1]).getroot()
        write_node = next(node for node in graph.findall("node") if node.get("id") == "write")
        Path(write_node.findtext("parameters/file", default="")).write_bytes(b"candidate")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(b"competing-winner")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    with pytest.raises(SnapPipelineError, match="refusing to overwrite"):
        run_snap_pipeline(
            input_path=source,
            output_path=destination,
            interim_dir=tmp_path / "interim",
            snap_executable=_executable(tmp_path),
            raw_root=source.parent,
            executor=race_executor,
        )

    assert destination.read_bytes() == b"competing-winner"


@pytest.mark.parametrize(
    ("bbox", "start", "end", "message"),
    [
        ((54, 43, 50, 46), "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", "longitude"),
        ((50, -91, 54, 46), "2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z", "latitude"),
        ((50, 43, 54, 46), "2024-01-01T00:00:00", "2024-01-02T00:00:00Z", "timezone"),
        ((50, 43, 54, 46), "2024-01-03T00:00:00Z", "2024-01-02T00:00:00Z", "earlier"),
    ],
)
def test_marine_subset_rejects_invalid_spatial_temporal_boundaries(
    bbox, start: str, end: str, message: str
):
    with pytest.raises(ValueError, match=message):
        MarineSubsetRequest("dataset", ("uo",), bbox, start, end, "subset.nc", "reanalysis")


def test_assigned_source_functions_stay_within_fifty_ast_lines():
    source_root = Path(__file__).parents[2] / "src" / "marine_dataset"
    paths = (
        source_root / "processing" / "sentinel1_pipeline.py",
        source_root / "sources" / "copernicus_dataspace.py",
        source_root / "sources" / "copernicus_marine.py",
        source_root / "sources" / "sentinel3.py",
    )
    oversized = []
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                span = node.end_lineno - node.lineno + 1
                if span > 50:
                    oversized.append(f"{path.name}:{node.name}:{span}")
    assert oversized == []
