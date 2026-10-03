"""Bridge to the auth dependencies owned by the auth track (``petpulse.auth``).

Routes in this package depend on ``current_user`` and ``require_pet_access`` exactly as the
API contract names them. While ``petpulse.auth`` does not exist yet, both names resolve to
fail-closed stand-ins that answer **401 for every request**, so nothing is ever served
unauthenticated. As soon as ``petpulse.auth`` lands, the real dependencies are picked up here
without code changes. Once it has landed, import from ``petpulse.auth`` directly and delete
this module.

Tests override these objects through ``app.dependency_overrides``; because the names are the
real functions once ``petpulse.auth`` exists, the same overrides keep working afterwards.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

from fastapi import HTTPException

_AUTH_MODULE = "petpulse.auth"


def _current_user_unavailable() -> Any:
    raise HTTPException(status_code=401, detail="authentication is not configured")


def _require_pet_access_unavailable(pet_id: str) -> Any:
    raise HTTPException(status_code=401, detail="authentication is not configured")


_FALLBACKS: dict[str, Callable[..., Any]] = {
    "current_user": _current_user_unavailable,
    "require_pet_access": _require_pet_access_unavailable,
}


def _resolve(name: str) -> Callable[..., Any]:
    try:
        module = importlib.import_module(_AUTH_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != _AUTH_MODULE:
            raise  # petpulse.auth exists but one of *its* imports is broken: fail loudly
        return _FALLBACKS[name]
    dependency: Callable[..., Any] = getattr(module, name)
    return dependency


current_user: Callable[..., Any] = _resolve("current_user")
require_pet_access: Callable[..., Any] = _resolve("require_pet_access")
