"""Copernicus Data Space Ecosystem shared client stub.

Step 01 contract: source adapters are NOT implemented yet. This module only
documents registration/access requirements and fails clearly if called.

Prerequisites (documented, not installed by this package):
- Free account at https://dataspace.copernicus.eu
- Credentials via MARINE_DATA_CDSE_USERNAME / MARINE_DATA_CDSE_PASSWORD
- Official catalogue API is OData (https://documentation.dataspace.copernicus.eu)
- Licence: Copernicus Programme free access, attribution required; verify terms
  before redistributing derived products.
"""

from __future__ import annotations


class NotImplementedAdapterError(NotImplementedError):
    """Raised when a source adapter that is not yet built is invoked."""


def require_registered() -> None:
    raise NotImplementedAdapterError(
        "Copernicus Data Space adapter is not implemented in Step 01. "
        "Registration required: https://dataspace.copernicus.eu (free account)."
    )
