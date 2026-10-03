"""``POST /api/pets/{pet_id}/chat``: grounded chat (shared API contract, Track C)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from petpulse.deps import get_llm, get_store
from petpulse.providers.llm import LLMProvider
from petpulse.auth import current_user, require_pet_access
from petpulse.services.assistant import MAX_MESSAGE_CHARS, AssistantUnavailable, ChatResponse, answer_question
from petpulse.store.base import Store

router = APIRouter(tags=["assistant"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)
    tz: str = Field(default="UTC", min_length=1, max_length=64)


async def run_chat(pet_id: str, body: ChatRequest, user: Any, pet: Any, store: Store, llm: LLMProvider) -> ChatResponse:
    try:
        return await answer_question(
            pet_id, user.uid, body.message, body.tz, store=store, llm=llm, pet_name=getattr(pet, "name", None)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AssistantUnavailable as exc:
        raise HTTPException(
            status_code=503, detail=f"the assistant is unavailable ({exc.reason}); nothing was invented"
        ) from exc


@router.post("/api/pets/{pet_id}/chat", response_model=ChatResponse)
async def chat(
    pet_id: str,
    body: ChatRequest,
    user: Any = Depends(current_user),
    pet: Any = Depends(require_pet_access),
    store: Store = Depends(get_store),
    llm: LLMProvider = Depends(get_llm),
) -> ChatResponse:
    return await run_chat(pet_id, body, user, pet, store, llm)
