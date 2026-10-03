"""Track C routes (API contract): notes, chat and insights. Owner gets 2xx, another user 404,
no credentials 401; bad input 422; a provider outage on chat is 503, never an invented reply.

Auth is the real ``petpulse.auth``: ``client`` is signed in as alice (who owns ``make_pet()``
pets), ``anon_client`` has no token, ``client_as("bob")`` is another user.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

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
def pets(make_pet):
    return make_pet("alice"), make_pet("bob")


@pytest.fixture
def chat_app(app, store, fake_llm):
    """The contract chat route on its own: in ``api_server`` the legacy handler still matches first."""
    from petpulse import deps
    from petpulse.routers import assistant

    chat = FastAPI()
    chat.include_router(assistant.router)
    chat.dependency_overrides.update({deps.get_store: lambda: store, deps.get_llm: lambda: fake_llm})
    return chat


def as_user(uid: str) -> dict[str, str]:
    from petpulse.auth import issue_token

    return {"Authorization": f"Bearer {issue_token(uid)}"}


def post_note(client: TestClient, pet: str, text: str, **extra: Any) -> Any:
    return client.post(f"/api/pets/{pet}/notes", json={"text": text, **extra})


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
    response = client.get(f"/api/pets/{alice_pet}/notes?limit=2")
    assert response.status_code == 200 and [n["text"] for n in response.json()] == [
        "Third walk of the day.",
        "Second walk of the day.",
    ]
    assert client.get(f"/api/pets/{alice_pet}/notes?limit=0").status_code == 422


@pytest.mark.parametrize(
    "body",
    [{"text": ""}, {"text": "x" * 5001}, {"text": "fine", "tz": "Nowhere/City"}, {"text": "fine", "urgent": True}, {}],
)
def test_bad_note_input_is_422(client, pets, body):
    alice_pet, _ = pets
    response = client.post(f"/api/pets/{alice_pet}/notes", json=body)
    assert response.status_code == 422


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/pets/{pet}/notes", {"text": "Walked."}),
        ("get", "/api/pets/{pet}/notes", None),
        ("get", "/api/pets/{pet}/insights", None),
    ],
)
def test_owner_only(client, anon_client, client_as, pets, method, path, body):
    alice_pet, _ = pets
    url = path.format(pet=alice_pet)
    kwargs = {"json": body} if body is not None else {}
    assert getattr(anon_client, method)(url, **kwargs).status_code == 401
    assert getattr(client_as("bob"), method)(url, **kwargs).status_code == 404
    assert getattr(client, method)(url, **kwargs).status_code in (200, 201)


def test_insights_are_computed_with_mode(client, pets):
    alice_pet, _ = pets
    post_note(client, alice_pet, "He vomited blood this morning.")
    body = client.get(f"/api/pets/{alice_pet}/insights?tz=America/New_York").json()
    assert set(body) == {"facts", "alerts", "headline", "mode"} and body["mode"] == "demo"
    assert body["alerts"][0]["severity"] == body["alerts"][0]["level"] == "urgent"
    assert all(isinstance(item["text"], str) and item["level"] for item in body["alerts"] + body["facts"])
    assert "Notes (last 7 days): 1 notes" in [fact["text"] for fact in body["facts"]]
    assert client.get(f"/api/pets/{alice_pet}/insights?tz=Bad/Zone").status_code == 422


def test_contract_chat_route(chat_app, pets, store):
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
    chat_client = TestClient(chat_app, headers=as_user("alice"))
    response = chat_client.post(url, json={"message": "Why was he limping?", "tz": "UTC"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) == {"answer", "status", "citations", "chart", "mode"} and body["status"] == "answered"
    assert body["citations"][0]["id"] == "n1" and body["citations"][0]["date"] == "2026-09-30"
    assert TestClient(chat_app).post(url, json={"message": "hi"}).status_code == 401
    bob_client = TestClient(chat_app, headers=as_user("bob"))
    assert bob_client.post(url, json={"message": "hi"}).status_code == 404
    assert chat_client.post(f"/api/pets/{bob_pet}/chat", json={"message": "hi"}).status_code == 404
    assert chat_client.post(url, json={"query": "old shape"}).status_code == 422


def test_chat_outage_is_503(chat_app, pets, store, fake_llm):
    alice_pet, _ = pets
    store.set(f"pets/{alice_pet}/notes/n1", {"text": "He was limping.", "created_at": "2026-09-30T12:00:00Z"})
    fake_llm.fail = True
    response = TestClient(chat_app, headers=as_user("alice")).post(
        f"/api/pets/{alice_pet}/chat", json={"message": "Why was he limping?"}
    )
    assert response.status_code == 503


def test_app_chat_dispatches_contract_and_legacy_bodies(client, anon_client, client_as, pets, store):
    """The legacy handler still owns ``POST .../chat``: ``{"message"}`` (the contract, used by the
    new UI) goes to the grounded assistant; ``{"query"}`` still reaches the legacy chatbot."""
    alice_pet, _ = pets
    url = f"/api/pets/{alice_pet}/chat"
    contract = client.post(url, json={"message": "Has he had a seizure?", "tz": "America/New_York"})
    assert contract.status_code == 200 and set(contract.json()) == {"answer", "status", "citations", "chart", "mode"}
    assert contract.json()["status"] == "not_in_records"
    assert client.post(url, json={"message": "hi", "extra": 1}).status_code == 422
    assert anon_client.post(url, json={"message": "hi"}).status_code == 401
    assert client_as("bob").post(url, json={"message": "hi"}).status_code == 404
    assert "citations" not in client.post(url, json={"query": "How is Max?"}).json()


def test_chat_dosing_question_with_no_matching_records_is_out_of_scope(client, pets, fake_llm):
    alice_pet, _ = pets
    response = client.post(f"/api/pets/{alice_pet}/chat", json={"message": "What dose of ibuprofen should I give Max?"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "out_of_scope" and body["citations"] == [] and body["chart"] is None
    assert fake_llm.calls == []
