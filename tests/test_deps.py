"""Factories in petpulse.deps build the right implementation from the environment."""

from __future__ import annotations

import pytest

from petpulse import deps
from petpulse.config import ConfigError
from petpulse.providers import FakeLLM, FakeSTT, GoogleSTT, OpenAILLM, OpenAISTT
from petpulse.store import JsonFileStore, MemoryStore

FAKE_KEY = "sk-test-not-real"  # pragma: allowlist secret


def test_demo_defaults(monkeypatch):
    assert isinstance(deps.get_store(), MemoryStore)  # conftest sets STORE=memory
    assert isinstance(deps.get_llm(), FakeLLM)
    assert isinstance(deps.get_stt(), FakeSTT)
    assert deps.get_llm() is deps.get_llm()  # cached


def test_json_store_lives_under_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("STORE", "json")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "d"))
    deps.reset()
    store = deps.get_store()
    assert isinstance(store, JsonFileStore)
    store.set("pets/p1", {"name": "Max"})
    assert (tmp_path / "d" / "db.json").exists()
    deps.get_blobs().put("records/x.pdf", b"1")
    assert (tmp_path / "d" / "blobs" / "records" / "x.pdf").exists()


def test_auto_builds_openai_adapters_when_key_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    deps.reset()
    assert isinstance(deps.get_llm(), OpenAILLM)
    assert isinstance(deps.get_stt(), OpenAISTT)


def test_google_stt_when_explicit(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/secrets/sa.json")
    deps.reset()
    assert isinstance(deps.get_stt(), GoogleSTT)


def test_explicit_openai_without_key_fails_fast(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    deps.reset()
    with pytest.raises(ConfigError):
        deps.get_llm()


def test_override_and_reset():
    llm = FakeLLM(fail=True)
    deps.override(llm=llm)
    assert deps.get_llm() is llm
    with pytest.raises(TypeError):
        deps.override(database=object())
    deps.reset()
    assert deps.get_llm() is not llm


def test_legacy_db_follows_overrides():
    db = deps.legacy_db()
    first = MemoryStore()
    deps.override(store=first)
    db.collection("pets").document("p1").set({"name": "Max"})
    second = MemoryStore()
    deps.override(store=second)
    assert not db.collection("pets").document("p1").get().exists
    assert first.get("pets/p1") == {"name": "Max"}
