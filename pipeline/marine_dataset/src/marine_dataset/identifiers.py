"""Deterministic stable identifiers (pipeline_inst.md section 8, section 16).

Identifiers are derived from *canonical source identifiers* plus a versioned
namespace. Local filesystem paths are never used as identifiers. The same
canonical input must always yield the same identifier; materially different
input must yield a different identifier.
"""

from __future__ import annotations

import hashlib
import re
from typing import Iterable, Optional

_NAMESPACE_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]*$")
_ID_CHAR_RE = re.compile(r"[^a-z0-9_-]+")

# Default key length used by the v1 content-addressed ids.
_DEFAULT_TRUNC = 12


class IdentifierError(ValueError):
    """Raised for invalid identifier namespaces or components."""


def _validate_namespace(namespace: str) -> None:
    if not _NAMESPACE_RE.match(namespace):
        raise IdentifierError(
            f"invalid namespace {namespace!r}; use lowercase [a-z0-9_.-]"
        )


def _slug(value: str) -> str:
    """Normalise a single canonical component to a safe slug."""
    slug = value.strip().lower()
    slug = _ID_CHAR_RE.sub("-", slug)
    return slug.strip("-")


def content_hash(*parts: str, length: Optional[int] = _DEFAULT_TRUNC) -> str:
    """SHA-256 content hash over canonical parts, truncated for readability."""
    payload = "\x1f".join(parts).encode("utf-8")
    digest = hashlib.sha256(payload).hexdigest()
    if length:
        return digest[:length]
    return digest


def _namespace_kind(kind: str) -> str:
    return _slug(kind).replace("-", "_")


def stable_id(
    namespace: str,
    kind: str,
    components: Iterable[str],
    *,
    version: str = "v1",
    trunc: Optional[int] = _DEFAULT_TRUNC,
) -> str:
    """Build a deterministic, content-derived stable identifier.

    Args:
        namespace: Versioned namespace, e.g. ``marine`` or ``marine.dev.v2``.
        kind: Record kind (scene, label, tile, weather_record, ...).
        components: Canonical source components (source IDs, timestamps, ...).
            Order matters. Local file paths must NOT be passed here.
        version: Version label included in the output.
        trunc: Hash truncation length; None disables truncation.

    Returns:
        A stable id of the form ``<namespace>:<kind>:<version>:<hash>``.
    """
    _validate_namespace(namespace)
    _validate_namespace(version)
    kind_slug = _namespace_kind(kind)
    if not kind_slug:
        raise IdentifierError("kind must not be empty")
    canon_parts = [namespace, kind_slug, version]
    canon_parts.extend(_slug(c) for c in components if c)
    digest = content_hash(*canon_parts, length=trunc)
    return f"{namespace}:{kind_slug}:{version}:{digest}"


def scene_id(namespace: str, platform: str, product_identifier: str, version: str = "v1") -> str:
    """Stable id for a satellite scene from its canonical product identifier."""
    return stable_id(
        namespace, "scene", [platform, product_identifier], version=version
    )


def tile_id(
    namespace: str,
    parent_scene_id: str,
    col: int,
    row: int,
    crs: str,
    resolution_m: str,
    version: str = "v1",
) -> str:
    """Stable id for a tile derived from scene + grid coordinates."""
    return stable_id(
        namespace,
        "tile",
        [parent_scene_id, f"c{col}", f"r{row}", crs, str(resolution_m)],
        version=version,
    )


def label_id(namespace: str, source_record_id: str, annotation_method: str, version: str = "v1") -> str:
    """Stable id for a label from its canonical source record id."""
    return stable_id(
        namespace, "label", [source_record_id, annotation_method], version=version
    )


def record_id(
    namespace: str,
    kind: str,
    *components: str,
    version: str = "v1",
    trunc: Optional[int] = _DEFAULT_TRUNC,
) -> str:
    """Generic stable id for environmental / context / infra records."""
    return stable_id(namespace, kind, components, version=version, trunc=trunc)
