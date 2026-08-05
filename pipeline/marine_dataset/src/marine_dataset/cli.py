"""Command-line interface for the marine-dataset pipeline.

Registers every command from pipeline_inst.md section 13. Commands that are not
yet implemented fail clearly (non-zero exit) and never report success.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer

from marine_dataset.config import Config, default_config, dump_config, load_config
from marine_dataset.logging_config import get_logger, setup_logging

app = typer.Typer(
    name="marine-data",
    help="Build a reproducible marine pollution / oil-spill detection dataset.",
    no_args_is_help=True,
)

log = get_logger("cli")

# Commands that exist but are not yet implemented. They must fail clearly.
_PLACEHOLDER_COMMANDS = [
    "search-sentinel1",
    "download-sentinel1",
    "search-sentinel3",
    "download-sentinel3",
    "collect-weather",
    "collect-ocean",
    "collect-vessels",
    "collect-infrastructure",
    "import-labels",
    "preprocess",
    "align",
    "tile",
    "split",
    "validate",
    "build-manifest",
    "build-dataset-card",
    "run-all",
]


def _load_config_or_default(config_path: Optional[Path]) -> Config:
    if config_path is not None:
        return load_config(config_path)
    return default_config()


def _not_implemented(command: str) -> None:
    message = (
        f"ERROR: command '{command}' is registered but not implemented "
        "in this build step. It will never report success. Implement it "
        "before use."
    )
    log.error(message)
    typer.secho(message, err=True)
    raise typer.Exit(code=2)


@app.command()
def init_config(
    config_path: Path = typer.Option(
        Path("configs/default.yaml"),
        "--config",
        help="Path to the configuration file to validate.",
    ),
    output_config: Optional[Path] = typer.Option(
        None,
        "--output-config",
        help="Where to write a copy of the validated config "
        "(default: only dry-run prints, files are never overwritten).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and print configuration without writing files.",
    ),
    base_dir: Path = typer.Option(
        Path("data"),
        "--base-dir",
        help="Base directory for data storage paths.",
    ),
    create_dirs: bool = typer.Option(
        True,
        "--create-dirs/--no-create-dirs",
        help="Create the section-14 storage tree.",
    ),
) -> None:
    """Validate configuration and initialise the storage tree."""
    config = _load_config_or_default(config_path)
    resolved = config.paths.resolve_all(base_dir)

    if dry_run:
        print(dump_config(config))
        print(
            f"\n[init-config --dry-run] validated {config_path}; "
            f"would create dirs under {resolved.base}."
        )
        return

    if output_config is not None:
        if output_config.exists() and output_config.resolve() == config_path.resolve():
            raise typer.BadParameter(
                "--output-config must differ from --config; refusing to "
                "overwrite the source configuration."
            )
        output_config.parent.mkdir(parents=True, exist_ok=True)
        output_config.write_text(dump_config(config), encoding="utf-8")
        log.info("wrote validated config to %s", output_config)

    if create_dirs:
        for path in (
            resolved.raw,
            resolved.interim,
            resolved.processed,
            resolved.manifests,
            resolved.reports,
            resolved.cache,
            resolved.quarantine,
        ):
            path.mkdir(parents=True, exist_ok=True)
        # Ensure raw sub-tree exists (section 14).
        for sub in ("sentinel1", "sentinel3", "weather", "ocean", "vessels",
                    "infrastructure", "labels"):
            (resolved.raw / sub).mkdir(parents=True, exist_ok=True)
        for sub in ("scenes", "tiles", "masks", "environmental_grids"):
            (resolved.processed / sub).mkdir(parents=True, exist_ok=True)
        log.info("created storage tree under %s", resolved.base)


def _register_placeholder(name: str) -> None:
    def command(
        config: Path = typer.Option(
            Path("configs/default.yaml"),
            "--config",
            help="Path to the configuration file.",
        ),
        dry_run: bool = typer.Option(
            False, "--dry-run", help="Dry run (still requires implementation)."
        ),
        region: Optional[list[str]] = typer.Option(
            None, "--region", help="Region name filter (repeatable)."
        ),
    ) -> None:
        _ = (config, dry_run, region)
        _not_implemented(name)

    command.__name__ = name.replace("-", "_")
    command.__doc__ = f"(NOT IMPLEMENTED) pipeline_inst.md section 13: {name}."
    app.command(name=name)(command)


for _cmd in _PLACEHOLDER_COMMANDS:
    _register_placeholder(_cmd)


@app.command("version")
def version() -> None:
    """Print the package version."""
    from marine_dataset import __version__

    print(f"marine-data {__version__}")


if __name__ == "__main__":
    setup_logging("INFO")
    app()
