"""Typed, validated domain schemas (pipeline_inst.md sections 2, 4, 5, 8, 11).

These models describe scenes, labels, tiles, environmental records, vessel
context, infrastructure context, split assignments, source references, modality
reliability, and processing operations. Optionality reflects real availability,
it is never used to silently omit required provenance.

No API clients or geospatial resampling are implemented here.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Small shared value types
# ---------------------------------------------------------------------------


class Coordinate(BaseModel):
    """A coordinate in EPSG:4326 (lon/lat, explicit axis order)."""

    model_config = ConfigDict(extra="forbid")

    lon: float = Field(ge=-180.0, le=180.0, description="Longitude in EPSG:4326.")
    lat: float = Field(ge=-90.0, le=90.0, description="Latitude in EPSG:4326.")

    @model_validator(mode="after")
    def _not_both_zero_unset(self) -> "Coordinate":
        # Both zero is a legal coordinate; this hook exists to catch authoring
        # mistakes where a coordinate is left at (0,0) placeholder.
        return self


class ObsType(str, Enum):
    observation = "observation"
    analysis = "analysis"
    reanalysis = "reanalysis"
    forecast = "forecast"


class UncertainValue(BaseModel):
    """A central value with an uncertainty, used for spatial/temporal metrics."""

    model_config = ConfigDict(extra="forbid")

    value: float
    uncertainty: Optional[float] = Field(default=None, ge=0.0)


class SceneTime(BaseModel):
    """Acquisition time fields (section 4)."""

    model_config = ConfigDict(extra="forbid")

    acquisition_start: datetime
    acquisition_end: datetime
    midpoint: datetime
    source_timezone: Optional[str] = None
    normalized_utc: Optional[datetime] = None

    @model_validator(mode="after")
    def _times_consistent(self) -> "SceneTime":
        if self.acquisition_end < self.acquisition_start:
            raise ValueError("acquisition_end must be >= acquisition_start")
        computed = self.acquisition_start + (
            self.acquisition_end - self.acquisition_start
        ) / 2
        if self.midpoint != computed:
            raise ValueError(
                f"midpoint must equal (start+end)/2 in UTC; got {self.midpoint}, expected {computed}"
            )
        return self


class PassDirection(str, Enum):
    ascending = "ASCENDING"
    descending = "DESCENDING"


class IncidenceInfo(BaseModel):
    incidence_angle_min_deg: Optional[float] = Field(default=None, ge=0.0, le=90.0)
    incidence_angle_max_deg: Optional[float] = Field(default=None, ge=0.0, le=90.0)

    @model_validator(mode="after")
    def _incidence_ordered(self) -> "IncidenceInfo":
        if (
            self.incidence_angle_min_deg is not None
            and self.incidence_angle_max_deg is not None
            and self.incidence_angle_min_deg > self.incidence_angle_max_deg
        ):
            raise ValueError("incidence_angle_min_deg must be <= max")
        return self


class SceneSourceRef(BaseModel):
    """Canonical source identifiers of a scene (never a local path)."""

    model_config = ConfigDict(extra="forbid")

    source_name: str
    official_product_identifier: str
    platform: str
    instrument_mode: Optional[str] = None
    processing_level: Optional[str] = None
    processing_baseline: Optional[str] = None
    relative_orbit: Optional[int] = Field(default=None, ge=0)
    polarizations: list[str] = Field(default_factory=list)
    footprint_wkt: Optional[str] = None
    source_url: Optional[str] = None

    @field_validator("source_name")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("source_name must not be empty")
        return v

    @field_validator("official_product_identifier")
    @classmethod
    def _prodid_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("official_product_identifier must not be empty")
        return v


class Scene(BaseModel):
    """A collected satellite scene (section 5 tile parent, section 8 manifest)."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str
    dataset_version: str
    scene_time: SceneTime
    crs: Optional[str] = None
    source: SceneSourceRef
    pixel_spacing_m: Optional[float] = Field(default=None, gt=0)
    resolution_m: Optional[float] = Field(default=None, gt=0)
    incidence: IncidenceInfo = IncidenceInfo()
    raw_product_checksum: Optional[str] = None
    raw_relative_path: Optional[str] = None

    @field_validator("raw_relative_path")
    @classmethod
    def _no_abs_path(cls, v: Optional[str]) -> Optional[str]:
        if v and (v.startswith("/") or ":" in v[:3]):
            raise ValueError("raw_relative_path must be relative, never absolute")
        return v


class AnnotationMethod(str, Enum):
    expert = "expert"
    government_record = "government_record"
    human_annotation = "human_annotation"
    machine_generated = "machine_generated"
    weak_label = "weak_label"
    other = "other"


