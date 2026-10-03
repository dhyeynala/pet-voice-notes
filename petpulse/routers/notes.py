"""``POST/GET /api/pets/{pet_id}/notes`` (shared API contract, Track C)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from petpulse.deps import get_llm, get_store
from petpulse.providers.llm import LLMProvider
from petpulse.auth import current_user, require_pet_access
from petpulse.services.notes import MAX_NOTE_CHARS, Note, list_notes, process_note
from petpulse.store.base import Store

router = APIRouter(tags=["notes"])


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_NOTE_CHARS)
    tz: str = Field(default="UTC", min_length=1, max_length=64)


@router.post("/api/pets/{pet_id}/notes", response_model=Note, status_code=201)
async def create_note(
    pet_id: str,
    body: NoteCreate,
    user: Any = Depends(current_user),
    pet: Any = Depends(require_pet_access),
    store: Store = Depends(get_store),
    llm: LLMProvider = Depends(get_llm),
) -> Note:
    try:
        return await process_note(pet_id, user.uid, body.text, "text", body.tz, store=store, llm=llm)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/pets/{pet_id}/notes", response_model=list[Note])
def get_notes(
    pet_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    pet: Any = Depends(require_pet_access),
    store: Store = Depends(get_store),
) -> list[Note]:
    return list_notes(store, pet_id, limit)
