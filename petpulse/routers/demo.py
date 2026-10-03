"""Demo login and reset (demo mode only; every route here 404s when ``DEMO_MODE=false``).

- ``GET  /api/demo/users``  public: who you can log in as
- ``POST /api/demo/login``  public: ``{"uid": "alice"}`` (or ``{"name": "Sam"}`` to create a new
  demo user) -> ``{"token", "user": {"uid", "name"}}``
- ``POST /api/demo/reset``  authenticated: wipe the store and restore the seed

In Firebase sign-in mode (``AUTH_PROVIDER`` resolves to ``firebase``) all three return 404 with
``code: "demo_login_disabled"``; with the Firestore store, reset returns 409 (``code:
"reset_disabled"``) so a signed-in user can never wipe a real project.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends

from petpulse import pets as pet_records
from petpulse import seed
from petpulse.auth import current_user, issue_token
from petpulse.config import Settings
from petpulse.deps import get_blobs, get_settings, get_store
from petpulse.errors import ConflictError, NotFoundError, UnprocessableError
from petpulse.schemas.pets import DemoLogin, DemoUser, LoginResponse, User
from petpulse.store.base import Store
from petpulse.store.blobs import BlobStore

router = APIRouter(tags=["demo"])


def require_demo_mode(settings: Settings = Depends(get_settings)) -> None:
    if not settings.demo_mode:
        raise NotFoundError("not found")
    if settings.resolved_auth() == "firebase":
        raise NotFoundError("demo login is disabled: this server uses Firebase sign-in", code="demo_login_disabled")


@router.get("/api/demo/users", response_model=list[DemoUser], dependencies=[Depends(require_demo_mode)])
def list_demo_users(store: Store = Depends(get_store)) -> list[DemoUser]:
    seeded = [
        DemoUser(uid=u["uid"], name=str((pet_records.get_user(store, u["uid"]) or {}).get("name") or u["name"]))
        for u in seed.DEMO_USERS
    ]
    seeded_ids = {u.uid for u in seeded}
    extra = sorted(
        (
            DemoUser(uid=uid, name=str(doc.get("name") or uid))
            for uid, doc in store.query(pet_records.USERS, where=[("demo", "==", True)])
            if uid not in seeded_ids
        ),
        key=lambda u: (u.name.lower(), u.uid),
    )
    return seeded + extra


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:24] or "user"


@router.post("/api/demo/login", response_model=LoginResponse, dependencies=[Depends(require_demo_mode)])
def demo_login(body: DemoLogin, store: Store = Depends(get_store)) -> LoginResponse:
    if (body.uid is None) == (body.name is None):
        raise UnprocessableError("send exactly one of uid or name")
    if body.name is not None:
        uid = f"{_slug(body.name)}-{uuid.uuid4().hex[:8]}"
        user = pet_records.save_user(store, uid, body.name)
    else:
        assert body.uid is not None
        uid = body.uid
        known = {u["uid"]: u for u in seed.DEMO_USERS}
        record = pet_records.get_user(store, uid)
        if record is None and uid in known:
            # Store not seeded (SEED_ON_START=false): seeded users can still log in.
            pet_records.save_user(store, uid, known[uid]["name"], email=known[uid]["email"])
        elif record is None:
            raise NotFoundError("unknown demo user")
        user = User(uid=uid, name=pet_records.display_name(store, uid))
    return LoginResponse(token=issue_token(user.uid), user=user)


@router.post("/api/demo/reset", dependencies=[Depends(require_demo_mode)])
def demo_reset(
    user: User = Depends(current_user),
    store: Store = Depends(get_store),
    blobs: BlobStore = Depends(get_blobs),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    if settings.resolved_store() == "firestore":
        raise ConflictError("demo reset is disabled with the Firestore store", code="reset_disabled")
    summary = seed.reset_demo_data(store, blobs=blobs)
    return {"status": "reset", "seed": summary.as_dict()}
