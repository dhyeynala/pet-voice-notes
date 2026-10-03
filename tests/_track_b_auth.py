"""Test-only stand-ins for ``petpulse.auth`` (owned by the auth track), via dependency_overrides.

``X-Test-User: <uid>`` authenticates; ``require_pet_access`` answers 404 unless the uid is in
``pets/<pet_id>.owners``, which is the contract's behaviour. The overrides are keyed on the
objects the routers actually depend on (``petpulse.routers._auth_bridge``), which are the real
``petpulse.auth`` functions once that module exists, so these tests keep working after it lands.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Optional

from fastapi import FastAPI, Header, HTTPException

TEST_USER_HEADER = "X-Test-User"


def install_fake_auth(app: FastAPI, store: Any) -> None:
    from petpulse.routers import _auth_bridge as bridge

    def fake_current_user(x_test_user: Optional[str] = Header(None)) -> Any:
        if not x_test_user:
            raise HTTPException(status_code=401, detail="not authenticated")
        return SimpleNamespace(uid=x_test_user, name=x_test_user.title())

    def fake_require_pet_access(pet_id: str, x_test_user: Optional[str] = Header(None)) -> Any:
        if not x_test_user:
            raise HTTPException(status_code=401, detail="not authenticated")
        pet = store.get(f"pets/{pet_id}")
        if not pet or x_test_user not in pet.get("owners", []):
            raise HTTPException(status_code=404, detail="pet not found")
        return {"id": pet_id, **pet}

    app.dependency_overrides[bridge.current_user] = fake_current_user
    app.dependency_overrides[bridge.require_pet_access] = fake_require_pet_access


def as_user(uid: str) -> dict[str, str]:
    return {TEST_USER_HEADER: uid}


def seed_pets(store: Any) -> tuple[str, str]:
    """Alice's Max and Bob's Max (distinct ids, as after the C2 fix). Returns (alice_pet, bob_pet)."""
    for uid, name in (("alice", "Alice"), ("bob", "Bob")):
        store.set(f"users/{uid}", {"name": name})
    store.set("pets/pet-alice-max", {"name": "Max", "animal_type": "dog", "owners": ["alice"]})
    store.set("pets/pet-bob-max", {"name": "Max", "animal_type": "dog", "owners": ["bob"]})
    return "pet-alice-max", "pet-bob-max"
