"""``FirestoreStore`` / ``FirebaseBlobStore`` against in-process SDK fakes (no network, no firebase_admin).

The contract tests run on both ``MemoryStore`` and ``FirestoreStore`` so the two cannot drift; the
app-level test seeds the demo data into Firestore and drives the real routes over it.
"""

from __future__ import annotations

import io
import json

import pytest

from petpulse.store.base import ArrayUnion, NotFound
from petpulse.store.firestore import FirebaseBlobStore, FirestoreStore
from petpulse.store.memory import MemoryStore
from tests.fake_firebase import (
    FAKE_SERVICE_ACCOUNT,
    FakeArrayUnion,
    FakeBucket,
    FakeFieldFilter,
    FakeFirestoreClient,
    install,
)


def firestore_store(client: FakeFirestoreClient | None = None) -> FirestoreStore:
    return FirestoreStore(client or FakeFirestoreClient(), array_union=FakeArrayUnion, field_filter=FakeFieldFilter)


@pytest.fixture(params=["memory", "firestore"])
def any_store(request):
    return MemoryStore() if request.param == "memory" else firestore_store()


# ---------------------------------------------------------------------------- Store contract
def test_get_set_replace_and_missing(any_store):
    assert any_store.get("pets/p1") is None
    any_store.set("pets/p1", {"name": "Max", "meta": {"a": 1}})
    any_store.set("pets/p1", {"name": "Rex"})
    assert any_store.get("pets/p1") == {"name": "Rex"}


def test_merge_is_shallow_like_memory_store(any_store):
    any_store.set("pets/p1", {"name": "Max", "meta": {"a": 1, "b": 2}, "odd-key": 1})
    any_store.set("pets/p1", {"meta": {"a": 9}, "odd-key": 2}, merge=True)
    assert any_store.get("pets/p1") == {"name": "Max", "meta": {"a": 9}, "odd-key": 2}
    any_store.set("pets/p2", {}, merge=True)
    assert any_store.get("pets/p2") == {}


def test_array_union(any_store):
    any_store.set("pets/p1", {"owners": ["alice"]})
    any_store.set("pets/p1", {"owners": ArrayUnion(["alice", "bob"])}, merge=True)
    assert any_store.get("pets/p1") == {"owners": ["alice", "bob"]}
    any_store.set("pets/p3", {"owners": ArrayUnion(["carol"])})
    assert any_store.get("pets/p3") == {"owners": ["carol"]}


def test_add_query_and_delete_in_subcollections(any_store):
    ids = [any_store.add("pets/p1/notes", {"n": n, "tags": ["x"] if n % 2 else []}) for n in range(5)]
    any_store.add("pets/p2/notes", {"n": 99})
    any_store.set("pets/p1", {"name": "Max"})
    assert len(set(ids)) == 5 and all(len(i) == 32 for i in ids)
    assert sorted(doc["n"] for _, doc in any_store.query("pets/p1/notes")) == [0, 1, 2, 3, 4]
    assert [d["n"] for _, d in any_store.query("pets/p1/notes", where=[("n", ">=", 3)], order_by=[("n", "desc")])] == [4, 3]
    assert [d["n"] for _, d in any_store.query("pets/p1/notes", where=[("tags", "array_contains", "x")])] in ([1, 3], [3, 1])
    assert [d["n"] for _, d in any_store.query("pets/p1/notes", where=[("n", "in", [0, 2])], order_by=[("n", "asc")])] == [
        0,
        2,
    ]
    assert [d["n"] for _, d in any_store.query("pets/p1/notes", order_by=[("n", "asc")], limit=2)] == [0, 1]
    assert any_store.query("pets/p1/notes", limit=0) == []
    any_store.delete(f"pets/p1/notes/{ids[0]}")
    any_store.delete("pets/p1/notes/does-not-exist")
    assert len(any_store.query("pets/p1/notes")) == 4
    assert any_store.get("pets/p1") == {"name": "Max"}  # subcollection rows are not parent docs


