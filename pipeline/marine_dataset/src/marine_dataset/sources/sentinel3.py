"""Sentinel-3 (SLSTR/OLCI) search & download adapter.

Not implemented in Step 01. Registration needs: Copernicus Data Space account.
Licence: Copernicus free access + attribution; verify terms before redistribution.
Built in Step 10.
"""

from __future__ import annotations

from marine_dataset.sources.copernicus_dataspace import NotImplementedAdapterError


def require_registered() -> None:
    raise NotImplementedAdapterError(
        "sentinel3.py adapter is not implemented yet; see pipeline_inst.md for the owning step."
    )
