"""Step 02 tests: schema validation (impossible values, provenance, typing)."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from marine_dataset.schemas import (
    Confidence,
    Label,
    ObsType,
    ProcessingOperation,
    Scene,
    SceneSourceRef,
    SceneTime,
    VesselContext,
)


def _scene_time():
    start = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 10, 12, tzinfo=timezone.utc)
    mid = start + (end - start) / 2
    return SceneTime(
        acquisition_start=start,
        acquisition_end=end,
        midpoint=mid,
        source_timezone="UTC",
        normalized_utc=start,
    )


def test_scene_time_requires_consistent_midpoint():
    start = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 10, 12, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        SceneTime(acquisition_start=end, acquisition_end=start,
                  midpoint=start)  # reversed times -> error


def test_impossible_coordinate_rejected():
    with pytest.raises(ValidationError):
        from marine_dataset.schemas import Coordinate

        Coordinate(lon=200.0, lat=0.0)


def test_impossible_time_rejected():
    start = datetime(2024, 1, 1, 10, 0, tzinfo=timezone.utc)
    end = datetime(2024, 1, 1, 10, 12, tzinfo=timezone.utc)
    # midpoint not equal to (start+end)/2
    wrong_mid = datetime(2024, 1, 1, 11, 0, tzinfo=timezone.utc)
    with pytest.raises(ValidationError):
        SceneTime(acquisition_start=start, acquisition_end=end, midpoint=wrong_mid)


def test_invalid_score_rejected():
    with pytest.raises(ValidationError):
        from marine_dataset.schemas import Reliability

        Reliability(label_quality_score=1.5)


def test_invalid_class_id_and_confidence():
    src = SceneSourceRef(
        source_name="CDSE", official_product_identifier="P1", platform="S1A"
    )
    base = dict(
        label_id="l1", dataset_version="0.1", scene_id="s1", class_name="x",
        geometry_wkt="POINT(0 0)", crs="EPSG:4326", label_source="gov",
        source_record_id="r1", source_url_or_identifier="u1",
        annotation_timestamp=datetime.now(timezone.utc),
    )
    with pytest.raises(ValidationError):
        Label(**base, class_id=-1, label_confidence=Confidence.verified)
    with pytest.raises(ValidationError):
        Label(**base, class_id=0, label_confidence="bogus_confidence")


def test_missing_crs_units_provenance_rejected():
    # Scene requires a source reference; a bare scene without it fails.
    with pytest.raises(ValidationError):
        Scene(scene_id="s1", dataset_version="0.1", scene_time=_scene_time())


def test_observation_vs_forecast_typing():
    # ObsType distinguishes reanalysis/observation from forecast.
    assert ObsType.reanalysis is not ObsType.forecast
    assert ObsType.forecast.value == "forecast"


def test_processing_operation_failure_requires_message():
    with pytest.raises(ValidationError):
        ProcessingOperation(operation_name="cal", library="snap",
                            library_version="9", failure_status=True)


def test_vessel_context_record_type():
    with pytest.raises(ValidationError):
        VesselContext(
            vessel_context_id="v1", dataset_version="0.1", scene_id="s1",
            vessel_id="ship1", geometry_wkt="POINT(0 0)",
            observed_at=datetime.now(timezone.utc), source_name="GFW",
        )