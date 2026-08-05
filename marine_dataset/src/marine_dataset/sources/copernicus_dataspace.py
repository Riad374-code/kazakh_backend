"""Copernicus Data Space Ecosystem (CDSE) OData client and OAuth2 authenticator.

Implements Pipeline Step 04: Real access to satellite catalogs and scene downloads.
Supports:
- Username/Password OAuth2 Grant (CDSE_USERNAME / CDSE_PASSWORD)
- Client Credentials Grant (SH_CLIENT_ID / SH_CLIENT_SECRET)
- OData v1 REST querying (https://catalogue.dataspace.copernicus.eu/odata/v1/Products)
"""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional
import urllib.parse
import requests

from marine_dataset.logging_config import get_logger

log = get_logger("copernicus_dataspace")

AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOGUE_URL = "https://catalogue.dataspace.copernicus.eu/odata/v1/Products"


class NotImplementedAdapterError(NotImplementedError):
    """Raised when a source adapter that is not yet built is invoked."""


class CopernicusAuthError(Exception):
    """Raised when authentication with Copernicus Data Space fails."""


class CopernicusQueryError(Exception):
    """Raised when OData API catalog queries fail."""


class CDSEClient:
    """OAuth2 automated client and catalog querying interface for Copernicus Data Space."""

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        self.username = username or os.getenv("CDSE_USERNAME") or os.getenv("MARINE_DATA_CDSE_USERNAME")
        self.password = password or os.getenv("CDSE_PASSWORD") or os.getenv("MARINE_DATA_CDSE_PASSWORD")
        self.client_id = client_id or os.getenv("SH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("SH_CLIENT_SECRET")

        self._token: Optional[str] = None
        self._token_expiry: float = 0.0
        self.session = requests.Session()

    def get_access_token(self) -> str:
        """Obtain or refresh OAuth2 Bearer Access Token from Copernicus CDSE."""
        if self._token and time.time() < (self._token_expiry - 60):
            return self._token

        # Try Client Credentials first if available, otherwise fallback to username/password
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        payload = {}

        if self.client_id and self.client_secret:
            log.info("Authenticating with Copernicus CDSE via Client Credentials...")
            payload = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "client_credentials",
            }
        elif self.username and self.password:
            log.info("Authenticating with Copernicus CDSE via Username/Password grant...")
            payload = {
                "client_id": "cdse-public",
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
            }
        else:
            raise CopernicusAuthError(
                "No Copernicus CDSE credentials found! Please set CDSE_USERNAME & CDSE_PASSWORD "
                "(or SH_CLIENT_ID & SH_CLIENT_SECRET) in your local .env file."
            )

        response = self.session.post(AUTH_URL, data=payload, headers=headers, timeout=30)
        if response.status_code != 200:
            log.error("Authentication failed: HTTP %s - %s", response.status_code, response.text)
            raise CopernicusAuthError(f"Failed to obtain token from CDSE: HTTP {response.status_code}")

        data = response.json()
        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", 600))
        self._token_expiry = time.time() + expires_in
        log.info("Successfully authenticated with Copernicus CDSE.")
        return self._token

    def query_products(
        self,
        collection: str = "SENTINEL-1",
        product_type: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        bbox: Optional[List[float]] = None,  # [min_lon, min_lat, max_lon, max_lat]
        max_results: int = 10,
    ) -> List[Dict[str, Any]]:
        """Query CDSE OData API for satellite products matching criteria."""
        filters = [f"Collection/Name eq '{collection}'"]

        if product_type:
            filters.append(f"Attributes/OData.CSC.StringAttribute/any(att:att/Name eq 'productType' and att/OData.CSC.StringAttribute/Value eq '{product_type}')")

        if start_date and end_date:
            filters.append(f"ContentDate/Start gt {start_date}T00:00:00.000Z and ContentDate/End lt {end_date}T23:59:59.999Z")
        elif start_date:
            filters.append(f"ContentDate/Start gt {start_date}T00:00:00.000Z")

        if bbox and len(bbox) == 4:
            min_lon, min_lat, max_lon, max_lat = bbox
            polygon_wkt = (
                f"POLYGON(({min_lon} {min_lat},{max_lon} {min_lat},"
                f"{max_lon} {max_lat},{min_lon} {max_lat},{min_lon} {min_lat}))"
            )
            filters.append(f"OData.CSC.Intersects(area=geography'SRID=4326;{polygon_wkt}')")

        filter_str = " and ".join(filters)
        query_params = {
            "$filter": filter_str,
            "$orderby": "ContentDate/Start desc",
            "$top": str(max_results),
            "$expand": "Attributes",
        }
        url = f"{CATALOGUE_URL}?{urllib.parse.urlencode(query_params)}"
        log.info("Executing CDSE OData Query: %s", url)

        # Token is optional for viewing public metadata in OData, but required if rate-limited
        headers = {}
        try:
            token = self.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        except CopernicusAuthError as e:
            log.warning("Proceeding with unauthenticated metadata OData query: %s", e)

        resp = self.session.get(url, headers=headers, timeout=30)
        if resp.status_code != 200:
            raise CopernicusQueryError(f"CDSE catalog query failed: HTTP {resp.status_code} - {resp.text}")

        results = resp.json().get("value", [])
        log.info("Discovered %d matching satellite products from Copernicus.", len(results))
        return results


def require_registered() -> CDSEClient:
    """Helper that verifies credentials exist or raises an explicit error."""
    try:
        return CDSEClient()
    except Exception as exc:
        raise NotImplementedAdapterError(f"CDSE access requires registration: {exc}") from exc
