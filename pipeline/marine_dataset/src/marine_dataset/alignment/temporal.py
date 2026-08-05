"""UTC temporal matching with explicit quality thresholds."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable


class MatchQuality(str, Enum):
    preferred = "preferred"
    acceptable = "acceptable"
    unmatched = "unmatched"


@dataclass(frozen=True)
class TemporalMatch:
    timestamp: datetime | None
    delta_minutes: float | None
    quality: MatchQuality
    interpolated: bool = False
    interpolation_method: str | None = None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def match_time(
    reference: datetime,
    candidates: Iterable[datetime],
    *,
    preferred_minutes: float,
    acceptable_minutes: float,
) -> TemporalMatch:
    if preferred_minutes > acceptable_minutes:
        raise ValueError("preferred threshold must not exceed acceptable threshold")
    ref = _utc(reference)
    normalized = sorted(
        (_utc(value) for value in candidates), key=lambda value: (abs(value - ref), value)
    )
    if not normalized:
        return TemporalMatch(None, None, MatchQuality.unmatched)
    chosen = normalized[0]
    delta = abs((chosen - ref).total_seconds()) / 60.0
    if delta <= preferred_minutes:
        quality = MatchQuality.preferred
    elif delta <= acceptable_minutes:
        quality = MatchQuality.acceptable
    else:
        return TemporalMatch(None, delta, MatchQuality.unmatched)
    return TemporalMatch(chosen, delta, quality)
