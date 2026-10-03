"""Shared fixtures: a hermetic demo app on ``MemoryStore`` with the deterministic fakes.

Every test runs with:
- no OpenAI/Google credentials (providers on ``auto`` resolve to the fakes),
- a fresh ``MemoryStore`` / ``FakeLLM`` / ``FakeSTT`` / ``LocalBlobStore`` (under ``tmp_path``),
- outbound network blocked.

The same instances are visible to new-style routes (via ``app.dependency_overrides``) and to
legacy modules (via ``petpulse.deps.override``).
"""

from __future__ import annotations

import os
import socket
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
os.chdir(ROOT)  # legacy tests use repo-relative paths

DEMO_ENV = {
    "DEMO_MODE": "true",
    "STORE": "memory",
    "LLM_PROVIDER": "auto",
    "STT_PROVIDER": "auto",
    "OPENAI_API_KEY": "",
    "GOOGLE_APPLICATION_CREDENTIALS": "",
    "AUTH_SECRET": "",
    "SEED_ON_START": "false",
    "DOG_API_KEY": "",
    "CAT_API_KEY": "",
}


@pytest.fixture(autouse=True)
def _hermetic_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[None]:
    from petpulse import deps

    for key, value in DEMO_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
    deps.reset()
    yield
    deps.reset()


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly on any outbound TCP/UDP connection (AF_UNIX stays allowed)."""
    real_connect = socket.socket.connect

    def guarded_connect(self: socket.socket, address: Any) -> Any:
        if self.family in (socket.AF_INET, socket.AF_INET6):
            host = address[0] if isinstance(address, tuple) else address
            if host not in ("127.0.0.1", "::1", "localhost"):
                raise RuntimeError(f"network access blocked in tests: {address!r}")
        return real_connect(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)


@pytest.fixture
def store():
    from petpulse.store.memory import MemoryStore

    return MemoryStore()


@pytest.fixture
def blobs(tmp_path: Path):
    from petpulse.store.blobs import LocalBlobStore

    return LocalBlobStore(tmp_path / "blobs")


@pytest.fixture
def fake_llm():
    from petpulse.providers.llm import FakeLLM

    return FakeLLM()


@pytest.fixture
def fake_stt():
    from petpulse.providers.stt import FakeSTT

    return FakeSTT()


@pytest.fixture
def app(store, blobs, fake_llm, fake_stt):
    import api_server
    from petpulse import deps

    deps.override(store=store, blobs=blobs, llm=fake_llm, stt=fake_stt)
    api_server.app.dependency_overrides.update(
        {
            deps.get_store: lambda: store,
            deps.get_blobs: lambda: blobs,
            deps.get_llm: lambda: fake_llm,
            deps.get_stt: lambda: fake_stt,
        }
    )
    # Legacy service singletons hold caches (chat data cache, breed cache); start clean.
    for name in ("_intelligent_chatbot_service", "_simple_rag_service", "_visualization_service", "_pet_ai"):
        setattr(api_server, name, None)
    yield api_server.app
    api_server.app.dependency_overrides.clear()


def _auth_headers(uid: str) -> dict[str, str]:
    """Headers that authenticate as ``uid``.

    There is no server-side auth yet (review C1), so this is empty. The auth track replaces
    the body with ``{"Authorization": f"Bearer {issue_token(uid)}"}``; every test that uses
    ``client_as`` then authenticates without further changes.
    """
    return {}


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


@pytest.fixture
def client_noraise(app):
    """Like ``client`` but returns 500 responses instead of re-raising server exceptions."""
    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def client_as(app) -> Iterator[Callable[[str], Any]]:
    """``client_as("alice")`` -> a TestClient that sends alice's auth headers."""
    from fastapi.testclient import TestClient

    clients: list[TestClient] = []

    def make(uid: str) -> TestClient:
        c = TestClient(app, headers=_auth_headers(uid))
        c.__enter__()
        clients.append(c)
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def no_retry_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip the legacy exponential-backoff sleeps in summarize_openai."""
    import summarize_openai

    monkeypatch.setattr(summarize_openai.time, "sleep", lambda _s: None)


def now_iso() -> str:
    return datetime.utcnow().isoformat()


@pytest.fixture
def make_pet(app) -> Callable[..., str]:
    """Create a pet through the legacy data layer; returns its id."""
    from firestore_store import add_pet_to_page_and_user

    def make(uid: str = "alice", name: str = "Max", animal_type: str = "dog", **extra: Any) -> str:
        pet = add_pet_to_page_and_user(uid, {"name": name, "animal_type": animal_type, **extra}, "default-page")
        return str(pet["id"])

    return make