def test_top_level_collections_used_by_the_llm_layer(any_store):
    call_id = any_store.add("llm_calls", {"task": "note_extract", "ok": True})
    any_store.set("meta/seed", {"version": 1})
    assert any_store.get(f"llm_calls/{call_id}") == {"task": "note_extract", "ok": True}
    assert any_store.get("meta/seed") == {"version": 1}


def test_update_requires_existing_document(any_store):
    with pytest.raises(NotFound):
        any_store.update("pets/nope", {"a": 1})
    any_store.set("pets/p1", {"a": 1})
    any_store.update("pets/p1", {"b": 2})
    assert any_store.get("pets/p1") == {"a": 1, "b": 2}


@pytest.mark.parametrize("path", ["pets", "pets/p1/notes", "pets/../users/x", ""])
def test_bad_document_paths_are_rejected(any_store, path):
    with pytest.raises(ValueError):
        any_store.get(path)


def test_non_json_documents_are_rejected(any_store):
    with pytest.raises(TypeError):
        any_store.set("pets/p1", {"when": object()})


def test_unsupported_operator_is_rejected(any_store):
    any_store.set("pets/p1", {"a": "x"})
    with pytest.raises(ValueError):
        any_store.query("pets", where=[("a", "like", "x")])


# ---------------------------------------------------------------------------- Firestore specifics
def test_merge_sends_an_explicit_field_list_not_a_deep_merge():
    client = FakeFirestoreClient()
    store = firestore_store(client)
    store.set("pets/p1", {"name": "Max", "odd-key": 1, "back`tick": 2}, merge=True)
    assert client.calls[-1] == ("set", "pets/p1", ["name", "`odd-key`", "`back\\`tick`"])


def test_queries_use_field_filters_and_firestore_directions():
    client = FakeFirestoreClient()
    store = firestore_store(client)
    store.query("pets", where=[("owners", "array_contains", "alice")], order_by=[("created_at", "desc")], limit=3)
    _, path, filters, orders, limit = client.calls[-1]
    assert path == "pets" and limit == 3
    assert filters == (FakeFieldFilter("owners", "array_contains", "alice"),)
    assert orders == (("created_at", "DESCENDING"),)


# ---------------------------------------------------------------------------- blobs
def test_firebase_blob_store_round_trip():
    bucket = FakeBucket()
    blobs = FirebaseBlobStore(bucket)
    key = "pets/p1/records/abc.pdf"
    assert not blobs.exists(key)
    blobs.put(key, b"%PDF-1.4 data")
    assert bucket.objects[key] == (b"%PDF-1.4 data", "application/pdf")
    assert blobs.exists(key)
    with blobs.open(key) as fh:
        assert isinstance(fh, io.BytesIO) and fh.read() == b"%PDF-1.4 data"
    blobs.delete(key)
    blobs.delete(key)  # missing is fine, like LocalBlobStore
    with pytest.raises(FileNotFoundError):
        blobs.open(key)


@pytest.mark.parametrize("key", ["../x", "pets//x", "pets/../../etc/passwd", "/abs", "pets/x y"])
def test_firebase_blob_store_rejects_bad_keys(key):
    with pytest.raises(ValueError):
        FirebaseBlobStore(FakeBucket()).put(key, b"x")


def test_blob_errors_other_than_not_found_propagate():
    class Boom(Exception):
        code = 500

    class Bucket(FakeBucket):
        def blob(self, name):
            blob = super().blob(name)
            blob.download_as_bytes = lambda: (_ for _ in ()).throw(Boom())  # type: ignore[method-assign]
            return blob

    with pytest.raises(Boom):
        FirebaseBlobStore(Bucket()).open("pets/p1/records/a.pdf")


