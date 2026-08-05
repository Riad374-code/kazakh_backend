"""OSM/Overpass collector (coastline, ports, infrastructure).

Not implemented in Step 01. Data under ODbL; attribution required; preserve
query, retrieval time, OSM IDs and tags. Built in Step 11.
"""

from __future__ import annotations

from marine_dataset.sources.copernicus_dataspace import NotImplementedAdapterError


def require_registered() -> None:
    raise NotImplementedAdapterError(
        "osm_overpass.py adapter is not implemented yet; see pipeline_inst.md for the owning step."
    )
