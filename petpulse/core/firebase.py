"""Optional Firebase mode: the Admin SDK app and ID-token verification.

``firebase_admin`` is imported lazily, only when Firebase is actually used, so the default
install and the Docker image do not need it (it lives in ``requirements-live.txt``).
``Settings.check()`` refuses to start when Firebase is selected but the package is missing.

The backend uses the Admin SDK, which bypasses Firestore security rules: every route still goes
through ``current_user`` / ``require_pet_access``. ``firestore.rules`` only guards direct client
access to the database.
"""

from __future__ import annotations

import importlib
import threading
from typing import Any, Optional

from petpulse.core.config import ConfigError, Settings

APP_NAME = "petpulse"

_lock = threading.Lock()
_app: Any = None


class FirebaseTokenError(ValueError):
    """The ID token is missing, malformed, wrongly signed, expired, revoked or for another project."""


class FirebaseUnavailable(RuntimeError):
    """The token could not be checked right now (Google's signing certificates are unreachable)."""


def _import(name: str) -> Any:
    try:
        return importlib.import_module(name)
    except ImportError as exc:  # pragma: no cover - guarded by Settings.check() at startup
        raise ConfigError("Firebase mode needs firebase-admin: pip install -r requirements-live.txt") from exc


def get_app(settings: Settings) -> Any:
    """The process-wide ``firebase_admin.App`` (created on first use)."""
    global _app
    with _lock:
        if _app is None:
            firebase_admin = _import("firebase_admin")
            credentials = _import("firebase_admin.credentials")
            info, _ = settings.firebase_credentials()
            if info is None:
                # Settings.check() guarantees this; never fall back to Application Default Credentials.
                raise ConfigError("Firebase mode requires service-account credentials (see docs/firebase.md)")
            credential = credentials.Certificate(info)
            options: dict[str, str] = {}
            project = settings.firebase_project()
            if project:
                options["projectId"] = project
            if settings.firebase_storage_bucket:
                options["storageBucket"] = settings.firebase_storage_bucket
            _app = firebase_admin.initialize_app(credential, options, name=APP_NAME)
        return _app


def reset() -> None:
    """Forget the app (tests, ``deps.reset``). Never imports ``firebase_admin``."""
    global _app
    with _lock:
        app, _app = _app, None
    if app is not None:
        try:
            _import("firebase_admin").delete_app(app)
        except (ValueError, ConfigError):
            pass


def verify_id_token(token: str, settings: Settings) -> dict[str, Any]:
    """Verify a Firebase ID token (signature, expiry, audience = our project); return its claims.

    Raises ``FirebaseTokenError`` for any token problem (fail closed) and ``FirebaseUnavailable``
    when the signing certificates cannot be fetched.
    """
    if not token or len(token) > 8192:
        raise FirebaseTokenError("malformed token")
    app = get_app(settings)
    auth = _import("firebase_admin.auth")
    try:
        claims: Any = auth.verify_id_token(token, app=app, check_revoked=False)
    except auth.CertificateFetchError as exc:
        raise FirebaseUnavailable("could not fetch Firebase signing certificates") from exc
    except Exception as exc:  # InvalidIdTokenError, ExpiredIdTokenError, ValueError, ...: all fail closed
        raise FirebaseTokenError(type(exc).__name__) from None
    if not isinstance(claims, dict):
        raise FirebaseTokenError("malformed claims")
    uid = claims.get("uid") or claims.get("sub")
    if not isinstance(uid, str) or not uid:
        raise FirebaseTokenError("token has no uid")
    return {**claims, "uid": uid}


def display_name(claims: dict[str, Any]) -> Optional[str]:
    for key in ("name", "email"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()[:80]
    return None
