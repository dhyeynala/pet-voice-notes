"""Pre-contract routes kept for old clients. The bundled UI no longer calls any of them.

Each one has a contract replacement (``docs/api-contract.md``) except markdown, and each is
auth + ownership protected like every other ``/api`` route:

- ``POST /api/upload_pdf``  form ``pet`` + ``file``   -> use ``POST /api/pets/{pet_id}/records``
- ``GET  /api/user-pets/{user_id}``                   -> use ``GET /api/me/pets``
- ``POST /api/pets/{user_id}``                        -> use ``POST /api/pets``
- ``GET|POST /api/markdown``  free-form markdown stored on the pet (``pets/{id}.markdown``)

Delete this module (and ``require_self`` / ``require_body_pet_access`` /
``require_query_pet_access`` in ``petpulse.core.auth``) once nothing calls these routes.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Request, UploadFile

from petpulse.auth import Pet, User, current_user, require_body_pet_access, require_query_pet_access, require_self
from petpulse.deps import get_blobs, get_llm, get_store
from petpulse.errors import UnprocessableError
from petpulse import pets as pet_records
from petpulse.providers.llm import LLMProvider
from petpulse.routers import records as records_router
from petpulse.store.base import Store
from petpulse.store.blobs import BlobStore

logger = logging.getLogger(__name__)

router = APIRouter(tags=["legacy"])


@router.post("/api/upload_pdf")
async def upload_pdf(
    file: UploadFile = File(...),
    pet: Pet = Depends(require_body_pet_access),
    user: User = Depends(current_user),
    store: Store = Depends(get_store),
    blobs: BlobStore = Depends(get_blobs),
    llm: LLMProvider = Depends(get_llm),
) -> dict[str, Any]:
    """Same validation and storage as ``POST /api/pets/{pet_id}/records`` (review C3)."""
    data = await records_router.read_capped(file)
    record = await records_router.create_record(store, blobs, pet.id, data, file.filename, uid=user.uid, llm=llm)
    # No public URL: the original is served by the owner-checked records/{id}/file route.
    return {"message": "PDF processed", "summary": record["summary"], "url": None, "record": record}


@router.get("/api/user-pets/{user_id}", dependencies=[Depends(require_self)])
def user_pets(user_id: str, store: Store = Depends(get_store)) -> list[dict[str, Any]]:
    return pet_records.list_pets(store, user_id)


@router.post("/api/pets/{user_id}", dependencies=[Depends(require_self)])
async def create_pet_for_user(user_id: str, request: Request, store: Store = Depends(get_store)) -> dict[str, Any]:
    data = await request.json()
    if not isinstance(data, dict) or not data.get("name"):
        raise UnprocessableError("Pet name is required")
    if not data.get("animal_type"):
        raise UnprocessableError("Animal type is required")
    return {"status": "success", "pet": pet_records.create_pet(store, user_id, data)}


# Markdown lives on the (owned) pet; ``page`` is accepted from old clients and ignored (C2).
@router.get("/api/markdown")
def get_markdown(pet: Optional[Pet] = Depends(require_query_pet_access), store: Store = Depends(get_store)) -> dict[str, str]:
    if pet is None:
        return {"markdown": ""}
    doc = store.get(f"pets/{pet.id}") or {}
    markdown = doc.get("markdown")
    return {"markdown": markdown if isinstance(markdown, str) else ""}


@router.post("/api/markdown")
async def update_markdown(
    request: Request, pet: Pet = Depends(require_body_pet_access), store: Store = Depends(get_store)
) -> dict[str, str]:
    data = await request.json()
    markdown = data.get("markdown", "") if isinstance(data, dict) else ""
    if not isinstance(markdown, str):
        raise UnprocessableError("markdown must be a string")
    store.set(f"pets/{pet.id}", {"markdown": markdown}, merge=True)
    return {"status": "updated"}