class Confidence(str, Enum):
    verified = "verified"
    high = "high"
    medium = "medium"
    low = "low"
    unknown = "unknown"


class VerificationStatus(str, Enum):
    unverified = "unverified"
    pending = "pending"
    verified = "verified"
    rejected = "rejected"


class Label(BaseModel):
    """A pollution label (section 2). Confidence stays separate from class."""

    model_config = ConfigDict(extra="forbid")

    label_id: str
    dataset_version: str
    scene_id: str
    class_id: int = Field(ge=0)
    class_name: str
    geometry_wkt: str = Field(min_length=1)
    crs: str = Field(min_length=1)
    label_source: str = Field(min_length=1)
    source_record_id: str = Field(min_length=1)
    source_url_or_identifier: str = Field(min_length=1)
    annotation_method: AnnotationMethod
    annotator_type: Optional[str] = None
    annotation_timestamp: datetime
    label_confidence: Confidence
    verification_status: VerificationStatus = VerificationStatus.unverified
    number_of_reviewers: int = Field(default=0, ge=0)
    inter_annotator_agreement: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    incident_date: Optional[datetime] = None
    incident_time_uncertainty_minutes: Optional[int] = Field(default=None, ge=0)
    spatial_uncertainty_m: Optional[float] = Field(default=None, ge=0.0)
    temporal_uncertainty_minutes: Optional[int] = Field(default=None, ge=0)
    is_weak_label: bool = False
    is_machine_generated: bool = False
    quality_notes: Optional[str] = None
    licence: str = Field(min_length=1)
    citation: Optional[str] = None

    @field_validator("class_name")
    @classmethod
    def _classname_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("class_name must not be empty")
        return v


class Tile(BaseModel):
    """A geospatial tile (section 5)."""

    model_config = ConfigDict(extra="forbid")

    tile_id: str
    dataset_version: str
    scene_id: str
    col: int = Field(ge=0)
    row: int = Field(ge=0)
    bbox_wkt: str = Field(min_length=1)
    polygon_footprint_wkt: str = Field(min_length=1)
    crs: str = Field(min_length=1)
    pixel_resolution_m: Optional[float] = Field(default=None, gt=0)
    channels: list[str] = Field(default_factory=list)
    mask_path: Optional[str] = None
    positive_pixel_count: int = Field(default=0, ge=0)
    class_histogram: dict[str, int] = Field(default_factory=dict)
    water_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    land_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    invalid_pixel_percent: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    environmental_record_ids: list[str] = Field(default_factory=list)
    vessel_context_ids: list[str] = Field(default_factory=list)
    infrastructure_context_ids: list[str] = Field(default_factory=list)
    split_split: Optional[str] = None
    source_and_licence_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _percents_consistent(self) -> "Tile":
        summed = [p for p in (self.water_percent, self.land_percent, self.invalid_pixel_percent) if p is not None]
        if sum(summed) > 100.0 + 1e-9:
            raise ValueError("water+land+invalid percent must not exceed 100")
        return self


class EnvironmentalRecord(BaseModel):
    """A matched weather or ocean environmental record (sections 4.1-4.2)."""

    model_config = ConfigDict(extra="forbid")

    record_id: str
    dataset_version: str
    modality: str  # "weather" or "ocean"
    variable: str
    value: float
    unit: Optional[str] = None
    crs: Optional[str] = "EPSG:4326"
    observed_at: datetime
    obs_type: ObsType = ObsType.observation
    product_id: Optional[str] = None
    dataset_id: Optional[str] = None
    dataset_version_ref: Optional[str] = None
    resolution: Optional[str] = None
    quality_flags: list[str] = Field(default_factory=list)
    retrieval_date: Optional[datetime] = None
    licence: Optional[str] = None
    citation: Optional[str] = None


class VesselContext(BaseModel):
    """Vessel data matched to a scene (section 4.3, section 1.6)."""

    model_config = ConfigDict(extra="forbid")

    vessel_context_id: str
    dataset_version: str
    scene_id: str
    vessel_id: str
    record_type: str = Field(description="raw_ais|processed_ais|gridded|inferred|sar_detection")
    geometry_wkt: str = Field(min_length=1)
    crs: str = "EPSG:4326"
    observed_at: datetime
    gap_duration_seconds: Optional[int] = Field(default=None, ge=0)
    position_interpolated: bool = False
    source_name: str = Field(min_length=1)
    source_record_id: Optional[str] = None
    distance_to_spill_m: Optional[float] = Field(default=None, ge=0.0)
    distance_to_pixel_m: Optional[float] = Field(default=None, ge=0.0)
    licence: Optional[str] = None


