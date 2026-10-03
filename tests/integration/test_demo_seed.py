"""Demo login/reset routes and the seed data (load once, reset restores, Bob can't see Alice's Max)."""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from petpulse import seed
from petpulse.core import deps
from petpulse.seed import demo_data
from petpulse.seed.demo_data import ALICE_LUNA_ID, ALICE_MAX_ID, BOB_MAX_ID
from petpulse.store.memory import JsonFileStore, MemoryStore

NOW = datetime(2026, 10, 3, 18, 30, tzinfo=timezone.utc)


@pytest.fixture
def seeded(app, store, monkeypatch):
    """The app started with SEED_ON_START=true on an empty store; yields a client factory."""
    monkeypatch.setenv("SEED_ON_START", "true")
    deps.get_settings.cache_clear()
    clients: list[TestClient] = []

    def make(uid: str | None = None) -> TestClient:
        c = TestClient(app)
        c.__enter__()
        clients.append(c)
        if uid:
            token = c.post("/api/demo/login", json={"uid": uid}).json()["token"]
            c.headers["Authorization"] = f"Bearer {token}"
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)


# ---------------------------------------------------------------------------- login flow
def test_demo_users_are_public(anon_client):
    assert anon_client.get("/api/demo/users").json() == [{"uid": "alice", "name": "Alice"}, {"uid": "bob", "name": "Bob"}]


