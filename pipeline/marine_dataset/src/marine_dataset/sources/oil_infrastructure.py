"""Provider-neutral infrastructure record normalization."""

from __future__ import annotations

from typing import Any

from marine_dataset.context import normalize_context


def normalize_records(
    records: list[dict[str, Any]], source_name: str = "infrastructure_registry"
) -> tuple[dict[str, Any], ...]:
    return tuple(normalize_context(item, source_name=source_name) for item in records)
