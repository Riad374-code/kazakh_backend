"""Open-Meteo Historical / Archive API collector.

Not implemented in Step 01. No account required, but the free tier is
non-commercial by default and rate-limited; verify current terms and endpoint
(model selection must be recorded). Built in Step 05.
"""

from __future__ import annotations

from marine_dataset.sources.copernicus_dataspace import NotImplementedAdapterError


def require_registered() -> None:
    raise NotImplementedAdapterError(
        "open_meteo.py adapter is not implemented yet; see pipeline_inst.md for the owning step."
    )
