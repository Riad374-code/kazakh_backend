"""Minimal OSM Overpass adapter with explicit attribution and caching hooks."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

import requests

from marine_dataset.context import normalize_context

OVERPASS_URL = "https://overpass-api.de/api/interpreter"


@dataclass(frozen=True)
class OverpassResult:
    records: tuple[dict[str, Any], ...]
    query: str
    source_url: str
    complete: bool


def build_query(bbox: tuple[float, float, float, float], keys: tuple[str, ...]) -> str:
    if len(bbox) != 4 or bbox[1] >= bbox[3] or bbox[0] >= bbox[2]:
        raise ValueError("bbox must be (min_lon,min_lat,max_lon,max_lat)")
    if not keys or any(not key.strip() or '"' in key or "\\" in key for key in keys):
        raise ValueError("at least one non-empty OSM key is required")
    south, west, north, east = bbox[1], bbox[0], bbox[3], bbox[2]
    clauses = "".join(f'nwr["{key}"]({south},{west},{north},{east});' for key in keys)
    return f"[out:json][timeout:60];({clauses});out geom;"


def fetch(
    bbox: tuple[float, float, float, float],
    keys: tuple[str, ...] = ("amenity", "man_made", "power", "industrial"),
    *,
    session: Any | None = None,
    request: Callable[..., Any] | None = None,
) -> OverpassResult:
    query = build_query(bbox, keys)
    sender = request or (session or requests).post
    response = sender(OVERPASS_URL, data={"data": query}, timeout=60)
    response.raise_for_status()
    payload = response.json()
    records = tuple(
        normalize_context(item, source_name="osm_overpass") for item in payload.get("elements", [])
    )
    return OverpassResult(records=records, query=query, source_url=OVERPASS_URL, complete=True)


def cache_payload(result: OverpassResult) -> bytes:
    """Canonical bytes for an immutable cache artifact."""
    return (
        json.dumps({"query": result.query, "records": result.records}, sort_keys=True, default=str)
        + "\n"
    ).encode()
