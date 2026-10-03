"""Transitional seam for the auth dependencies owned by Track A (``petpulse.auth``).

The Track C routers depend on ``current_user`` and ``require_pet_access`` by name. Until
``petpulse/auth.py`` is on the integration branch, both resolve to fail-closed stand-ins
(401, nothing is ever served unauthenticated). Once it lands this module just re-exports the
real functions; it can then be replaced by a direct import.
"""

from __future__ import annotations

import importlib
from typing import Any, Callable

from fastapi import HTTPException


def _pending_current_user() -> Any:
    raise HTTPException(status_code=401, detail="authentication required")


def _pending_require_pet_access(pet_id: str) -> Any:
    raise HTTPException(status_code=401, detail="authentication required")


def _load() -> tuple[Callable[..., Any], Callable[..., Any]]:
    try:
        module = importlib.import_module("petpulse.auth")
    except ModuleNotFoundError as exc:
        if exc.name != "petpulse.auth":
            raise
        return _pending_current_user, _pending_require_pet_access
    return module.current_user, module.require_pet_access


current_user, require_pet_access = _load()
