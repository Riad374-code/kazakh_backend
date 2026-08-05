"""Shared Copernicus Data Space STAC discovery and OData download client."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urljoin, urlparse

import requests

from marine_dataset.storage import RawImmutableError

STAC_SEARCH_URL = "https://stac.dataspace.copernicus.eu/v1/search"
TOKEN_URL = (
    "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
)
ODATA_DOWNLOAD = "https://download.dataspace.copernicus.eu/odata/v1/Products({product_id})/$value"
TRANSIENT_STATUS = {429, 500, 502, 503, 504}
TRUSTED_STAC_HOST = "stac.dataspace.copernicus.eu"
CONTENT_RANGE_PATTERN = re.compile(r"^bytes (\d+)-(\d+)/(\d+|\*)$")
DOWNLOAD_CHUNK_SIZE = 1024 * 1024
DEFAULT_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024 * 1024


class SourceRequestError(RuntimeError):
    """Provider request failed without leaking credentials."""


@dataclass(frozen=True)
class RawWriteResult:
    path: Path
    sha256: str
    created: bool


def _staging_directory(path: Path) -> Path:
    if len(path.parents) >= 3 and path.parents[1].name.lower() == "raw":
        return path.parents[2] / "interim" / path.parent.name
    return path.parent / ".staging"


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(DOWNLOAD_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _finalize_staged_file(path: Path, staged: Path, digest: str) -> RawWriteResult:
    """Atomically publish by exclusive hard-link; raw targets are never replaced."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(staged, path)
        created = True
    except FileExistsError:
        created = False
    actual = _hash_file(path)
    if actual != digest:
        if created:
            path.unlink(missing_ok=True)
        raise RawImmutableError(f"refusing conflicting immutable raw artifact: {path}")
    staged.unlink(missing_ok=True)
    return RawWriteResult(path, actual, created)


def publish_staged_file(
    path: Path, staged: Path, expected_sha256: str | None = None
) -> RawWriteResult:
    """Publish an already downloaded file without buffering it in memory."""
    digest = _hash_file(staged)
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        raise SourceRequestError("download checksum mismatch")
    return _finalize_staged_file(path, staged, digest)


def write_raw_once(path: Path, data: bytes, expected_sha256: str | None = None) -> RawWriteResult:
    """Create a raw artifact exactly once using unique staging outside ``raw``."""
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        raise SourceRequestError("download checksum mismatch")
    if path.exists():
        existing = _hash_file(path)
        if existing != digest:
            raise RawImmutableError(f"refusing to replace immutable raw artifact: {path}")
        return RawWriteResult(path, digest, False)
    staging = _staging_directory(path)
    staging.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{path.name}.", suffix=".part", dir=staging, delete=False
    )
    staged = Path(handle.name)
    try:
        with handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        return _finalize_staged_file(path, staged, digest)
    finally:
        staged.unlink(missing_ok=True)


