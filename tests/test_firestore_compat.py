"""The transitional Firestore-shaped facade used by the legacy modules."""

from __future__ import annotations

import pytest

from petpulse.store import MemoryStore, NotFound
from petpulse.store.firestore_compat import ArrayUnion, CompatClient


@pytest.fixture
def db():
    store = MemoryStore()
    return CompatClient(lambda: store), store


def test_document_roundtrip(db):
    client, store = db
    ref = client.collection("pets").document("max")
    assert not ref.get().exists and ref.get().to_dict() is None
    ref.set({"name": "Max"})
    snap = ref.get()
    assert snap.exists and snap.id == "max" and snap.to_dict() == {"name": "Max"} and snap.get("name") == "Max"
    ref.update({"age": 6})
    assert store.get("pets/max") == {"name": "Max", "age": 6}
    ref.delete()
    assert not ref.get().exists
    with pytest.raises(NotFound):
        ref.update({"age": 7})


def test_subcollections_add_where_stream(db):
    client, _ = db
    notes = client.collection("pets").document("max").collection("analytics")
    _, ref = notes.add({"category": "diet", "timestamp": "2026-10-01T10:00:00"})
    notes.add({"category": "sleep", "timestamp": "2026-10-02T10:00:00"})
    notes.add({"category": "diet", "timestamp": "2026-09-01T10:00:00"})
    assert ref.get().to_dict()["category"] == "diet"

    rows = list(notes.where("category", "==", "diet").where("timestamp", ">=", "2026-09-15").stream())
    assert [r.id for r in rows] == [ref.id]
    ordered = notes.order_by("timestamp", direction="DESCENDING").limit(2).get()
    assert [r.to_dict()["category"] for r in ordered] == ["sleep", "diet"]


def test_array_union_and_array_contains_alias(db):
    client, _ = db
    users = client.collection("users")
    users.document("u1").set({"pets": ArrayUnion(["max"])}, merge=True)
    users.document("u1").set({"pets": ArrayUnion(["max", "luna"])}, merge=True)
    assert users.document("u1").get().to_dict() == {"pets": ["max", "luna"]}
    assert [s.id for s in users.where("pets", "array-contains", "luna").stream()] == ["u1"]


def test_auto_id_document(db):
    client, _ = db
    ref = client.collection("pets").document()
    assert len(ref.id) == 32 and client.collection("pets").id == "pets"
