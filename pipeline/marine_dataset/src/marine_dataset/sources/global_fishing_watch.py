"""Authorised-only GFW boundary; no scraping or invented data."""

from __future__ import annotations

import os
from typing import Any


class UnavailableSource(RuntimeError):
    pass


def require_authorisation(env_name: str = "GFW_TOKEN") -> str:
    token = os.getenv(env_name, "").strip()
    if not token:
        raise UnavailableSource(
            "Global Fishing Watch access is unavailable: configure an authorised token"
        )
    return token


def unavailable_record(reason: str) -> dict[str, Any]:
    return {"source_name": "global_fishing_watch", "status": "unavailable", "reason": reason}
