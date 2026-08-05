"""Sentinel-1 GRD query validation and STAC metadata mapping."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from shapely.geometry import shape

from marine_dataset.identifiers import scene_id
from marine_dataset.schemas import IncidenceInfo, Scene, SceneSourceRef, SceneTime


class Sentinel1Query(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    bbox: tuple[float, float, float, float] | None = None
    intersects: dict[str, Any] | None = None
    start: str
    end: str
    polarizations: tuple[Literal["VV", "VH"], ...] = ("VV",)
    orbit_direction: Literal["ASCENDING", "DESCENDING"] | None = None
    relative_orbit: int | None = Field(default=None, ge=1)
    platform: Literal["sentinel-1a", "sentinel-1b", "sentinel-1c"] | None = None
    limit: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def _one_geometry(self) -> "Sentinel1Query":
        if (self.bbox is None) == (self.intersects is None):
            raise ValueError("provide exactly one of bbox or intersects")
        if self.bbox and (self.bbox[0] >= self.bbox[2] or self.bbox[1] >= self.bbox[3]):
            raise ValueError("invalid bbox ordering")
        if self.bbox and not (
            -180 <= self.bbox[0] <= 180
            and -90 <= self.bbox[1] <= 90
            and -180 <= self.bbox[2] <= 180
            and -90 <= self.bbox[3] <= 90
        ):
            raise ValueError("bbox coordinates are outside EPSG:4326 bounds")
        if self.intersects:
            geometry = shape(self.intersects)
            if geometry.is_empty or not geometry.is_valid:
                raise ValueError("intersects must be a valid non-empty GeoJSON geometry")
        if _parse_time(self.end) < _parse_time(self.start):
            raise ValueError("end must not precede start")
        return self

    @field_validator("polarizations")
    @classmethod
    def _vv_required(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if "VV" not in value:
            raise ValueError("Sentinel-1 oil-spill search requires VV")
        return value

    def to_stac_body(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "collections": ["sentinel-1-grd"],
            "datetime": f"{self.start}/{self.end}",
            "limit": self.limit,
            "filter-lang": "cql2-json",
        }
        body["bbox" if self.bbox else "intersects"] = (
            list(self.bbox) if self.bbox else self.intersects
        )
        filters: list[dict[str, Any]] = [
            {"op": "=", "args": [{"property": "sar:instrument_mode"}, "IW"]},
        ]
        filters.extend(
            {
                "op": "a_contains",
                "args": [{"property": "sar:polarizations"}, polarization],
            }
            for polarization in self.polarizations
        )
        if self.orbit_direction:
            filters.append(
                {"op": "=", "args": [{"property": "sat:orbit_state"}, self.orbit_direction.lower()]}
            )
        if self.relative_orbit:
            filters.append(
                {"op": "=", "args": [{"property": "sat:relative_orbit"}, self.relative_orbit]}
            )
        if self.platform:
            filters.append({"op": "=", "args": [{"property": "platform"}, self.platform]})
        body["filter"] = {"op": "and", "args": filters}
        return body


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _scene_source(item: dict[str, Any], props: dict[str, Any]) -> SceneSourceRef:
    platform = str(props.get("platform", "unknown"))
    return SceneSourceRef(
        source_name="Copernicus Data Space Ecosystem",
        official_product_identifier=str(item["id"]),
        platform=platform,
        instrument_mode=props.get("sar:instrument_mode"),
        processing_level=props.get("processing:level") or "GRD",
        processing_baseline=props.get("processing:baseline"),
        absolute_orbit=props.get("sat:absolute_orbit"),
        relative_orbit=props.get("sat:relative_orbit"),
        pass_direction=str(props["sat:orbit_state"]).upper()
        if props.get("sat:orbit_state")
        else None,
        polarizations=list(props.get("sar:polarizations", [])),
        incidence_angle_available=any(
            key in props
            for key in (
                "sar:incidence_angle",
                "sar:incidence_angle_min",
                "sar:incidence_angle_max",
            )
        ),
        footprint_wkt=shape(item["geometry"]).wkt if item.get("geometry") else None,
        source_url=next(
            (link.get("href") for link in item.get("links", []) if link.get("rel") == "self"), None
        ),
    )


def parse_sentinel1_item(item: dict[str, Any], dataset_version: str) -> Scene:
    props = item.get("properties", {})
    start = _parse_time(props.get("start_datetime") or props["datetime"])
    end = _parse_time(props.get("end_datetime") or props.get("datetime") or props["start_datetime"])
    midpoint = start + (end - start) / 2
    platform = str(props.get("platform", "unknown"))
    incidence_value = props.get("sar:incidence_angle")
    return Scene(
        scene_id=scene_id("marine", platform, str(item["id"])),
        dataset_version=dataset_version,
        scene_time=SceneTime(
            acquisition_start=start,
            acquisition_end=end,
            midpoint=midpoint,
            source_timezone="UTC",
            normalized_utc=midpoint,
        ),
        source=_scene_source(item, props),
        pixel_spacing_m=props.get("sar:pixel_spacing"),
        resolution_m=props.get("gsd"),
        incidence=IncidenceInfo(
            incidence_angle_min_deg=props.get("sar:incidence_angle_min", incidence_value),
            incidence_angle_max_deg=props.get("sar:incidence_angle_max", incidence_value),
        ),
    )


def require_registered() -> None:
    from marine_dataset.sources.copernicus_dataspace import require_registered as require_cdse

    require_cdse()
