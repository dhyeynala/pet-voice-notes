"""Cached factories for settings, storage and providers.

Routes take these as FastAPI dependencies (``Depends(get_store)``), so tests can use
``app.dependency_overrides``. Code that is not dependency-injected (the seed, services called
outside a request) calls the same functions directly; ``override()`` swaps the instances for
both paths at once.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from petpulse.core import firebase
from petpulse.core.config import Settings
from petpulse.providers.llm import FakeLLM, LLMProvider, OpenAILLM
from petpulse.providers.stt import FakeSTT, GoogleSTT, OpenAISTT, STTProvider
from petpulse.store.base import Store
from petpulse.store.blobs import BlobStore, LocalBlobStore
from petpulse.store.memory import JsonFileStore, MemoryStore

_overrides: dict[str, Any] = {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


@lru_cache(maxsize=1)
def _build_store() -> Store:
    settings = get_settings()
    resolved = settings.resolved_store()
    if resolved == "firestore":
        return _firestore_store(settings)
    if resolved == "memory":
        return MemoryStore()
    return JsonFileStore(settings.data_dir / "db.json")


@lru_cache(maxsize=1)
def _build_blobs() -> BlobStore:
    settings = get_settings()
    if settings.resolved_blobs() == "firebase":
        return _firebase_blobs(settings)
    return LocalBlobStore(settings.data_dir / "blobs")


def _firestore_store(settings: Settings) -> Store:
    # Lazy: firebase_admin is an optional dependency (requirements-live.txt).
    from petpulse.store.firestore import FirestoreStore

    settings.check()
    return FirestoreStore.from_app(firebase.get_app(settings))


def _firebase_blobs(settings: Settings) -> BlobStore:
    from petpulse.store.firestore import FirebaseBlobStore

    settings.check()
    return FirebaseBlobStore.from_app(firebase.get_app(settings))


def _openai_key(settings: Settings) -> str:
    settings.check()
    assert settings.openai_api_key is not None  # guaranteed by check()
    return settings.openai_api_key.get_secret_value()


@lru_cache(maxsize=1)
def _build_llm() -> LLMProvider:
    settings = get_settings()
    if settings.resolved_llm() == "openai":
        return OpenAILLM(api_key=_openai_key(settings), model=settings.openai_model, timeout=settings.llm_timeout_seconds)
    return FakeLLM(mode=settings.fake_llm_mode)


@lru_cache(maxsize=1)
def _build_stt() -> STTProvider:
    settings = get_settings()
    choice = settings.resolved_stt()
    if choice == "openai":
        return OpenAISTT(
            api_key=_openai_key(settings),
            model=settings.stt_openai_model,
            timeout=settings.stt_timeout_seconds,
            language=settings.stt_language,
        )
    if choice == "google":
        settings.check()
        return GoogleSTT(
            credentials_path=settings.google_application_credentials,
            language_code=settings.stt_language,
            timeout=settings.stt_timeout_seconds,
            model=settings.stt_google_model,
        )
    return FakeSTT()


def get_store() -> Store:
    return _overrides["store"] if "store" in _overrides else _build_store()


def get_blobs() -> BlobStore:
    return _overrides["blobs"] if "blobs" in _overrides else _build_blobs()


def get_llm() -> LLMProvider:
    return _overrides["llm"] if "llm" in _overrides else _build_llm()


def get_stt() -> STTProvider:
    return _overrides["stt"] if "stt" in _overrides else _build_stt()


def override(**instances: Any) -> None:
    """Replace ``store``, ``blobs``, ``llm`` and/or ``stt`` for every caller (tests)."""
    unknown = set(instances) - {"store", "blobs", "llm", "stt"}
    if unknown:
        raise TypeError(f"unknown override(s): {sorted(unknown)}")
    _overrides.update(instances)


def reset() -> None:
    """Drop overrides and cached instances; the next call re-reads the environment."""
    _overrides.clear()
    firebase.reset()  # never imports firebase_admin
    for factory in (get_settings, _build_store, _build_blobs, _build_llm, _build_stt):
        factory.cache_clear()
