"""Step 03 tests: licence gate, policy, and licence_report generator."""

from __future__ import annotations

import pytest

from marine_dataset.licences import (
    GateAction,
    LicenceGateFailure,
    LicencePolicy,
    render_licence_report,
    run_redistribution_gate,
    source_attribution_lines,
    write_licence_report,
)
from marine_dataset.provenance import load_registry


def test_policy_allow_resolved(registry_fixture):
    reg = load_registry(registry_fixture)
    policy = LicencePolicy(on_unresolved="warn")
    good = reg.by_key("good_source")
    assert policy.action_for(good) == GateAction.allow


def test_policy_quarantine_unresolved_and_incompatible(registry_fixture):
    reg = load_registry(registry_fixture)
    policy = LicencePolicy(on_unresolved="warn")
    assert policy.action_for(reg.by_key("unresolved_source")) == GateAction.quarantine
    assert policy.action_for(reg.by_key("incompatible_source")) == GateAction.quarantine


def test_policy_fail_unresolved(registry_fixture):
    reg = load_registry(registry_fixture)
    policy = LicencePolicy(on_unresolved="fail")
    assert policy.action_for(reg.by_key("unresolved_source")) == GateAction.fail


def test_run_gate_returns_blocked(registry_fixture):
    reg = load_registry(registry_fixture)
    policy = LicencePolicy(on_unresolved="warn")
    blocked = run_redistribution_gate(reg, policy)
    keys = {s.source_key for s in blocked}
    assert "unresolved_source" in keys
    assert "incompatible_source" in keys


def test_run_gate_fails_when_policy_says_fail(registry_fixture):
    reg = load_registry(registry_fixture)
    policy = LicencePolicy(on_unresolved="fail")
    with pytest.raises(LicenceGateFailure):
        run_redistribution_gate(reg, policy)


def test_quarantine_hook_invoked(registry_fixture, tmp_path):
    from marine_dataset.storage import Storage

    reg = load_registry(registry_fixture)
    policy = LicencePolicy(on_unresolved="warn")
    storage = Storage(tmp_path / "data")
    hits = []
    run_redistribution_gate(
        reg,
        policy,
        quarantine_manager=storage,
        on_quarantine=lambda e, r: hits.append(e.source_key),
    )
    assert "unresolved_source" in hits


def test_attribution_survives_manifest_export(registry_fixture):
    reg = load_registry(registry_fixture)
    lines = source_attribution_lines(reg)
    assert any("Good Contributors" in line for line in lines)


def test_report_generation(tmp_path, registry_fixture):
    reg = load_registry(registry_fixture)
    out = write_licence_report(reg, tmp_path, repo_root=tmp_path)
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "# Licence Report" in text
    assert "good_source" in text
    assert "unresolved_source" in text
    assert "NOT CHECKED" in text
    # machine-readable report also present
    assert (tmp_path / "licence_report.json").is_file()


def test_render_report_has_required_sections(registry_fixture):
    reg = load_registry(registry_fixture)
    text = render_licence_report(reg, ".")
    for section in ("Per-source status", "Attribution & citation", "References"):
        assert section in text
