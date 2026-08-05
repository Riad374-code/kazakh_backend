from __future__ import annotations

from datetime import datetime, timedelta

from marine_dataset.context import haversine_m, merge_context, normalize_context
from marine_dataset.contracts import paginate, response_envelope
from marine_dataset.dataset_card import build_dataset_card
from marine_dataset.splitting import assign_splits, leakage_report
from marine_dataset.stages.anomaly import weekly_anomalies
from marine_dataset.stages.classification import classify
from marine_dataset.stages.forecast import advection_forecast
from marine_dataset.stages.heatmap import risk_heatmap
from marine_dataset.stages.impact import energy_impact
from marine_dataset.stages.prioritization import rank_events
from marine_dataset.validation import score_row, validate_rows
from marine_dataset.validation.reproducibility import directory_checksum
from marine_dataset.vessels import (
    grid_density,
    interpolate_position,
    reject_speed_jumps,
    within_window,
)


def test_context_vessels_and_splits_are_deterministic(tmp_path):
    record = normalize_context({"id": 1, "geometry": "POINT(1 2)"}, source_name="osm")
    assert record["context_id"] == "osm:1"
    merged = merge_context([record, {**record, "geometry": "POINT(2 3)"}])
    assert merged[0]["geometry_conflicts"]
    assert haversine_m(0, 0, 0, 1) > 100_000
    first = datetime(2024, 1, 1)
    second = first + timedelta(hours=1)
    points = (
        {"observed_at": first, "lon": 0, "lat": 0},
        {"observed_at": second, "lon": 0.001, "lat": 0},
    )
    assert within_window(first, first, second)
    assert interpolate_position(points[0], points[1], first + timedelta(minutes=30))[
        "position_interpolated"
    ]
    assert len(reject_speed_jumps(points)) == 2
    assert grid_density([{"lon": 0.01, "lat": 0.01}])
    rows = assign_splits([{"scene_id": "s1", "tile_id": "t1"}, {"scene_id": "s2", "tile_id": "t2"}])
    assert rows == assign_splits(
        [{"scene_id": "s1", "tile_id": "t1"}, {"scene_id": "s2", "tile_id": "t2"}]
    )
    assert (
        leakage_report(
            [
                {**rows[0], "incident_id": "i", "split": "train"},
                {"scene_id": "s3", "incident_id": "i", "split": "test"},
            ]
        )["status"]
        == "fail"
    )


def test_stage_baselines_and_contracts(tmp_path):
    observations = [{"timestamp": i, "value": value} for i, value in enumerate([1, 1, 1, 1, 10])]
    assert weekly_anomalies(observations, window=2)[-1]["is_anomaly"]
    assert classify({"sar_dark_spot": 1})["pollution_type"] == "oil_hydrocarbon"
    forecast = advection_forecast({"lon": 50, "lat": 44}, wind_speed_mps=1, horizons_days=(7,))
    assert 0 <= forecast["paths"][0]["spread_probability"] <= 1
    assert rank_events([{"event_id": "a", "size": 1}])[0]["priority_score"] > 0
    assert energy_impact({"event_id": "a"})["status"] == "not_estimated"
    assert (
        risk_heatmap([{"cell_id": "c"}], [{"event_id": "e", "severity": 1, "probability": 1}])[0][
            "risk"
        ]
        == 1
    )
    assert paginate([1, 2], page_size=1)["has_next"]
    assert response_envelope({}, data_version="1", generated_at="now")["contract_version"] == "1"
    scored = score_row({"satellite_quality_score": 1})
    assert scored["overall_sample_quality_score"] == 1
    assert validate_rows([{"scene_id": "s", "path": "relative.json"}])["status"] == "pass"
    card, issues = build_dataset_card(tmp_path, dataset_version="1")
    assert card.exists() and issues.exists()
    assert directory_checksum(tmp_path)
