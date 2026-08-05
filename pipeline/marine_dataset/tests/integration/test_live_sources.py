"""Explicitly opt-in, user-bounded provider smoke tests."""

from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from marine_dataset.sources.copernicus_dataspace import CDSEClient
from marine_dataset.sources.open_meteo import OpenMeteoClient, WeatherRequest

pytestmark = [pytest.mark.integration, pytest.mark.live]


def test_user_selected_small_cdse_product(tmp_path):
    product_id = os.getenv("CDSE_LIVE_PRODUCT_ID")
    if not product_id:
        pytest.skip("set CDSE_LIVE_PRODUCT_ID to an explicitly selected small OData product")
    maximum_bytes = int(os.getenv("CDSE_LIVE_MAX_BYTES", str(50 * 1024 * 1024)))
    result = CDSEClient(max_download_bytes=maximum_bytes).download_product(
        product_id, tmp_path / "raw" / "sentinel1" / "live-product.zip"
    )
    assert result.path.is_file()
    assert result.path.stat().st_size <= maximum_bytes


def test_one_day_open_meteo_archive_response():
    if os.getenv("OPEN_METEO_LIVE_TEST") != "1":
        pytest.skip("set OPEN_METEO_LIVE_TEST=1 to run the bounded archive smoke test")
    request = WeatherRequest(44.0, 51.0, "2024-01-01", "2024-01-01", ("rain",), "era5")
    result = OpenMeteoClient(requests_per_minute=10_000).collect(request)
    assert result.model == "era5"
    assert result.retrieved_at <= datetime.now(timezone.utc)
