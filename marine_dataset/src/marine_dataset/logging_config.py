"""Structured logging setup (pipeline_inst.md section 16).

Logs must never contain secrets. Secrets come from environment variables only.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_LOGGER_NAME = "marine_dataset"
_CONFIGURED = False


def setup_logging(level: str = "INFO", log_dir: Path | None = None) -> logging.Logger:
    """Configure the package logger once and return it.

    Args:
        level: One of DEBUG, INFO, WARNING, ERROR, CRITICAL.
        log_dir: Optional directory for a rotating file log. Created if absent.
    """
    global _CONFIGURED
    logger = logging.getLogger(_LOGGER_NAME)
    if _CONFIGURED:
        return logger

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s"
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    logger.addHandler(console)

    if log_dir is not None:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        try:
            file_handler = logging.FileHandler(
                log_dir / "marine_dataset.log", encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            logger.addHandler(file_handler)
        except OSError as exc:  # pragma: no cover - environment dependent
            logger.warning("could not attach file log handler: %s", exc)

    _CONFIGURED = True
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child logger of the package logger."""
    if name:
        return logging.getLogger(f"{_LOGGER_NAME}.{name}")
    return logging.getLogger(_LOGGER_NAME)