def test_login_returns_a_token_that_works(anon_client):
    response = anon_client.post("/api/demo/login", json={"uid": "alice"})
    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {"uid": "alice", "name": "Alice"}
    me = anon_client.get("/api/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.json() == {"uid": "alice", "name": "Alice"}


def test_login_with_a_name_creates_a_new_demo_user(anon_client):
    body = anon_client.post("/api/demo/login", json={"name": "Sam Lee"}).json()
    assert body["user"]["name"] == "Sam Lee" and body["user"]["uid"].startswith("sam-lee-")
    users = anon_client.get("/api/demo/users").json()
    assert users[:2] == [{"uid": "alice", "name": "Alice"}, {"uid": "bob", "name": "Bob"}]
    assert body["user"] in users
    headers = {"Authorization": f"Bearer {body['token']}"}
    assert anon_client.get("/api/me/pets", headers=headers).json() == []


@pytest.mark.parametrize(
    "body, status",
    [({"uid": "mallory"}, 404), ({}, 422), ({"uid": "alice", "name": "A"}, 422), ({"uid": "alice", "role": "admin"}, 422)],
)
def test_bad_logins(anon_client, body, status):
    response = anon_client.post("/api/demo/login", json=body)
    assert response.status_code == status
    assert isinstance(response.json()["detail"], str)


def test_demo_routes_are_off_outside_demo_mode(app, monkeypatch, client):
    monkeypatch.setenv("DEMO_MODE", "false")
    deps.get_settings.cache_clear()
    assert client.get("/api/demo/users").status_code == 404
    assert client.post("/api/demo/login", json={"uid": "alice"}).status_code == 404
    assert client.post("/api/demo/reset").status_code == 404


# ---------------------------------------------------------------------------- seeded app
def test_seed_loads_on_first_start(seeded, store):
    alice = seeded("alice")
    pets = alice.get("/api/me/pets").json()
    assert [(p["name"], p["animal_type"]) for p in pets] == [("Max", "dog"), ("Luna", "cat")]
    assert [p["id"] for p in pets] == [ALICE_MAX_ID, ALICE_LUNA_ID]
    assert all(p["owners"] == ["alice"] for p in pets)


def test_bob_cannot_see_alices_max(seeded):
    alice, bob = seeded("alice"), seeded("bob")
    bob_pets = bob.get("/api/me/pets").json()
    assert [(p["id"], p["name"], p["breed"]) for p in bob_pets] == [(BOB_MAX_ID, "Max", "French Bulldog")]
    assert bob.get(f"/api/pets/{ALICE_MAX_ID}").status_code == 404
    assert bob.get(f"/api/pets/{ALICE_MAX_ID}/analytics").status_code == 404
    assert alice.get(f"/api/pets/{BOB_MAX_ID}").status_code == 404
    assert alice.get(f"/api/pets/{ALICE_MAX_ID}").json()["breed"] == "Golden Retriever"


def test_seeded_max_drives_the_dashboard(seeded):
    alice = seeded("alice")
    data = alice.get(f"/api/pets/{ALICE_MAX_ID}/analytics?days=30").json()
    assert {d["category"] for d in data} >= set(demo_data.CATEGORIES) and len(data) > 200
    insights = alice.get(f"/api/pets/{ALICE_MAX_ID}/insights?tz=UTC")
    assert insights.status_code == 200
    assert "urgent_note" in {a["id"] for a in insights.json()["alerts"]}
    notes = alice.get(f"/api/pets/{ALICE_MAX_ID}/notes").json()
    assert len(notes) == 8 and notes[0]["urgent"] is True


def test_seed_is_idempotent_across_restarts(seeded, store):
    seeded()
    before = store.snapshot()
    seeded()  # second startup on the same (now non-empty) store
    assert store.snapshot() == before
    assert seed.seed_if_empty(store) is None


def test_existing_data_is_never_overwritten_by_the_seed(seeded, store):
    store.set("users/zoe", {"name": "Zoe"})
    seeded()
    assert store.query("pets") == []


def test_reset_restores_the_seed_and_is_idempotent(seeded, store):
    alice = seeded("alice")
    created = alice.post("/api/pets", json={"name": "Rex", "animal_type": "dog"}).json()
    store.delete(f"pets/{ALICE_LUNA_ID}")

    first = alice.post("/api/demo/reset")
    assert first.status_code == 200 and first.json()["status"] == "reset"
    after_first = _shape(store)
    second = alice.post("/api/demo/reset").json()
    assert second["seed"] == first.json()["seed"]
    assert _shape(store) == after_first

    ids = [p["id"] for p in alice.get("/api/me/pets").json()]
    assert ids == [ALICE_MAX_ID, ALICE_LUNA_ID] and created["id"] not in ids
    assert alice.get("/api/me").status_code == 200  # the token survives a reset


def test_reset_requires_auth(anon_client):
    assert anon_client.post("/api/demo/reset").status_code == 401


def _shape(store: MemoryStore) -> dict[str, int]:
    return {coll: len(docs) for coll, docs in store.snapshot().items()}


# ---------------------------------------------------------------------------- seed content
def test_seed_content():
    store = MemoryStore()
    summary = seed.seed_demo_data(store, now=NOW)
    assert (summary.users, summary.pets) == (2, 3)
    assert store.get("users/alice")["email"] == "alice@demo.local"

    for pet_id in (ALICE_MAX_ID, ALICE_LUNA_ID, BOB_MAX_ID):
        assert uuid.UUID(pet_id).version == 4
        assert store.get(f"pets/{pet_id}")["schema_version"] == 2

    max_rows = [doc for _, doc in store.query(f"pets/{ALICE_MAX_ID}/analytics")]
    by_category = Counter(doc["category"] for doc in max_rows)
    assert set(by_category) == set(demo_data.CATEGORIES)
    assert 250 <= len(max_rows) <= 450
    stamps = [datetime.fromisoformat(doc["timestamp"]) for doc in max_rows]
    naive_now = NOW.replace(tzinfo=None)
    assert all(naive_now - timedelta(days=30) <= s <= naive_now for s in stamps)
    assert all(s.tzinfo is None for s in stamps)  # legacy format the old dashboard parses

    def mean_energy(lo: int, hi: int) -> float:
        levels = [
            d["level"]
            for d in max_rows
            if d["category"] == "energy_levels" and lo <= (naive_now - datetime.fromisoformat(d["timestamp"])).days <= hi
        ]
        return sum(levels) / len(levels)

    assert mean_energy(0, 6) < 3 < mean_energy(7, 29)  # the energy dip in the last week

    assert len(store.query(f"pets/{ALICE_LUNA_ID}/analytics")) < len(max_rows) / 2
    assert 0 < len(store.query(f"pets/{BOB_MAX_ID}/analytics")) < len(max_rows) / 2


def test_seed_notes():
    store = MemoryStore()
    seed.seed_demo_data(store, now=NOW)
    notes = [doc for _, doc in store.query(f"pets/{ALICE_MAX_ID}/notes", order_by=[("created_at", "asc")])]
    assert len(notes) == 8
    urgent = [n for n in notes if n["urgent"]]
    assert len(urgent) == 1 and "some blood" in urgent[0]["text"]
    assert urgent[0]["needs_review"] and {f["flag"] for f in urgent[0]["red_flags"]} == {"blood", "repeated_vomiting"}
    assert "tired" in notes[0]["text"] and (NOW - datetime.fromisoformat(notes[0]["created_at"])).days >= 39
    for note in notes:
        assert note["pet_id"] == ALICE_MAX_ID and note["uid"] == "alice" and note["mode"] == "demo"
        assert note["source"] in ("text", "voice") and note["kind"] in ("MEDICAL", "DAILY_ACTIVITY", "MIXED")
        assert note["status"] == "processed" and datetime.fromisoformat(note["created_at"]).tzinfo is not None
    all_urgent = [
        doc
        for pet in (ALICE_MAX_ID, ALICE_LUNA_ID, BOB_MAX_ID)
        for _, doc in store.query(f"pets/{pet}/notes")
        if doc["urgent"]
    ]
    assert len(all_urgent) == 1
    # Notes live in one place only: no legacy textinput / voice-notes mirror any more.
    assert store.query(f"pets/{ALICE_MAX_ID}/textinput") == [] and store.query(f"pets/{ALICE_MAX_ID}/voice-notes") == []


def test_seed_is_deterministic_for_a_given_now():
    a, b = MemoryStore(), MemoryStore()
    seed.seed_demo_data(a, now=NOW)
    seed.seed_demo_data(b, now=NOW)

    def content(store: MemoryStore) -> list[str]:
        # Document ids from store.add() are random; the content is not.
        return sorted(json.dumps(doc, sort_keys=True) for docs in store.snapshot().values() for doc in docs.values())

    assert content(a) == content(b)


def test_seed_never_writes_future_timestamps():
    early_morning = datetime(2026, 10, 3, 0, 5, tzinfo=timezone.utc)
    store = MemoryStore()
    seed.seed_demo_data(store, now=early_morning)
    for coll, docs in store.snapshot().items():
        for doc in docs.values():
            for key in ("timestamp", "created_at"):
                if key in doc:
                    moment = datetime.fromisoformat(doc[key])
                    moment = moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)
                    assert moment <= early_morning, (coll, doc)


