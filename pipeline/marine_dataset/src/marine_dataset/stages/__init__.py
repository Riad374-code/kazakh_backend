"""Offline deterministic baselines for product stages 1-6."""

from marine_dataset.stages.anomaly import weekly_anomalies
from marine_dataset.stages.classification import classify
from marine_dataset.stages.forecast import advection_forecast
from marine_dataset.stages.impact import energy_impact
from marine_dataset.stages.prioritization import rank_events

__all__ = ["weekly_anomalies", "classify", "advection_forecast", "energy_impact", "rank_events"]
