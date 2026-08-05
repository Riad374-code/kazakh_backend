"""Ocean match metadata that never describes daily means as instantaneous."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from marine_dataset.alignment.temporal import TemporalMatch, match_time


@dataclass(frozen=True)
class OceanMatch:
    temporal: TemporalMatch
    temporal_resolution: str
    product_type: str
    represents_acquisition_instant: bool


def match_ocean(
    scene_midpoint: datetime,
    ocean_times: Iterable[datetime],
    *,
    acceptable_minutes: float,
    temporal_resolution: str,
    product_type: str,
) -> OceanMatch:
    temporal = match_time(
        scene_midpoint,
        ocean_times,
        preferred_minutes=acceptable_minutes,
        acceptable_minutes=acceptable_minutes,
    )
    is_instant = temporal_resolution.lower() in {"instantaneous", "hourly"}
    return OceanMatch(temporal, temporal_resolution, product_type, is_instant)
