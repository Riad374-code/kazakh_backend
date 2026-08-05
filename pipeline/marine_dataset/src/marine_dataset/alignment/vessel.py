"""Timestamp-preserving vessel-to-scene matching without source inference."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Sequence


@dataclass(frozen=True)
class VesselObservation:
    observation_id: str
    vessel_id: str
    observed_at: datetime
    source_name: str
    record_type: str
    gap_duration: timedelta | None = None

    def __post_init__(self) -> None:
        _as_utc(self.observed_at)
        if not self.source_name.strip():
            raise ValueError("source_name is required; source inference is prohibited")
        if self.gap_duration is not None and self.gap_duration < timedelta(0):
            raise ValueError("gap_duration must be non-negative")


@dataclass(frozen=True)
class VesselMatch:
    observation: VesselObservation
    observed_at_utc: datetime
    delta_seconds: float


@dataclass(frozen=True)
class VesselMatchResult:
    matches: tuple[VesselMatch, ...]
    unmatched_reason: str | None
    maximum_time_delta: timedelta
    maximum_ais_gap: timedelta


def match_vessels(
    scene_midpoint: datetime,
    observations: Sequence[VesselObservation],
    *,
    maximum_time_delta: timedelta,
    maximum_ais_gap: timedelta,
) -> VesselMatchResult:
    """Match existing records only; never interpolate tracks or infer vessel sources."""
    if maximum_time_delta < timedelta(0) or maximum_ais_gap < timedelta(0):
        raise ValueError("matching windows must be non-negative")
    midpoint = _as_utc(scene_midpoint)
    matches: list[VesselMatch] = []
    for observation in observations:
        observed_at = _as_utc(observation.observed_at)
        delta = abs(observed_at - midpoint)
        gap = observation.gap_duration or timedelta(0)
        if delta <= maximum_time_delta and gap <= maximum_ais_gap:
            matches.append(VesselMatch(observation, observed_at, delta.total_seconds()))
    ordered = tuple(
        sorted(
            matches,
            key=lambda item: (
                item.delta_seconds,
                item.observed_at_utc,
                item.observation.observation_id,
            ),
        )
    )
    if ordered:
        reason = None
    elif not observations:
        reason = "no_vessel_observations_available"
    else:
        reason = "no_observation_within_time_and_gap_thresholds"
    return VesselMatchResult(ordered, reason, maximum_time_delta, maximum_ais_gap)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)
