"""Provider-neutral EMODnet record boundary."""

from __future__ import annotations

from typing import Any

from marine_dataset.context import normalize_context


def normalize_records(records: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    return tuple(normalize_context(item, source_name="emodnet") for item in records)
