"""Copernicus Marine Service (CMEMS) collector.

Not implemented in Step 01. Registration needs: account at
data.marine.copernicus.eu; terms restrict redistribution of raw products.
Use official Copernicus Marine Toolbox / motu-client. Built in Step 05.
"""

from __future__ import annotations

from marine_dataset.sources.copernicus_dataspace import NotImplementedAdapterError


def require_registered() -> None:
    raise NotImplementedAdapterError(
        "copernicus_marine.py adapter is not implemented yet; see pipeline_inst.md for the owning step."
    )
