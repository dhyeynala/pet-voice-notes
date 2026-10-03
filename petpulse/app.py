"""The FastAPI app: middleware, startup hooks and router registration. No route bodies.

The app imports and starts with no environment at all. Configuration lives in
``petpulse.core.config.Settings`` (every field has a demo-safe default); storage and AI
providers are resolved lazily through ``petpulse.core.deps``. Nothing reads key files or
builds SDK clients at import time.
"""

from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from petpulse import seed
from petpulse.core import errors
from petpulse.core.deps import get_blobs, get_settings, get_store
from petpulse.routers import analytics as analytics_router
from petpulse.routers import assistant as assistant_router
from petpulse.routers import demo as demo_router
from petpulse.routers import health as health_router
from petpulse.routers import insights as insights_router
from petpulse.routers import legacy as legacy_router
from petpulse.routers import notes as notes_router
from petpulse.routers import pets as pets_router
from petpulse.routers import records as records_router
from petpulse.routers import voice as voice_router

# Load .env (if present) so local runs see the same values as Settings.
load_dotenv()

PUBLIC_DIR = Path(__file__).resolve().parents[1] / "public"

app = FastAPI(title="PetPulse")

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


@app.on_event("startup")
async def startup_event() -> None:
    # Fail fast on contradictory provider config (e.g. LLM_PROVIDER=openai without a key).
    settings = get_settings()
    settings.check()
    print(
        f"Mode: {settings.overall_mode()} | store={settings.resolved_store()} auth={settings.resolved_auth()} "
        f"llm={settings.resolved_llm()} stt={settings.resolved_stt()}"
    )


@app.on_event("startup")
async def load_demo_seed() -> None:
    """Load the demo seed into an empty store (SEED_ON_START=true, the default).

    Skipped under Firebase sign-in: the seeded owners are demo logins nobody could use there.
    """
    settings = get_settings()
    if settings.seed_on_start and settings.resolved_auth() == "demo":
        seed.seed_if_empty(get_store(), blobs=get_blobs())


# Every /api route except /api/health, /api/auth/config, /api/demo/users and /api/demo/login
# needs a bearer token (petpulse.core.auth); routes that touch a pet also check that the caller owns it.
app.include_router(health_router.router)
app.include_router(demo_router.router)
app.include_router(pets_router.router)
app.include_router(records_router.router)
app.include_router(analytics_router.router)
app.include_router(notes_router.router)
app.include_router(assistant_router.router)
app.include_router(insights_router.router)
app.include_router(voice_router.router)
app.include_router(legacy_router.router)


# Serve index last to avoid route shadowing
@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(PUBLIC_DIR / "index.html")


app.mount("/", StaticFiles(directory=PUBLIC_DIR, html=True), name="static")
