"""The app runs end to end in demo mode on the store and the fakes (no keys, no network)."""

from __future__ import annotations

import sys


def test_index_and_static_files_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/styles.css").status_code == 200


def test_create_and_list_pets_on_the_legacy_routes(client, store):
    """The pre-contract create/list routes still work for the signed-in user (uuid ids, owners)."""
    response = client.post("/api/pets/alice", json={"name": "Luna", "animal_type": "cat", "age": 3})
    assert response.json()["status"] == "success"
    pet_id = response.json()["pet"]["id"]
    pets = client.get("/api/user-pets/alice").json()
    assert [(p["id"], p["name"], p["age"]) for p in pets] == [(pet_id, "Luna", 3)]
    assert store.get(f"pets/{pet_id}")["owners"] == ["alice"]
    assert [p["id"] for p in client.get("/api/me/pets").json()] == [pet_id]
    assert client.post("/api/pets/alice", json={"animal_type": "cat"}).status_code == 422


def test_text_note_is_extracted_by_the_fake(client, store, fake_llm, make_pet):
    pet_id = make_pet()
    note = client.post(f"/api/pets/{pet_id}/notes", json={"text": "Max had a long walk at the park."}).json()
    assert note["status"] == "processed" and note["mode"] == "demo" and note["urgent"] is False
    assert {c["task"] for c in fake_llm.calls} == {"note_extract.v1"}
    assert store.get(f"pets/{pet_id}/notes/{note['id']}")["text"] == "Max had a long walk at the park."
    assert store.query(f"pets/{pet_id}/textinput") == []  # no legacy mirror


def test_analytics_write_and_read(client, make_pet):
    pet_id = make_pet()
    created = client.post(f"/api/pets/{pet_id}/analytics/exercise", json={"type": "walk", "duration": 30})
    assert created.status_code == 201 and created.json()["duration"] == 30
    client.post(f"/api/pets/{pet_id}/analytics/energy_levels", json={"level": 4})
    data = client.get(f"/api/pets/{pet_id}/analytics").json()
    assert sorted(d["category"] for d in data) == ["energy_levels", "exercise"]
    assert [d["category"] for d in client.get(f"/api/pets/{pet_id}/analytics?category=exercise").json()] == ["exercise"]


def test_chat_answers_from_the_records_with_a_citation(client, make_pet):
    pet_id = make_pet()
    note = client.post(f"/api/pets/{pet_id}/notes", json={"text": "He was limping on his left leg after the walk."}).json()
    body = client.post(f"/api/pets/{pet_id}/chat", json={"message": "Why was he limping?", "tz": "UTC"}).json()
    assert body["status"] == "answered" and body["mode"] == "demo"
    assert [c["id"] for c in body["citations"]] == [note["id"]]


def test_legacy_chat_body_is_rejected(client, make_pet):
    pet_id = make_pet()
    response = client.post(f"/api/pets/{pet_id}/chat", json={"query": "How is Max?"})
    assert response.status_code == 422


def test_pdf_upload_goes_to_local_blob_store(client, store, blobs, make_pet, tmp_path):
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Apoquel 16 mg daily. Recheck in 2 weeks.")
    pdf_bytes = doc.tobytes()
    pet_id = make_pet()

    body = client.post(
        "/api/upload_pdf",
        data={"uid": "alice", "pet": pet_id},
        files={"file": ("visit.pdf", pdf_bytes, "application/pdf")},
    ).json()
    assert body["message"] == "PDF processed"
    assert body["url"] is None
    assert "Apoquel" in body["summary"]
    [(_, record)] = store.query(f"pets/{pet_id}/records")
    assert record["filename"] == "visit.pdf" and "file_url" not in record
    assert body["record"]["pages"] == 1 and body["record"]["status"] == "summarized"
    assert blobs.exists(record["blob_key"])


def test_markdown_is_stored_on_the_owned_pet(client, client_as, store, make_pet):
    pet_id = make_pet()
    assert client.get("/api/markdown").json() == {"markdown": ""}
    assert client.post("/api/markdown", json={"pet": pet_id, "markdown": "# Max"}).json() == {"status": "updated"}
    assert client.get(f"/api/markdown?pet={pet_id}").json() == {"markdown": "# Max"}
    assert store.get(f"pets/{pet_id}")["name"] == "Max"  # merged, not replaced
    bob = client_as("bob")
    assert bob.get(f"/api/markdown?pet={pet_id}").status_code == 404
    assert bob.post("/api/markdown", json={"pet": pet_id, "markdown": "x"}).status_code == 404


def test_demo_mode_makes_no_live_sdk_imports(client, make_pet):
    pet_id = make_pet()
    client.post(f"/api/pets/{pet_id}/notes", json={"text": "Max ate dinner"})
    client.post(f"/api/pets/{pet_id}/chat", json={"message": "How is Max?"})
    assert "google.cloud.speech" not in sys.modules
    assert "firebase_admin" not in sys.modules
