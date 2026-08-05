"""Reproducibility artifacts for Step 23."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def build_dataset_card(
    output_dir: Path,
    *,
    dataset_version: str,
    sources: list[dict[str, Any]] | None = None,
    reproduction_command: str = "marine-data run-all",
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    card = output_dir / "dataset_card.md"
    issues = output_dir / "known_issues.md"
    source_lines = (
        "\n".join(
            f"- {item.get('source_name', 'unknown')}: {item.get('licence', 'unresolved')}"
            for item in (sources or [])
        )
        or "- No source records supplied."
    )
    card.write_text(
        f"# Marine Pollution Dataset Card\n\n- Version: `{dataset_version}`\n- Reproduction: `{reproduction_command}`\n\n## Purpose\nMultimodal research dataset for marine-pollution decision support.\n\n## Sources and licences\n{source_lines}\n\n## Limits\nSAR dark regions can be low wind, natural films, biological activity, rain cells, currents, fronts, or other look-alikes; they are not automatically oil. Predictions and scenario estimates require validation.\n\n## Recommended use\nResearch, quality-controlled monitoring, and human-reviewed decision support.\n\n## Prohibited use\nDo not treat weak labels, model outputs, or missing infrastructure records as verified facts.\n",
        encoding="utf-8",
    )
    issues.write_text(
        "# Known issues\n\n- External credentials, provider coverage, and authoritative coefficients must be supplied locally.\n- Registration/manual approval is not simulated.\n",
        encoding="utf-8",
    )
    return card, issues
