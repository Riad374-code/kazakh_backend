"""Oil infrastructure aggregator.

Not implemented in Step 01. Candidate sources (EMODnet Human Activities, OSM,
Global Energy Monitor, national portals) each need individual licence review.
Never mark inferred locations as verified. Built in Step 11.
"""

from __future__ import annotations

from marine_dataset.sources.copernicus_dataspace import NotImplementedAdapterError


def require_registered() -> None:
    raise NotImplementedAdapterError(
        "oil_infrastructure.py adapter is not implemented yet; see pipeline_inst.md for the owning step."
    )
