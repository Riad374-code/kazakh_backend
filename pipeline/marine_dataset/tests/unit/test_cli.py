"""Step 01 CLI tests: --help and init-config (no network, dry-run)."""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from marine_dataset.cli import app

runner = CliRunner()

_SHIPPED = Path("configs/default.yaml").resolve()


def _copy_shipped_config(tmp_path) -> Path:
    target = tmp_path / "config.yaml"
    target.write_text(_SHIPPED.read_text(encoding="utf-8"), encoding="utf-8")
    return target


def test_help_exit_zero():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init-config" in result.output
    assert "search-sentinel1" in result.output
    assert "run-all" in result.output


def test_init_config_dry_run(tmp_path):
    cfg = _copy_shipped_config(tmp_path)
    result = runner.invoke(
        app,
        [
            "init-config",
            "--config",
            str(cfg),
            "--dry-run",
            "--base-dir",
            str(tmp_path / "data"),
        ],
    )
    assert result.exit_code == 0
    assert "validated" in result.output


def test_init_config_creates_tree(tmp_path):
    cfg = _copy_shipped_config(tmp_path)
    result = runner.invoke(
        app,
        [
            "init-config",
            "--config",
            str(cfg),
            "--base-dir",
            str(tmp_path / "data"),
        ],
    )
    assert result.exit_code == 0
    assert (tmp_path / "data" / "raw" / "sentinel1").is_dir()
    assert (tmp_path / "data" / "processed" / "tiles").is_dir()
    assert (tmp_path / "data" / "manifests").is_dir()
    # source config must not be modified
    assert "base" in cfg.read_text(encoding="utf-8")


def test_init_config_writes_validated_copy(tmp_path):
    cfg = _copy_shipped_config(tmp_path)
    out = tmp_path / "validated" / "user.yaml"
    result = runner.invoke(
        app,
        [
            "init-config",
            "--config",
            str(cfg),
            "--output-config",
            str(out),
            "--base-dir",
            str(tmp_path / "data"),
        ],
    )
    assert result.exit_code == 0
    assert out.is_file()
    assert "dataset_version" in out.read_text(encoding="utf-8")


def test_init_config_refuses_to_overwrite_source(tmp_path):
    cfg = _copy_shipped_config(tmp_path)
    result = runner.invoke(
        app,
        [
            "init-config",
            "--config",
            str(cfg),
            "--output-config",
            str(cfg),
            "--base-dir",
            str(tmp_path / "data"),
        ],
    )
    assert result.exit_code != 0


def test_placeholder_command_fails_clearly(tmp_path):
    cfg = _copy_shipped_config(tmp_path)
    result = runner.invoke(app, ["search-sentinel1", "--config", str(cfg)])
    assert result.exit_code == 2
    stderr = result.stderr
    as_bytes = stderr if isinstance(stderr, bytes) else (stderr or "").encode()
    assert "not implemented" in as_bytes.decode().lower()


def test_placeholder_never_reports_success(tmp_path):
    cfg = _copy_shipped_config(tmp_path)
    for cmd in ["tile", "preprocess", "align", "split", "validate"]:
        result = runner.invoke(app, [cmd, "--config", str(cfg)])
        assert result.exit_code == 2, f"{cmd} must fail clearly"


def test_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0