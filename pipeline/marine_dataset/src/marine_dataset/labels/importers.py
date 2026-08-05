"""Unified GeoJSON label importer preserving source and uncertainty metadata."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from shapely.geometry import shape

from marine_dataset.identifiers import label_id
from marine_dataset.schemas import AnnotationMethod, Confidence, Label, VerificationStatus

MAX_GEOJSON_BYTES = 100 * 1024 * 1024
MAX_FEATURES = 100_000


def import_geojson_labels(
    path: Path,
    *,
    scene_id: str,
    dataset_version: str,
    label_source: str,
    licence: str,
    default_class_id: int = 10,
    default_class_name: str = "unknown_or_unreviewed",
    ontology: Mapping[int, str] | None = None,
) -> tuple[Label, ...]:
    features = _load_features(path)
    return tuple(
        _label_from_feature(
            feature,
            index=index,
            path=path,
            scene_id=scene_id,
            dataset_version=dataset_version,
            label_source=label_source,
            licence=licence,
            default_class_id=default_class_id,
            default_class_name=default_class_name,
            ontology=ontology,
        )
        for index, feature in enumerate(features)
    )


def _load_features(path: Path) -> list[Mapping[str, Any]]:
    if path.stat().st_size > MAX_GEOJSON_BYTES:
        raise ValueError("GeoJSON exceeds configured import size limit")
    payload = json.loads(path.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    if not isinstance(features, list) or len(features) > MAX_FEATURES:
        raise ValueError("GeoJSON feature collection is invalid or too large")
    return features


def _label_from_feature(
    feature: Mapping[str, Any],
    *,
    index: int,
    path: Path,
    scene_id: str,
    dataset_version: str,
    label_source: str,
    licence: str,
    default_class_id: int,
    default_class_name: str,
    ontology: Mapping[int, str] | None,
) -> Label:
    props: Mapping[str, Any] = feature.get("properties", {})
    source_record = str(props.get("source_record_id") or feature.get("id") or index)
    method = AnnotationMethod(props.get("annotation_method", "other"))
    class_id = int(props.get("class_id", default_class_id))
    class_name = str(props.get("class_name", default_class_name))
    _validate_ontology(class_id, class_name, ontology)
    return Label(
        label_id=label_id("marine", source_record, method.value),
        dataset_version=dataset_version,
        scene_id=scene_id,
        class_id=class_id,
        class_name=class_name,
        geometry_wkt=shape(feature["geometry"]).wkt,
        crs=str(props.get("crs", "EPSG:4326")),
        label_source=label_source,
        source_record_id=source_record,
        source_url_or_identifier=str(props.get("source_url_or_identifier", path.name)),
        annotation_method=method,
        annotator_type=props.get("annotator_type"),
        annotation_timestamp=_parse_time(props.get("annotation_timestamp")),
        label_confidence=Confidence(props.get("label_confidence", "unknown")),
        verification_status=VerificationStatus(props.get("verification_status", "unverified")),
        number_of_reviewers=int(props.get("number_of_reviewers", 0)),
        is_weak_label=bool(props.get("is_weak_label", False)),
        is_machine_generated=bool(props.get("is_machine_generated", False)),
        quality_notes=props.get("quality_notes")
        or "Unavailable optional fields preserved as null.",
        licence=licence,
        citation=props.get("citation"),
    )


def _validate_ontology(
    class_id: int,
    class_name: str,
    ontology: Mapping[int, str] | None,
) -> None:
    if ontology is not None and ontology.get(class_id) != class_name:
        raise ValueError(f"class {class_id}:{class_name} is not present in the supplied ontology")


def _parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
