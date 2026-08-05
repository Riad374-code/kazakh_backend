"""Small deterministic artifact helpers for Steps 23-24."""

from __future__ import annotations

import hashlib
from pathlib import Path


def directory_checksum(path: Path) -> str:
    digest = hashlib.sha256()
    for file in sorted(item for item in path.rglob("*") if item.is_file()):
        digest.update(file.relative_to(path).as_posix().encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()
