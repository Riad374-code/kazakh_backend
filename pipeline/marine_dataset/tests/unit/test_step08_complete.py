from datetime import datetime, timedelta, timezone

import numpy as np
import pytest
from affine import Affine

from marine_dataset.alignment.pipeline import (
    TimedValue,
    align_ocean_value,
    align_weather_value,
    scene_midpoint,
)
from marine_dataset.alignment.spatial import GridSpec
from marine_dataset.alignment.temporal import MatchQuality
from marine_dataset.alignment.vessel import VesselObservation, match_vessels
from marine_dataset.processing.tiling import (
    NegativeCandidate,
    TileContext,
    TileThresholds,
    iter_geospatial_tiles,
    stratified_negative_sample,
)

UTC = timezone.utc


def test_scene_midpoint_normalizes_timezone_and_rejects_naive_values():
    east = timezone(timedelta(hours=4))
    start = datetime(2025, 1, 1, 4, 0, tzinfo=east)
    end = datetime(2025, 1, 1, 4, 2, tzinfo=east)

    assert scene_midpoint(start, end) == datetime(2025, 1, 1, 0, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="timezone-aware"):
        scene_midpoint(datetime(2025, 1, 1), end)


def test_weather_alignment_records_threshold_and_interpolation_metadata():
    midpoint = datetime(2025, 1, 1, 1, 0, tzinfo=UTC)
    values = (
        TimedValue(midpoint - timedelta(minutes=20), 10.0, "weather:before"),
        TimedValue(midpoint + timedelta(minutes=20), 20.0, "weather:after"),
    )

    result = align_weather_value(midpoint, values, interpolate=True)

    assert result.value == 15.0
    assert result.quality is MatchQuality.preferred
    assert result.interpolated is True
    assert result.interpolation_method == "linear"
    assert result.source_record_ids == ("weather:before", "weather:after")
    assert result.source_timestamps_utc == tuple(item.observed_at for item in values)


def test_ocean_daily_mean_is_not_mislabeled_and_coverage_is_gated():
    midpoint = datetime(2025, 1, 1, 12, tzinfo=UTC)
    value = TimedValue(midpoint, 0.4, "ocean:daily")

    result = align_ocean_value(
        midpoint,
        (value,),
        acceptable_minutes=720,
        temporal_semantics="daily_mean",
        spatial_coverage_fraction=0.95,
    )
    unavailable = align_ocean_value(
        midpoint,
        (value,),
        acceptable_minutes=720,
        temporal_semantics="daily_mean",
        spatial_coverage_fraction=0.2,
    )

    assert result.value == 0.4
    assert result.temporal_semantics == "daily_mean"
    assert result.represents_acquisition_instant is False
    assert result.spatial_coverage_fraction == 0.95
    assert unavailable.value is None
    assert unavailable.unmatched_reason == "insufficient_spatial_coverage"


def test_vessel_matching_preserves_source_timestamp_and_enforces_gap():
    midpoint = datetime(2025, 1, 1, 12, tzinfo=UTC)
    included = VesselObservation(
        "ais:1",
        "ship:1",
        midpoint - timedelta(minutes=5),
        "provider",
        "raw_ais",
        timedelta(minutes=3),
    )
    excessive_gap = VesselObservation(
        "ais:2",
        "ship:2",
        midpoint,
        "provider",
        "raw_ais",
        timedelta(hours=2),
    )

    result = match_vessels(
        midpoint,
        (included, excessive_gap),
        maximum_time_delta=timedelta(minutes=30),
        maximum_ais_gap=timedelta(minutes=15),
    )

    assert len(result.matches) == 1
    assert result.matches[0].observation is included
    assert result.matches[0].observed_at_utc == included.observed_at
    assert result.unmatched_reason is None


def test_geospatial_tiles_include_auditable_metadata_and_thresholds():
    grid = GridSpec("EPSG:32639", Affine(10, 0, 100, 0, -10, 200), 2, 2, np.nan)
    values = np.array([[[1.0, 2.0], [3.0, np.nan]]])
    labels = np.array([[0, 2], [2, 0]], dtype=np.uint8)
    water = np.array([[1, 1], [1, 0]], dtype=bool)
    land = np.array([[0, 0], [0, 0]], dtype=bool)
    context = TileContext(environmental_record_ids=("weather:1",))

    tiles = tuple(
        iter_geospatial_tiles(
            values,
            grid=grid,
            channels=("vv_db",),
            context=context,
            tile_size=2,
            class_mask=labels,
            water_mask=water,
            land_mask=land,
            thresholds=TileThresholds(minimum_valid_percent=70, minimum_positive_pixels=2),
        )
    )

    assert len(tiles) == 1
    tile = tiles[0]
    assert tile.bbox == (100.0, 180.0, 120.0, 200.0)
    assert tile.crs == "EPSG:32639"
    assert tile.resolution == (10.0, 10.0)
    assert tile.channels == ("vv_db",)
    assert tile.class_histogram == ((0, 2), (2, 2))
    assert tile.positive_pixel_count == 2
    assert tile.water_percent == 75.0
    assert tile.invalid_pixel_percent == 25.0
    assert tile.context.environmental_record_ids == ("weather:1",)


def test_empty_mask_policy_and_context_absence_are_explicit():
    grid = GridSpec("EPSG:4326", Affine.identity(), 2, 2, None)
    context = TileContext(unmatched_reasons=("weather_unavailable", "vessels_unavailable"))

    assert (
        tuple(
            iter_geospatial_tiles(
                np.ones((2, 2)),
                grid=grid,
                channels=("vv",),
                context=context,
                tile_size=2,
                empty_mask_policy="drop",
            )
        )
        == ()
    )
    with pytest.raises(ValueError, match="context IDs"):
        TileContext()
    with pytest.raises(ValueError, match="empty class mask"):
        tuple(
            iter_geospatial_tiles(
                np.ones((2, 2)),
                grid=grid,
                channels=("vv",),
                context=context,
                tile_size=2,
                class_mask=np.zeros((2, 2), dtype=np.uint8),
                empty_mask_policy="error",
            )
        )


def test_negative_sampling_is_deterministic_stratified_and_group_safe():
    candidates = (
        NegativeCandidate("a", "far_shore", "winter", "calm", "group-positive"),
        NegativeCandidate("b", "far_shore", "winter", "calm", "group-b"),
        NegativeCandidate("c", "far_shore", "winter", "calm", "group-c"),
        NegativeCandidate("d", "shipping_lane", "summer", "rough", "group-d"),
        NegativeCandidate("e", "shipping_lane", "summer", "rough", "group-d"),
    )

    first = stratified_negative_sample(
        candidates,
        maximum_per_stratum=2,
        seed=42,
        positive_group_ids=frozenset({"group-positive"}),
    )
    second = stratified_negative_sample(
        tuple(reversed(candidates)),
        maximum_per_stratum=2,
        seed=42,
        positive_group_ids=frozenset({"group-positive"}),
    )

    assert first == second
    assert {item.stratum for item in first} == {
        ("far_shore", "winter", "calm"),
        ("shipping_lane", "summer", "rough"),
    }
    assert "group-positive" not in {item.group_id for item in first}
    assert len({item.group_id for item in first}) == len(first)
    assert stratified_negative_sample(candidates, maximum_per_stratum=0, seed=42) == ()
