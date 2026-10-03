"""``GET /api/pets/{pet_id}/insights``: facts and alerts computed by code (Track C)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from petpulse.config import Settings
from petpulse.deps import get_settings, get_store
from petpulse.routers._auth import require_pet_access
from petpulse.services.assistant import pet_name_for
from petpulse.services.events import load_events
from petpulse.services.insights import Insights, Mode, compute_insights
from petpulse.store.base import Store
from petpulse.timeutil import InvalidTimezone, utc_now, validate_tz

router = APIRouter(tags=["insights"])


@router.get("/api/pets/{pet_id}/insights", response_model=Insights)
def get_insights(
    pet_id: str,
    tz: str = Query(default="UTC", min_length=1, max_length=64),
    pet: Any = Depends(require_pet_access),
    store: Store = Depends(get_store),
    settings: Settings = Depends(get_settings),
) -> Insights:
    try:
        zone = validate_tz(tz)
    except InvalidTimezone as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # No model call here; ``mode`` mirrors /api/health ``features.insights`` for the UI badge.
    mode: Mode = "demo" if settings.feature_modes()["insights"]["mode"] == "demo" else "live"
    name = getattr(pet, "name", None) or pet_name_for(store, pet_id)
    return compute_insights(load_events(store, pet_id), tz=zone, now=utc_now(), pet_name=str(name), mode=mode)
