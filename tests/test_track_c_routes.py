"""Track C routes (API contract): notes, chat and insights. Owner gets 2xx, another user 404,
no credentials 401; bad input 422; a provider outage on chat is 503, never an invented reply.

Auth is the auth track's; these tests use the stand-ins in ``tests/_track_b_auth`` (keyed on
the objects the routers depend on, so they keep working once ``petpulse.auth`` lands).
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests._track_b_auth import as_user, install_fake_auth, seed_pets

NOTE_KEYS = {
    "id",
    "pet_id",
    "source",
    "text",
    "summary",
    "kind",
    "urgent",
    "needs_review",
    "red_flags",
    "observations",
    "status",
    "created_at",
    "mode",
}


@pytest.fixture
def pets(app, store):
    install_fake_auth(app, store)
    return seed_pets(store)


@pytest.fixture
def chat_client(store, fake_llm, pets):
    """The contract chat route on its own: in ``api_server`` the legacy handler still matches first."""
    from petpulse import deps
    from petpulse.routers import assistant
    from petpulse.routers import _auth_bridge as bridge

    app = FastAPI()
    app.include_router(assistant.router)
    real = TestClient(app)
    install_fake_auth(app, store)
    app.dependency_overrides.update({deps.get_store: lambda: store, deps.get_llm: lambda: fake_llm})
    assert bridge.current_user in app.dependency_overrides
    return real


def post_note(client: TestClient, pet: str, text: str, uid: str = "alice", **extra: Any) -> Any:
    return client.post(f"/api/pets/{pet}/notes", json={"text": text, **extra}, headers=as_user(uid))


def test_post_note_returns_201_with_the_contract_shape(client, pets, store):
    alice_pet, _ = pets
    response = post_note(client, alice_pet, "He vomited blood this morning.", tz="America/New_York")
    assert response.status_code == 201, response.text
    note = response.json()
    assert set(note) == NOTE_KEYS and note["urgent"] is True and note["source"] == "text"
    assert store.get(f"pets/{alice_pet}/notes/{note['id']}")["uid"] == "alice"


def test_list_notes_newest_first_with_limit(client, pets):
    alice_pet, _ = pets
    for text in ("First walk of the day.", "Second walk of the day.", "Third walk of the day."):
        assert post_note(client, alice_pet, text).status_code == 201
    response = client.get(f"/api/pets/{alice_pet}/notes?limit=2", headers=as_user("alice"))
    assert response.status_code == 200 and [n["text"] for n in response.json()] == [
        "Third walk of the day.",
        "Second walk of the day.",
    ]
    assert client.get(f"/api/pets/{alice_pet}/notes?limit=0", headers=as_user("alice")).status_code == 422


@pytest.mark.parametrize(
    "body",
    [{"text": ""}, {"text": "x" * 5001}, {"text": "fine", "tz": "Nowhere/City"}, {"text": "fine", "urgent": True}, {}],
)
def test_bad_note_input_is_422(client, pets, body):
    alice_pet, _ = pets
    response = client.post(f"/api/pets/{alice_pet}/notes", json=body, headers=as_user("alice"))
    assert response.status_code == 422


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/pets/{pet}/notes", {"text": "Walked."}),
        ("get", "/api/pets/{pet}/notes", None),
        ("get", "/api/pets/{pet}/insights", None),
    ],
)
def test_owner_only(client, pets, method, path, body):
    alice_pet, _ = pets
    url = path.format(pet=alice_pet)
    kwargs = {"json": body} if body is not None else {}
    assert getattr(client, method)(url, **kwargs).status_code == 401
    assert getattr(client, method)(url, headers=as_user("bob"), **kwargs).status_code == 404
    assert getattr(client, method)(url, headers=as_user("alice"), **kwargs).status_code in (200, 201)


def test_routes_fail_closed_without_the_auth_module(client, store):
    seed_pets(store)  # no fake auth installed: the bridge's stand-ins answer 401
    from petpulse.routers import _auth_bridge as bridge

    if bridge.current_user.__module__ != bridge.__name__:
        pytest.skip("petpulse.auth exists; covered by the auth track's route inventory")
    assert client.get("/api/pets/pet-alice-max/notes", headers=as_user("alice")).status_code == 401


def test_insights_are_computed_with_mode(client, pets):
    alice_pet, _ = pets
    post_note(client, alice_pet, "He vomited blood this morning.")
    body = client.get(f"/api/pets/{alice_pet}/insights?tz=America/New_York", headers=as_user("alice")).json()
    assert set(body) == {"facts", "alerts", "headline", "mode"} and body["mode"] == "demo"
    assert body["alerts"][0]["severity"] == "urgent"
    assert client.get(f"/api/pets/{alice_pet}/insights?tz=Bad/Zone", headers=as_user("alice")).status_code == 422


def test_contract_chat_route(chat_client, pets, store):
    alice_pet, bob_pet = pets
    store.set(
        f"pets/{alice_pet}/notes/n1",
        {
            "pet_id": alice_pet,
            "source": "text",
            "text": "He was limping on his left leg.",
            "summary": None,
            "kind": "MEDICAL",
            "urgent": False,
            "needs_review": False,
            "red_flags": [],
            "observations": [],
            "status": "processed",
            "created_at": "2026-09-30T12:00:00Z",
            "mode": "demo",
        },
    )
    url = f"/api/pets/{alice_pet}/chat"
    response = chat_client.post(url, json={"message": "Why was he limping?", "tz": "UTC"}, headers=as_user("alice"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"answer", "status", "citations", "chart", "mode"} and body["status"] == "answered"
    assert body["citations"][0]["id"] == "n1" and body["citations"][0]["date"] == "2026-09-30"
    assert chat_client.post(url, json={"message": "hi"}).status_code == 401
    assert chat_client.post(f"/api/pets/{bob_pet}/chat", json={"message": "hi"}, headers=as_user("alice")).status_code == 404
    assert chat_client.post(url, json={"query": "old shape"}, headers=as_user("alice")).status_code == 422


def test_chat_outage_is_503(chat_client, pets, store, fake_llm):
    alice_pet, _ = pets
    store.set(f"pets/{alice_pet}/notes/n1", {"text": "He was limping.", "created_at": "2026-09-30T12:00:00Z"})
    fake_llm.fail = True
    response = chat_client.post(
        f"/api/pets/{alice_pet}/chat", json={"message": "Why was he limping?"}, headers=as_user("alice")
    )
    assert response.status_code == 503


def test_legacy_chat_handler_still_answers_in_the_app(client, pets):
    """Known collision: the legacy ``POST .../chat`` (body ``{"query"}``) is registered first and
    still answers in ``api_server``. Deleting it (cleanup PR) activates the contract route; flip
    this test then."""
    alice_pet, _ = pets
    response = client.post(f"/api/pets/{alice_pet}/chat", json={"message": "hi"}, headers=as_user("alice"))
    assert "citations" not in response.json()
