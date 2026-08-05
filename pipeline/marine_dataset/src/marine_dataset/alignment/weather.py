"""Weather-to-scene alignment policy."""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from marine_dataset.alignment.temporal import TemporalMatch, match_time


def match_weather(
    scene_midpoint: datetime,
    weather_times: Iterable[datetime],
    *,
    preferred_minutes: float = 30,
    acceptable_minutes: float = 90,
) -> TemporalMatch:
    return match_time(
        scene_midpoint,
        weather_times,
        preferred_minutes=preferred_minutes,
        acceptable_minutes=acceptable_minutes,
    )
