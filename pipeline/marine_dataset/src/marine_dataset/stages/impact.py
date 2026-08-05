"""Stage 5 scenario-only energy impact calculations."""

from __future__ import annotations

from typing import Any


def energy_impact(
    event: dict[str, Any], coefficients: dict[str, float] | None = None
) -> dict[str, Any]:
    if not coefficients:
        return {
            "event_id": event.get("event_id"),
            "status": "not_estimated",
            "energy_impact_score": None,
            "missing_inputs": ("verified_coefficients",),
            "estimate_type": "scenario",
        }
    exposure = max(0.0, float(event.get("severity", 0) or 0)) * max(
        0.0, float(event.get("asset_exposure", 0) or 0)
    )
    monetary = exposure * float(coefficients.get("cost_per_unit", 0))
    return {
        "event_id": event.get("event_id"),
        "status": "estimated",
        "energy_impact_score": min(1.0, exposure),
        "monetary_estimate": monetary,
        "currency": coefficients.get("currency"),
        "base_year": coefficients.get("base_year"),
        "estimate_type": "scenario",
        "calculation_version": "energy_impact_v1",
    }
