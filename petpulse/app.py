"""The FastAPI app: ``create_app()`` wires middleware, startup and routers. No route bodies.

Run it with ``uvicorn petpulse.app:app``. The app imports and starts with no environment at all:
configuration lives in ``petpulse.core.config.Settings`` (every field has a demo-safe default),
and storage and AI providers are resolved lazily through ``petpulse.core.deps``. Nothing reads
key files or builds SDK clients at import time.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from petpulse import __version__, seed
from petpulse.core import errors
from petpulse.core.deps import get_blobs, get_settings, get_store
from petpulse.core.logging import configure_logging
from petpulse.routers import analytics, assistant, demo, health, insights, notes, pets, records, voice

PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"

# Registration order. Every /api route except /api/health, /api/auth/config, /api/demo/users and
# /api/demo/login needs a bearer token (petpulse.core.auth); routes that touch a pet also check
# that the caller owns it.
ROUTERS = (health, demo, pets, records, analytics, notes, assistant, insights, voice)

logger = logging.getLogger("petpulse.app")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    # Fail fast on contradictory provider config (e.g. LLM_PROVIDER=openai without a key).
    settings.check()
    logger.info(
        "mode=%s store=%s auth=%s llm=%s stt=%s",
        settings.overall_mode(),
        settings.resolved_store(),
        settings.resolved_auth(),
        settings.resolved_llm(),
        settings.resolved_stt(),
    )
    # Demo seed into an empty store (SEED_ON_START=true, the default). Skipped under Firebase
    # sign-in: the seeded owners are demo logins nobody could use there.
    if settings.seed_on_start and settings.resolved_auth() == "demo":
        seed.seed_if_empty(get_store(), blobs=get_blobs())
    yield


def create_app() -> FastAPI:
    # Load .env (if present) so local runs see the same values as Settings.
    load_dotenv()
    app = FastAPI(title="PetPulse", version=__version__, lifespan=lifespan)

    # Errors: one JSON shape ({"detail", "request_id"}), real status codes, no str(e) leaks on 500.
    errors.install(app)

    # CORS: explicit allow-list from settings (ALLOWED_ORIGINS). Auth is a bearer header, not a
    # cookie, so credentials are never allowed and no origin is reflected.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    for module in ROUTERS:
        app.include_router(module.router)

    # The UI last, so it never shadows an API route; html=True serves index.html at "/".
    app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="static")
    return app


app = create_app()
