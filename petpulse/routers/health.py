"""``GET /api/health``: liveness plus the Demo/Live mode of every AI-backed feature."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from petpulse import __version__
from petpulse.config import Settings
from petpulse.deps import get_settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "status": "healthy",
        "version": __version__,
        "mode": settings.overall_mode(),
        "store": settings.store,
        "llm": settings.resolved_llm(),
        "stt": settings.resolved_stt(),
        "features": settings.feature_modes(),
    }
