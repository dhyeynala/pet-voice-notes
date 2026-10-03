"""/api/health reports the overall and per-feature Demo/Live mode."""

from __future__ import annotations

from fastapi.testclient import TestClient

FAKE_KEY = "sk-test-not-real"  # pragma: allowlist secret


def test_health_in_demo_mode(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert {k: body[k] for k in ("status", "mode", "llm", "stt", "store")} == {
        "status": "healthy",
        "mode": "demo",
        "llm": "fake",
        "stt": "fake",
        "store": "memory",
    }
    assert set(body["features"]) == {"notes", "chat", "pdf_summary", "insights", "voice"}
    assert all(f == {"provider": "fake", "mode": "demo"} for f in body["features"].values())


def test_health_reports_live_when_key_present(monkeypatch):
    import petpulse.app as app_module
    from petpulse.core import deps

    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("STT_PROVIDER", "fake")
    deps.reset()
    with TestClient(app_module.app) as c:  # builds nothing live: health only reads settings
        body = c.get("/api/health").json()
    assert body["mode"] == "mixed"
    assert body["features"]["chat"] == {"provider": "openai", "mode": "live"}
    assert body["features"]["voice"] == {"provider": "fake", "mode": "demo"}
    assert "sk-test" not in str(body)


def test_startup_fails_fast_on_contradictory_config(monkeypatch):
    import pytest

    import petpulse.app as app_module
    from petpulse.core import deps
    from petpulse.core.config import ConfigError

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    deps.reset()
    with pytest.raises(ConfigError):
        with TestClient(app_module.app):
            pass
