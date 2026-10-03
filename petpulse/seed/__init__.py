"""Demo seed: load on first start, restore on ``POST /api/demo/reset``.

- ``seed_if_empty(store)``  writes the seed only when the store has no users and no pets
  (called at startup when ``SEED_ON_START=true``). Running it again is a no-op.
- ``reset_demo_data(store)`` wipes the store and writes the seed again. Pet ids are fixed, so
  the result is the same every time (timestamps move with "now").

The data itself lives in ``petpulse.seed.demo_data``.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, ContextManager, Optional, Protocol, runtime_checkable

from petpulse import pets as pet_records
from petpulse.seed.demo_data import DEMO_USERS, SEED_VERSION, DemoData, build
from petpulse.store.base import Store

__all__ = ["DEMO_USERS", "SEED_VERSION", "SeedSummary", "is_empty", "reset_demo_data", "seed_demo_data", "seed_if_empty"]

logger = logging.getLogger("petpulse.seed")

META_PATH = "meta/seed"

# Seeded notes are written in the contract Note shape to ``pets/{id}/notes`` and, while the
# legacy UI reads ``textinput`` / ``voice-notes``, mirrored there too. The notes track can turn
# this off once nothing reads the legacy collections.
LEGACY_NOTE_MIRROR = True
_LEGACY_KIND = {"MEDICAL": "MEDICAL", "DAILY_ACTIVITY": "DAILY_ACTIVITY"}  # everything else -> MIXED


@runtime_checkable
class _Clearable(Protocol):
    def clear(self) -> None: ...


@runtime_checkable
class _Batching(Protocol):
    def batch(self) -> ContextManager[None]: ...


@dataclass(frozen=True)
class SeedSummary:
    version: int
    users: int
    pets: int
    analytics: int
    notes: int

    def as_dict(self) -> dict[str, int]:
        return {
            "version": self.version,
            "users": self.users,
            "pets": self.pets,
            "analytics": self.analytics,
            "notes": self.notes,
        }


def is_empty(store: Store) -> bool:
    return not store.query(pet_records.USERS, limit=1) and not store.query(pet_records.PETS, limit=1)


def _batch(store: Store) -> ContextManager[None]:
    return store.batch() if isinstance(store, _Batching) else contextlib.nullcontext()


def _legacy_note(note: dict[str, Any], note_id: str) -> tuple[str, dict[str, Any]]:
    timestamp = str(note["created_at"]).removesuffix("+00:00")
    common = {
        "summary": note["summary"],
        "content_type": _LEGACY_KIND.get(note["kind"], "MIXED"),
        "timestamp": timestamp,
        "note_id": note_id,
    }
    if note["source"] == "voice":
        return "voice-notes", {"transcript": note["text"], **common}
    return "textinput", {"input": note["text"], "confidence": 1.0, "keywords": [], **common}


def _write(store: Store, data: DemoData, now: datetime) -> SeedSummary:
    analytics = notes = 0
    for user in data.users:
        pet_records.save_user(store, user["uid"], user["name"], email=user["email"], now=now)
    for pet in data.pets:
        pet_records.create_pet(store, pet.owner, pet.fields, pet_id=pet.id, now=now - timedelta(days=pet.created_days_ago))
        for entry in pet.analytics:
            store.add(f"pets/{pet.id}/analytics", entry)
            analytics += 1
        for note in pet.notes:
            note_id = store.add(f"pets/{pet.id}/notes", {**note, "pet_id": pet.id, "uid": pet.owner})
            notes += 1
            if LEGACY_NOTE_MIRROR:
                collection, legacy = _legacy_note(note, note_id)
                store.add(f"pets/{pet.id}/{collection}", legacy)
    summary = SeedSummary(SEED_VERSION, len(data.users), len(data.pets), analytics, notes)
    store.set(META_PATH, {**summary.as_dict(), "seeded_at": pet_records.utc_now_iso(now)})
    return summary


def seed_demo_data(store: Store, now: Optional[datetime] = None) -> SeedSummary:
    """Write the seed into ``store`` (does not check for existing data; see ``seed_if_empty``)."""
    moment = now or datetime.now(timezone.utc)
    with _batch(store):
        return _write(store, build(moment), moment)


def seed_if_empty(store: Store, now: Optional[datetime] = None) -> Optional[SeedSummary]:
    if not is_empty(store):
        return None
    summary = seed_demo_data(store, now)
    logger.info("loaded demo seed v%s: %s", summary.version, summary.as_dict())
    return summary


def reset_demo_data(store: Store, now: Optional[datetime] = None) -> SeedSummary:
    """Delete everything in ``store`` and write the seed again."""
    if not isinstance(store, _Clearable):
        raise NotImplementedError(f"{type(store).__name__} cannot be wiped; demo reset needs a clearable store")
    with _batch(store):
        store.clear()
        return seed_demo_data(store, now)
