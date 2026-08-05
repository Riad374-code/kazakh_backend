"""Validated configuration for the marine dataset pipeline.

Implements every configurable item from pipeline_inst.md section 15 using
Pydantic models loaded from YAML with optional environment-variable overrides.

Nothing in this module performs network I/O or hardcodes real geographic
regions, product IDs, or credentials.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Optional

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

_ENV_PREFIX = "MARINE_DATA_"


class OrbitDirection(str, Enum):
    ascending = "ASCENDING"
    descending = "DESCENDING"


class ProductType(str, Enum):
    grd = "GRD"


class Polarization(str, Enum):
    VV = "VV"
    VH = "VH"
    VV_VH = "VV+VH"


class ObservationType(str, Enum):
    observation = "observation"
    analysis = "analysis"
    reanalysis = "reanalysis"
    forecast = "forecast"


class ResamplingMethod(str, Enum):
    nearest = "nearest"
    bilinear = "bilinear"
    cubic = "cubic"


class LocationMethod(str, Enum):
    verified = "verified"
    inferred = "inferred"
    approximate = "approximate"


class LicenceStatus(str, Enum):
    resolved = "resolved"
    unresolved = "unresolved"
    incompatible = "incompatible"


class RegionConfig(BaseModel):
    """A geographic region of interest (section 15: geographic regions)."""

    name: str = Field(description="Stable region name used in identifiers.")
    min_lon: float = Field(ge=-180.0, le=180.0)
    min_lat: float = Field(ge=-90.0, le=90.0)
    max_lon: float = Field(ge=-180.0, le=180.0)
    max_lat: float = Field(ge=-90.0, le=90.0)
    country: Optional[list[str]] = Field(default_factory=list)

    @model_validator(mode="after")
    def _bounds_sane(self) -> "RegionConfig":
        if self.min_lon >= self.max_lon:
            raise ValueError(
                f"region '{self.name}': min_lon ({self.min_lon}) must be < max_lon ({self.max_lon})"
            )
        if self.min_lat >= self.max_lat:
            raise ValueError(
                f"region '{self.name}': min_lat ({self.min_lat}) must be < max_lat ({self.max_lat})"
            )
        return self


class SceneSearchConfig(BaseModel):
    """Satellite scene search parameters (section 15)."""

    product_type: ProductType = ProductType.grd
    polarizations: list[Polarization] = Field(default_factory=lambda: [Polarization.VV])
    orbit_directions: list[OrbitDirection] = Field(
        default_factory=lambda: [OrbitDirection.ascending, OrbitDirection.descending]
    )
    relative_orbits: Optional[list[int]] = None
    platform: Optional[str] = None
    max_results: int = Field(default=10, ge=1, le=10000)


class TileConfig(BaseModel):
    """Tiling parameters (section 15, section 5)."""

    size_px: int = Field(default=256, ge=16, le=4096)
    overlap_px: int = Field(default=0, ge=0)
    target_crs: str = Field(default="EPSG:4326")
    target_resolution_m: Optional[float] = Field(default=None, gt=0)
    min_valid_water_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    min_positive_mask_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)


class QualityThresholds(BaseModel):
    """Quality thresholds used to gate artifacts (section 15: quality thresholds)."""

    weather_delta_minutes: int = Field(default=90, ge=0)
    ocean_delta_minutes: int = Field(default=90, ge=0)
    max_warnings: int = Field(default=20, ge=0)
    min_coverage_fraction: float = Field(default=0.5, ge=0.0, le=1.0)


class RetryPolicy(BaseModel):
    """Retry with exponential backoff (section 16)."""

    max_attempts: int = Field(default=3, ge=1, le=20)
    base_delay_seconds: float = Field(default=2.0, gt=0)
    max_delay_seconds: float = Field(default=120.0, gt=0)
    backoff_factor: float = Field(default=2.0, gt=1.0)
    http_timeout_seconds: float = Field(default=30.0, gt=0)


class RateLimit(BaseModel):
    """Rate limiting configuration (section 15)."""

    requests_per_minute: int = Field(default=30, ge=1, le=3600)
    max_concurrent_requests: int = Field(default=4, ge=1, le=128)


class PathsConfig(BaseModel):
    """Storage paths (section 14-15). Defaults are relative unless overridden."""

    base: Path = Field(default=Path("data"))
    raw: Path = Field(default=Path("data/raw"))
    interim: Path = Field(default=Path("data/interim"))
    processed: Path = Field(default=Path("data/processed"))
    manifests: Path = Field(default=Path("data/manifests"))
    reports: Path = Field(default=Path("data/reports"))
    cache: Path = Field(default=Path("data/cache"))
    quarantine: Path = Field(default=Path("data/quarantine"))

    def resolve_all(self, base_override: Optional[Path] = None) -> "PathsConfig":
        """Resolve config paths, treating unqualified ones relative to ``base``.

        ``base`` itself is the root data directory. Fields declared as plain
        relative names (e.g. ``raw: 'raw'``) become ``base / name``. Fully
        absolute paths and paths that already carry a full relative prefix are
        used unchanged.
        """
        base = base_override if base_override is not None else self.base
        resolved = {"base": base}
        for name in ("raw", "interim", "processed", "manifests", "reports", "cache", "quarantine"):
            raw = getattr(self, name)
            if raw.is_absolute():
                resolved[name] = raw
            else:
                resolved[name] = base / raw
        return PathsConfig(**resolved)


class CompressionConfig(BaseModel):
    """Compression settings (section 15)."""

    coerce_default: bool = True
    gdal_profile: Literal["GeoTIFF", "COG"] = "GeoTIFF"
    compression: Literal["DEFLATE", "LZW", "ZSTD", "NONE"] = "DEFLATE"
    z_level: int = Field(default=6, ge=0, le=9)


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_dir: Path = Path("logs")


class Config(BaseModel):
    """Top-level validated configuration."""

    model_config = ConfigDict(extra="forbid")

    dataset_version: str = Field(default="0.1.0")
    seed: int = Field(default=42, ge=0)
    regions: list[RegionConfig]
    date_start: date
    date_end: date
    scene_search: SceneSearchConfig = SceneSearchConfig()
    tile: TileConfig = TileConfig()
    weather_variables: list[str] = Field(default_factory=list)
    ocean_variables: list[str] = Field(default_factory=list)
    observations: list[ObservationType] = Field(
        default_factory=lambda: [ObservationType.reanalysis, ObservationType.observation]
    )
    negative_sampling_ratio: float = Field(default=1.0, ge=0.0)
    split_strategy: str = Field(default="group_by_scene")
    split_test_holdout: float = Field(default=0.2, ge=0.0, le=0.9)
    split_val_holdout: float = Field(default=0.2, ge=0.0, le=0.9)
    resampling_method: ResamplingMethod = ResamplingMethod.bilinear
    mask_resampling_method: ResamplingMethod = ResamplingMethod.nearest
    ontology_path: Path = Field(default=Path("configs/label_ontology.yaml"))
    rate_limit: RateLimit = RateLimit()
    retry: RetryPolicy = RetryPolicy()
    paths: PathsConfig = PathsConfig()
    compression: CompressionConfig = CompressionConfig()
    quality: QualityThresholds = QualityThresholds()
    logging: LoggingConfig = LoggingConfig()
    licence_on_incompatible: Literal["warn", "fail"] = "warn"

    @field_validator("date_end")
    @classmethod
    def _date_end_ge_start(cls, v: date, info: Any) -> date:
        date_start = info.data.get("date_start")
        if date_start is not None and v < date_start:
            raise ValueError(
                f"date_end ({v}) must be >= date_start ({date_start})"
            )
        return v

    @field_validator("split_strategy")
    @classmethod
    def _valid_split_strategy(cls, v: str) -> str:
        allowed = {
            "group_by_scene",
            "group_by_incident",
            "spatial_holdout",
            "temporal_holdout",
            "region_holdout",
            "combined_spatiotemporal_holdout",
        }
        if v not in allowed:
            raise ValueError(f"split_strategy must be one of {sorted(allowed)}, got {v!r}")
        return v

    @model_validator(mode="after")
    def _holdouts_consistent(self) -> "Config":
        if self.split_val_holdout + self.split_test_holdout > 0.99:
            raise ValueError(
                f"split_val_holdout + split_test_holdout must be < 1.0, got "
                f"{self.split_val_holdout + self.split_test_holdout}"
            )
        if self.regions and self.date_start and self.date_end:
            _ = self  # bound check already done
        return self


class EnvOverrides:
    """Apply MARINE_DATA_* environment overrides to loaded config values."""

    @staticmethod
    def load(source: dict[str, Any]) -> dict[str, Any]:
        for key, value in os.environ.items():
            if not key.startswith(_ENV_PREFIX):
                continue
            field_name = key[len(_ENV_PREFIX):].lower()
            if field_name in {
                "seed", "negative_sampling_ratio", "split_val_holdout",
                "split_test_holdout", "licence_on_incompatible",
            }:
                source[field_name] = EnvOverrides._coerce(value)
        return source

    @staticmethod
    def _coerce(value: str) -> Any:
        if value.isdigit():
            return int(value)
        low = value.lower()
        if low in {"true", "false"}:
            return low == "true"
        return value


def default_config() -> Config:
    """Return the shipped default configuration (safe placeholder values only)."""
    return load_config(_default_config_path())


def load_config(
    path: Path | str | None = None,
    *,
    env: bool = True,
) -> Config:
    """Load and validate a YAML config, applying environment overrides.

    Args:
        path: Path to a YAML config file. If None, uses ``MARINE_DATA_CONFIG``
            or the shipped ``configs/default.yaml``.
        env: If True, apply MARINE_DATA_* environment overrides.

    Paths remain exactly as declared in YAML; call ``PathsConfig.resolve_all``
    to materialise a resolved storage tree for directory creation.
    """
    if path is None:
        path = _config_path_from_env() or _default_config_path()
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise ValueError(f"config root must be a mapping, got {type(data).__name__}")
    if env:
        data = EnvOverrides.load(data)
    return Config.model_validate(data)


def _default_config_path() -> Path:
    candidates = [
        Path(os.getenv("MARINE_DATA_CONFIG", "")),
        Path("configs/default.yaml"),
        Path(__file__).resolve().parent / "configs" / "default.yaml",
        Path(__file__).resolve().parent.parent / "configs" / "default.yaml",
    ]
    for candidate in candidates:
        if str(candidate) and candidate.is_file():
            return candidate
    raise FileNotFoundError(
        "unable to locate default.yaml; pass --config or set MARINE_DATA_CONFIG"
    )


def _config_path_from_env() -> Optional[Path]:
    value = os.environ.get("MARINE_DATA_CONFIG")
    if value:
        return Path(value)
    return None


def dump_config(config: Config) -> str:
    """Serialize a validated config back to canonical YAML (round-trip)."""
    return yaml.safe_dump(
        json_roundtrip(config.model_dump(mode="json", exclude_none=True)),
        sort_keys=False,
    )


def dump_config_bytes(config: Config) -> bytes:
    return io.BytesIO(dump_config(config).encode("utf-8")).getvalue()


def cfg_sha256(config: Config) -> str:
    """Content hash of the canonical serialized config (reproducibility)."""
    return hashlib.sha256(dump_config_bytes(config)).hexdigest()


def json_roundtrip(value: Any) -> Any:
    """Convert any Pydantic model into plain JSON-safe primitives."""
    if isinstance(value, BaseModel):
        return json_roundtrip(value.model_dump(mode="json", exclude_none=True))
    if isinstance(value, dict):
        return {str(k): json_roundtrip(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_roundtrip(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, SecretStr):
        return value.get_secret_value()
    return value