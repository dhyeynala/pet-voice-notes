"""The app runs end to end in demo mode on the store and the fakes (no keys, no network)."""

from __future__ import annotations

import sys


def test_index_and_static_files_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/styles.css").status_code == 200


def test_create_and_list_pets(client, store):
    """Create and list through the contract routes (uuid ids, owners = the caller)."""
    response = client.post("/api/pets", json={"name": "Luna", "animal_type": "cat", "age": 3})
    assert response.status_code == 201
    pet_id = response.json()["id"]
    pets = client.get("/api/me/pets").json()
    assert [(p["id"], p["name"], p["age"]) for p in pets] == [(pet_id, "Luna", 3)]
    assert store.get(f"pets/{pet_id}")["owners"] == ["alice"]
    assert client.post("/api/pets", json={"animal_type": "cat"}).status_code == 422


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


def test_pdf_upload_goes_to_local_blob_store(client, store, blobs, make_pet):
    import json

    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Apoquel 16 mg daily. Recheck in 2 weeks.")
    pet_id = make_pet()

    response = client.post(f"/api/pets/{pet_id}/records", files={"file": ("visit.pdf", doc.tobytes(), "application/pdf")})
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["pages"] == 1 and body["status"] == "summarized" and body["filename"] == "visit.pdf"
    assert "Apoquel" in json.dumps(body["summary"])
    [(_, record)] = store.query(f"pets/{pet_id}/records")
    assert "file_url" not in record and blobs.exists(record["blob_key"])
    assert client.get(f"/api/pets/{pet_id}/records/{body['id']}/file").content.startswith(b"%PDF-")


def test_demo_mode_makes_no_live_sdk_imports(client, make_pet):
    pet_id = make_pet()
    client.post(f"/api/pets/{pet_id}/notes", json={"text": "Max ate dinner"})
    client.post(f"/api/pets/{pet_id}/chat", json={"message": "How is Max?"})
    assert "google.cloud.speech" not in sys.modules
    assert "firebase_admin" not in sys.modules
