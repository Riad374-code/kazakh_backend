"""Offline contract tests for acquisition, processing, labels, alignment and exports."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
import xarray as xr
from affine import Affine
from shapely.geometry import box, mapping

from marine_dataset.alignment.temporal import MatchQuality, match_time
from marine_dataset.labels.ontology import load_ontology
from marine_dataset.labels.rasterize import RasterizeOptions, rasterize_labels
from marine_dataset.labels.weak_labels import WeakLabelEvidence, classify_weak_label
from marine_dataset.manifests.dataset import DatasetTables, build_dataset_artifacts
from marine_dataset.processing.sentinel1 import derived_channels, linear_to_db
from marine_dataset.processing.tiling import iter_tiles
from marine_dataset.sources.copernicus_dataspace import CDSEClient, write_raw_once
from marine_dataset.sources.copernicus_marine import derive_current_vectors, ensure_coverage
from marine_dataset.sources.open_meteo import WeatherRequest, parse_weather_response
from marine_dataset.sources.sentinel1 import Sentinel1Query, parse_sentinel1_item
from marine_dataset.sources.sentinel3 import (
    Sentinel3Variable,
    coregistration_record,
    extract_sentinel3_variable,
)
from marine_dataset.storage import RawImmutableError


class FakeResponse:
    def __init__(self, payload, *, status=200, content=None, headers=None):
        self.payload = payload
        self.status_code = status
        self.headers = headers or {}
        self.content = content if content is not None else json.dumps(payload).encode()

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def iter_content(self, chunk_size):
        del chunk_size
        yield self.content


class FakeSession:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        page = self.pages.pop(0)
        return page if isinstance(page, FakeResponse) else FakeResponse(page)


def test_cdse_follows_next_and_deduplicates():
    first = {
        "features": [{"id": "a"}],
        "links": [{"rel": "next", "href": "https://stac.dataspace.copernicus.eu/v1/search?page=2"}],
    }
    second = {"features": [{"id": "a"}, {"id": "b"}], "links": []}
    session = FakeSession([first, second])
    items = CDSEClient(session=session).search({"collections": ["sentinel-1-grd"]})
    assert [item["id"] for item in items] == ["a", "b"]
    assert session.calls[1][1] == "https://stac.dataspace.copernicus.eu/v1/search?page=2"


def test_cdse_rejects_untrusted_pagination_link():
    first = {
        "features": [{"id": "a"}],
        "links": [{"rel": "next", "href": "http://169.254.169.254/latest/meta-data"}],
    }
    with pytest.raises(RuntimeError, match="untrusted STAC pagination"):
        CDSEClient(session=FakeSession([first])).search({"collections": ["sentinel-1-grd"]})


def test_write_raw_once_is_idempotent_and_immutable(tmp_path):
    target = tmp_path / "raw" / "sentinel1" / "scene.zip"
    assert write_raw_once(target, b"abc").created
    assert not write_raw_once(target, b"abc").created
    with pytest.raises(RawImmutableError):
        write_raw_once(target, b"different")


def test_download_resumes_partial_and_refreshes_unauthorized_token(tmp_path, monkeypatch):
    destination = tmp_path / "raw" / "sentinel1" / "scene.zip"
    staging = tmp_path / "interim" / "sentinel1"
    staging.mkdir(parents=True)
    (staging / "scene.zip.download.part").write_bytes(b"abc")
    unauthorized = FakeResponse({}, status=401)
    resumed = FakeResponse({}, status=206, content=b"def", headers={"Content-Range": "bytes 3-5/6"})
    session = FakeSession([unauthorized, resumed])
    client = CDSEClient(session=session)
    tokens = iter(["stale", "fresh"])
    monkeypatch.setattr(client, "access_token", lambda refresh=False: next(tokens))
    result = client.download_product("11111111-1111-1111-1111-111111111111", destination)
    assert result.created
    assert destination.read_bytes() == b"abcdef"
    assert session.calls[0][2]["headers"]["Range"] == "bytes=3-"
    assert session.calls[1][2]["headers"]["Authorization"] == "Bearer fresh"


def test_sentinel1_query_and_metadata_mapping():
    query = Sentinel1Query(
        bbox=(50, 43, 54, 46),
        start="2024-01-01T00:00:00Z",
        end="2024-01-02T00:00:00Z",
        polarizations=("VV", "VH"),
        orbit_direction="ASCENDING",
        relative_orbit=42,
    )
    body = query.to_stac_body()
    assert body["collections"] == ["sentinel-1-grd"]
    assert body["bbox"] == [50.0, 43.0, 54.0, 46.0]
    assert any(part.get("op") == "a_contains" for part in body["filter"]["args"])
    item = {
        "id": "S1A_TEST",
        "geometry": mapping(box(50, 43, 51, 44)),
        "properties": {
            "start_datetime": "2024-01-01T00:00:00Z",
            "end_datetime": "2024-01-01T00:01:00Z",
            "platform": "sentinel-1a",
            "sar:instrument_mode": "IW",
            "sar:polarizations": ["VV", "VH"],
            "sat:orbit_state": "ascending",
            "sat:relative_orbit": 42,
            "sat:absolute_orbit": 12345,
            "sar:incidence_angle": 34.5,
        },
        "assets": {},
    }
    scene = parse_sentinel1_item(item, "0.1.0")
    assert scene.source.relative_orbit == 42
    assert scene.source.absolute_orbit == 12345
    assert scene.source.pass_direction == "ASCENDING"
    assert scene.source.incidence_angle_available
    assert scene.source.instrument_mode == "IW"
    assert scene.scene_time.midpoint.second == 30


def test_open_meteo_requires_explicit_model_and_preserves_units():
    with pytest.raises(ValueError):
        WeatherRequest(50, 44, "2024-01-01", "2024-01-02", ("rain",), "best_match")
    request = WeatherRequest(50, 44, "2024-01-01", "2024-01-02", ("rain",), "era5")
    payload = {
        "latitude": 44.0,
        "longitude": 50.0,
        "hourly": {"time": ["2024-01-01T00:00"], "rain": [1.5]},
        "hourly_units": {"rain": "mm"},
        "utc_offset_seconds": 0,
        "timezone": "GMT",
    }
    parsed = parse_weather_response(
        payload, request, retrieved_at=datetime(2024, 1, 3, tzinfo=timezone.utc)
    )
    assert parsed.model == "era5"
    assert parsed.records[0].unit == "mm"
    assert parsed.raw_response == payload


def test_current_vectors_and_caspian_coverage_gate():
    u = np.array([1.0, 0.0, np.nan])
    v = np.array([0.0, 1.0, np.nan])
    speed, direction = derive_current_vectors(u, v)
    assert np.allclose(speed[:2], [1.0, 1.0])
    assert np.allclose(direction[:2], [90.0, 0.0])
    with pytest.raises(ValueError, match="no valid ocean coverage"):
        ensure_coverage(np.array([np.nan, np.nan]))


def test_sar_math_does_not_mutate_inputs():
    vv = np.array([[1.0, 10.0], [0.0, np.nan]])
    vh = np.array([[0.5, 2.0], [1.0, np.nan]])
    original = vv.copy()
    db = linear_to_db(vv)
    channels = derived_channels(vv, vh)
    assert db[0, 1] == pytest.approx(10.0)
    assert np.isnan(db[1, 0])
    assert channels["vv_vh_ratio"][0, 0] == pytest.approx(2.0)
    assert np.array_equal(vv, original, equal_nan=True)


def test_ontology_weak_labels_and_masks():
    ontology = load_ontology("configs/label_ontology.yaml")
    assert [entry.class_id for entry in ontology.classes] == list(range(11))
    weak = classify_weak_label(
        WeakLabelEvidence(sar_dark=True, chlorophyll_z=0.1, turbidity_z=0.2),
        rule_version="1.0",
    )
    assert weak.pollution_type == "oil_or_hydrocarbon"
    assert weak.is_weak_label and weak.is_machine_generated
    transform = Affine.translation(0, 4) * Affine.scale(1, -1)
    mask = rasterize_labels(
        [(box(1, 1, 3, 3), 1)],
        out_shape=(4, 4),
        transform=transform,
        options=RasterizeOptions(all_touched=False),
    )
    assert mask.dtype == np.uint8
    assert int((mask == 1).sum()) == 4


def test_temporal_matching_and_tiles():
    reference = datetime(2024, 1, 1, 12, tzinfo=timezone.utc)
    candidates = [reference - timedelta(minutes=30), reference + timedelta(minutes=90)]
    match = match_time(reference, candidates, preferred_minutes=30, acceptable_minutes=90)
    assert match.quality == MatchQuality.preferred
    assert match.delta_minutes == 30
    data = np.arange(36).reshape(6, 6)
    tiles = list(iter_tiles(data, tile_size=4, overlap=2, edge_policy="drop"))
    assert [(tile.row, tile.col) for tile in tiles] == [(0, 0), (0, 2), (2, 0), (2, 2)]


def test_dataset_artifacts_and_sentinel3_native_resolution(tmp_path):
    build_dataset_artifacts(tmp_path, DatasetTables())
    assert (tmp_path / "dataset_manifest.parquet").is_file()
    assert (tmp_path / "checksums.sha256").is_file()
    assert "split_not_run" in (tmp_path / "known_issues.md").read_text(encoding="utf-8")

    dataset = xr.Dataset(
        {"CHL_OC4ME": (("y", "x"), np.array([[1.0, 2.0], [3.0, -999.0]]))},
        attrs={"spatial_resolution_m": 300.0, "processing_baseline": "003"},
    )
    dataset["CHL_OC4ME"].attrs.update(units="log10(mg m-3)", _FillValue=-999.0)
    extracted = extract_sentinel3_variable(dataset, Sentinel3Variable.chlorophyll)
    assert extracted.native_shape == (2, 2)
    assert extracted.native_resolution_m == 300.0
    assert np.isnan(extracted.values[1, 1])
    coreg = coregistration_record(box(0, 0, 2, 2), box(1, 1, 3, 3), 60, 300.0)
    assert coreg.coverage_fraction == pytest.approx(0.25)
    assert coreg.native_resolution_m == 300.0
