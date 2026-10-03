"""Voice routes: GET /api/voice/samples and POST /api/pets/{pet_id}/voice-notes.

Real auth (``petpulse.auth``): ``client`` is signed in as alice, who owns ``PET``.
"""

from __future__ import annotations

import json
from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from petpulse import deps
from petpulse.config import Settings
from petpulse.pets import create_pet
from petpulse.providers.llm import FakeLLM
from petpulse.providers.stt import FakeSTT
from petpulse.samples import audio_manifest
from petpulse.services import voice as voice_service
from tests.audio_fixtures import mp4, wav, webm

PET = "pet-max-1"
URL = f"/api/pets/{PET}/voice-notes"
LISTED = [
    {"id": "walk_and_dinner", "label": "Routine: walk and dinner"},
    {"id": "vomiting_blood", "label": "Urgent: vomiting with blood"},
    {"id": "heartworm_pill", "label": "Medication: heartworm pill"},
    {"id": "silence", "label": "Silence (no speech)"},
]


def _sample(sample_id: str) -> bytes:
    sample = audio_manifest().get(sample_id)
    assert sample is not None
    return sample.read_bytes()


@pytest.fixture
def auth(store) -> str:
    """Alice's pet ``PET`` (fixed id so URLs are constants)."""
    create_pet(store, "alice", {"name": "Max", "animal_type": "dog"}, pet_id=PET)
    return PET


@pytest.fixture
def settings_override(app) -> Iterator[Any]:
    def apply(**fields: Any) -> Settings:
        settings = Settings(_env_file=None, store="memory", **fields)  # type: ignore[call-arg]
        app.dependency_overrides[deps.get_settings] = lambda: settings
        return settings

    yield apply


def _post(client: TestClient, url: str = URL, **kwargs: Any) -> Any:
    return client.post(url, **kwargs)


# --------------------------------------------------------------------------- samples
def test_samples_list_ids_and_labels_only(client, auth):
    response = client.get("/api/voice/samples")
    assert response.status_code == 200
    assert response.json() == LISTED


def test_routes_require_a_token(anon_client, auth, store):
    for response in (
        anon_client.get("/api/voice/samples"),
        anon_client.post(URL, data={"sample_id": "vomiting_blood"}),
        anon_client.post(URL, files={"audio": ("b", _sample("walk_and_dinner"), "audio/webm")}),
    ):
        assert response.status_code == 401 and response.json()["detail"] == "not authenticated"
    assert store.query(f"pets/{PET}/voice-notes") == []


# ------------------------------------------------------------------------- happy path
def test_sample_id_is_transcribed_and_stored_as_a_voice_note(client, auth, store, fake_stt):
    response = _post(client, data={"sample_id": "vomiting_blood", "tz": "America/New_York"})
    assert response.status_code == 201, response.text
    body = response.json()
    expected = audio_manifest().get("vomiting_blood")
    assert expected is not None
    assert body["transcription"] == {"status": "ok", "text": expected.transcript, "confidence": 0.97}
    note = body["note"]
    assert note["source"] == "voice" and note["text"] == expected.transcript
    assert note["pet_id"] == PET and note["id"]
    assert fake_stt.calls == [{"bytes": len(_sample("vomiting_blood")), "mime": "audio/webm", "hint": "vomiting_blood.webm"}]
    [(note_id, stored)] = store.query(f"pets/{PET}/notes")
    assert note_id == note["id"] and stored["source"] == "voice" and stored["text"] == expected.transcript
    assert store.query(f"pets/{PET}/voice-notes") == []  # not the legacy collection


@pytest.mark.parametrize(
    "sample_id, urgent", [("vomiting_blood", True), ("walk_and_dinner", False), ("heartworm_pill", False)]
)
def test_urgency_comes_through_the_note_pipeline(client, auth, sample_id, urgent):
    note = _post(client, data={"sample_id": sample_id}).json()["note"]
    assert note["urgent"] is urgent and note["status"] == "processed" and note["mode"] == "demo"
    if urgent:
        present = {f["flag"] for f in note["red_flags"] if f["status"] == "present"}
        assert {"blood", "repeated_vomiting"} <= present
    listed = client.get(f"/api/pets/{PET}/notes").json()
    assert [(n["id"], n["source"], n["urgent"]) for n in listed] == [(note["id"], "voice", urgent)]


@pytest.mark.parametrize(
    "sample_id, declared",
    [("walk_and_dinner", "audio/webm;codecs=opus"), ("heartworm_pill", "audio/ogg; codecs=opus"), ("walk_and_dinner", "")],
)
def test_browser_upload_is_sniffed_and_transcribed(client, auth, sample_id, declared):
    files = {"audio": ("blob", _sample(sample_id), declared or "application/octet-stream")}
    response = _post(client, files=files, data={"tz": "Europe/Berlin"})
    assert response.status_code == 201, response.text
    assert response.json()["transcription"]["text"] == audio_manifest().get(sample_id).transcript  # type: ignore[union-attr]


