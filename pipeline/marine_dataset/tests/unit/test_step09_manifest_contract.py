"""Step 09 dataset manifest contract tests."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from marine_dataset.manifests.dataset import (
    DatasetContractError,
    DatasetTables,
    build_dataset_artifacts,
    verify_checksums,
)


def _valid_tables() -> dict[str, list[dict[str, object]]]:
    return {
        "scenes": [
            {
                "scene_id": "scene:1",
                "dataset_version": "1.0.0",
                "source_name": "Copernicus Sentinel-1",
                "official_product_identifier": "S1A_PRODUCT",
                "raw_relative_path": "raw/sentinel1/S1A_PRODUCT.zip",
                "raw_product_checksum": "a" * 64,
                "licence": "Copernicus Sentinel Data Legal Notice",
            }
        ],
        "tiles": [
            {
                "tile_id": "tile:1",
                "dataset_version": "1.0.0",
                "scene_id": "scene:1",
                "raster_path": "processed/tiles/tile-1.tif",
                "mask_path": "processed/masks/tile-1.tif",
            }
        ],
        "labels": [
            {
                "label_id": "label:1",
                "dataset_version": "1.0.0",
                "scene_id": "scene:1",
                "label_source": "expert review",
                "source_record_id": "review:1",
                "source_url_or_identifier": "authority:review:1",
                "licence": "internal-review-terms",
            }
        ],
        "environment": [
            {
                "record_id": "environment:1",
                "dataset_version": "1.0.0",
                "modality": "weather",
                "source_name": "Open-Meteo",
                "product_id": "era5",
                "licence": "CC BY 4.0",
            }
        ],
        "vessels": [],
        "infrastructure": [],
        "split_manifest": [],
        "dataset_manifest": [
            {
                "scene_id": "scene:1",
                "tile_id": "tile:1",
                "dataset_version": "1.0.0",
                "label_id": "label:1",
                "weather_record_id": "environment:1",
            }
        ],
    }


def test_builder_writes_explicit_empty_schemas_and_complete_contract(tmp_path: Path):
    outputs = build_dataset_artifacts(tmp_path, DatasetTables(dataset_version="1.0.0"))

    scene_columns = pd.read_parquet(outputs["scenes"]).columns.tolist()
    assert scene_columns[:2] == ["scene_id", "dataset_version"]
    assert "official_product_identifier" in scene_columns
    assert "status" not in scene_columns

    contract = json.loads(outputs["ml_export_contract"].read_text(encoding="utf-8"))
    assert contract["channel_axis_order"] == "CHW"
    assert contract["normalization"]["fit_scope"] == "training_split_only"
    assert contract["split"]["status"] == "not_run"
    assert contract["feature_availability"]["representation"] == "per_sample_boolean_map"
    assert outputs["sample_index"].is_file()
    assert verify_checksums(tmp_path) == []


def test_builder_validates_relations_and_builds_deterministic_sample_index(tmp_path: Path):
    rows = _valid_tables()
    original = json.loads(json.dumps(rows))
    first = tmp_path / "first"
    second = tmp_path / "second"

    build_dataset_artifacts(first, DatasetTables(rows, "1.0.0"))
    build_dataset_artifacts(second, DatasetTables(rows, "1.0.0"))

    first_index = pd.read_parquet(first / "sample_index.parquet")
    second_index = pd.read_parquet(second / "sample_index.parquet")
    pd.testing.assert_frame_equal(first_index, second_index)
    assert first_index.loc[0, "sample_id"].startswith("sample:")
    assert rows == original

    quality = json.loads((first / "quality_report.json").read_text(encoding="utf-8"))
    assert quality["status"] == "not_run"
    assert quality["manifest_contract_validation"]["status"] == "passed"
    assert quality["row_counts"]["dataset_manifest"] == 1


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda rows: rows["scenes"].append(dict(rows["scenes"][0])), "duplicate"),
        (
            lambda rows: rows["tiles"][0].update(scene_id="scene:missing"),
            "foreign key",
        ),
        (
            lambda rows: rows["tiles"][0].update(raster_path="C:/absolute/tile.tif"),
            "relative",
        ),
        (
            lambda rows: rows["labels"][0].update(licence=""),
            "licence",
        ),
        (
            lambda rows: rows["environment"][0].update(dataset_version="2.0.0"),
            "dataset_version",
        ),
    ],
)
def test_invalid_manifest_contract_is_rejected(tmp_path: Path, mutation, message: str):
    rows = _valid_tables()
    mutation(rows)
    with pytest.raises(DatasetContractError, match=message):
        build_dataset_artifacts(tmp_path, DatasetTables(rows, "1.0.0"))


def test_unknown_table_is_rejected(tmp_path: Path):
    with pytest.raises(DatasetContractError, match="unknown table"):
        build_dataset_artifacts(
            tmp_path,
            DatasetTables({"invented": [{"id": "fabricated"}]}, "1.0.0"),
        )
