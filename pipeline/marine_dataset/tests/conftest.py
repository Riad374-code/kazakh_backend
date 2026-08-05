"""Shared fixtures/tiny data for offline unit tests."""

from __future__ import annotations

import pytest
import yaml


@pytest.fixture
def minimal_config_yaml(tmp_path):
    return {
        "dataset_version": "0.1.0",
        "seed": 42,
        "regions": [
            {
                "name": "test_region",
                "min_lon": 50.0,
                "min_lat": 43.0,
                "max_lon": 54.0,
                "max_lat": 46.0,
                "country": [],
            }
        ],
        "date_start": "2024-01-01",
        "date_end": "2024-01-02",
    }


@pytest.fixture
def config_file(tmp_path, minimal_config_yaml):
    p = tmp_path / "config.yaml"
    p.write_text(yaml.safe_dump(minimal_config_yaml, sort_keys=False), encoding="utf-8")
    return p


@pytest.fixture
def registry_fixture(tmp_path):
    """A small hand-written registry (no invented licence facts for build gate)."""
    data = {
        "version": "1.0",
        "sources": [
            {
                "source_key": "good_source",
                "source_name": "Good",
                "provider": "A",
                "access_method": "api",
                "licence_name": "CC BY 4.0",
                "attribution_text": "(c) Good Contributors",
                "commercial_use": True,
                "redistribution": True,
                "modification": True,
                "share_alike": True,
                "licence_status": "resolved",
                "account_required": False,
                "api_key_required": False,
                "terms_checked_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "source_key": "unresolved_source",
                "source_name": "Unresolved",
                "provider": "B",
                "access_method": "download",
                "licence_status": "unresolved",
                "account_required": False,
                "api_key_required": False,
            },
            {
                "source_key": "incompatible_source",
                "source_name": "Incompatible",
                "provider": "C",
                "access_method": "download",
                "licence_name": "All rights reserved",
                "commercial_use": False,
                "redistribution": False,
                "modification": False,
                "licence_status": "incompatible",
                "account_required": False,
                "api_key_required": False,
            },
        ],
    }
    p = tmp_path / "registry.yaml"
    p.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return p