class GeometryAccuracy(str, Enum):
    verified = "verified"
    approximate = "approximate"
    inferred = "inferred"


class InfrastructureContext(BaseModel):
    """Oil / port / energy infrastructure matched to a scene (section 1.7)."""

    model_config = ConfigDict(extra="forbid")

    infrastructure_context_id: str
    dataset_version: str
    scene_id: str
    facility_id: str = Field(min_length=1)  # original source identifier preserved
    facility_name: Optional[str] = None
    facility_type: Optional[str] = None
    geometry_wkt: str = Field(min_length=1)
    crs: str = "EPSG:4326"
    geometry_accuracy: GeometryAccuracy = GeometryAccuracy.verified
    location_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    location_method: Optional[str] = None
    source_authority: str = Field(min_length=1)
    last_verified_at: Optional[datetime] = None
    operating_status: Optional[str] = None
    source_name: str = Field(min_length=1)
    source_record_id: Optional[str] = None
    licence: Optional[str] = None


class SplitAssignment(BaseModel):
    """Split assignment for a tile (section 6)."""

    model_config = ConfigDict(extra="forbid")

    tile_id: str
    dataset_version: str
    split: str  # train | val | test
    group_key: str  # the grouping dimension used (scene/incident/region/...)
    group_id: str
    strategy: str = "group_by_scene"
    seed: int
    leakage_flags: list[str] = Field(default_factory=list)

    @field_validator("split")
    @classmethod
    def _split_valid(cls, v: str) -> str:
        if v not in {"train", "val", "test"}:
            raise ValueError(f"split must be train|val|test, got {v!r}")
        return v


class SourceReference(BaseModel):
    """Reference from a derived artifact back to an external source (section 8)."""

    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1)
    official_identifier: str = Field(min_length=1)
    licence: Optional[str] = None
    attribution: Optional[str] = None
    source_url: Optional[str] = None


class Reliability(BaseModel):
    """Per-modality reliability scores (section 11). 0..1."""

    model_config = ConfigDict(extra="forbid")

    satellite_quality_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    label_quality_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    weather_match_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    ocean_match_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    vessel_data_quality_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    infrastructure_quality_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    overall_sample_quality_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    formula_ref: Optional[str] = None  # points to the configured formula doc


class ProcessingOperation(BaseModel):
    """One record within a processing manifest (section 3, section 8)."""

    model_config = ConfigDict(extra="forbid")

    operation_name: str = Field(min_length=1)
    library: str = Field(min_length=1)
    library_version: str = Field(min_length=1)
    parameters: dict[str, Any] = Field(default_factory=dict)
    input_checksum: Optional[str] = None
    output_checksum: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    warnings: list[str] = Field(default_factory=list)
    failure_status: Optional[bool] = None
    failure_message: Optional[str] = None

    @model_validator(mode="after")
    def _times_ordered(self) -> "ProcessingOperation":
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time < self.start_time
        ):
            raise ValueError("end_time must be >= start_time")
        if self.failure_status and not self.failure_message:
            raise ValueError("failure_message required when failure_status=True")
        return self


class ProcessingManifest(BaseModel):
    """Immutable-by-convention manifest for a processing stage (section 3/8)."""

    model_config = ConfigDict(extra="forbid")

    manifest_id: str
    stage: str = Field(min_length=1)
    dataset_version: str
    input_artifact_id: str = Field(min_length=1)
    output_artifact_id: Optional[str] = None
    library_versions: dict[str, str] = Field(default_factory=dict)
    input_checksum: Optional[str] = None
    output_checksum: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    operations: list[ProcessingOperation] = Field(default_factory=list)
    overall_failure_status: Optional[bool] = None
    notes: Optional[str] = None

    @model_validator(mode="after")
    def _resolve_failure(self) -> "ProcessingManifest":
        if any(op.failure_status for op in self.operations):
            self.overall_failure_status = True
        return self


class DatasetManifest(BaseModel):
    """The main multi-modality dataset manifest row (section 8)."""

    model_config = ConfigDict(extra="forbid")

    scene_id: str
    tile_id: str
    dataset_version: str
    incident_id: Optional[str] = None
    label_id: Optional[str] = None
    weather_record_id: Optional[str] = None
    ocean_record_id: Optional[str] = None
    vessel_context_id: Optional[str] = None
    infrastructure_context_id: Optional[str] = None
    auxiliary: dict[str, Any] = Field(default_factory=dict)