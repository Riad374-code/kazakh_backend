"""Machine-readable source registry (pipeline_inst.md section 7).

Every source record carries every section 7 field. Licence facts are only
recorded when actually verified/sourced; unknown facts are marked
``licence_status: unresolved`` and the source is not admitted to redistributable
builds.

No live terms are invented. ``terms_checked_at`` records the check time and the
source URL is stored for auditability.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class LicenceStatus(str, Enum):
    resolved = "resolved"
    unresolved = "unresolved"
    incompatible = "incompatible"


class AccessMethod(str, Enum):
    api = "api"
    download = "download"
    web = "web"


class SourceEntry(BaseModel):
    """A single registry record with all pipeline_inst.md section 7 fields."""

    model_config = ConfigDict(extra="forbid")

    source_key: str = Field(description="Stable key used to reference this source.")

    # identity / access
    source_name: str
    provider: str
    dataset_or_product: Optional[str] = None
    official_identifier: Optional[str] = None
    access_method: AccessMethod = AccessMethod.api
    api_or_download_interface: Optional[str] = None
    terms_url: Optional[str] = Field(default=None, description="Official terms URL.")

    # licence fields
    licence_name: Optional[str] = None
    licence_version: Optional[str] = None
    attribution_text: Optional[str] = None
    commercial_use: bool = False
    redistribution: bool = False
    modification: bool = False
    share_alike: Optional[bool] = None
    licence_status: LicenceStatus = LicenceStatus.unresolved

    # access constraints
    account_required: bool = False
    api_key_required: bool = False
    rate_limits: Optional[str] = None

    # coverage and resolution
    geographic_coverage: Optional[str] = None
    temporal_coverage: Optional[str] = None
    spatial_resolution: Optional[str] = None
    temporal_resolution: Optional[str] = None

    # provenance / traceability
    retrieval_timestamp: Optional[datetime] = None
    source_version: Optional[str] = None
    citation: Optional[str] = None
    known_limitations: list[str] = Field(default_factory=list)
    terms_checked_at: Optional[datetime] = Field(
        default=None, description="When official terms were last verified."
    )
    terms_document_checksum: Optional[str] = None
    terms_archived_reference: Optional[str] = None

    # our own operational flags
    requires_registration: bool = False
    requires_credentials: bool = False
    requires_manual_approval: bool = False
    notes: Optional[str] = None

    @field_validator("source_key")
    @classmethod
    def _key_slug(cls, v: str) -> str:
        if not v or any(not (c.isalnum() or c in "_-.") for c in v):
            raise ValueError(f"invalid source_key {v!r}")
        return v

    @model_validator(mode="after")
    def _resolved_requires_check(self) -> "SourceEntry":
        if self.licence_status == LicenceStatus.resolved and self.terms_checked_at is None:
            raise ValueError(
                "a source marked resolved must record terms_checked_at (we do not guess licences)"
            )
        return self


class SourceRegistry(BaseModel):
    """The validated registry container."""

    model_config = ConfigDict(extra="forbid")

    version: str = "1.0"
    updated_at: Optional[datetime] = None
    sources: list[SourceEntry] = Field(default_factory=list)

    def by_key(self, key: str) -> Optional[SourceEntry]:
        for entry in self.sources:
            if entry.source_key == key:
                return entry
        return None

    def unsupported_for_redistribution(self) -> list[SourceEntry]:
        """Sources that are unresolved or incompatibly licensed."""
        return [
            s
            for s in self.sources
            if s.licence_status != LicenceStatus.resolved or not s.redistribution
        ]

    def unresolved(self) -> list[SourceEntry]:
        return [s for s in self.sources if s.licence_status == LicenceStatus.unresolved]

    def requiring_action(self) -> list[SourceEntry]:
        """Sources needing registration, credentials, or manual approval."""
        return [
            s
            for s in self.sources
            if s.requires_registration or s.requires_credentials or s.requires_manual_approval
        ]


def load_registry(path: Path | str) -> SourceRegistry:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("registry YAML root must be a mapping")
    return SourceRegistry.model_validate(data)


def dump_registry(registry: SourceRegistry) -> bytes:
    return yaml.safe_dump(
        _to_jsonable(registry.model_dump(exclude_none=False)),
        sort_keys=False,
        allow_unicode=True,
    ).encode("utf-8")


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return _to_jsonable(value.model_dump())
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def natural_key_default_registry() -> Path:
    """Expected committed location: metadata/source_registry.yaml."""
    # Search upward from the package for the repo-level metadata directory.
    start = Path(__file__).resolve()
    for candidate in start.parents:
        potential = candidate / "metadata" / "source_registry.yaml"
        if potential.is_file():
            return potential
    # Fall back to a conventional relative path if not located yet.
    return Path("metadata/source_registry.yaml")


def registry_report_data(registry: SourceRegistry) -> dict[str, Any]:
    """Machine-readable licence report data (section 7 / Step 03)."""
    return {
        "version": registry.version,
        "updated_at": registry.updated_at.isoformat() if registry.updated_at else None,
        "total_sources": len(registry.sources),
        "resolved": len(
            [s for s in registry.sources if s.licence_status == LicenceStatus.resolved]
        ),
        "unresolved": len(registry.unresolved()),
        "incompatible": len(
            [s for s in registry.sources if s.licence_status == LicenceStatus.incompatible]
        ),
        "not_redistributable": len(registry.unsupported_for_redistribution()),
        "sources": [
            {
                "source_key": s.source_key,
                "licence_name": s.licence_name,
                "licence_status": s.licence_status.value if s.licence_status else None,
                "commercial": s.commercial_use,
                "redistribution": s.redistribution,
                "modification": s.modification,
                "share_alike": s.share_alike,
                "account_required": s.account_required,
                "api_key_required": s.api_key_required,
                "rate_limits": s.rate_limits,
                "terms_checked_at": (
                    s.terms_checked_at.isoformat() if s.terms_checked_at else None
                ),
                "terms_url": s.terms_url,
                "requires_action": (
                    s.requires_registration or s.requires_credentials or s.requires_manual_approval
                ),
            }
            for s in registry.sources
        ],
    }


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