def test_unknown_audio_gets_a_deterministic_canned_transcript(client, auth):
    blob = webm([0, 1000]) + bytes(range(256)) * 16
    first = _post(client, files={"audio": ("recording.webm", blob, "audio/webm")}).json()
    second = _post(client, files={"audio": ("recording.webm", blob, "audio/webm")}).json()
    assert first["transcription"]["status"] == "ok"
    assert first["transcription"]["text"] == second["transcription"]["text"]


def test_mp4_and_wav_uploads_are_accepted(client, auth, fake_stt):
    assert _post(client, files={"audio": ("a.m4a", mp4(3.0), "audio/mp4")}).status_code == 201
    assert _post(client, files={"audio": ("a.wav", wav(1.0), "audio/wav")}).status_code == 201
    assert [c["mime"] for c in fake_stt.calls] == ["audio/mp4", "audio/wav"]


def test_process_note_is_awaited_with_the_contract_signature(client, auth, monkeypatch, store):
    seen: list[tuple[Any, ...]] = []
    real = voice_service.process_note

    async def spy(pet_id: str, uid: str, text: str, source: str, tz: str, **kwargs: Any) -> Any:
        seen.append((pet_id, uid, text, source, tz, kwargs["store"] is store))
        return await real(pet_id, uid, text, source, tz, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(voice_service, "process_note", spy)
    body = _post(client, data={"sample_id": "vomiting_blood", "tz": "Asia/Tokyo"}).json()
    transcript = audio_manifest().get("vomiting_blood").transcript  # type: ignore[union-attr]
    assert seen == [(PET, "alice", transcript, "voice", "Asia/Tokyo", True)]
    assert body["note"]["urgent"] is True


def test_note_pipeline_value_error_is_400(client, auth, monkeypatch, store):
    async def refuse(*args: Any, **kwargs: Any) -> Any:
        raise ValueError("note text is longer than 5000 characters")

    monkeypatch.setattr(voice_service, "process_note", refuse)
    before = store.snapshot()
    response = _post(client, data={"sample_id": "walk_and_dinner"})
    assert response.status_code == 400 and "5000 characters" in response.json()["detail"]
    assert store.snapshot() == before


def test_llm_failure_still_stores_an_unprocessed_voice_note(client, auth, app, store):
    down = FakeLLM(fail=True)  # simulated outage on every call
    app.dependency_overrides[deps.get_llm] = lambda: down
    response = _post(client, data={"sample_id": "vomiting_blood"})
    assert response.status_code == 201, response.text
    note = response.json()["note"]
    assert note["status"] == "unprocessed" and note["needs_review"] is True and note["summary"] is None
    assert [doc["source"] for _, doc in store.query(f"pets/{PET}/notes")] == ["voice"]


# ---------------------------------------------------------------- nothing is stored
def _assert_nothing_stored(store, before: dict[str, Any], blobs) -> None:
    assert store.snapshot() == before
    assert not blobs.root.exists() or not any(p.is_file() for p in blobs.root.rglob("*"))


def test_silence_sample_is_422_and_stores_nothing(client, auth, store, blobs):
    before = store.snapshot()
    response = _post(client, data={"sample_id": "silence"})
    assert response.status_code == 422
    assert "No speech" in response.json()["detail"]
    _assert_nothing_stored(store, before, blobs)


def test_near_silent_wav_is_422_without_calling_the_provider(client, auth, store, blobs, fake_stt):
    before = store.snapshot()
    response = _post(client, files={"audio": ("quiet.wav", wav(2.0, amplitude=4), "audio/wav")})
    assert response.status_code == 422
    assert fake_stt.calls == []
    _assert_nothing_stored(store, before, blobs)


def test_stt_error_is_502_and_stores_nothing(client, auth, store, blobs, fake_stt):
    fake_stt.fail = True
    before = store.snapshot()
    response = _post(client, files={"audio": ("blob", _sample("walk_and_dinner"), "audio/webm")})
    assert response.status_code == 502
    assert "simulated STT outage" in response.json()["detail"]
    _assert_nothing_stored(store, before, blobs)


def test_provider_exception_is_502_not_500(client, auth, app, store):
    class Exploding(FakeSTT):
        def transcribe(self, audio: bytes, mime: str, hint: str | None = None) -> Any:
            raise RuntimeError("boom")

    app.dependency_overrides[deps.get_stt] = lambda: Exploding()
    before = store.snapshot()
    assert _post(client, data={"sample_id": "walk_and_dinner"}).status_code == 502
    assert store.snapshot() == before


def test_audio_is_not_kept(client, auth, store, blobs):
    secret_audio = webm([0, 500]) + b"UNIQUE-AUDIO-MARKER" * 200
    assert _post(client, files={"audio": ("blob", secret_audio, "audio/webm")}).status_code == 201
    dump = json.dumps(store.snapshot())
    assert "UNIQUE-AUDIO-MARKER" not in dump and "VU5JUVVF" not in dump  # raw or base64
    _assert_nothing_stored(store, store.snapshot(), blobs)


# ------------------------------------------------------------------- input validation
@pytest.mark.parametrize(
    "files, declared_status",
    [
        ({"audio": ("notes.txt", b"hello there" * 400, "text/plain")}, 415),
        ({"audio": ("x.webm", b"%PDF-1.7" + b"\x00" * 4000, "audio/webm")}, 415),  # sniffing wins
        ({"audio": ("x.mp3", b"ID3\x04" + b"\x00" * 4000, "audio/mpeg")}, 415),
    ],
)
def test_unsupported_types_are_415(client, auth, store, files, declared_status):
    before = store.snapshot()
    assert _post(client, files=files).status_code == declared_status
    assert store.snapshot() == before


def test_format_the_provider_cannot_decode_is_415(client, auth, app):
    app.dependency_overrides[deps.get_stt] = lambda: FakeSTT(
        supported_mimes=frozenset({"audio/webm", "audio/ogg", "audio/wav"})
    )
    response = _post(client, files={"audio": ("a.m4a", mp4(3.0), "audio/mp4")})
    assert response.status_code == 415 and "audio/mp4" in response.json()["detail"]


def test_json_body_is_415(client, auth):
    assert _post(client, json={"sample_id": "walk_and_dinner"}).status_code == 415


def test_size_cap_is_413(client, auth, store, settings_override):
    settings_override(voice_max_bytes=10_000)
    big = webm([0]) + b"\x00" * 12_000
    assert _post(client, files={"audio": ("big.webm", big, "audio/webm")}).status_code == 413
    # Content-Length is checked before the multipart body is parsed.
    response = client.post(URL, content=b"x" * 200_000, headers={"content-type": "multipart/form-data; boundary=zz"})
    assert response.status_code == 413


def test_duration_cap_is_413(client, auth, settings_override):
    settings_override(voice_max_seconds=3.0)
    assert _post(client, data={"sample_id": "vomiting_blood"}).status_code == 413  # 3.7 s
    assert _post(client, files={"audio": ("long.webm", webm([0, 30_000, 61_000]), "audio/webm")}).status_code == 413
    assert _post(client, files={"audio": ("long.m4a", mp4(4.0), "audio/mp4")}).status_code == 413


@pytest.mark.parametrize(
    "kwargs, detail",
    [
        ({"data": {"tz": "UTC"}}, "exactly one"),
        (
            {"data": {"sample_id": "walk_and_dinner"}, "files": {"audio": ("b", _sample("walk_and_dinner"), "audio/webm")}},
            "exactly one",
        ),
        ({"data": {"sample_id": "../../etc/passwd"}}, "Unknown sample_id"),
        ({"data": {"sample_id": "walk_and_dinner", "tz": "Mars/Olympus"}}, "Unknown time zone"),
    ],
)
def test_bad_form_input_is_400(client, auth, kwargs, detail):
    response = _post(client, **kwargs)
    assert response.status_code == 400 and detail in response.json()["detail"]


def test_empty_upload_is_no_speech(client, auth):
    assert _post(client, files={"audio": ("blob", b"", "audio/webm")}).status_code == 422


def test_other_users_pet_is_404(client_as, auth, store):
    before = store.snapshot()
    response = _post(client_as("bob"), data={"sample_id": "vomiting_blood"})
    assert response.status_code == 404 and response.json()["detail"] == "pet not found"
    assert store.snapshot() == before


def test_voice_route_is_documented_as_multipart(app):
    schema = app.openapi()["paths"][URL.replace(PET, "{pet_id}")]["post"]
    props = schema["requestBody"]["content"]["multipart/form-data"]["schema"]["properties"]
    assert set(props) == {"audio", "sample_id", "tz"}


def test_legacy_server_microphone_routes_are_gone(client):
    for path in ("/api/start", "/api/start_recording", "/api/stop_recording"):
        assert client.post(path, json={"uid": "alice", "pet": "max"}).status_code in (404, 405)
    assert client.get("/api/recording_status").status_code == 404
