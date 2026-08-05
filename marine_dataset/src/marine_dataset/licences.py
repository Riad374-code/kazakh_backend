"""Build-time licence policy, gate, and report generation (Step 03 / section 7).

Separates source-data licences from software licences. Provides:
- a ``LicencePolicy`` governing how gates react to incompatible/unresolved sources,
- a ``RedistributionGate`` that blocks (or quarantines) unsupported sources,
- a deterministic ``licence_report.md`` generator.

All facts come from the registry; nothing here guesses licence terms.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from marine_dataset.logging_config import get_logger
from marine_dataset.provenance import (
    LicenceStatus,
    SourceEntry,
    SourceRegistry,
    registry_report_data,
)
from marine_dataset.storage import Storage

log = get_logger("licences")


class GateAction(str, Enum):
    allow = "allow"
    quarantine = "quarantine"
    fail = "fail"


class LicencePolicy:
    """Build-time policy for the redistribution gate."""

    def __init__(
        self,
        *,
        on_incompatible: str = "warn",
        on_unresolved: str = "warn",
    ) -> None:
        if on_incompatible not in ("warn", "fail"):
            raise ValueError("on_incompatible must be 'warn' or 'fail'")
        if on_unresolved not in ("allow", "warn", "fail"):
            raise ValueError("on_unresolved must be 'allow', 'warn' or 'fail'")
        self.on_incompatible = on_incompatible
        self.on_unresolved = on_unresolved

    def action_for(self, entry: SourceEntry) -> GateAction:
        """Decide the gate action for a source entry."""
        if entry.licence_status == LicenceStatus.incompatible:
            return GateAction.quarantine
        if entry.licence_status == LicenceStatus.unresolved:
            if self.on_unresolved == "fail":
                return GateAction.fail
            if self.on_unresolved == "warn":
                return GateAction.quarantine
            return GateAction.allow
        if not entry.redistribution:
            return GateAction.quarantine
        return GateAction.allow


def gate_warning_or_fail(
    entry: SourceEntry, policy: LicencePolicy
) -> Optional[GateAction]:
    """Return the action to take, escalating to fail where the policy demands."""
    action = policy.action_for(entry)
    if action == GateAction.fail:
        log.error(
            "licence gate FAIL for %s (%s): incompatible/unresolved and policy is fail.",
            entry.source_key,
            entry.licence_status.value if entry.licence_status else "unknown",
        )
        return GateAction.fail
    if action == GateAction.quarantine:
        reason = (
            "incompatible" if entry.licence_status == LicenceStatus.incompatible
            else "unresolved"
        )
        log.warning("licence gate quarantining %s (%s)", entry.source_key, reason)
        return GateAction.quarantine
    return None


def run_redistribution_gate(
    registry: SourceRegistry,
    policy: LicencePolicy,
    *,
    fail_on_incompatible: bool = False,
    quarantine_manager: Optional[Storage] = None,
    on_quarantine: Optional[Callable[[SourceEntry, str], None]] = None,
) -> list[SourceEntry]:
    """Evaluate every source; quarantine/fail unsupported ones.

    Returns the list of blocked sources. If ``fail_on_incompatible`` is True (or
    the policy's per-source setting is 'fail'), a ``LicenceGateFailure`` is
    raised instead of returning.
    """
    blocked: list[SourceEntry] = []
    for entry in registry.sources:
        action = gate_warning_or_fail(entry, policy)
        if action is None:
            continue
        if action == GateAction.fail or (fail_on_incompatible and not entry.redistribution):
            raise LicenceGateFailure(
                f"source {entry.source_key} is not redistributable "
                f"(status={entry.licence_status.value if entry.licence_status else '?'})"
            )
        if action == GateAction.quarantine:
            reason = (
                "incompatible"
                if entry.licence_status == LicenceStatus.incompatible
                else "unresolved"
            )
            if quarantine_manager is not None:
                quarantine_manager.quarantine_dir()
            if on_quarantine is not None:
                on_quarantine(entry, reason)
            blocked.append(entry)
    return blocked


class LicenceGateFailure(RuntimeError):
    """Raised when the build-time licence policy fails a source."""


# ---------------------------------------------------------------------------
# Markdown report generator
# ---------------------------------------------------------------------------


def _yesno(value: bool) -> str:
    return "yes" if value else "no"


def render_licence_report(registry: SourceRegistry, repo_root: Path | str) -> str:
    """Render a human-readable licence_report.md from registry facts."""
    data = registry_report_data(registry)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    lines: list[str] = []
    lines.append("# Licence Report")
    lines.append("")
    lines.append(
        f"Generated: {now}  ·  registry version: {data['version']}  ·  "
        f"updated_at: {data['updated_at'] or 'n/a'}"
    )
    lines.append("")
    lines.append(
        "Source-data licences are kept separate from software licences. "
        "This report is generated from `metadata/source_registry.yaml`; "
        "entries are not fabricated and unresolved facts remain unresolved."
    )
    lines.append("")
    lines.append(
        f"**Summary:** {data['total_sources']} sources; {data['resolved']} resolved, "
        f"{data['unresolved']} unresolved, {data['incompatible']} incompatible, "
        f"{data['not_redistributable']} not redistributable."
    )
    lines.append("")

    lines.append("## Per-source status")
    lines.append("")
    lines.append("| source_key | licence | status | commercial | redistribute | modify | share_alike | account | api_key | rate_limits | terms_checked_at |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in data["sources"]:
        rows = [
            s["source_key"],
            s["licence_name"] or "unverified",
            s["licence_status"] or "?",
            _yesno(s["commercial"]),
            _yesno(s["redistribution"]),
            _yesno(s["modification"]),
            _yesno(bool(s["share_alike"])),
            _yesno(s["account_required"]),
            _yesno(s["api_key_required"]),
            s["rate_limits"] or "-",
            s["terms_checked_at"] or "NOT CHECKED",
        ]
        lines.append("| " + " | ".join(rows) + " |")
    lines.append("")

    lines.append("## Attribution & citation")
    lines.append("")
    for entry in registry.sources:
        if entry.attribution_text:
            lines.append(f"- **{entry.source_key}**: {entry.attribution_text}")
    lines.append("")

    lines.append("## References")
    lines.append("")
    lines.append(
        f"- Registry: `{Path(repo_root) / 'metadata' / 'source_registry.yaml'}` "
        "(programmatic source of truth)."
    )
    lines.append("")
    return "\n".join(lines) + "\n"


def write_licence_report(
    registry: SourceRegistry,
    output_dir: Path | str,
    repo_root: Path | str,
    *,
    storage: Optional[Storage] = None,
) -> Path:
    """Write licence_report.md (and a machine-readable .json) to ``output_dir``."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    md_path = output_dir / "licence_report.md"
    text = render_licence_report(registry, repo_root)
    if storage is not None:
        storage.write_text(md_path, text)
    else:
        md_path.write_text(text, encoding="utf-8")

    json_path = output_dir / "licence_report.json"
    json_data = registry_report_data(registry)
    import json as _json

    if storage is not None:
        storage.write_text(json_path, _json.dumps(json_data, indent=2))
    else:
        json_path.write_text(_json.dumps(json_data, indent=2), encoding="utf-8")
    return md_path


def source_attribution_lines(registry: SourceRegistry) -> list[str]:
    """Attribution strings that must survive manifest export (Step 03 gate)."""
    return [entry.attribution_text for entry in registry.sources if entry.attribution_text]