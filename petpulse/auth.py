"""Demo authentication: HMAC-signed bearer tokens and ownership checks (review C1).

Tokens are ``v1.<payload>.<signature>`` where ``payload`` is base64url JSON
``{"uid": ..., "exp": <unix seconds>}`` and ``signature`` is base64url
HMAC-SHA256(secret, ``v1.<payload>``). The secret is ``AUTH_SECRET`` or, when that is unset, a
random value generated once per process (tokens then stop working after a restart, and the
client simply logs in again). Only the server can mint tokens, so the uid in a valid token is
trusted; a uid sent in a path, query or body never is.

FastAPI dependencies:

- ``current_user``        -> ``User`` or 401
- ``require_pet_access``  -> ``Pet`` or 404 (404, not 403, so pet ids can't be probed)
- ``require_self``        legacy ``/{user_id}`` routes: the path uid must be the caller (403)
- ``require_body_pet_access`` / ``require_query_pet_access``  legacy routes that name the pet
  in a JSON/form body or the query string instead of the path

With ``AUTH_PROVIDER`` resolving to ``firebase`` (track G), ``current_user`` accepts only Firebase
ID tokens instead, verified with the Admin SDK (signature, expiry, audience = our project); the
token's uid becomes ``User.uid``, so ownership checks are unchanged. Demo tokens are then rejected.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time
from typing import Any, Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from petpulse import firebase
from petpulse import pets as pet_records
from petpulse.config import Settings
from petpulse.deps import get_settings, get_store
from petpulse.errors import (
    ForbiddenError,
    NotFoundError,
    ServiceUnavailableError,
    UnauthorizedError,
    UnprocessableError,
)
from petpulse.schemas.pets import Pet, User
from petpulse.store.base import Store

__all__ = [
    "InvalidToken",
    "Pet",
    "User",
    "current_user",
    "issue_token",
    "require_body_pet_access",
    "require_pet_access",
    "require_query_pet_access",
    "require_self",
    "verify_token",
]

TOKEN_VERSION = "v1"
_generated_secret: Optional[bytes] = None
_bearer = HTTPBearer(auto_error=False, description="Demo token from POST /api/demo/login, or a Firebase ID token")


class InvalidToken(ValueError):
    """The token is missing, malformed, wrongly signed or expired."""


def _secret(settings: Settings) -> bytes:
    global _generated_secret
    if settings.auth_secret is not None:
        return settings.auth_secret.get_secret_value().encode("utf-8")
    if _generated_secret is None:
        _generated_secret = secrets.token_bytes(32)
    return _generated_secret


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def _sign(secret: bytes, message: str) -> str:
    return _b64encode(hmac.new(secret, message.encode("ascii"), hashlib.sha256).digest())


def issue_token(uid: str, *, settings: Optional[Settings] = None, now: Optional[float] = None) -> str:
    settings = settings or get_settings()
    issued = time.time() if now is None else now
    payload = {"uid": uid, "exp": int(issued + settings.auth_token_ttl_minutes * 60)}
    body = f"{TOKEN_VERSION}.{_b64encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))}"
    return f"{body}.{_sign(_secret(settings), body)}"


def verify_token(token: str, *, settings: Optional[Settings] = None, now: Optional[float] = None) -> str:
    """Return the uid in ``token`` or raise ``InvalidToken``."""
    settings = settings or get_settings()
    parts = token.split(".")
    if len(parts) != 3 or parts[0] != TOKEN_VERSION:
        raise InvalidToken("malformed token")
    body = f"{parts[0]}.{parts[1]}"
    if not hmac.compare_digest(_sign(_secret(settings), body), parts[2]):
        raise InvalidToken("bad signature")
    try:
        payload: Any = json.loads(_b64decode(parts[1]))
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise InvalidToken("malformed payload") from exc
    if not isinstance(payload, dict):
        raise InvalidToken("malformed payload")
    uid, exp = payload.get("uid"), payload.get("exp")
    if not isinstance(uid, str) or not pet_records.is_valid_id(uid) or not isinstance(exp, int):
        raise InvalidToken("malformed payload")
    if exp <= (time.time() if now is None else now):
        raise InvalidToken("expired")
    return uid


# ---------------------------------------------------------------------------- dependencies
def current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    settings: Settings = Depends(get_settings),
    store: Store = Depends(get_store),
) -> User:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("not authenticated")
    if settings.resolved_auth() == "firebase":
        return _firebase_user(credentials.credentials, settings, store)
    try:
        uid = verify_token(credentials.credentials, settings=settings)
    except InvalidToken:
        raise UnauthorizedError("invalid or expired token") from None
    return User(uid=uid, name=pet_records.display_name(store, uid))


def _firebase_user(token: str, settings: Settings, store: Store) -> User:
    """A verified Firebase ID token -> ``User``. Creates ``users/{uid}`` on first sign-in."""
    try:
        claims = firebase.verify_id_token(token, settings)
    except firebase.FirebaseTokenError:
        raise UnauthorizedError("invalid or expired token") from None
    except firebase.FirebaseUnavailable:
        raise ServiceUnavailableError("sign-in cannot be verified right now", code="auth_unavailable") from None
    uid = str(claims["uid"])
    if not pet_records.is_valid_id(uid):
        # Store paths can't hold it (Firebase's own uids are 28 alphanumerics, which always fit).
        raise UnauthorizedError("invalid or expired token")
    if pet_records.get_user(store, uid) is None:
        email = claims.get("email")
        pet_records.save_user(
            store,
            uid,
            firebase.display_name(claims) or "PetPulse user",
            email=email if isinstance(email, str) else "",
            demo=False,
        )
    return User(uid=uid, name=pet_records.display_name(store, uid))


def load_owned_pet(store: Store, user: User, pet_id: str) -> Pet:
    pet = pet_records.get_pet(store, pet_id)
    if pet is None or not pet_records.is_owner(pet, user.uid):
        raise NotFoundError("pet not found")
    return pet_records.to_pet(pet)


def require_pet_access(pet_id: str, user: User = Depends(current_user), store: Store = Depends(get_store)) -> Pet:
    """For routes with a ``{pet_id}`` path parameter: the pet, if the caller owns it."""
    return load_owned_pet(store, user, pet_id)


def require_self(user_id: str, user: User = Depends(current_user)) -> User:
    """Legacy ``/{user_id}`` routes: the uid in the path must be the signed-in user."""
    if user_id != user.uid:
        raise ForbiddenError("user id does not match the signed-in user")
    return user


async def _request_fields(request: Request) -> dict[str, Any]:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        form = await request.form()
        return {key: value for key, value in form.items() if isinstance(value, str)}
    try:
        data = await request.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


async def require_body_pet_access(
    request: Request, user: User = Depends(current_user), store: Store = Depends(get_store)
) -> Pet:
    """Legacy routes that send ``{"uid", "pet"}`` in a JSON or form body.

    ``pet`` must be a pet the caller owns (404); ``uid``, if sent, must be the caller (403).
    """
    fields = await _request_fields(request)
    uid = fields.get("uid")
    if uid not in (None, "") and uid != user.uid:
        raise ForbiddenError("uid does not match the signed-in user")
    pet_id = fields.get("pet")
    if not isinstance(pet_id, str) or not pet_id:
        raise UnprocessableError("pet is required")
    return load_owned_pet(store, user, pet_id)


def require_query_pet_access(
    pet: Optional[str] = None, user: User = Depends(current_user), store: Store = Depends(get_store)
) -> Optional[Pet]:
    """Legacy routes with an optional ``?pet=`` query parameter."""
    if pet is None or pet == "":
        return None
    return load_owned_pet(store, user, pet)
