"""The legacy routes run end to end in demo mode on the store and the fakes.

These pin current behaviour after the Phase 0 rewire (minimal behaviour change). Known bugs
are covered separately in test_known_bugs.py.
"""

from __future__ import annotations

import sys
from datetime import datetime

from petpulse.providers.llm import LegacyTask


def test_index_and_static_files_are_served(client):
    assert client.get("/").status_code == 200
    assert client.get("/styles.css").status_code == 200


def test_create_and_list_pets(client, store):
    response = client.post("/api/pets/alice", json={"name": "Luna", "animal_type": "cat", "age": 3})
    assert response.json()["status"] == "success"
    pets = client.get("/api/user-pets/alice").json()
    assert [(p["id"], p["name"], p["age"]) for p in pets] == [("luna", "Luna", 3)]
    assert store.get("users/alice")["pets"] == ["luna"]


def test_text_note_is_classified_and_summarised_by_fake(client, store, fake_llm, make_pet):
    pet_id = make_pet()
    body = client.post(f"/api/pets/{pet_id}/textinput", json={"input": "Max had a long walk at the park."}).json()
    assert body["status"] == "success"
    assert body["content_type"] == "DAILY_ACTIVITY"
    assert body["summary"] == "[Simulated summary] Max had a long walk at the park."
    assert {c["task"] for c in fake_llm.calls} == {LegacyTask.NOTE_CLASSIFY, LegacyTask.NOTE_SUMMARY}
    [(_, note)] = store.query(f"pets/{pet_id}/textinput")
    assert note["input"] == "Max had a long walk at the park."
    # DAILY_ACTIVITY notes are mirrored into analytics (legacy behaviour)
    assert len(store.query(f"pets/{pet_id}/analytics")) == 1


def test_analytics_write_read_and_charts(client, make_pet):
    pet_id = make_pet()
    assert client.post(f"/api/pets/{pet_id}/analytics/exercise", json={"type": "walk", "duration": 30}).json()["status"] == (
        "success"
    )
    client.post(f"/api/pets/{pet_id}/analytics/energy_levels", json={"level": 4})
    data = client.get(f"/api/pets/{pet_id}/analytics").json()["data"]
    assert sorted(d["category"] for d in data) == ["energy_levels", "exercise"]
    summary = client.get(f"/api/pets/{pet_id}/analytics/summary").json()["summary"]
    assert summary["exercise"]["total"] == 1
    viz = client.get(f"/api/pets/{pet_id}/visualizations").json()
    assert viz["data_points"] == 2 and "weekly_activity" in viz["visualizations"]


def test_daily_routine_uses_rule_based_headlines_in_demo(client, make_pet):
    pet_id = make_pet()
    client.post(f"/api/pets/{pet_id}/analytics/diet", json={"food": "kibble"})
    today = datetime.utcnow().strftime("%Y-%m-%d")
    body = client.post(f"/api/pets/{pet_id}/daily_routine", json={"date": today}).json()
    assert body["data_points"] == 1
    assert any("Max" in h for h in body["headlines"])


def test_chat_returns_simulated_answer(client, make_pet):
    pet_id = make_pet()
    body = client.post(f"/api/pets/{pet_id}/chat", json={"query": "How is Max?"}).json()
    assert body["status"] == "success"
    assert body["response"].startswith("[Simulated answer]")


def test_knowledge_search_is_offline(client, make_pet):
    pet_id = make_pet()
    body = client.post(f"/api/pets/{pet_id}/knowledge_search", json={"query": "limping"}).json()
    assert body["status"] == "success" and body["results"]


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
    assert "Apoquel 16 mg daily" in body["summary"]
    [(_, record)] = store.query(f"pets/{pet_id}/records")
    assert record["file_name"] == "visit.pdf" and record["file_url"] is None
    assert blobs.exists(record["blob_key"])


def test_server_recording_reports_missing_pyaudio(client, monkeypatch):
    monkeypatch.setitem(sys.modules, "pyaudio", None)  # make ``import pyaudio`` fail
    body = client.post("/api/start_recording", json={"uid": "alice", "pet": "max"}).json()
    assert body["status"] == "error" and "PyAudio" in body["message"]


def test_legacy_transcription_goes_through_stt_provider(fake_stt, app):
    import transcribe

    assert transcribe._transcribe_audio_data(b"\x00" * 10) == "No speech detected"
    text = transcribe._transcribe_audio_data(b"\x01\x02" * 4000)
    assert text and not text.startswith("Error")
    assert fake_stt.calls[-1]["mime"] == "audio/wav"
    fake_stt.fail = True
    assert transcribe._transcribe_audio_data(b"\x01\x02" * 4000).startswith("Error:")


def test_demo_mode_makes_no_live_sdk_imports(client, make_pet):
    pet_id = make_pet()
    client.post(f"/api/pets/{pet_id}/textinput", json={"input": "Max ate dinner"})
    client.post(f"/api/pets/{pet_id}/chat", json={"query": "How is Max?"})
    assert "google.cloud.speech" not in sys.modules
    assert "firebase_admin" not in sys.modules
