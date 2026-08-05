"""Versioned dashboard response envelopes (Step 21)."""

from __future__ import annotations

from typing import Any


def response_envelope(
    data: Any,
    *,
    data_version: str,
    generated_at: str,
    provenance: tuple[str, ...] = (),
    quality: float | None = None,
    uncertainty: Any = None,
    missing_inputs: tuple[str, ...] = (),
) -> dict[str, Any]:
    if not data_version.strip() or not generated_at.strip():
        raise ValueError("data_version and generated_at are required")
    return {
        "contract_version": "1",
        "generated_at": generated_at,
        "data_version": data_version,
        "data": data,
        "provenance": provenance,
        "quality": quality,
        "uncertainty": uncertainty,
        "missing_inputs": missing_inputs,
        "limitations": ("Predictions and scenarios are not observations",),
    }


def paginate(items: list[Any], *, page: int = 1, page_size: int = 50) -> dict[str, Any]:
    if page < 1 or page_size < 1 or page_size > 1000:
        raise ValueError("page must be >=1 and page_size must be 1..1000")
    start = (page - 1) * page_size
    return {
        "items": items[start : start + page_size],
        "page": page,
        "page_size": page_size,
        "total": len(items),
        "has_next": start + page_size < len(items),
    }
