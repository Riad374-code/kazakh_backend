"""Additional offline edge and geospatial tests for Steps 06-10."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest
import rasterio
import xarray as xr
from affine import Affine
from shapely.geometry import box

from marine_dataset.alignment.ocean import match_ocean
from marine_dataset.alignment.spatial import GridSpec, ensure_aligned
from marine_dataset.alignment.weather import match_weather
from marine_dataset.labels.importers import import_geojson_labels
from marine_dataset.labels.rasterize import (
    LabelShape,
    RasterizeOptions,
    rasterize_label_shapes,
    write_mask_geotiff,
)
from marine_dataset.manifests.dataset import (
    DatasetTables,
    build_dataset_artifacts,
    verify_checksums,
)
from marine_dataset.processing.raster import reproject_raster
from marine_dataset.processing.sentinel1 import (
    PreprocessPlan,
    ScientificCapabilityError,
    local_texture,
    validate_scientific_capabilities,
)
from marine_dataset.processing.tiling import iter_tiles
from marine_dataset.sources.copernicus_marine import MarineSubsetRequest
from marine_dataset.sources.sentinel3 import (
    Sentinel3Variable,
    assert_resolution_claim,
    decode_quality_bits,
    parse_sentinel3_item,
    process_sentinel3_file,
    quality_mask,
    validate_collection,
)


def test_spatial_and_environment_alignment_policies():
    transform = Affine.translation(50, 46) * Affine.scale(0.1, -0.1)
    grid = GridSpec("EPSG:4326", transform, 10, 10, -9999)
    ensure_aligned(grid, GridSpec("EPSG:4326", transform, 10, 10, -9999))
    with pytest.raises(ValueError, match="pixel-aligned"):
        ensure_aligned(grid, GridSpec("EPSG:4326", transform, 9, 10, -9999))
    reference = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    weather = match_weather(reference, [reference], preferred_minutes=30, acceptable_minutes=90)
    ocean = match_ocean(
        reference,
        [reference],
        acceptable_minutes=90,
        temporal_resolution="daily mean",
        product_type="reanalysis",
    )
    assert weather.delta_minutes == 0
    assert not ocean.represents_acquisition_instant
    assert grid.resolution == (0.1, 0.1)


def test_raster_reprojection_and_mask_output(tmp_path, monkeypatch):
    rasterio_root = Path(rasterio.__file__).parent
    monkeypatch.setenv("PROJ_LIB", str(rasterio_root / "proj_data"))
    monkeypatch.setenv("GDAL_DATA", str(rasterio_root / "gdal_data"))
    source = tmp_path / "source.tif"
    target = tmp_path / "target.tif"
    profile = {
        "driver": "GTiff",
        "height": 4,
        "width": 4,
        "count": 1,
        "dtype": "float32",
        "crs": "EPSG:4326",
        "transform": Affine.translation(50, 46) * Affine.scale(0.1, -0.1),
        "nodata": -9999.0,
    }
    with rasterio.open(source, "w", **profile) as dataset:
        dataset.write(np.ones((4, 4), dtype=np.float32), 1)
    record = reproject_raster(source, target, "EPSG:3857")
    assert target.is_file()
    assert record.method == "bilinear"
    mask_path = write_mask_geotiff(
        tmp_path / "mask.tif",
        np.zeros((4, 4), dtype=np.uint8),
        transform=profile["transform"],
        crs="EPSG:4326",
    )
    assert mask_path.is_file()
    with pytest.raises(ValueError, match="JPEG"):
        write_mask_geotiff(
            tmp_path / "mask.jpg",
            np.zeros((2, 2), dtype=np.uint8),
            transform=profile["transform"],
            crs="EPSG:4326",
        )


def test_label_importer_preserves_unknowns(tmp_path):
    path = tmp_path / "labels.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "id": "label-1",
                        "geometry": {"type": "Point", "coordinates": [51, 44]},
                        "properties": {"annotation_method": "other"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    labels = import_geojson_labels(
        path,
        scene_id="scene-1",
        dataset_version="0.1.0",
        label_source="fixture",
        licence="test-only",
    )
    assert labels[0].class_name == "unknown_or_unreviewed"
    assert labels[0].quality_notes
    assert labels[0].annotation_timestamp is None


def test_rasterize_clips_and_applies_class_priority():
    footprint = box(0, 0, 2, 2)
    transform = Affine.translation(0, 2) * Affine.scale(1, -1)
    labels = (
        LabelShape(box(0, 0, 2, 2), 2, "EPSG:4326"),
        LabelShape(box(1, 1, 3, 3), 1, "EPSG:4326"),
    )
    mask, metadata = rasterize_label_shapes(
        labels,
        out_shape=(2, 2),
        transform=transform,
        target_crs="EPSG:4326",
        footprint=footprint,
        options=RasterizeOptions(class_priority=(2, 1)),
    )
    assert mask[0, 1] == 1
    assert metadata.clipped_geometry_count == 1


def test_preprocess_capability_texture_and_padding():
    with pytest.raises(ScientificCapabilityError, match="SNAP"):
        validate_scientific_capabilities(PreprocessPlan(), {})
    validate_scientific_capabilities(
        PreprocessPlan(),
        {
            "precise_orbit": True,
            "thermal_noise": True,
            "calibration": True,
            "terrain_correction": True,
        },
    )
    texture = local_texture(np.array([[1.0, 2.0], [3.0, 4.0]]), 3)
    assert np.isfinite(texture).all()
    padded = list(iter_tiles(np.ones((3, 3)), tile_size=4, edge_policy="pad"))
    assert padded[0].values.shape == (4, 4)


def test_manifest_checksum_tamper_detection(tmp_path):
    build_dataset_artifacts(tmp_path, DatasetTables())
    assert verify_checksums(tmp_path) == []
    (tmp_path / "dataset_card.md").write_text("tampered", encoding="utf-8")
    assert verify_checksums(tmp_path) == ["dataset_card.md"]


def test_sentinel3_quality_and_collection_guards():
    values = np.array([[1.0, np.nan], [2.0, 3.0]])
    result = quality_mask(
        values,
        cloud_mask=np.array([[False, False], [True, False]]),
        valid_mask=np.array([[True, True], [True, False]]),
    )
    assert result.tolist() == [[True, False], [False, False]]
    validate_collection("configured", {"configured"})
    with pytest.raises(ValueError, match="current CDSE"):
        validate_collection("missing", {"configured"})
    valid, cloud = decode_quality_bits(
        np.array([[0, 1, 2]], dtype=np.uint8), invalid_bits=(0,), cloud_bits=(1,)
    )
    assert valid.tolist() == [[True, False, True]]
    assert cloud.tolist() == [[False, False, True]]
    with pytest.raises(ValueError, match="finer"):
        assert_resolution_claim(300, 10)


def test_sentinel3_stac_metadata_mapping():
    item = {
        "id": "S3_TEST",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[50, 43], [51, 43], [51, 44], [50, 44], [50, 43]]],
        },
        "properties": {
            "datetime": "2024-01-01T00:00:00Z",
            "platform": "sentinel-3a",
            "processing:level": "L2",
            "gsd": 300,
        },
        "assets": {"quality_flags": {}, "data": {}},
    }
    metadata = parse_sentinel3_item(item)
    assert metadata.product_id == "S3_TEST"
    assert metadata.native_resolution_m == 300
    assert metadata.cloud_or_quality_assets == ("quality_flags",)


def test_sentinel3_file_processing_preserves_native_grid(tmp_path):
    source = tmp_path / "s3.nc"
    output = tmp_path / "chlorophyll.nc"
    dataset = xr.Dataset(
        {
            "CHL_OC4ME": (("y", "x"), np.array([[1.0, 2.0], [3.0, 4.0]])),
            "quality": (("y", "x"), np.array([[0, 1], [0, 0]], dtype=np.uint8)),
        },
        attrs={"spatial_resolution_m": 300.0},
    )
    dataset["CHL_OC4ME"].attrs["units"] = "log10(mg m-3)"
    dataset.to_netcdf(source)
    extracted = process_sentinel3_file(
        source,
        output,
        Sentinel3Variable.chlorophyll,
        quality_variable="quality",
        invalid_bits=(0,),
    )
    assert extracted.native_shape == (2, 2)
    with xr.open_dataset(output) as processed:
        assert processed.attrs["grid_status"] == "native"
        assert not bool(processed["chlorophyll_valid"].values[0, 1])


def test_marine_request_requires_dataset_selection():
    with pytest.raises(ValueError, match="dataset_id"):
        MarineSubsetRequest(
            "",
            (),
            (50, 43, 54, 46),
            "2024-01-01T00:00:00Z",
            "2024-01-02T00:00:00Z",
            "out.nc",
            "reanalysis",
        )
    with pytest.raises(ValueError, match="basename"):
        MarineSubsetRequest(
            "dataset",
            ("uo",),
            (50, 43, 54, 46),
            "2024-01-01T00:00:00Z",
            "2024-01-02T00:00:00Z",
            "../out.nc",
            "reanalysis",
        )
