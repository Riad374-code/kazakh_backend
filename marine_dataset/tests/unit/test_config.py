"""Step 01 tests: configuration and CLI skeleton (offline, deterministic)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from marine_dataset.config import (
    Config,
    RegionConfig,
    dump_config,
    load_config,
)
from marine_dataset.logging_config import setup_logging


def test_valid_config_loads(config_file):
    cfg = load_config(config_file)
    assert isinstance(cfg, Config)
    assert cfg.seed == 42
    assert cfg.regions[0].name == "test_region"
    assert cfg.date_start.isoformat() == "2024-01-01"
    assert cfg.split_strategy == "group_by_scene"


def test_bad_date_range_rejected(tmp_path):
    from marine_dataset.config import load_config

    cfg_data = {
        "regions": [{"name": "r", "min_lon": 0, "min_lat": 0, "max_lon": 1, "max_lat": 1}],
        "date_start": "2024-01-10",
        "date_end": "2024-01-01",
    }
    p = tmp_path / "bad.yaml"
    p.write_text(__import__("yaml").safe_dump(cfg_data), encoding="utf-8")
    with pytest.raises(Exception):
        load_config(p)


def test_bad_crs_region_rejected():
    with pytest.raises(Exception):
        RegionConfig(
            name="bad",
            min_lon=10.0,
            min_lat=5.0,
            max_lon=5.0,
            max_lat=10.0,
        )


def test_bad_rate_rejected():
    from marine_dataset.config import RateLimit

    with pytest.raises(Exception):
        RateLimit(requests_per_minute=0)
    with pytest.raises(Exception):
        RateLimit(max_concurrent_requests=0)


def test_bad_threshold_rejected():
    from marine_dataset.config import QualityThresholds

    with pytest.raises(Exception):
        QualityThresholds(min_coverage_fraction=1.5)
    with pytest.raises(Exception):
        QualityThresholds(max_warnings=-1)


def test_env_override(monkeypatch, config_file):
    monkeypatch.setenv("MARINE_DATA_SEED", "7")
    cfg = load_config(config_file, env=True)
    assert cfg.seed == 7
    # no env -> default stays
    monkeypatch.delenv("MARINE_DATA_SEED")
    cfg2 = load_config(config_file, env=True)
    assert cfg2.seed == 42


def test_yaml_roundtrip(config_file):
    cfg = load_config(config_file)
    text = dump_config(cfg)
    reparsed = __import__("yaml").safe_load(text)
    assert reparsed["seed"] == 42
    assert reparsed["regions"][0]["name"] == "test_region"


def test_default_config_no_credentials(tmp_path):
    # The shipped default must load and must not contain any secrets.
    cfg = load_config(Path("configs/default.yaml"))
    resolved = cfg.paths.resolve_all()
    assert resolved.raw == (Path("data") / "raw")
    text = dump_config(cfg)
    for secret_word in ("password", "token", "api_key"):
        assert secret_word.lower() not in text.lower()


def test_logging_setup(tmp_path):
    logger = setup_logging("WARNING", tmp_path / "logs")
    assert logger.name == "marine_dataset"
    assert (tmp_path / "logs").is_dir()