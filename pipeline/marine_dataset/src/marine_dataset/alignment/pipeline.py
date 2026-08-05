"""Auditable scene-time, weather, and ocean alignment contracts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Sequence

from marine_dataset.alignment.temporal import MatchQuality, match_time


@dataclass(frozen=True)
class TimedValue:
    observed_at: datetime
    value: float
    record_id: str

    def __post_init__(self) -> None:
        _as_utc(self.observed_at)


@dataclass(frozen=True)
class WeatherAlignment:
    value: float | None
    quality: MatchQuality
    source_record_ids: tuple[str, ...]
    source_timestamps_utc: tuple[datetime, ...]
    interpolated: bool
    interpolation_method: str | None
    delta_minutes: float | None
    unmatched_reason: str | None


@dataclass(frozen=True)
class OceanAlignment:
    value: float | None
    quality: MatchQuality
    source_record_ids: tuple[str, ...]
    source_timestamps_utc: tuple[datetime, ...]
    temporal_semantics: Literal["instantaneous", "daily_mean", "period_mean"]
    represents_acquisition_instant: bool
    spatial_coverage_fraction: float
    delta_minutes: float | None
    unmatched_reason: str | None


def scene_midpoint(acquisition_start: datetime, acquisition_end: datetime) -> datetime:
    """Return the acquisition interval midpoint normalized to UTC."""
    start = _as_utc(acquisition_start)
    end = _as_utc(acquisition_end)
    if end < start:
        raise ValueError("acquisition_end must not precede acquisition_start")
    return start + (end - start) / 2


def align_weather_value(
    midpoint: datetime,
    observations: Sequence[TimedValue],
    *,
    preferred_minutes: float = 30,
    acceptable_minutes: float = 90,
    interpolate: bool = False,
) -> WeatherAlignment:
    """Nearest match, or linear interpolation between valid bracketing observations."""
    _validate_weather_thresholds(preferred_minutes, acceptable_minutes)
    reference = _as_utc(midpoint)
    ordered = tuple(sorted(observations, key=lambda item: _as_utc(item.observed_at)))
    if interpolate:
        interpolated = _interpolated_weather(
            reference,
            ordered,
            preferred_minutes=preferred_minutes,
            acceptable_minutes=acceptable_minutes,
        )
        if interpolated is not None:
            return interpolated
    return _nearest_weather(
        reference,
        ordered,
        preferred_minutes=preferred_minutes,
        acceptable_minutes=acceptable_minutes,
    )


def _nearest_weather(
    reference: datetime,
    observations: Sequence[TimedValue],
    *,
    preferred_minutes: float,
    acceptable_minutes: float,
) -> WeatherAlignment:
    match = match_time(
        reference,
        (item.observed_at for item in observations),
        preferred_minutes=preferred_minutes,
        acceptable_minutes=acceptable_minutes,
    )
    if match.timestamp is None:
        return WeatherAlignment(
            None,
            match.quality,
            (),
            (),
            False,
            None,
            match.delta_minutes,
            "no_weather_within_threshold",
        )
    selected = next(item for item in observations if _as_utc(item.observed_at) == match.timestamp)
    return WeatherAlignment(
        selected.value,
        match.quality,
        (selected.record_id,),
        (match.timestamp,),
        False,
        None,
        match.delta_minutes,
        None,
    )


def _interpolated_weather(
    reference: datetime,
    observations: Sequence[TimedValue],
    *,
    preferred_minutes: float,
    acceptable_minutes: float,
) -> WeatherAlignment | None:
    bracket = _bracket(reference, observations)
    if bracket is None:
        return None
    before, after = bracket
    furthest = max(
        abs(_as_utc(before.observed_at) - reference),
        abs(_as_utc(after.observed_at) - reference),
    )
    if furthest > timedelta(minutes=acceptable_minutes):
        return None
    quality = (
        MatchQuality.preferred
        if furthest <= timedelta(minutes=preferred_minutes)
        else MatchQuality.acceptable
    )
    return WeatherAlignment(
        _linear_value(reference, before, after),
        quality,
        (before.record_id, after.record_id),
        (_as_utc(before.observed_at), _as_utc(after.observed_at)),
        True,
        "linear",
        furthest.total_seconds() / 60,
        None,
    )


def align_ocean_value(
    midpoint: datetime,
    observations: Sequence[TimedValue],
    *,
    acceptable_minutes: float,
    temporal_semantics: Literal["instantaneous", "daily_mean", "period_mean"],
    spatial_coverage_fraction: float,
    minimum_coverage_fraction: float = 0.8,
) -> OceanAlignment:
    """Match ocean data while retaining mean semantics and spatial coverage."""
    _validate_ocean_thresholds(
        acceptable_minutes,
        spatial_coverage_fraction,
        minimum_coverage_fraction,
    )
    if spatial_coverage_fraction < minimum_coverage_fraction:
        return _unmatched_ocean(
            temporal_semantics,
            spatial_coverage_fraction,
            "insufficient_spatial_coverage",
        )
    reference = _as_utc(midpoint)
    match = match_time(
        reference,
        (item.observed_at for item in observations),
        preferred_minutes=acceptable_minutes,
        acceptable_minutes=acceptable_minutes,
    )
    if match.timestamp is None:
        return _unmatched_ocean(
            temporal_semantics,
            spatial_coverage_fraction,
            "no_ocean_record_within_threshold",
            delta_minutes=match.delta_minutes,
            quality=match.quality,
        )
    selected = next(item for item in observations if _as_utc(item.observed_at) == match.timestamp)
    return OceanAlignment(
        selected.value,
        match.quality,
        (selected.record_id,),
        (match.timestamp,),
        temporal_semantics,
        temporal_semantics == "instantaneous",
        spatial_coverage_fraction,
        match.delta_minutes,
        None,
    )


def _unmatched_ocean(
    temporal_semantics: Literal["instantaneous", "daily_mean", "period_mean"],
    coverage: float,
    reason: str,
    *,
    delta_minutes: float | None = None,
    quality: MatchQuality = MatchQuality.unmatched,
) -> OceanAlignment:
    return OceanAlignment(
        None,
        quality,
        (),
        (),
        temporal_semantics,
        False,
        coverage,
        delta_minutes,
        reason,
    )


def _validate_weather_thresholds(preferred: float, acceptable: float) -> None:
    if preferred < 0 or acceptable < 0:
        raise ValueError("weather thresholds must be non-negative")


def _validate_ocean_thresholds(acceptable: float, coverage: float, minimum: float) -> None:
    if acceptable < 0:
        raise ValueError("acceptable_minutes must be non-negative")
    if not 0 <= coverage <= 1:
        raise ValueError("spatial_coverage_fraction must be within [0, 1]")
    if not 0 <= minimum <= 1:
        raise ValueError("minimum_coverage_fraction must be within [0, 1]")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _bracket(
    reference: datetime, values: Sequence[TimedValue]
) -> tuple[TimedValue, TimedValue] | None:
    before = [item for item in values if _as_utc(item.observed_at) <= reference]
    after = [item for item in values if _as_utc(item.observed_at) >= reference]
    if not before or not after:
        return None
    left, right = before[-1], after[0]
    if left.record_id == right.record_id:
        return None
    return left, right


def _linear_value(reference: datetime, before: TimedValue, after: TimedValue) -> float:
    start = _as_utc(before.observed_at)
    end = _as_utc(after.observed_at)
    span = (end - start).total_seconds()
    if span <= 0:
        raise ValueError("interpolation timestamps must be strictly ordered")
    weight = (reference - start).total_seconds() / span
    return before.value + weight * (after.value - before.value)