# ---------------------------------------------------------------------------- wiring
def test_deps_build_firestore_and_storage_from_settings(monkeypatch):
    from petpulse.core import config, deps, firebase

    fake = install(monkeypatch)
    monkeypatch.setattr(config, "firebase_admin_installed", lambda: True)
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", json.dumps(FAKE_SERVICE_ACCOUNT))
    monkeypatch.setenv("FIREBASE_STORAGE_BUCKET", "petpulse-test.firebasestorage.app")
    deps.reset()
    store, blobs = deps.get_store(), deps.get_blobs()
    assert isinstance(store, FirestoreStore) and isinstance(blobs, FirebaseBlobStore)
    assert len(fake.apps) == 1  # one shared app
    app = fake.apps[0]
    assert app["name"] == firebase.APP_NAME
    assert app["credential"] == ("certificate", FAKE_SERVICE_ACCOUNT)
    assert app["options"] == {"projectId": "petpulse-test", "storageBucket": "petpulse-test.firebasestorage.app"}
    store.set("pets/p1", {"name": "Max"})
    assert fake.client.docs["pets/p1"] == {"name": "Max"}


def test_firestore_without_bucket_keeps_local_blobs(monkeypatch):
    from petpulse.core import config, deps
    from petpulse.store.blobs import LocalBlobStore

    install(monkeypatch)
    monkeypatch.setattr(config, "firebase_admin_installed", lambda: True)
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", json.dumps(FAKE_SERVICE_ACCOUNT))
    deps.reset()
    assert isinstance(deps.get_store(), FirestoreStore)
    assert isinstance(deps.get_blobs(), LocalBlobStore)


# ---------------------------------------------------------------------------- the app on Firestore
@pytest.fixture
def firestore_app(app, monkeypatch):
    """The demo app, seeded, with every store/blob call going through the Firebase classes."""
    import petpulse.app as app_module
    from petpulse import seed
    from petpulse.core import deps

    client = FakeFirestoreClient()
    store = firestore_store(client)
    blobs = FirebaseBlobStore(FakeBucket())
    deps.override(store=store, blobs=blobs)
    app_module.app.dependency_overrides.update({deps.get_store: lambda: store, deps.get_blobs: lambda: blobs})
    summary = seed.seed_demo_data(store, blobs=blobs)
    return app, store, client, summary


def test_seed_and_core_flows_run_on_firestore(firestore_app, client_as):
    from petpulse.seed import demo_data

    _, store, client, summary = firestore_app
    assert summary.pets == 3 and summary.notes > 0 and summary.records == 1
    assert any(path.startswith("pets/") and "/notes/" in path for path in client.docs)

    alice, bob = client_as("alice"), client_as("bob")
    pets = alice.get("/api/me/pets").json()
    assert sorted(p["name"] for p in pets) == ["Luna", "Max"]
    max_id = demo_data.ALICE_MAX_ID

    for url in (
        f"/api/pets/{max_id}",
        f"/api/pets/{max_id}/notes",
        f"/api/pets/{max_id}/records",
        f"/api/pets/{max_id}/analytics?days=30",
        f"/api/pets/{max_id}/insights",
    ):
        assert alice.get(url).status_code == 200, url
        assert bob.get(url).status_code == 404, url

    note = alice.post(f"/api/pets/{max_id}/notes", json={"text": "Max ate all his dinner and walked 30 minutes."})
    assert note.status_code in (200, 201), note.text
    chat = alice.post(f"/api/pets/{max_id}/chat", json={"message": "Has Max vomited recently?"})
    assert chat.status_code == 200, chat.text
    assert any(path.startswith("llm_calls/") for path in client.docs)

    record = alice.get(f"/api/pets/{max_id}/records").json()[0]
    pdf = alice.get(f"/api/pets/{max_id}/records/{record['id']}/file")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-")
    assert bob.get(f"/api/pets/{max_id}/records/{record['id']}/file").status_code == 404

    created = alice.post("/api/pets", json={"name": "Pip", "animal_type": "bird"})
    assert created.status_code == 201
    assert store.get(f"pets/{created.json()['id']}")["owners"] == ["alice"]


def test_demo_reset_is_refused_on_firestore(monkeypatch, client):
    from petpulse.core import config, deps

    monkeypatch.setattr(config, "firebase_admin_installed", lambda: True)
    monkeypatch.setenv("STORE_BACKEND", "firestore")
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", json.dumps(FAKE_SERVICE_ACCOUNT))
    deps.get_settings.cache_clear()  # store/blobs stay overridden by the app fixture
    response = client.post("/api/demo/reset")
    assert response.status_code == 409
    assert response.json()["code"] == "reset_disabled"
