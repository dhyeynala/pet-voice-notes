"""``GET /api/health``: liveness plus the Demo/Live mode of every AI-backed feature.

``GET /api/auth/config`` (public): which sign-in the UI should show, with the Firebase web
config when sign-in goes through Firebase (track G).
"""

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
        "store": settings.resolved_store(),
        "llm": settings.resolved_llm(),
        "stt": settings.resolved_stt(),
        "features": settings.feature_modes(),
        "auth": settings.resolved_auth(),
        "blobs": settings.resolved_blobs(),
    }


@router.get("/api/auth/config", tags=["auth"])
def auth_config(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    """Public. ``firebase`` is the browser SDK config (apiKey/authDomain/projectId), else ``null``."""
    web = settings.firebase_web_config()
    if web is None:
        return {"provider": "demo", "mode": "demo", "firebase": None}
    return {"provider": "firebase", "mode": "firebase", "firebase": web}
