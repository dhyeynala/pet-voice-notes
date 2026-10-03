"""LocalBlobStore: server-generated keys, no escape from the blob root."""

from __future__ import annotations

import pytest

from petpulse.store.blobs import BlobStore, LocalBlobStore, new_key


def test_roundtrip(tmp_path):
    blobs = LocalBlobStore(tmp_path / "blobs")
    assert isinstance(blobs, BlobStore)
    key = new_key("pets", "p1", "records", suffix=".pdf")
    assert key.startswith("pets/p1/records/") and key.endswith(".pdf")
    blobs.put(key, b"%PDF-1.4")
    assert blobs.exists(key)
    with blobs.open(key) as fh:
        assert fh.read() == b"%PDF-1.4"
    blobs.delete(key)
    blobs.delete(key)  # idempotent
    assert not blobs.exists(key)


def test_keys_are_unique():
    assert new_key("records") != new_key("records")


@pytest.mark.parametrize("bad", ["../x", "a/../../x", "/etc/passwd", "a//b", ".hidden", "a/b c", ""])
def test_rejects_unsafe_keys(tmp_path, bad):
    blobs = LocalBlobStore(tmp_path)
    with pytest.raises(ValueError):
        blobs.put(bad, b"x")


def test_rejects_bad_suffix():
    with pytest.raises(ValueError):
        new_key("records", suffix="/../x")
