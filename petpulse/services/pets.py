"""Pet and user records in the ``Store``.

Layout (review C2 fix):

- ``users/{uid}``  ``{name, email, demo, created_at}``
- ``pets/{id}``    ``{name, animal_type, breed, age, weight, gender, owners: [uid], created_by,
  created_at, schema_version: 2}`` where ``id`` is a server-generated uuid4. A pet's name is
  display data only, so two users' "Max" are two different pets. Ownership lives on the pet
  (``owners``); there are no shared pages.

Per-pet data stays in sub-collections (``pets/{id}/analytics``, ``.../notes``, ...).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Mapping, Optional

from petpulse.schemas.pets import Pet, User
from petpulse.store.base import Store

PETS = "pets"
USERS = "users"
PET_SCHEMA_VERSION = 2

# Ids are server-generated (uuid4) for new pets; the pattern also admits seeded/legacy ids but
# never path separators, so a pet id can't address another collection.
_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_PET_FIELDS = ("name", "animal_type", "breed", "age", "weight", "gender")


def utc_now_iso(now: Optional[datetime] = None) -> str:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def is_valid_id(value: str) -> bool:
    return bool(_ID.match(value))


# ---------------------------------------------------------------------------- users
def get_user(store: Store, uid: str) -> Optional[dict[str, Any]]:
    if not is_valid_id(uid):
        return None
    return store.get(f"{USERS}/{uid}")


def save_user(
    store: Store, uid: str, name: str, *, email: str = "", demo: bool = True, now: Optional[datetime] = None
) -> User:
    if not is_valid_id(uid):
        raise ValueError(f"invalid uid {uid!r}")
    existing = store.get(f"{USERS}/{uid}") or {}
    store.set(
        f"{USERS}/{uid}",
        {
            "name": name,
            "email": email or existing.get("email", ""),
            "demo": demo,
            "created_at": existing.get("created_at") or utc_now_iso(now),
        },
        merge=True,
    )
    return User(uid=uid, name=name)


def display_name(store: Store, uid: str) -> str:
    user = get_user(store, uid)
    name = user.get("name") if user else None
    return name if isinstance(name, str) and name else uid


# ---------------------------------------------------------------------------- pets
def new_pet_document(uid: str, fields: Mapping[str, Any], *, now: Optional[datetime] = None) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "name": fields.get("name") or "",
        "animal_type": fields.get("animal_type") or "",
        "breed": fields.get("breed") or "",
        "age": fields.get("age"),
        "weight": fields.get("weight"),
        "gender": fields.get("gender") or None,
        "owners": [uid],
        "created_by": uid,
        "created_at": utc_now_iso(now),
        "schema_version": PET_SCHEMA_VERSION,
    }
    return doc


def create_pet(
    store: Store,
    uid: str,
    fields: Mapping[str, Any],
    *,
    pet_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """Create a pet owned by ``uid`` under a fresh uuid4 (or the given seed id); return it with ``id``."""
    pet_id = pet_id or str(uuid.uuid4())
    if not is_valid_id(pet_id):
        raise ValueError(f"invalid pet id {pet_id!r}")
    doc = new_pet_document(uid, fields, now=now)
    store.set(f"{PETS}/{pet_id}", doc)
    return {"id": pet_id, **doc}


def get_pet(store: Store, pet_id: str) -> Optional[dict[str, Any]]:
    if not is_valid_id(pet_id):
        return None
    doc = store.get(f"{PETS}/{pet_id}")
    return {"id": pet_id, **doc} if doc is not None else None


def is_owner(pet: Mapping[str, Any], uid: str) -> bool:
    owners = pet.get("owners")
    return isinstance(owners, list) and uid in owners


def list_pets(store: Store, uid: str) -> list[dict[str, Any]]:
    """Pets owned by ``uid``, oldest first."""
    rows = store.query(PETS, where=[("owners", "array_contains", uid)])
    pets = [{"id": pet_id, **doc} for pet_id, doc in rows]
    pets.sort(key=lambda pet: (str(pet.get("created_at") or ""), str(pet.get("name") or ""), pet["id"]))
    return pets


def to_pet(pet: Mapping[str, Any]) -> Pet:
    data = {key: pet.get(key) for key in ("id", *_PET_FIELDS, "owners", "created_at")}
    data["breed"] = data["breed"] or ""
    data["owners"] = list(data["owners"] or [])
    data["created_at"] = str(data["created_at"] or "")
    return Pet.model_validate(data)
