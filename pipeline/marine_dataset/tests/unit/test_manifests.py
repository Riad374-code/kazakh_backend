"""Step 02 tests: processing manifests."""

from __future__ import annotations

from datetime import datetime, timezone

from marine_dataset.manifests.builder import (
    build_processing_manifest,
    serialize_manifest,
    write_processing_manifest,
)
from marine_dataset.schemas import ProcessingOperation


def test_manifest_records_full_payload(tmp_path):
    op = ProcessingOperation(
        operation_name="calibration",
        library="gdal",
        library_version="3.8.0",
        parameters={"polarization": "VV"},
        input_checksum="in0",
        output_checksum="out0",
        start_time=datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc),
        end_time=datetime(2024, 1, 1, 10, 5, tzinfo=timezone.utc),
        warnings=["speckle filter skipped"],
        failure_status=False,
    )
    m = build_processing_manifest(
        stage="preprocess",
        dataset_version="0.1",
        input_artifact_id="scene:abc",
        output_artifact_id="scene:abc:processed",
        operations=[op],
    )
    assert m.operations[0].library == "gdal"
    assert m.operations[0].input_checksum == "in0"
    assert m.operations[0].warnings == ["speckle filter skipped"]
    assert m.overall_failure_status is None  # no failing op


def test_manifest_deterministic_id():
    m1 = build_processing_manifest(stage="tile", dataset_version="0.1", input_artifact_id="x")
    m2 = build_processing_manifest(stage="tile", dataset_version="0.1", input_artifact_id="x")
    assert m1.manifest_id == m2.manifest_id


def test_manifest_write_json(tmp_path):
    m = build_processing_manifest(
        stage="preprocess", dataset_version="0.1", input_artifact_id="scene:1"
    )
    out = write_processing_manifest(m, tmp_path)
    assert out.is_file()
    assert "manifest_preprocess" in out.name
    assert "preprocess" in out.read_text(encoding="utf-8")


def test_manifest_serialization_roundtrip():
    m = build_processing_manifest(stage="align", dataset_version="0.1", input_artifact_id="scene:1")
    text = serialize_manifest(m)
    assert '"stage": "align"' in text