class CDSEClient:
    """Small injectable client using the current official STAC and OData APIs."""

    def __init__(
        self,
        session: Any | None = None,
        *,
        timeout: float = 30.0,
        max_attempts: int = 3,
        max_download_bytes: int = DEFAULT_MAX_DOWNLOAD_BYTES,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.session = session or requests.Session()
        self.timeout = timeout
        self.max_attempts = max_attempts
        if max_download_bytes <= 0:
            raise ValueError("max_download_bytes must be positive")
        self.max_download_bytes = max_download_bytes
        self.sleeper = sleeper
        self._access_token: str | None = None

    def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        allowed_statuses = set(kwargs.pop("allowed_statuses", ()))
        kwargs.setdefault("timeout", self.timeout)
        for attempt in range(self.max_attempts):
            try:
                response = self.session.request(method, url, **kwargs)
            except requests.RequestException:
                if attempt + 1 == self.max_attempts:
                    raise SourceRequestError("Copernicus request failed") from None
                self.sleeper(2**attempt)
                continue
            if response.status_code in allowed_statuses or response.status_code < 400:
                return response
            if response.status_code not in TRANSIENT_STATUS:
                raise SourceRequestError(
                    f"Copernicus request failed with HTTP {response.status_code}"
                )
            if attempt + 1 == self.max_attempts:
                raise SourceRequestError(
                    f"Copernicus request failed with HTTP {response.status_code}"
                )
            self.sleeper(2**attempt)
        raise SourceRequestError("Copernicus request exhausted retries")

    def search(
        self,
        body: Mapping[str, Any],
        *,
        max_items: int | None = None,
        on_page: Callable[[int, Mapping[str, Any]], None] | None = None,
    ) -> list[dict[str, Any]]:
        """POST a STAC search and follow provider-supplied ``rel=next`` links."""
        response = self._request("POST", STAC_SEARCH_URL, json=dict(body))
        items: dict[str, dict[str, Any]] = {}
        visited_pages = {STAC_SEARCH_URL}
        page_number = 0
        while True:
            payload = response.json()
            page_number += 1
            if on_page:
                on_page(page_number, payload)
            for item in payload.get("features", []):
                item_id = str(item.get("id", ""))
                if item_id:
                    items.setdefault(item_id, item)
                    if max_items and len(items) >= max_items:
                        return list(items.values())
            next_link = next(
                (
                    link.get("href")
                    for link in payload.get("links", [])
                    if link.get("rel") == "next"
                ),
                None,
            )
            if not next_link:
                return list(items.values())
            next_url = urljoin(STAC_SEARCH_URL, str(next_link))
            parsed = urlparse(next_url)
            if parsed.scheme != "https" or parsed.hostname != TRUSTED_STAC_HOST:
                raise SourceRequestError("untrusted STAC pagination link")
            if next_url in visited_pages:
                raise SourceRequestError("repeated STAC pagination link")
            visited_pages.add(next_url)
            response = self._request("GET", next_url)

    def collection_ids(self) -> set[str]:
        response = self._request("GET", "https://stac.dataspace.copernicus.eu/v1/collections")
        return {
            str(collection["id"])
            for collection in response.json().get("collections", [])
            if collection.get("id")
        }

    def access_token(self, *, refresh: bool = False) -> str:
        if self._access_token and not refresh:
            return self._access_token
        username = os.getenv("CDSE_USERNAME")
        password = os.getenv("CDSE_PASSWORD")
        if not username or not password:
            raise SourceRequestError("CDSE credentials are required for product download")
        data = {
            "client_id": "cdse-public",
            "grant_type": "password",
            "username": username,
            "password": password,
        }
        totp = os.getenv("CDSE_TOTP")
        if totp:
            data["totp"] = totp
        response = self._request("POST", TOKEN_URL, data=data)
        token = response.json().get("access_token")
        if not token:
            raise SourceRequestError("CDSE authentication returned no access token")
        self._access_token = str(token)
        return self._access_token

    def download_product(
        self,
        product_id: str,
        destination: Path,
        *,
        expected_sha256: str | None = None,
    ) -> RawWriteResult:
        _validate_product_id(product_id)
        existing = _existing_download(destination, expected_sha256)
        if existing:
            return existing
        staging = _staging_directory(destination)
        staging.mkdir(parents=True, exist_ok=True)
        partial = staging / f"{destination.name}.download.part"
        lock = _claim_download(staging, destination.name)
        try:
            response, mode, offset = self._download_response(product_id, partial)
            self._stream_response(response, partial, mode, offset)
            digest = _hash_file(partial)
            if expected_sha256 and digest.lower() != expected_sha256.lower():
                raise SourceRequestError("download checksum mismatch")
            return _finalize_staged_file(destination, partial, digest)
        finally:
            lock.unlink(missing_ok=True)

    def _download_response(self, product_id: str, partial: Path) -> tuple[Any, str, int]:
        offset = partial.stat().st_size if partial.exists() else 0
        headers = {"Authorization": f"Bearer {self.access_token()}"}
        if offset:
            headers["Range"] = f"bytes={offset}-"
        url = ODATA_DOWNLOAD.format(product_id=product_id)
        response = self._request("GET", url, headers=headers, stream=True, allowed_statuses={401})
        if response.status_code == 401:
            headers["Authorization"] = f"Bearer {self.access_token(refresh=True)}"
            response = self._request("GET", url, headers=headers, stream=True)
        if offset and response.status_code == 206:
            match = CONTENT_RANGE_PATTERN.match(response.headers.get("Content-Range", ""))
            if not match or int(match.group(1)) != offset:
                raise SourceRequestError("invalid Content-Range in resumed download")
            return response, "ab", offset
        return response, "wb", 0

    def _stream_response(self, response: Any, partial: Path, mode: str, offset: int) -> None:
        expected_size = _expected_download_size(response, offset)
        if expected_size is not None and expected_size > self.max_download_bytes:
            raise SourceRequestError("download exceeds configured maximum size")
        downloaded_size = offset
        with partial.open(mode) as target:
            for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                if not chunk:
                    continue
                downloaded_size += len(chunk)
                if downloaded_size > self.max_download_bytes:
                    raise SourceRequestError("download exceeds configured maximum size")
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if expected_size is not None and partial.stat().st_size != expected_size:
            raise SourceRequestError("download ended before the advertised content length")


def _validate_product_id(product_id: str) -> None:
    try:
        uuid.UUID(product_id)
    except ValueError as exc:
        raise SourceRequestError("CDSE OData product ID must be a UUID") from exc


def _existing_download(destination: Path, expected_sha256: str | None) -> RawWriteResult | None:
    if not destination.exists():
        return None
    existing = _hash_file(destination)
    if expected_sha256 and existing.lower() != expected_sha256.lower():
        raise RawImmutableError(
            f"immutable raw artifact does not match expected checksum: {destination}"
        )
    return RawWriteResult(destination, existing, False)


def _claim_download(staging: Path, destination_name: str) -> Path:
    lock = staging / f"{destination_name}.download.lock"
    try:
        lock.touch(exist_ok=False)
    except FileExistsError as exc:
        raise SourceRequestError(f"download already in progress: {destination_name}") from exc
    return lock


def _expected_download_size(response: Any, offset: int) -> int | None:
    content_range = response.headers.get("Content-Range")
    if content_range:
        match = CONTENT_RANGE_PATTERN.match(content_range)
        if match and match.group(3) != "*":
            return int(match.group(3))
    content_length = response.headers.get("Content-Length")
    if content_length and content_length.isdigit():
        return offset + int(content_length)
    return None


def require_registered() -> None:
    """Raise when authenticated CDSE use is attempted without credentials."""
    if not os.getenv("CDSE_USERNAME") or not os.getenv("CDSE_PASSWORD"):
        raise SourceRequestError("register with CDSE and set CDSE_USERNAME/CDSE_PASSWORD")
