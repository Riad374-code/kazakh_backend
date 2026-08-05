"""Validated, deterministic Step 09 dataset artifact builder."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path, PureWindowsPath
from typing import Any, Mapping, Sequence

import pandas as pd
import yaml

PARQUET_TABLES = (
    "dataset_manifest",
    "scenes",
    "tiles",
    "labels",
    "environment",
    "vessels",
    "infrastructure",
    "split_manifest",
)

TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "dataset_manifest": (
        "scene_id",
        "dataset_version",
        "tile_id",
        "incident_id",
        "label_id",
        "weather_record_id",
        "ocean_record_id",
        "vessel_context_id",
        "infrastructure_context_id",
        "auxiliary",
    ),
    "scenes": (
        "scene_id",
        "dataset_version",
        "source_name",
        "official_product_identifier",
        "platform",
        "acquisition_start",
        "acquisition_end",
        "crs",
        "raw_relative_path",
        "raw_product_checksum",
        "licence",
    ),
    "tiles": (
        "tile_id",
        "dataset_version",
        "scene_id",
        "col",
        "row",
        "bbox_wkt",
        "crs",
        "raster_path",
        "mask_path",
        "channels",
    ),
    "labels": (
        "label_id",
        "dataset_version",
        "scene_id",
        "class_id",
        "class_name",
        "label_source",
        "source_record_id",
        "source_url_or_identifier",
        "licence",
    ),
    "environment": (
        "record_id",
        "dataset_version",
        "modality",
        "variable",
        "value",
        "unit",
        "source_name",
        "product_id",
        "dataset_id",
        "licence",
    ),
    "vessels": (
        "vessel_context_id",
        "dataset_version",
        "scene_id",
        "vessel_id",
        "record_type",
        "source_name",
        "source_record_id",
        "licence",
    ),
    "infrastructure": (
        "infrastructure_context_id",
        "dataset_version",
        "scene_id",
        "facility_id",
        "source_name",
        "source_record_id",
        "licence",
    ),
    "split_manifest": (
        "tile_id",
        "dataset_version",
        "split",
        "group_key",
        "group_id",
        "strategy",
        "seed",
        "leakage_flags",
    ),
}

COLUMN_DTYPES = {
    "col": "Int64",
    "row": "Int64",
    "class_id": "Int64",
    "value": "Float64",
    "seed": "Int64",
    "source_row_index": "Int64",
}

ID_COLUMNS = {
    "scenes": "scene_id",
    "tiles": "tile_id",
    "labels": "label_id",
    "environment": "record_id",
    "vessels": "vessel_context_id",
    "infrastructure": "infrastructure_context_id",
    "split_manifest": "tile_id",
}

PROVENANCE_FIELDS = {
    "scenes": (("source_name",), ("official_product_identifier",), ("licence", "licence_ref")),
    "labels": (
        ("label_source",),
        ("source_record_id",),
        ("source_url_or_identifier",),
        ("licence", "licence_ref"),
    ),
    "environment": (("product_id", "dataset_id"), ("licence", "licence_ref")),
    "vessels": (("source_name",), ("source_record_id",), ("licence", "licence_ref")),
    "infrastructure": (
        ("source_name",),
        ("source_record_id",),
        ("licence", "licence_ref"),
    ),
}

DEFAULT_ML_EXPORT_CONTRACT: dict[str, Any] = {
    "schema_version": "1.0",
    "status": "not_configured",
    "channels": [],
    "channel_axis_order": "CHW",
    "dtype": "float32",
    "units": {},
    "nodata": {"representation": "mask", "value": None},
    "normalization": {
        "status": "not_run",
        "fit_scope": "training_split_only",
        "method": None,
        "parameters": {},
    },
    "target": {"status": "not_configured", "source": "labels.parquet", "field": "class_id"},
    "weights": {"status": "not_configured", "source": None, "field": None},
    "split": {
        "status": "not_run",
        "source": "split_manifest.parquet",
        "allowed_values": ["train", "val", "test"],
    },
    "feature_availability": {
        "representation": "per_sample_boolean_map",
        "required_features": [],
        "optional_features": [],
    },
}

_STABLE_ID = re.compile(r"^[^\s]+$")
_CHECKSUM = re.compile(r"^[0-9a-f]{64}$")


class DatasetContractError(ValueError):
    """Raised before output when dataset rows violate the Step 09 contract."""


@dataclass(frozen=True)
class DatasetTables:
    tables: Mapping[str, Sequence[Mapping[str, Any]]] = field(default_factory=dict)
    dataset_version: str = "0.1.0"
    ml_export_contract: Mapping[str, Any] = field(default_factory=dict)


def _copy_rows(dataset: DatasetTables) -> dict[str, list[dict[str, Any]]]:
    unknown = sorted(set(dataset.tables) - set(PARQUET_TABLES))
    if unknown:
        raise DatasetContractError(f"unknown table(s): {', '.join(unknown)}")
    return {name: [dict(row) for row in dataset.tables.get(name, ())] for name in PARQUET_TABLES}


def _present(row: Mapping[str, Any], alternatives: tuple[str, ...]) -> bool:
    return any(row.get(name) is not None and str(row.get(name)).strip() for name in alternatives)


def _validate_ids_and_versions(
    rows: Mapping[str, Sequence[Mapping[str, Any]]], version: str
) -> None:
    if not version.strip():
        raise DatasetContractError("dataset_version must not be empty")
    for table, records in rows.items():
        seen: set[str] = set()
        id_column = ID_COLUMNS.get(table)
        for index, row in enumerate(records):
            if row.get("dataset_version") != version:
                raise DatasetContractError(
                    f"{table}[{index}] dataset_version must equal {version!r}"
                )
            if id_column:
                value = row.get(id_column)
                if not isinstance(value, str) or not _STABLE_ID.fullmatch(value):
                    raise DatasetContractError(
                        f"{table}[{index}] has invalid stable ID {id_column}"
                    )
                if value in seen:
                    raise DatasetContractError(f"duplicate {id_column} {value!r} in {table}")
                seen.add(value)


def _validate_provenance(rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    for table, groups in PROVENANCE_FIELDS.items():
        for index, row in enumerate(rows[table]):
            for alternatives in groups:
                if not _present(row, alternatives):
                    field_name = "licence" if "licence" in alternatives else "/".join(alternatives)
                    raise DatasetContractError(f"{table}[{index}] missing provenance {field_name}")


def _validate_relative_paths(rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    for table, records in rows.items():
        for index, row in enumerate(records):
            for field_name, value in row.items():
                if not field_name.endswith(("_path", "_relative_path")) or value in (None, ""):
                    continue
                path = str(value)
                windows = PureWindowsPath(path)
                if (
                    Path(path).is_absolute()
                    or windows.is_absolute()
                    or windows.drive
                    or ".." in windows.parts
                ):
                    raise DatasetContractError(
                        f"{table}[{index}].{field_name} must be a safe relative artifact reference"
                    )


def _id_set(rows: Mapping[str, Sequence[Mapping[str, Any]]], table: str, field: str) -> set[str]:
    return {str(row[field]) for row in rows[table] if row.get(field)}


def _validate_foreign_keys(rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    ids = {
        "scene": _id_set(rows, "scenes", "scene_id"),
        "tile": _id_set(rows, "tiles", "tile_id"),
        "label": _id_set(rows, "labels", "label_id"),
        "environment": _id_set(rows, "environment", "record_id"),
        "vessel": _id_set(rows, "vessels", "vessel_context_id"),
        "infrastructure": _id_set(rows, "infrastructure", "infrastructure_context_id"),
    }
    checks = (
        ("tiles", "scene_id", "scene", True),
        ("labels", "scene_id", "scene", True),
        ("vessels", "scene_id", "scene", True),
        ("infrastructure", "scene_id", "scene", True),
        ("split_manifest", "tile_id", "tile", True),
        ("dataset_manifest", "scene_id", "scene", True),
        ("dataset_manifest", "tile_id", "tile", True),
        ("dataset_manifest", "label_id", "label", False),
        ("dataset_manifest", "weather_record_id", "environment", False),
        ("dataset_manifest", "ocean_record_id", "environment", False),
        ("dataset_manifest", "vessel_context_id", "vessel", False),
        ("dataset_manifest", "infrastructure_context_id", "infrastructure", False),
    )
    for table, field_name, target, required in checks:
        for index, row in enumerate(rows[table]):
            value = row.get(field_name)
            if required and value in (None, ""):
                raise DatasetContractError(f"{table}[{index}].{field_name} is required")
            if value not in (None, "") and str(value) not in ids[target]:
                raise DatasetContractError(
                    f"foreign key {table}[{index}].{field_name}={value!r} does not exist"
                )


def _validate_manifest_uniqueness(rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    seen: set[tuple[str, ...]] = set()
    for row in rows["dataset_manifest"]:
        key = tuple(str(row.get(name) or "") for name in ("scene_id", "tile_id", "label_id"))
        if key in seen:
            raise DatasetContractError(f"duplicate dataset_manifest sample key {key!r}")
        seen.add(key)


def _validate(dataset: DatasetTables, rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> None:
    _validate_ids_and_versions(rows, dataset.dataset_version)
    _validate_provenance(rows)
    _validate_relative_paths(rows)
    _validate_foreign_keys(rows)
    _validate_manifest_uniqueness(rows)


def _json_cell(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return value


def _write_parquet(path: Path, rows: Sequence[Mapping[str, Any]], columns: tuple[str, ...]) -> None:
    extras = sorted({key for row in rows for key in row if key not in columns})
    ordered_columns = [*columns, *extras]
    normalized = [{key: _json_cell(row.get(key)) for key in ordered_columns} for row in rows]
    frame = pd.DataFrame(normalized, columns=ordered_columns)
    for key in ordered_columns:
        dtype = COLUMN_DTYPES.get(key, "string")
        frame[key] = pd.Series(frame[key], dtype=dtype)
    frame.to_parquet(path, index=False)


def _copy_or_placeholder(source: Path | None, destination: Path, payload: dict[str, Any]) -> None:
    if source is not None and not source.is_file():
        raise DatasetContractError(f"artifact source does not exist: {source}")
    if source is not None:
        shutil.copyfile(source, destination)
    else:
        destination.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in base.keys() | override.keys():
        base_value = base.get(key)
        override_value = override.get(key)
        if isinstance(base_value, Mapping) and isinstance(override_value, Mapping):
            result[key] = _deep_merge(base_value, override_value)
        elif key in override:
            result[key] = override_value
        else:
            result[key] = base_value
    return result


def _ml_contract(dataset: DatasetTables) -> dict[str, Any]:
    contract = _deep_merge(DEFAULT_ML_EXPORT_CONTRACT, dataset.ml_export_contract)
    channels = contract.get("channels")
    if not isinstance(channels, list) or any(not isinstance(item, str) for item in channels):
        raise DatasetContractError("ML export contract channels must be an ordered string list")
    if len(channels) != len(set(channels)):
        raise DatasetContractError("ML export contract channels must be unique")
    units = contract.get("units")
    if not isinstance(units, Mapping) or any(channel not in units for channel in channels):
        raise DatasetContractError("ML export contract must specify units for every channel")
    return contract


def _sample_index(
    rows: Mapping[str, Sequence[Mapping[str, Any]]], version: str
) -> list[dict[str, Any]]:
    split_by_tile = {str(row["tile_id"]): row.get("split") for row in rows["split_manifest"]}
    ordered = sorted(
        rows["dataset_manifest"],
        key=lambda row: tuple(
            str(row.get(name) or "") for name in ("scene_id", "tile_id", "label_id")
        ),
    )
    return [
        _sample_row(row, source_index, split_by_tile, version)
        for source_index, row in enumerate(ordered)
    ]


def _sample_row(
    row: Mapping[str, Any],
    source_index: int,
    split_by_tile: Mapping[str, Any],
    version: str,
) -> dict[str, Any]:
    identity = "|".join(
        str(row.get(name) or "") for name in ("scene_id", "tile_id", "label_id", "incident_id")
    )
    digest = hashlib.sha256(f"{version}|{identity}".encode()).hexdigest()[:24]
    return {
        "sample_id": f"sample:{digest}",
        "dataset_version": version,
        "scene_id": row.get("scene_id"),
        "tile_id": row.get("tile_id"),
        "label_id": row.get("label_id"),
        "split": split_by_tile.get(str(row.get("tile_id"))) or None,
        "feature_availability": _feature_availability(row),
        "source_row_index": source_index,
    }


def _feature_availability(row: Mapping[str, Any]) -> Mapping[str, Any]:
    auxiliary = row.get("auxiliary")
    supplied = auxiliary.get("feature_availability") if isinstance(auxiliary, Mapping) else None
    if isinstance(supplied, Mapping):
        return supplied
    return {
        "label": bool(row.get("label_id")),
        "weather": bool(row.get("weather_record_id")),
        "ocean": bool(row.get("ocean_record_id")),
        "vessel": bool(row.get("vessel_context_id")),
        "infrastructure": bool(row.get("infrastructure_context_id")),
    }


def _write_checksums(root: Path) -> Path:
    lines = []
    files = sorted(
        item for item in root.iterdir() if item.is_file() and item.name != "checksums.sha256"
    )
    for path in files:
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}")
    target = root / "checksums.sha256"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def build_dataset_artifacts(
    output_dir: Path,
    dataset: DatasetTables,
    *,
    source_registry: Path | None = None,
    label_ontology: Path | None = None,
) -> dict[str, Path]:
    """Validate immutable input rows, then materialize the complete Step 09 bundle."""
    rows = _copy_rows(dataset)
    _validate(dataset, rows)
    contract = _ml_contract(dataset)
    samples = _sample_index(rows, dataset.dataset_version)
    _validate_artifact_sources(source_registry, label_ontology)
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs = _write_table_artifacts(output_dir, rows)
    outputs = {**outputs, **_write_sample_index(output_dir, samples)}
    outputs = {
        **outputs,
        **_write_contract_artifacts(
            output_dir,
            contract,
            source_registry=source_registry,
            label_ontology=label_ontology,
        ),
    }
    outputs = {
        **outputs,
        **_write_report_artifacts(output_dir, dataset.dataset_version, rows, samples),
    }
    return {**outputs, "checksums": _write_checksums(output_dir)}


def _validate_artifact_sources(*sources: Path | None) -> None:
    for source in sources:
        if source is not None and not source.is_file():
            raise DatasetContractError(f"artifact source does not exist: {source}")


def _write_table_artifacts(
    output_dir: Path,
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    for name in PARQUET_TABLES:
        path = output_dir / f"{name}.parquet"
        _write_parquet(path, rows[name], TABLE_COLUMNS[name])
        outputs[name] = path
    return outputs


def _write_sample_index(output_dir: Path, samples: Sequence[Mapping[str, Any]]) -> dict[str, Path]:
    sample_index = output_dir / "sample_index.parquet"
    _write_parquet(
        sample_index,
        samples,
        (
            "sample_id",
            "dataset_version",
            "scene_id",
            "tile_id",
            "label_id",
            "split",
            "feature_availability",
            "source_row_index",
        ),
    )
    return {"sample_index": sample_index}


def _write_contract_artifacts(
    output_dir: Path,
    contract: Mapping[str, Any],
    *,
    source_registry: Path | None,
    label_ontology: Path | None,
) -> dict[str, Path]:
    registry = output_dir / "source_registry.yaml"
    ontology = output_dir / "label_ontology.yaml"
    _copy_or_placeholder(source_registry, registry, {"status": "source_registry_not_supplied"})
    _copy_or_placeholder(label_ontology, ontology, {"status": "label_ontology_not_supplied"})
    contract_path = output_dir / "ml_export_contract.json"
    contract_path.write_text(
        json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "source_registry": registry,
        "label_ontology": ontology,
        "ml_export_contract": contract_path,
    }


def _write_report_artifacts(
    output_dir: Path,
    version: str,
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
    samples: Sequence[Mapping[str, Any]],
) -> dict[str, Path]:
    quality = _write_quality_report(output_dir, rows, samples)
    licence, card, issues = _write_markdown_reports(output_dir, version, len(samples))
    return {
        "quality_report": quality,
        "licence_report": licence,
        "dataset_card": card,
        "known_issues": issues,
    }


def _write_quality_report(
    output_dir: Path,
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
    samples: Sequence[Mapping[str, Any]],
) -> Path:
    row_counts = {name: len(rows[name]) for name in PARQUET_TABLES}
    row_counts["sample_index"] = len(samples)
    quality = output_dir / "quality_report.json"
    quality.write_text(
        json.dumps(
            {
                "status": "not_run",
                "reason": "Full Step 14 quality validation is unavailable.",
                "manifest_contract_validation": {"status": "passed", "checks": 5},
                "row_counts": row_counts,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return quality


def _write_markdown_reports(output_dir: Path, version: str, sample_count: int) -> tuple[Path, ...]:
    licence = output_dir / "licence_report.md"
    licence.write_text(
        "# Licence Report\n\nStatus: **not run**.\n\n"
        "Row-level licence/provenance presence passed; compatibility and redistribution review remain pending.\n",
        encoding="utf-8",
    )
    card = output_dir / "dataset_card.md"
    card.write_text(
        f"# Dataset Card\n\nVersion: `{version}`\n\n"
        f"Samples indexed: {sample_count}.\n\n"
        "Status: partial Step 09 build; split and full quality checks not run.\n",
        encoding="utf-8",
    )
    issues = output_dir / "known_issues.md"
    issues.write_text(
        "# Known Issues\n\n- `split_not_run`: grouped splitting is not available yet.\n"
        "- `quality_not_run`: full dataset validation is not available yet.\n"
        "- `licence_review_not_run`: licence compatibility requires human review.\n",
        encoding="utf-8",
    )
    return licence, card, issues


def verify_checksums(root: Path) -> list[str]:
    """Return malformed, missing, unsafe, or checksum-mismatched artifact references."""
    failures: list[str] = []
    checksum_file = root / "checksums.sha256"
    if not checksum_file.is_file():
        return ["checksums.sha256"]
    for line_number, line in enumerate(checksum_file.read_text(encoding="utf-8").splitlines(), 1):
        if "  " not in line:
            failures.append(f"checksums.sha256:{line_number}")
            continue
        expected, relative = line.split("  ", 1)
        candidate = Path(relative)
        if not _CHECKSUM.fullmatch(expected) or candidate.is_absolute() or ".." in candidate.parts:
            failures.append(relative or f"checksums.sha256:{line_number}")
            continue
        target = (root / candidate).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            failures.append(relative)
            continue
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            failures.append(relative)
    return failures
