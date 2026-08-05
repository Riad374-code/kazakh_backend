"""Safe storage APIs (pipeline_inst.md sections 14 and 16).

Provides:
- atomic-derive-write of derived artifacts,
- directory creation,
- content checksums (SHA-256),
- duplicate detection,
- cache lookup,
- quarantine,
- immutable-raw enforcement (section 14: raw is immutable).

Raw writes are refused; derived artifacts are written atomically so a failed
write never leaves a valid-looking partial artifact behind.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from pathlib import Path
from typing import BinaryIO, Iterable, Optional, Union

CHUNK = 1 << 20


class StorageError(RuntimeError):
    """Base error for storage operations."""


class RawImmutableError(StorageError):
    """Raised when code attempts to write into an immutable raw bucket."""


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    """Compute the SHA-256 of a file streaming in chunks (cross-platform)."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_dir(path: Path) -> Path:
    """Create ``path`` and all parents; return the resolved path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


class Storage:
    """Manages the section-14 storage tree with safety invariants."""

    def __init__(
        self,
        base: Union[str, Path],
        *,
        raw: Optional[Union[str, Path]] = None,
        quarantine: Optional[Union[str, Path]] = None,
    ) -> None:
        self.base = Path(base).resolve()
        self.raw = Path(raw).resolve() if raw else (self.base / "raw")
        self._quarantine = Path(quarantine).resolve() if quarantine else (self.base / "quarantine")

    # -- directories --------------------------------------------------------

    def raw_dir(self) -> Path:
        return ensure_dir(self.raw)

    def processed_dir(self) -> Path:
        return ensure_dir(self.base / "processed")

    def interim_dir(self) -> Path:
        return ensure_dir(self.base / "interim")

    def cache_dir(self) -> Path:
        return ensure_dir(self.base / "cache")

    def quarantine_dir(self) -> Path:
        return ensure_dir(self._quarantine)

    # -- immutable raw ------------------------------------------------------

    def assert_raw_immutable(self, target: Path) -> None:
        """Refuse writes whose target resolves inside the raw tree."""
        resolved = target.resolve()
        raw_root = self.raw.resolve()
        if resolved == raw_root or raw_root in resolved.parents:
            raise RawImmutableError(f"refusing to write {resolved}; data/raw is immutable")

    # -- checksums & duplicates ---------------------------------------------

    @staticmethod
    def checksum_bytes(data: bytes) -> str:
        return sha256_bytes(data)

    def checksum_of(self, path: Path) -> str:
        return sha256_file(path)

    def find_duplicate(
        self,
        data: bytes,
        search_roots: Iterable[Union[str, Path]],
        *,
        counter: Optional[Path] = None,
    ) -> Optional[Path]:
        """Return the first existing file with identical content, else None.

        Args:
            data: The byte content to look for.
            search_roots: Directories to scan (raw buckets are allowed to index).
            counter: Optional path to an on-disk content-addressed inventory.
        """
        digest = self.checksum_bytes(data)
        if counter is not None and counter.is_file():
            seen = self._read_counter(counter)
            hit = seen.get(digest)
            if hit and Path(hit).is_file() and self.checksum_of(Path(hit)) == digest:
                return Path(hit)
        for root in search_roots:
            root = Path(root)
            if not root.is_dir():
                continue
            for candidate in root.rglob("*"):
                if not candidate.is_file():
                    continue
                if sha256_file(candidate) == digest:
                    if counter is not None:
                        self._record_counter(counter, digest, candidate)
                    return candidate
        return None

    def _read_counter(self, path: Path) -> dict[str, str]:
        result: dict[str, str] = {}
        if not path.is_file():
            return result
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split(" ", 1)
            if len(parts) == 2:
                result[parts[0]] = parts[1]
        return result

    def _record_counter(self, path: Path, digest: str, target: Path) -> None:
        ensure_dir(path.parent)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"{digest} {target}\n")

    # -- atomic derived writes ----------------------------------------------

    def write_atomic_bytes(self, path: Path, data: bytes, *, overwrite: bool = True) -> Path:
        """Atomically write derived bytes to ``path``.

        The write targets temp in the same directory then os.replace, so a crash
        never leaves a valid-looking partial file.
        """
        path = path.resolve()
        self.assert_raw_immutable(path)
        if path.exists() and not overwrite:
            raise storage_exists(path)
        ensure_dir(path.parent)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        # best-effort durability
        self._fsync_dir(path.parent)
        return path

    def write_atomic_file(self, path: Path, source: BinaryIO, *, overwrite: bool = True) -> Path:
        """Stream ``source`` into ``path`` atomically."""
        path = path.resolve()
        self.assert_raw_immutable(path)
        if path.exists() and not overwrite:
            raise storage_exists(path)
        ensure_dir(path.parent)
        fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp_", suffix=".part")
        try:
            with os.fdopen(fd, "wb") as out:
                shutil.copyfileobj(source, out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(tmp, path)
        except BaseException:
            try:
                os.remove(tmp)
            except OSError:
                pass
            raise
        self._fsync_dir(path.parent)
        return path

    @staticmethod
    def _fsync_dir(directory: Path) -> None:
        # Directory fsync is not portable on Windows; best-effort only.
        try:
            fd = os.open(str(directory), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass

    def write_text(self, path: Path, text: str, *, overwrite: bool = True) -> Path:
        return self.write_atomic_bytes(path, text.encode("utf-8"), overwrite=overwrite)

    # -- cache ---------------------------------------------------------------

    def cache_path(self, key: str, suffix: str = ".bin") -> Path:
        """Return a deterministic cache path under the cache bucket."""
        return ensure_dir(self.cache_dir()) / f"{key}{suffix}"

    def cache_lookup(self, key: str, suffix: str = ".bin") -> Optional[Path]:
        path = Path(self.cache_dir()) / f"{key}{suffix}"
        return path if path.is_file() else None

    def cache_store(self, key: str, data: bytes, suffix: str = ".bin") -> Path:
        return self.write_atomic_bytes(self.cache_path(key, suffix), data)

    # -- quarantine ------------------------------------------------------------

    def quarantine(self, artifact: Union[str, Path], reason: str) -> Path:
        """Move an incompatible/unresolved artifact into quarantine.

        Returns the quarantine destination.
        """
        source = Path(artifact).resolve()
        if not source.exists():
            raise StorageError(f"cannot quarantine missing artifact: {source}")
        qdir = ensure_dir(self.quarantine_dir() / reason.replace(" ", "_"))
        dest = qdir / source.name
        if dest.exists():
            dest = qdir / f"{source.name}.{self.checksum_of(source)[:8]}"
        shutil.move(str(source), str(dest))
        return dest

    def quarantine_write(self, relative: str, data: bytes, reason: str) -> Path:
        """Write bytes directly into quarantine (no raw immutability conflict)."""
        qdir = ensure_dir(self.quarantine_dir() / reason.replace(" ", "_"))
        dest = Path(qdir) / relative
        return self.write_atomic_bytes(dest, data)


def storage_exists(path: Path) -> StorageError:
    return StorageError(f"refusing to overwrite existing file: {path}")
