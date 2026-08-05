"""Global Fishing Watch adapter.

Not implemented in Step 01. Registration needs: registered API token.
Allowed fields are limited by GFW terms; do not imply raw global AIS is free.
Built in Steps 12/14.
"""

from __future__ import annotations

from marine_dataset.sources.copernicus_dataspace import NotImplementedAdapterError


def require_registered() -> None:
    raise NotImplementedAdapterError(
        "global_fishing_watch.py adapter is not implemented yet; see pipeline_inst.md for the owning step."
    )
