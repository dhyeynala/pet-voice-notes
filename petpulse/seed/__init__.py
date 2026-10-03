"""Demo seed: load on first start, restore on ``POST /api/demo/reset``.

- ``seed_if_empty(store)``  writes the seed only when the store has no users and no pets
  (called at startup when ``SEED_ON_START=true``). Running it again is a no-op.
- ``reset_demo_data(store)`` wipes the store and writes the seed again. Pet ids are fixed, so
  the result is the same every time (timestamps move with "now").

Pass ``blobs`` to also seed one sample vet-record PDF for Alice's Max (through the records
router's ``create_record``, so it is stored and summarized like an upload) and, on reset, to
delete the blobs of the records being wiped. The PDF is only seeded while the LLM provider
resolves to the fake: seeding must never make a billed live call at startup.

The data itself lives in ``petpulse.seed.demo_data``.
"""

from __future__ import annotations

import contextlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, ContextManager, Optional, Protocol, runtime_checkable

from petpulse import pets as pet_records
from petpulse.seed.demo_data import ALICE_MAX_ID, DEMO_USERS, SEED_VERSION, DemoData, build
from petpulse.store.base import Store
from petpulse.store.blobs import BlobStore

__all__ = ["DEMO_USERS", "SEED_VERSION", "SeedSummary", "is_empty", "reset_demo_data", "seed_demo_data", "seed_if_empty"]

logger = logging.getLogger("petpulse.seed")

META_PATH = "meta/seed"


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
    records: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "version": self.version,
            "users": self.users,
            "pets": self.pets,
            "analytics": self.analytics,
            "notes": self.notes,
            "records": self.records,
        }


def is_empty(store: Store) -> bool:
    return not store.query(pet_records.USERS, limit=1) and not store.query(pet_records.PETS, limit=1)


def _batch(store: Store) -> ContextManager[None]:
    return store.batch() if isinstance(store, _Batching) else contextlib.nullcontext()


SAMPLE_RECORD_FILENAME = "maple-street-vet-visit.pdf"
SAMPLE_RECORD_DAYS_AGO = 12  # matches the seeded vet-visit exit event
SAMPLE_RECORD_LINES = (
    "Maple Street Veterinary Clinic - visit summary (synthetic demo record)",
    "Patient: Max, Golden Retriever, 6 years, 68.0 lbs. Owner: Alice.",
    "Reason for visit: wellness exam; scratching ears and shaking head.",
    "Findings: mild otitis externa, left ear. Heart and lungs normal. Coat good.",
    "Plan: continue Apoquel 16 mg once daily for itching.",
    "Clean ears twice weekly with an ear cleanser. Recheck in 2 weeks.",
)


def sample_record_pdf() -> bytes:
    """A tiny one-page synthetic vet note (no real data)."""
    import pymupdf

    doc: Any = pymupdf.open()  # type: ignore[no-untyped-call]
    page = doc.new_page()
    for i, line in enumerate(SAMPLE_RECORD_LINES):
        page.insert_text((56, 72 + 18 * i), line, fontsize=11)
    data: bytes = doc.tobytes()
    doc.close()
    return data


def _llm_is_fake() -> bool:
    from petpulse.deps import get_settings

    return get_settings().resolved_llm() == "fake"


def _seed_record(store: Store, blobs: BlobStore, now: datetime) -> int:
    from petpulse.routers.records import create_record_sync  # lazy: pulls in PyMuPDF

    record = create_record_sync(store, blobs, ALICE_MAX_ID, sample_record_pdf(), SAMPLE_RECORD_FILENAME)
    when = (now - timedelta(days=SAMPLE_RECORD_DAYS_AGO)).astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)
    stamp = when.replace(hour=18, minute=0).isoformat()
    store.set(f"pets/{ALICE_MAX_ID}/records/{record['id']}", {"created_at": stamp, "timestamp": stamp}, merge=True)
    return 1


def _delete_record_blobs(store: Store, blobs: BlobStore) -> None:
    for pet_id, _ in store.query(pet_records.PETS):
        for _, record in store.query(f"pets/{pet_id}/records"):
            key = record.get("blob_key")
            if isinstance(key, str) and key:
                try:
                    blobs.delete(key)
                except (OSError, ValueError):
                    logger.warning("could not delete blob %s during demo reset", key)


def _write(store: Store, data: DemoData, now: datetime, blobs: Optional[BlobStore] = None) -> SeedSummary:
    analytics = notes = 0
    for user in data.users:
        pet_records.save_user(store, user["uid"], user["name"], email=user["email"], now=now)
    for pet in data.pets:
        pet_records.create_pet(store, pet.owner, pet.fields, pet_id=pet.id, now=now - timedelta(days=pet.created_days_ago))
        for entry in pet.analytics:
            store.add(f"pets/{pet.id}/analytics", entry)
            analytics += 1
        for note in pet.notes:
            store.add(f"pets/{pet.id}/notes", {**note, "pet_id": pet.id, "uid": pet.owner})
            notes += 1
    records = 0
    if blobs is not None:
        if _llm_is_fake():
            records = _seed_record(store, blobs, now)
        else:
            logger.info("live LLM configured: skipping the sample PDF record (no billed calls while seeding)")
    summary = SeedSummary(SEED_VERSION, len(data.users), len(data.pets), analytics, notes, records)
    store.set(META_PATH, {**summary.as_dict(), "seeded_at": pet_records.utc_now_iso(now)})
    return summary


def seed_demo_data(store: Store, now: Optional[datetime] = None, blobs: Optional[BlobStore] = None) -> SeedSummary:
    """Write the seed into ``store`` (does not check for existing data; see ``seed_if_empty``)."""
    moment = now or datetime.now(timezone.utc)
    with _batch(store):
        return _write(store, build(moment), moment, blobs)


def seed_if_empty(store: Store, now: Optional[datetime] = None, blobs: Optional[BlobStore] = None) -> Optional[SeedSummary]:
    if not is_empty(store):
        return None
    summary = seed_demo_data(store, now, blobs)
    logger.info("loaded demo seed v%s: %s", summary.version, summary.as_dict())
    return summary


def reset_demo_data(store: Store, now: Optional[datetime] = None, blobs: Optional[BlobStore] = None) -> SeedSummary:
    """Delete everything in ``store`` (and, with ``blobs``, the record files) and reseed."""
    if not isinstance(store, _Clearable):
        raise NotImplementedError(f"{type(store).__name__} cannot be wiped; demo reset needs a clearable store")
    with _batch(store):
        if blobs is not None:
            _delete_record_blobs(store, blobs)
        store.clear()
        return seed_demo_data(store, now, blobs)
