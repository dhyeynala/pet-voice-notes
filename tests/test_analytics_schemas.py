"""Typed analytics writes and reads (review M7, M3)."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from tests._track_b_auth import as_user, install_fake_auth, seed_pets

# One payload per category, shaped exactly like the tracking forms in public/main.html send them.
VALID = {
    "diet": {"food": "kibble", "quantity": "1 cup", "time": "08:30", "type": "breakfast", "notes": ""},
    "exercise": {"type": "walk", "duration": 30, "intensity": "moderate", "location": "park", "notes": ""},
    "medication": {"name": "Apoquel", "dosage": "16 mg", "time": "09:00", "frequency": "once", "purpose": "itch"},
    "grooming": {"types": ["bath", "brushing"], "duration": 0, "products": "", "notes": ""},
    "energy_levels": {"level": 4, "notes": ""},
    "bowel_movements": {"consistency": "normal", "time": "07:15", "notes": ""},
    "exit_events": {"type": "potty", "duration": 0, "destination": "yard"},
    "weight": {"value": 31.5, "unit": "kg", "method": "vet-visit", "time": "", "notes": ""},
    "sleep": {"duration": 9.5, "quality": "good", "location": "crate", "interruptions": 0, "notes": ""},
    "mood": {"level": 3, "triggers": ["visitors"], "behavior": ["playful"], "time": "18:00", "notes": ""},
    "temperature": {"value": 38.6, "unit": "C"},
    "water_intake": {"amount": 750, "unit": "ml"},
    "activity": {"type": "sniff walk", "duration": 20},
}

INVALID = [
    ("diet", {"food": "kibble", "calories": 300}, "extra key"),
    ("diet", {"food": ""}, "required text blank"),
    ("diet", {"food": "kibble", "type": "brunch"}, "off-enum"),
    ("diet", {"food": "kibble", "time": "25:00"}, "bad time"),
    ("diet", {"food": "kibble", "notes": "x" * 2001}, "notes too long"),
    ("diet", {"food": "<img src=x onerror=alert(1)>" * 10}, "over length"),
    ("exercise", {"type": "walk", "duration": None}, "NaN from the form (sent as null)"),
    ("exercise", {"type": "walk"}, "duration missing"),
    ("exercise", {"type": "walk", "duration": 0}, "zero minutes"),
    ("exercise", {"type": "walk", "duration": 1441}, "over a day"),
    ("exercise", {"type": "walk", "duration": "30 min"}, "string duration"),
    ("exercise", {"type": "walk", "duration": 30.5}, "fractional minutes"),
    ("exercise", {"type": "walk", "duration": True}, "bool as int"),
    ("medication", {"name": "Apoquel", "dose": "16 mg"}, "dose is not the field name"),
    ("medication", {"name": "Apoquel"}, "dosage missing"),
    ("grooming", {"type": "bath"}, "type is not the field name"),
    ("grooming", {"types": "bath"}, "types must be a list"),
    ("grooming", {"types": []}, "no grooming type"),
    ("grooming", {"types": ["shave"]}, "off-enum grooming type"),
    ("energy_levels", {"level": 0}, "below range"),
    ("energy_levels", {"level": 6}, "above range"),
    ("energy_levels", {}, "level missing"),
    ("weight", {"value": 0, "unit": "kg"}, "zero weight"),
    ("weight", {"value": 30, "unit": "stone"}, "unit"),
    ("sleep", {"duration": 25}, "over 24h"),
    ("sleep", {"duration": -1}, "negative"),
    ("mood", {"level": 3, "triggers": ["rain"]}, "off-enum trigger"),
    ("temperature", {"value": 50, "unit": "C"}, "implausible C"),
    ("temperature", {"value": 38.5, "unit": "F"}, "implausible F"),
    ("water_intake", {"amount": 0}, "zero water"),
    ("bowel_movements", {"consistency": "unknown"}, "off-enum"),
]


@pytest.mark.parametrize("category", sorted(VALID))
def test_every_category_accepts_the_form_payload(category):
    from petpulse.schemas.analytics import validate_entry

    entry = validate_entry(category, VALID[category])
    assert set(entry.model_dump()) >= set(VALID[category])


def test_every_category_has_a_schema_and_example():
    from petpulse.schemas.analytics import CATEGORIES, ENTRY_MODELS

    assert set(CATEGORIES) == set(VALID) == set(ENTRY_MODELS)
    for model in ENTRY_MODELS.values():
        assert model.model_config.get("extra") == "forbid"


@pytest.mark.parametrize("category, payload, why", INVALID, ids=[case[2] for case in INVALID])
def test_schema_rejects_invalid_payloads(category, payload, why):
    from petpulse.schemas.analytics import validate_entry

    with pytest.raises(ValidationError):
        validate_entry(category, payload)


def test_nan_and_infinity_are_rejected():
    from petpulse.schemas.analytics import validate_entry

    for bad in (float("nan"), float("inf")):
        with pytest.raises(ValidationError):
            validate_entry("sleep", {"duration": bad})
        with pytest.raises(ValidationError):
            validate_entry("weight", {"value": bad, "unit": "kg"})


# ----------------------------------------------------------------- API (served at the contract paths)
@pytest.fixture
def pet(app, store):
    install_fake_auth(app, store)
    return seed_pets(store)[0]


def test_post_entry_returns_201_entry_and_stores_only_validated_fields(client, store, pet):
    response = client.post(f"/api/pets/{pet}/analytics/medication", json=VALID["medication"], headers=as_user("alice"))
    assert response.status_code == 201, response.text
    entry = response.json()
    assert entry["category"] == "medication" and entry["pet_id"] == pet and entry["dosage"] == "16 mg"
    assert {"id", "timestamp"} <= set(entry)

    stored = store.get(f"pets/{pet}/analytics/{entry['id']}")
    assert set(stored) == set(VALID["medication"]) | {"category", "pet_id", "timestamp", "source", "schema_version"}


@pytest.mark.parametrize("category, payload, why", INVALID[:8], ids=[case[2] for case in INVALID[:8]])
def test_post_invalid_entry_is_422_and_nothing_is_stored(client, store, pet, category, payload, why):
    response = client.post(f"/api/pets/{pet}/analytics/{category}", json=payload, headers=as_user("alice"))
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], str)
    assert store.query(f"pets/{pet}/analytics") == []


def test_post_mass_assignment_cannot_override_server_fields(client, store, pet):
    payload = {**VALID["energy_levels"], "timestamp": "1999-01-01T00:00:00", "category": "diet", "pet_id": "other"}
    response = client.post(f"/api/pets/{pet}/analytics/energy_levels", json=payload, headers=as_user("alice"))
    assert response.status_code == 422
    assert store.query(f"pets/{pet}/analytics") == []


def test_post_raw_nan_json_is_422(client, store, pet):
    response = client.post(
        f"/api/pets/{pet}/analytics/exercise",
        content=b'{"type": "walk", "duration": NaN}',
        headers={"Content-Type": "application/json", **as_user("alice")},
    )
    assert response.status_code == 422
    assert store.query(f"pets/{pet}/analytics") == []


def test_post_unknown_category_and_non_json_are_422(client, pet):
    assert client.post(f"/api/pets/{pet}/analytics/vibes", json={}, headers=as_user("alice")).status_code == 422
    response = client.post(
        f"/api/pets/{pet}/analytics/diet",
        content=b"not json",
        headers={"Content-Type": "application/json", **as_user("alice")},
    )
    assert response.status_code == 422


def test_get_entries_filters_sorts_and_skips_bad_rows(client, store, pet):
    for category in ("diet", "exercise", "energy_levels"):
        assert client.post(f"/api/pets/{pet}/analytics/{category}", json=VALID[category]).status_code == 201
    now = datetime.utcnow()
    store.add(
        f"pets/{pet}/analytics", {"category": "diet", "food": "old", "timestamp": (now - timedelta(days=40)).isoformat()}
    )
    store.add(f"pets/{pet}/analytics", {"category": "diet", "food": "bad ts", "timestamp": "not a date"})
    store.add(f"pets/{pet}/analytics", {"category": "diet", "food": "no ts"})
    store.add(
        f"pets/{pet}/analytics", {"category": "diet", "food": "tz", "timestamp": (now - timedelta(days=1)).isoformat() + "Z"}
    )

    entries = client.get(f"/api/pets/{pet}/analytics").json()
    assert isinstance(entries, list)
    assert [e["category"] for e in entries][:3] == ["energy_levels", "exercise", "diet"]  # newest first
    assert sorted(e.get("food") for e in entries if e["category"] == "diet") == ["kibble", "tz"]

    diet = client.get(f"/api/pets/{pet}/analytics", params={"category": "diet", "days": 60}).json()
    assert sorted(e["food"] for e in diet) == ["kibble", "old", "tz"]
    assert all(e["pet_id"] == pet and e["id"] for e in diet)


@pytest.mark.parametrize("params", [{"days": 0}, {"days": 366}, {"category": "vibes"}, {"days": "x"}])
def test_get_entries_rejects_bad_query(client, pet, params):
    assert client.get(f"/api/pets/{pet}/analytics", params=params).status_code == 422


def _router_only_app(store) -> FastAPI:
    """The new router on its own: what serves these paths once the legacy handlers are removed."""
    from petpulse import deps
    from petpulse.routers import analytics

    app = FastAPI()
    app.include_router(analytics.router)
    app.dependency_overrides[deps.get_store] = lambda: store
    install_fake_auth(app, store)
    return app


def test_router_routes_enforce_pet_ownership(store):
    alice_pet, _ = seed_pets(store)
    with TestClient(_router_only_app(store)) as c:
        created = c.post(f"/api/pets/{alice_pet}/analytics/diet", json=VALID["diet"], headers=as_user("alice"))
        assert created.status_code == 201
        assert c.get(f"/api/pets/{alice_pet}/analytics", headers=as_user("alice")).json()[0]["id"] == created.json()["id"]
        assert c.get(f"/api/pets/{alice_pet}/analytics", headers=as_user("bob")).status_code == 404
        assert c.post(f"/api/pets/{alice_pet}/analytics/diet", json=VALID["diet"], headers=as_user("bob")).status_code == 404
        assert c.get(f"/api/pets/{alice_pet}/analytics").status_code == 401
        assert (
            c.post(
                f"/api/pets/{alice_pet}/analytics/diet", json={"food": "x", "evil": 1}, headers=as_user("alice")
            ).status_code
            == 422
        )
    assert len(store.query(f"pets/{alice_pet}/analytics")) == 1
