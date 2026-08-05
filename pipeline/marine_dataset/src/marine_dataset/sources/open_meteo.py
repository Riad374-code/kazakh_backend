"""Open-Meteo historical weather collector with explicit model provenance."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import requests

from marine_dataset.sources.copernicus_dataspace import SourceRequestError, write_raw_once

ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ALLOWED_MODELS = {
    "era5",
    "era5_seamless",
    "era5_land",
    "ecmwf_ifs",
    "cerra",
    "era5_ensemble",
    "ecmwf_ifs_analysis_long_window",
}
ALLOWED_VARIABLES = {
    "precipitation",
    "rain",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "surface_pressure",
    "temperature_2m",
    "relative_humidity_2m",
    "cloud_cover",
    "visibility",
    "weather_code",
}
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
OPEN_METEO_ATTRIBUTION = "Open-Meteo.com"
OPEN_METEO_LICENCE_NOTE = (
    "Free/open-access terms depend on the selected upstream dataset and intended use; "
    "verify commercial and redistribution rights before release."
)


@dataclass(frozen=True)
class WeatherRequest:
    latitude: float
    longitude: float
    start_date: str
    end_date: str
    variables: tuple[str, ...]
    model: str

    def __post_init__(self) -> None:
        if self.model == "best_match" or self.model not in ALLOWED_MODELS:
            raise ValueError("select an explicit documented Open-Meteo historical model")
        if not self.variables:
            raise ValueError("at least one weather variable is required")
        unknown = set(self.variables) - ALLOWED_VARIABLES
        if unknown:
            raise ValueError(f"unsupported Open-Meteo variable(s): {sorted(unknown)}")
        if not -90 <= self.latitude <= 90 or not -180 <= self.longitude <= 180:
            raise ValueError("weather coordinates are outside EPSG:4326 bounds")
        if date.fromisoformat(self.end_date) < date.fromisoformat(self.start_date):
            raise ValueError("weather end_date must not precede start_date")

    def params(self) -> dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "hourly": ",".join(self.variables),
            "models": self.model,
            "timezone": "GMT",
            "cell_selection": "sea",
            "elevation": "nan",
        }


@dataclass(frozen=True)
class WeatherRecord:
    observed_at: datetime
    variable: str
    value: float | None
    unit: str | None


@dataclass(frozen=True)
class WeatherDataset:
    model: str
    latitude: float
    longitude: float
    grid_resolution: str | None
    temporal_resolution: str
    retrieved_at: datetime
    records: tuple[WeatherRecord, ...]
    raw_response: dict[str, Any]
    missing_variables: tuple[str, ...]
    upstream_dataset: str
    attribution: str = OPEN_METEO_ATTRIBUTION
    licence_note: str = OPEN_METEO_LICENCE_NOTE


def parse_weather_response(
    payload: dict[str, Any], request: WeatherRequest, *, retrieved_at: datetime
) -> WeatherDataset:
    if payload.get("utc_offset_seconds", 0) != 0:
        raise ValueError("Open-Meteo response must use UTC/GMT")
    hourly = payload.get("hourly", {})
    units = payload.get("hourly_units", {})
    timestamps = hourly.get("time", [])
    missing = tuple(variable for variable in request.variables if variable not in hourly)
    records: list[WeatherRecord] = []
    for index, timestamp in enumerate(timestamps):
        observed = datetime.fromisoformat(timestamp).replace(tzinfo=timezone.utc)
        for variable in request.variables:
            values = hourly.get(variable, [])
            value = values[index] if index < len(values) else None
            records.append(WeatherRecord(observed, variable, value, units.get(variable)))
    return WeatherDataset(
        request.model,
        float(payload.get("latitude", request.latitude)),
        float(payload.get("longitude", request.longitude)),
        payload.get("model_grid_resolution"),
        "hourly",
        retrieved_at.astimezone(timezone.utc),
        tuple(records),
        dict(payload),
        missing,
        request.model,
    )


class OpenMeteoClient:
    def __init__(
        self,
        session: Any | None = None,
        timeout: float = 30.0,
        *,
        max_attempts: int = 3,
        requests_per_minute: int = 30,
        sleeper: Any = time.sleep,
        clock: Any = time.monotonic,
    ) -> None:
        if max_attempts < 1 or requests_per_minute < 1:
            raise ValueError("retry and rate-limit values must be positive")
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_attempts = max_attempts
        self.minimum_interval = 60.0 / requests_per_minute
        self.sleeper = sleeper
        self.clock = clock
        self._last_request_at: float | None = None

    def collect(self, request: WeatherRequest, *, raw_path: Path | None = None) -> WeatherDataset:
        if raw_path and raw_path.exists():
            payload = json.loads(raw_path.read_text(encoding="utf-8"))
            retrieved_at = datetime.fromtimestamp(raw_path.stat().st_mtime, tz=timezone.utc)
            return parse_weather_response(payload, request, retrieved_at=retrieved_at)
        response = self._get_with_retry(request)
        payload = response.json()
        retrieved_at = datetime.now(timezone.utc)
        if raw_path:
            raw_bytes = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
            write_raw_once(raw_path, raw_bytes)
        return parse_weather_response(payload, request, retrieved_at=retrieved_at)

    def _get_with_retry(self, request: WeatherRequest) -> Any:
        for attempt in range(self.max_attempts):
            now = self.clock()
            if self._last_request_at is not None:
                remaining = self.minimum_interval - (now - self._last_request_at)
                if remaining > 0:
                    self.sleeper(remaining)
            try:
                response = self.session.get(
                    ARCHIVE_URL, params=request.params(), timeout=self.timeout
                )
            except requests.RequestException:
                if attempt + 1 == self.max_attempts:
                    raise SourceRequestError("Open-Meteo request failed") from None
                self.sleeper(2**attempt)
                continue
            finally:
                self._last_request_at = self.clock()
            if response.status_code < 400:
                return response
            if response.status_code not in TRANSIENT_STATUS or attempt + 1 == self.max_attempts:
                raise SourceRequestError(
                    f"Open-Meteo request failed with HTTP {response.status_code}"
                )
            self.sleeper(2**attempt)
        raise SourceRequestError("Open-Meteo request exhausted retries")


def require_registered() -> None:
    """Open-Meteo historical free endpoint needs no registration."""
    return None
