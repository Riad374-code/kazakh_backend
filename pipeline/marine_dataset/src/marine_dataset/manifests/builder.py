"""Manifest persistence helpers (pipeline_inst.md sections 3 and 8).

Step 02 scope: processing manifests are written as machine-readable JSON. The
full dataset manifest (parquet linking modalities) lands in its owning step.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from marine_dataset.identifiers import content_hash
from marine_dataset.schemas import ProcessingManifest, ProcessingOperation
from marine_dataset.storage import Storage, ensure_dir


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def build_processing_manifest(
    *,
    stage: str,
    dataset_version: str,
    input_artifact_id: str,
    output_artifact_id: Optional[str] = None,
    library_versions: Optional[dict[str, str]] = None,
    input_checksum: Optional[str] = None,
    output_checksum: Optional[str] = None,
    operations: Optional[list[ProcessingOperation]] = None,
    notes: Optional[str] = None,
) -> ProcessingManifest:
    """Construct a validated processing manifest with a deterministic id."""
    ops = operations or []
    start = min((op.start_time for op in ops if op.start_time), default=utc_now())
    end = max((op.end_time for op in ops if op.end_time), default=None)
    seed = input_artifact_id
    manifest_id = content_hash("manifest", stage, dataset_version, seed)
    return ProcessingManifest(
        manifest_id=manifest_id,
        stage=stage,
        dataset_version=dataset_version,
        input_artifact_id=input_artifact_id,
        output_artifact_id=output_artifact_id,
        library_versions=library_versions or {},
        input_checksum=input_checksum,
        output_checksum=output_checksum,
        start_time=start,
        end_time=end,
        operations=ops,
        notes=notes,
    )


def write_processing_manifest(
    manifest: ProcessingManifest,
    manifests_dir: Path,
    *,
    storage: Optional[Storage] = None,
) -> Path:
    """Persist a processing manifest as JSON and return its path."""
    ensure_dir(manifests_dir)
    filename = f"manifest_{manifest.stage}_{manifest.manifest_id}.json"
    payload = json.dumps(manifest.model_dump(mode="json"), indent=2)
    if storage is not None:
        return storage.write_text(manifests_dir / filename, payload)
    path = manifests_dir / filename
    path.write_text(payload, encoding="utf-8")
    return path


def serialize_manifest(manifest: ProcessingManifest) -> str:
    return json.dumps(manifest.model_dump(mode="json"), indent=2)


def attachment_checksum(artifact: Path) -> str:
    """Return the checksum of a manifest-referenced artifact (empty if absent)."""
    if artifact.is_file():
        return Storage.checksum_of(artifact) if artifact else ""
    return ""