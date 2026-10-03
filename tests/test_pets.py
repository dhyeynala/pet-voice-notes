"""``/api/me``, ``/api/me/pets``, ``POST /api/pets``, ``GET /api/pets/{id}`` (review C2)."""

from __future__ import annotations

import uuid

import pytest

MAX = {"name": "Max", "animal_type": "dog", "breed": "Golden Retriever", "age": 6, "weight": 68.5, "gender": "male"}


def test_me(client):
    assert client.get("/api/me").json() == {"uid": "alice", "name": "alice"}


def test_create_pet_returns_a_uuid4_pet_owned_by_the_caller(client, store):
    response = client.post("/api/pets", json=MAX)
    assert response.status_code == 201
    pet = response.json()
    assert uuid.UUID(pet["id"]).version == 4
    assert set(pet) == {"id", "name", "animal_type", "breed", "age", "weight", "gender", "owners", "created_at"}
    assert {k: pet[k] for k in MAX} == MAX
    assert pet["owners"] == ["alice"]
    assert pet["created_at"].endswith("+00:00")
    stored = store.get(f"pets/{pet['id']}")
    assert stored["owners"] == ["alice"] and stored["created_by"] == "alice" and stored["schema_version"] == 2
    assert client.get(f"/api/pets/{pet['id']}").json() == pet


def test_ui_form_shape_is_accepted(client):
    """The add-pet form sends "" for an unselected gender and null for empty numbers."""
    body = {"name": "  Luna ", "animal_type": "cat", "breed": "", "age": None, "weight": None, "gender": ""}
    pet = client.post("/api/pets", json=body).json()
    assert (pet["name"], pet["breed"], pet["age"], pet["gender"]) == ("Luna", "", None, None)


@pytest.mark.parametrize(
    "body",
    [
        {"animal_type": "dog"},
        {"name": "", "animal_type": "dog"},
        {"name": "x" * 61, "animal_type": "dog"},
        {"name": "Max", "animal_type": "dragon"},
        {"name": "Max", "animal_type": "dog", "age": -1},
        {"name": "Max", "animal_type": "dog", "weight": 1e9},
        {"name": "Max", "animal_type": "dog", "owners": ["mallory"]},  # extra=forbid
        {"name": "Max", "animal_type": "dog", "id": "chosen-id"},
    ],
)
def test_invalid_pet_bodies_are_422_with_a_string_detail(client, store, body):
    response = client.post("/api/pets", json=body)
    assert response.status_code == 422
    payload = response.json()
    assert isinstance(payload["detail"], str) and payload["request_id"]
    assert all(set(err) == {"loc", "msg", "type"} for err in payload["errors"])
    assert store.query("pets") == []


def test_two_users_same_name_are_two_pets_and_each_sees_only_theirs(client_as):
    alice, bob = client_as("alice"), client_as("bob")
    a = alice.post("/api/pets", json=MAX).json()
    b = bob.post("/api/pets", json={**MAX, "breed": "French Bulldog"}).json()
    assert a["id"] != b["id"]
    assert [p["id"] for p in alice.get("/api/me/pets").json()] == [a["id"]]
    assert [p["id"] for p in bob.get("/api/me/pets").json()] == [b["id"]]
    assert bob.get(f"/api/pets/{a['id']}").status_code == 404
    assert alice.get(f"/api/pets/{b['id']}").status_code == 404
    assert bob.get(f"/api/pets/{b['id']}").json()["breed"] == "French Bulldog"


def test_my_pets_are_listed_oldest_first(client):
    first = client.post("/api/pets", json={"name": "Zed", "animal_type": "dog"}).json()
    second = client.post("/api/pets", json={"name": "Abby", "animal_type": "cat"}).json()
    ids = [p["id"] for p in client.get("/api/me/pets").json()]
    assert ids.index(first["id"]) <= ids.index(second["id"])


def test_pet_ids_cannot_address_other_collections(client, store):
    store.set("users/alice", {"name": "Alice"})
    for bad in ("..", "users", "x y", "a" * 65):
        assert client.get(f"/api/pets/{bad}").status_code == 404


def test_legacy_create_route_uses_uuid_ids_and_no_shared_page(client, store):
    pet = client.post("/api/pets/alice", json={"name": "Max", "animal_type": "dog", "pageId": "default-page"}).json()["pet"]
    assert uuid.UUID(pet["id"]).version == 4
    assert store.get("pages/default-page") is None
    assert store.get(f"pets/{pet['id']}")["owners"] == ["alice"]
