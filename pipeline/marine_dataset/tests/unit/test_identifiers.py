"""Step 02 tests: deterministic stable identifiers."""

from __future__ import annotations

from marine_dataset.identifiers import (
    content_hash,
    label_id,
    scene_id,
    stable_id,
    tile_id,
)


def test_same_input_same_id():
    a = scene_id("marine", "S1A", "PROD_ABC_123")
    b = scene_id("marine", "S1A", "PROD_ABC_123")
    assert a == b


def test_different_input_different_id():
    a = scene_id("marine", "S1A", "PROD_ABC_123")
    b = scene_id("marine", "S1A", "PROD_ABC_124")
    assert a != b


def test_namespace_versioning():
    a = stable_id("marine.v1", "scene", ["S1A", "P1"])
    b = stable_id("marine.v2", "scene", ["S1A", "P1"])
    assert a != b


def test_local_path_not_part_of_id():
    # Same product id with different local paths must produce the SAME id.
    a = scene_id("marine", "S1A", "PROD_XYZ")
    b = scene_id("marine", "S1A", "PROD_XYZ")
    assert a == b
    assert "data" not in a


def test_tile_id_is_grid_coordinates():
    a = tile_id("marine", "scene:1", 3, 7, "EPSG:4326", "10")
    b = tile_id("marine", "scene:1", 3, 7, "EPSG:4326", "10")
    assert a == b
    c = tile_id("marine", "scene:1", 3, 8, "EPSG:4326", "10")
    assert a != c


def test_label_id():
    a = label_id("marine", "gov_record_42", "government_record")
    assert a.startswith("marine:label:v1:")
    # different source record -> different id
    b = label_id("marine", "gov_record_43", "government_record")
    assert a != b


def test_content_hash_deterministic():
    assert content_hash("a", "b") == content_hash("a", "b")
    assert content_hash("a", "b") != content_hash("a", "c")


def test_invalid_namespace_rejected():
    import pytest

    from marine_dataset.identifiers import IdentifierError

    with pytest.raises(IdentifierError):
        stable_id("Marine !", "scene", ["a"])
