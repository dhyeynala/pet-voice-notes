"""Typed analytics entries (review M7): ``POST``/``GET /api/pets/{pet_id}/analytics``.

Writes are validated against ``petpulse.schemas.analytics`` (one model per category,
``extra="forbid"``, bounded fields); only the validated fields plus server metadata are
stored. Reads skip rows whose timestamp cannot be parsed instead of failing (review M3).

The legacy handlers in ``api_server.py`` serve the same paths and delegate to
``create_entry`` / ``list_entries`` until they are removed, so both stay identical.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import ValidationError

from petpulse.deps import get_store
from petpulse.routers._auth_bridge import require_pet_access
from petpulse.schemas.analytics import CATEGORIES, ENTRY_MODELS, Entry, validate_entry
from petpulse.store.base import Store

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analytics"])

MAX_DAYS = 365


def utc_now() -> datetime:
    """Naive UTC "now", the format every legacy row and reader uses (timezones: LLM track)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse an ISO 8601 timestamp to naive UTC; ``None`` if missing or malformed."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _validation_detail(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors(include_url=False, include_input=False):
        loc = ".".join(str(p) for p in err.get("loc", ())) or "body"
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(parts)


def _check_category(category: str) -> None:
    if category not in ENTRY_MODELS:
        raise HTTPException(status_code=422, detail=f"unknown category {category!r}; expected one of {', '.join(CATEGORIES)}")


def create_entry(store: Store, pet_id: str, category: str, payload: Any) -> dict[str, Any]:
    """Validate and store one entry; returns the stored ``Entry`` as a dict."""
    _check_category(category)
    try:
        entry = validate_entry(category, payload)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_validation_detail(exc)) from exc
    doc = {
        **entry.model_dump(mode="json"),
        "category": category,
        "pet_id": pet_id,
        "timestamp": utc_now().isoformat(),
        "source": "form",
        "schema_version": 1,
    }
    entry_id = store.add(f"pets/{pet_id}/analytics", doc)
    return {"id": entry_id, **doc}


def list_entries(store: Store, pet_id: str, category: Optional[str] = None, days: int = 30) -> list[dict[str, Any]]:
    """Entries of the last ``days`` days, newest first. Rows with a bad timestamp are skipped."""
    if category is not None:
        _check_category(category)
    if not 1 <= days <= MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"days must be between 1 and {MAX_DAYS}")
    cutoff = utc_now() - timedelta(days=days)
    where: list[Any] = [("category", "==", category)] if category else []
    rows: list[tuple[datetime, dict[str, Any]]] = []
    skipped = 0
    for doc_id, doc in store.query(f"pets/{pet_id}/analytics", where=where):
        ts = parse_timestamp(doc.get("timestamp"))
        if ts is None or not isinstance(doc.get("category"), str):
            skipped += 1
            continue
        if ts >= cutoff:
            rows.append((ts, {**doc, "id": doc_id, "pet_id": pet_id}))
    if skipped:
        logger.warning("analytics: skipped %d row(s) with a missing/invalid timestamp or category (pet=%s)", skipped, pet_id)
    rows.sort(key=lambda row: row[0], reverse=True)
    return [doc for _, doc in rows]


@router.post(
    "/api/pets/{pet_id}/analytics/{category}",
    response_model=Entry,
    status_code=201,
    dependencies=[Depends(require_pet_access)],
)
def post_entry(
    pet_id: str,
    category: str,
    payload: dict[str, Any] = Body(...),
    store: Store = Depends(get_store),
) -> dict[str, Any]:
    return create_entry(store, pet_id, category, payload)


@router.get(
    "/api/pets/{pet_id}/analytics",
    response_model=list[Entry],
    dependencies=[Depends(require_pet_access)],
)
def get_entries(
    pet_id: str,
    category: Optional[str] = None,
    days: int = Query(30),
    store: Store = Depends(get_store),
) -> list[dict[str, Any]]:
    return list_entries(store, pet_id, category, days)
