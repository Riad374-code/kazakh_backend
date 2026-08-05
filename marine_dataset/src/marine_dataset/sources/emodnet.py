"""EMODnet collector.

Not implemented in Step 01. Open data; per-dataset licences, coverage and
update dates vary and must be preserved. Distinguish European vs global coverage.
Built in Step 11.
"""

from __future__ import annotations

from marine_dataset.sources.copernicus_dataspace import NotImplementedAdapterError


def require_registered() -> None:
    raise NotImplementedAdapterError(
        "emodnet.py adapter is not implemented yet; see pipeline_inst.md for the owning step."
    )