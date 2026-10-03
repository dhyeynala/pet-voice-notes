"""Firebase mode selection (STORE_BACKEND / AUTH_PROVIDER), fail-fast checks and the public endpoints."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from petpulse import config
from petpulse.config import ConfigError, Settings
from tests.fake_firebase import FAKE_SERVICE_ACCOUNT

SA_JSON = json.dumps(FAKE_SERVICE_ACCOUNT)
WEB_KEY = "web-api-key-for-tests"  # pragma: allowlist secret


def make(**env: str) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


@pytest.fixture
def installed(monkeypatch):
    """Pretend firebase-admin is installed (the test env deliberately does not have it)."""
    monkeypatch.setattr(config, "firebase_admin_installed", lambda: True)


@pytest.fixture
def sa_file(tmp_path):
    path = tmp_path / "sa.json"
    path.write_text(SA_JSON, encoding="utf-8")
    return str(path)


def test_zero_config_is_local_store_and_demo_login():
    s = make()
    assert (s.resolved_store(), s.resolved_auth(), s.resolved_blobs()) == ("memory", "demo", "local")  # STORE=memory in tests
    assert s.firebase_web_config() is None
    s.check()


def test_project_id_alone_does_not_switch_anything():
    s = make(firebase_project_id="petpulse-test", firebase_web_api_key=WEB_KEY)
    assert s.resolved_store() == "memory" and s.resolved_auth() == "demo"
    s.check()


def test_auto_picks_firestore_with_credentials_and_firebase_auth_with_web_key(installed):
    s = make(firebase_credentials_json=SA_JSON)
    assert s.resolved_store() == "firestore"
    assert s.resolved_auth() == "demo"  # no web key: the browser could not sign in
    assert s.firebase_project() == "petpulse-test"
    s.check()

    s = make(firebase_credentials_json=SA_JSON, firebase_web_api_key=WEB_KEY, firebase_storage_bucket="b")
    assert (s.resolved_store(), s.resolved_auth(), s.resolved_blobs()) == ("firestore", "firebase", "firebase")
    assert s.firebase_web_config() == {
        "apiKey": WEB_KEY,
        "authDomain": "petpulse-test.firebaseapp.com",
        "projectId": "petpulse-test",
    }
    s.check()


def test_google_stt_credentials_alone_never_enable_firebase(sa_file, installed):
    assert make(google_application_credentials=sa_file).resolved_store() == "memory"
    s = make(google_application_credentials=sa_file, firebase_project_id="petpulse-test")
    assert s.resolved_store() == "firestore"
    # A key for another project (e.g. the STT one) is not a Firebase credential.
    other = make(google_application_credentials=sa_file, firebase_project_id="another-project")
    assert other.resolved_store() == "memory" and other.firebase_credentials() == (None, None)


def test_explicit_local_backend_wins_over_credentials(installed):
    s = make(firebase_credentials_json=SA_JSON, firebase_web_api_key=WEB_KEY, store_backend="json", auth_provider="demo")
    assert (s.resolved_store(), s.resolved_auth(), s.resolved_blobs()) == ("memory", "demo", "local")
    assert s.firebase_web_config() is None
    s.check()


def test_choices_are_normalised():
    s = make(store_backend=" JSON ", auth_provider="")
    assert s.store_backend == "json" and s.auth_provider == "auto"


@pytest.mark.parametrize(
    "env, message",
    [
        ({"store_backend": "firestore"}, "STORE_BACKEND=firestore requires service-account credentials"),
        ({"auth_provider": "firebase"}, "AUTH_PROVIDER=firebase requires service-account credentials"),
        (
            {"auth_provider": "firebase", "firebase_project_id": "p", "firebase_web_api_key": "k"},
            "AUTH_PROVIDER=firebase requires service-account credentials",
        ),
        (
            {"auth_provider": "firebase", "firebase_credentials_json": SA_JSON},
            "AUTH_PROVIDER=firebase requires FIREBASE_WEB_API_KEY",
        ),
        ({"firebase_credentials_json": "{not json"}, "FIREBASE_CREDENTIALS_JSON is not valid JSON"),
        ({"firebase_credentials_json": '{"type": "authorized_user"}'}, "not a service-account key"),
        ({"firebase_credentials_json": json.dumps({**FAKE_SERVICE_ACCOUNT, "private_key": ""})}, "missing private_key"),
        (
            {"firebase_credentials_json": SA_JSON, "firebase_project_id": "another-project"},
            "FIREBASE_PROJECT_ID does not match",
        ),
    ],
)
def test_forced_or_broken_firebase_fails_fast(installed, env, message):
    with pytest.raises(ConfigError, match=message):
        make(**env).check()


def test_invalid_credentials_never_fall_back_silently_and_never_echo_the_key(installed):
    secret_ish = json.dumps({**FAKE_SERVICE_ACCOUNT, "type": "nope", "private_key": "do-not-print-me"})
    s = make(firebase_credentials_json=secret_ish)
    assert s.resolved_store() == "memory"
    with pytest.raises(ConfigError) as info:
        s.check()
    assert "do-not-print-me" not in str(info.value)


def test_unreadable_credentials_file_is_an_error(installed, tmp_path):
    s = make(google_application_credentials=str(tmp_path / "missing.json"), firebase_project_id="petpulse-test")
    with pytest.raises(ConfigError, match="not readable"):
        s.check()


def test_firebase_without_the_package_fails_with_install_hint(monkeypatch):
    monkeypatch.setattr(config, "firebase_admin_installed", lambda: False)
    with pytest.raises(ConfigError, match="requirements-live.txt"):
        make(firebase_credentials_json=SA_JSON).check()
    make().check()  # demo mode never needs it


def test_firebase_admin_installed_does_not_import(monkeypatch):
    import sys

    monkeypatch.setitem(sys.modules, "firebase_admin", None)
    assert config.firebase_admin_installed() is False
    monkeypatch.delitem(sys.modules, "firebase_admin")
    config.firebase_admin_installed()
    assert "firebase_admin" not in sys.modules


# ---------------------------------------------------------------------------- endpoints
def test_auth_config_and_health_in_demo_mode(anon_client):
    assert anon_client.get("/api/auth/config").json() == {"provider": "demo", "mode": "demo", "firebase": None}
    health = anon_client.get("/api/health").json()
    assert (health["auth"], health["store"], health["blobs"]) == ("demo", "memory", "local")


def test_auth_config_and_health_in_firebase_mode(monkeypatch, installed):
    import api_server
    from petpulse import deps

    monkeypatch.setenv("AUTH_PROVIDER", "firebase")
    monkeypatch.setenv("STORE_BACKEND", "json")  # Firebase sign-in on the local store
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", SA_JSON)
    monkeypatch.setenv("FIREBASE_WEB_API_KEY", WEB_KEY)
    monkeypatch.setenv("FIREBASE_AUTH_DOMAIN", "auth.example.test")
    deps.reset()
    with TestClient(api_server.app) as c:  # health/config only read settings; nothing touches Firebase
        body = c.get("/api/auth/config").json()
        health = c.get("/api/health").json()
    assert (health["auth"], health["store"], health["blobs"]) == ("firebase", "memory", "local")
    assert "not-a-real-key" not in str(health) + str(body)
    assert body == {
        "provider": "firebase",
        "mode": "firebase",
        "firebase": {"apiKey": WEB_KEY, "authDomain": "auth.example.test", "projectId": "petpulse-test"},
    }
    assert (health["auth"], health["store"], health["blobs"]) == ("firebase", "memory", "local")


def test_startup_fails_when_firestore_is_forced_without_credentials(monkeypatch):
    import api_server
    from petpulse import deps

    monkeypatch.setenv("STORE_BACKEND", "firestore")
    deps.reset()
    with pytest.raises(ConfigError, match="STORE_BACKEND=firestore"):
        with TestClient(api_server.app):
            pass


def test_auth_emulator_is_refused_for_real_projects(monkeypatch, installed):
    monkeypatch.setenv("FIREBASE_AUTH_EMULATOR_HOST", "127.0.0.1:9099")
    s = make(firebase_credentials_json=SA_JSON, firebase_web_api_key=WEB_KEY)
    with pytest.raises(ConfigError, match="FIREBASE_AUTH_EMULATOR_HOST"):
        s.check()
    assert "authEmulatorUrl" not in (s.firebase_web_config() or {})

    demo = json.dumps({**FAKE_SERVICE_ACCOUNT, "project_id": "demo-petpulse"})
    s = make(firebase_credentials_json=demo, firebase_web_api_key=WEB_KEY)
    s.check()
    assert s.firebase_web_config()["authEmulatorUrl"] == "http://127.0.0.1:9099"