def test_json_store_is_written_once_per_seed(tmp_path, monkeypatch):
    store = JsonFileStore(tmp_path / "db.json")
    writes: list[int] = []
    real = JsonFileStore._changed
    monkeypatch.setattr(JsonFileStore, "_changed", lambda self: (writes.append(1), real(self)))
    seed.seed_if_empty(store, now=NOW)
    assert len(writes) == 1
    reloaded = JsonFileStore(tmp_path / "db.json")
    assert reloaded.get(f"pets/{ALICE_MAX_ID}")["name"] == "Max"
    writes.clear()
    seed.reset_demo_data(store, now=NOW)
    assert len(writes) == 1


def test_reset_needs_a_clearable_store():
    class Bare:
        def query(self, *a, **k):
            return []

    with pytest.raises(NotImplementedError):
        seed.reset_demo_data(Bare())  # type: ignore[arg-type]


# ---------------------------------------------------------------------------- sample PDF record
def test_seed_adds_one_summarized_record_for_alices_max(seeded, blobs):
    alice = seeded("alice")
    records = alice.get(f"/api/pets/{ALICE_MAX_ID}/records").json()
    assert len(records) == 1
    record = records[0]
    assert record["filename"] == seed.SAMPLE_RECORD_FILENAME
    assert record["status"] == "summarized" and record["summary"]
    assert record["pages"] == 1
    assert record["created_at"] < datetime.now(timezone.utc).replace(tzinfo=None).isoformat()

    file = alice.get(f"/api/pets/{ALICE_MAX_ID}/records/{record['id']}/file")
    assert file.status_code == 200 and file.content.startswith(b"%PDF-")
    assert alice.get(f"/api/pets/{ALICE_LUNA_ID}/records").json() == []

    bob = seeded("bob")
    assert bob.get(f"/api/pets/{ALICE_MAX_ID}/records").status_code == 404
    assert bob.get(f"/api/pets/{ALICE_MAX_ID}/records/{record['id']}/file").status_code == 404


def test_reset_replaces_the_record_and_deletes_old_files(seeded, store, blobs):
    alice = seeded("alice")
    first = alice.get(f"/api/pets/{ALICE_MAX_ID}/records").json()[0]
    old_key = store.get(f"pets/{ALICE_MAX_ID}/records/{first['id']}")["blob_key"]
    assert blobs.exists(old_key)

    summary = alice.post("/api/demo/reset").json()["seed"]
    assert summary["records"] == 1
    after = alice.get(f"/api/pets/{ALICE_MAX_ID}/records").json()
    assert len(after) == 1 and after[0]["id"] != first["id"]
    assert not blobs.exists(old_key)
    new_key = store.get(f"pets/{ALICE_MAX_ID}/records/{after[0]['id']}")["blob_key"]
    assert blobs.exists(new_key)


def test_no_sample_record_without_blobs_or_with_a_live_llm(monkeypatch, blobs):
    store = MemoryStore()
    assert seed.seed_demo_data(store, now=NOW).records == 0
    assert store.query(f"pets/{ALICE_MAX_ID}/records") == []

    monkeypatch.setattr(seed, "_llm_is_fake", lambda: False)
    assert seed.seed_demo_data(MemoryStore(), now=NOW, blobs=blobs).records == 0


def test_sample_record_pdf_is_small_and_synthetic():
    data = seed.sample_record_pdf()
    assert data.startswith(b"%PDF-") and len(data) < 5_000
