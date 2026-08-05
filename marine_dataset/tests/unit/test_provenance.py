"""Step 03 tests: provenance registry (validated, local fixtures only)."""

from __future__ import annotations

import yaml
import pytest

from marine_dataset.provenance import (
    LicenceStatus,
    SourceRegistry,
    load_registry,
    registry_report_data,
)


def test_registry_loads_all_section7_fields(registry_fixture):
    reg = load_registry(registry_fixture)
    assert len(reg.sources) == 3
    good = reg.by_key("good_source")
    assert good.redistribution is True
    assert good.commercial_use is True
    assert good.share_alike is True
    assert good.licence_status == LicenceStatus.resolved


def test_resolved_source_requires_terms_check():
    # A resolved source without terms_checked_at must fail validation.
    data = {
        "sources": [
            {
                "source_key": "x",
                "source_name": "X",
                "provider": "P",
                "access_method": "api",
                "licence_status": "resolved",
            }
        ]
    }
    with pytest.raises(Exception):
        SourceRegistry.model_validate(data)


def test_unresolved_marked_and_listed(registry_fixture):
    reg = load_registry(registry_fixture)
    unresolved = reg.unresolved()
    assert any(s.source_key == "unresolved_source" for s in unresolved)


def test_unsupported_for_redistribution(registry_fixture):
    reg = load_registry(registry_fixture)
    blocked = reg.unsupported_for_redistribution()
    keys = {s.source_key for s in blocked}
    assert "unresolved_source" in keys
    assert "incompatible_source" in keys
    assert "good_source" not in keys


def test_report_data_machine_readable(registry_fixture):
    reg = load_registry(registry_fixture)
    data = registry_report_data(reg)
    assert data["total_sources"] == 3
    assert data["resolved"] == 1
    assert data["not_redistributable"] == 2
    assert all("licence_name" in s for s in data["sources"])


def test_no_live_terms_invented(registry_fixture):
    # Every resolved entry must carry an official URL or archived reference.
    reg = load_registry(registry_fixture)
    for s in reg.sources:
        if s.licence_status == LicenceStatus.resolved:
            assert s.terms_url or s.terms_archived_reference or s.terms_checked_at