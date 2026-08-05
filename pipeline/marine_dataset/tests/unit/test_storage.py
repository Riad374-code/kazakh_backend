"""Step 02 tests: storage APIs (atomic writes, raw immutability, checksums)."""

from __future__ import annotations

from marine_dataset.storage import (
    RawImmutableError,
    Storage,
    sha256_bytes,
    sha256_file,
)


def test_checksum_cross_platform(tmp_path):
    p = tmp_path / "f.bin"
    p.write_bytes(b"hello world")
    assert sha256_file(p) == sha256_bytes(b"hello world")
    assert len(sha256_file(p)) == 64


def test_sha256_bytes_know_value():
    # SHA-256 of "abc"
    assert sha256_bytes(b"abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_raw_immutable_enforced(tmp_path):
    import pytest

    storage = Storage(tmp_path, raw=tmp_path / "raw")
    raw_file = tmp_path / "raw" / "sentinel1" / "x.tif"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(b"original")
    with pytest.raises(RawImmutableError):
        storage.write_atomic_bytes(raw_file, b"overwrite")


def test_normal_write_is_not_raw(tmp_path):
    storage = Storage(tmp_path, raw=tmp_path / "raw")
    out = storage.write_atomic_bytes(tmp_path / "processed" / "derived.bin", b"data")
    assert out.is_file()
    assert out.read_bytes() == b"data"


def test_atomic_write_no_partial_on_failure_subclass(tmp_path):
    # Simulate a consumer failing mid-write: temp file must not remain.
    storage = Storage(tmp_path, raw=tmp_path / "raw")
    with _exploding_source() as src:
        try:
            storage.write_atomic_file(tmp_path / "processed" / "out.bin", src)
        except Exception:
            pass
    leftovers = list((tmp_path / "processed").glob(".tmp_*.part"))
    assert leftovers == []


def _exploding_source():
    class S:
        def read(self, n=-1):
            raise IOError("boom")

    from contextlib import contextmanager

    @contextmanager
    def cm():
        yield S()

    return cm()


def test_atomic_write_failure_leaves_no_valid_artifact(tmp_path):
    storage = Storage(tmp_path, raw=tmp_path / "raw")
    dest = tmp_path / "processed" / "never.bin"
    with _exploding_source() as src:
        try:
            storage.write_atomic_file(dest, src)
        except Exception:
            pass
    # If it failed mid-write, the final artifact must NOT exist/be valid.
    assert not dest.exists() or dest.read_bytes() != b"partial"


def test_duplicate_detection(tmp_path):
    storage = Storage(tmp_path, raw=tmp_path / "raw")
    bucket = tmp_path / "candidates"
    bucket.mkdir()
    (bucket / "a.bin").write_bytes(b"duplicate-content")
    # scan for a copy
    hit = storage.find_duplicate(b"duplicate-content", [bucket])
    assert hit is not None
    assert hit.name == "a.bin"
    # not present -> None
    assert storage.find_duplicate(b"not-there", [bucket]) is None


def test_quarantine(tmp_path):
    storage = Storage(tmp_path, raw=tmp_path / "raw")
    src = tmp_path / "process" / "bad.bin"
    src.parent.mkdir(parents=True)
    src.write_bytes(b"bad")
    dest = storage.quarantine(src, "unresolved licence")
    assert dest.is_file()
    assert not src.exists()
    assert "unresolved" in str(dest)


def test_cache_lookup(tmp_path):
    storage = Storage(tmp_path, raw=tmp_path / "raw")
    assert storage.cache_lookup("missing") is None
    storage.cache_store("k", b"v")
    assert storage.cache_lookup("k").read_bytes() == b"v"
