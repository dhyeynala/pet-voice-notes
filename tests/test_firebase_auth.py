"""Firebase sign-in mode: ID-token verification fails closed and ownership is unchanged.

``firebase_admin`` is replaced by the fakes in ``tests/fake_firebase.py``; nothing touches the network.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from petpulse import config, deps, firebase
from petpulse.config import Settings
from tests.fake_firebase import FAKE_SERVICE_ACCOUNT, CertificateFetchError, ExpiredIdTokenError, FakeFirebase, install
from tests.test_auth import PET_ROUTES, PROTECTED, _fill

WEB_KEY = "web-api-key-for-tests"  # pragma: allowlist secret
TOKENS = {
    "tok-alice": {"uid": "alice", "email": "alice@example.test"},
    "tok-bob": {"uid": "bob"},
    "tok-carol": {"uid": "Xq3carolFirebaseUid0000000001", "name": "Carol", "email": "carol@example.test"},
    "tok-expired": ExpiredIdTokenError("Token expired"),
    "tok-certs-down": CertificateFetchError("certs unreachable"),
    "tok-weird-uid": {"uid": "user/with/slashes"},
    "tok-no-uid": {"email": "nobody@example.test", "uid": None, "sub": None},
}


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fake_firebase(monkeypatch) -> FakeFirebase:
    fake = install(monkeypatch, FakeFirebase(tokens=dict(TOKENS)))
    monkeypatch.setattr(config, "firebase_admin_installed", lambda: True)
    return fake


@pytest.fixture
def firebase_mode(fake_firebase, monkeypatch, app):
    """The demo app with AUTH_PROVIDER=firebase (store stays the per-test MemoryStore)."""
    monkeypatch.setenv("AUTH_PROVIDER", "firebase")
    monkeypatch.setenv("FIREBASE_CREDENTIALS_JSON", json.dumps(FAKE_SERVICE_ACCOUNT))
    monkeypatch.setenv("FIREBASE_WEB_API_KEY", WEB_KEY)
    deps.get_settings.cache_clear()
    firebase.reset()
    assert deps.get_settings().resolved_auth() == "firebase"
    return fake_firebase


@pytest.fixture
def fb_client(firebase_mode, app):
    clients: list[TestClient] = []

    def make(token: str | None = None) -> TestClient:
        c = TestClient(app, headers=bearer(token) if token else {})
        c.__enter__()
        clients.append(c)
        return c

    yield make
    for c in clients:
        c.__exit__(None, None, None)


# ---------------------------------------------------------------------------- verify_id_token
def settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None, auth_provider="firebase", firebase_credentials_json=json.dumps(FAKE_SERVICE_ACCOUNT)
    )


def test_verify_returns_claims_and_never_skips_checks(fake_firebase):
    claims = firebase.verify_id_token("tok-alice", settings())
    assert claims["uid"] == "alice"
    call = fake_firebase.verify_calls[-1]
    assert call["app"] is not None and call["check_revoked"] is False
    assert fake_firebase.apps[-1]["options"] == {"projectId": "petpulse-test"}
    assert fake_firebase.apps[-1]["credential"] == ("certificate", FAKE_SERVICE_ACCOUNT)


def test_app_is_never_created_without_a_service_account(fake_firebase):
    from petpulse.config import ConfigError

    bare = Settings(_env_file=None, auth_provider="firebase", firebase_project_id="p")  # type: ignore[call-arg]
    with pytest.raises(ConfigError):
        firebase.get_app(bare)
    assert fake_firebase.apps == []


@pytest.mark.parametrize("token", ["tok-expired", "unknown-token", "tok-no-uid", "", "x" * 9000])
def test_bad_tokens_raise_token_error(fake_firebase, token):
    with pytest.raises(firebase.FirebaseTokenError):
        firebase.verify_id_token(token, settings())


def test_unexpected_sdk_errors_fail_closed(fake_firebase, monkeypatch):
    import sys

    def boom(*_a, **_k):
        raise RuntimeError("anything at all")

    monkeypatch.setattr(sys.modules["firebase_admin.auth"], "verify_id_token", boom)
    with pytest.raises(firebase.FirebaseTokenError):
        firebase.verify_id_token("tok-alice", settings())


def test_certificate_outage_is_unavailable_not_invalid(fake_firebase):
    with pytest.raises(firebase.FirebaseUnavailable):
        firebase.verify_id_token("tok-certs-down", settings())


# ---------------------------------------------------------------------------- the API in firebase mode
def test_first_sign_in_creates_the_user_from_verified_claims(fb_client):
    from petpulse import pets as pet_records

    me = fb_client("tok-carol").get("/api/me")
    assert me.status_code == 200
    assert me.json() == {"uid": "Xq3carolFirebaseUid0000000001", "name": "Carol"}
    record = pet_records.get_user(deps.get_store(), "Xq3carolFirebaseUid0000000001")
    assert record is not None and record["demo"] is False and record["email"] == "carol@example.test"
    assert fb_client("tok-carol").get("/api/me/pets").json() == []


@pytest.mark.parametrize("token", ["tok-expired", "unknown-token", "tok-weird-uid", "tok-no-uid"])
def test_bad_or_expired_firebase_tokens_are_401(fb_client, token):
    response = fb_client(token).get("/api/me")
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid or expired token"
    assert response.headers["www-authenticate"] == "Bearer"


def test_demo_tokens_are_rejected_in_firebase_mode(fb_client):
    from petpulse.auth import issue_token

    response = fb_client(issue_token("alice")).get("/api/me")
    assert response.status_code == 401


def test_certificate_outage_is_503_so_the_ui_does_not_log_out(fb_client):
    response = fb_client("tok-certs-down").get("/api/me")
    assert response.status_code == 503
    assert response.json()["code"] == "auth_unavailable"


def test_demo_login_endpoints_are_disabled(fb_client):
    anon = fb_client()
    for method, url in (("GET", "/api/demo/users"), ("POST", "/api/demo/login")):
        response = anon.request(method, url, json={"uid": "alice"})
        assert response.status_code == 404
        assert response.json()["code"] == "demo_login_disabled"
    assert fb_client("tok-alice").post("/api/demo/reset").status_code == 404


def test_client_sent_uid_is_never_trusted(fb_client, make_pet):
    pet_id = make_pet("alice")
    # A body uid that is not the verified caller is refused (legacy route).
    as_bob = fb_client("tok-bob").post("/api/markdown", json={"uid": "alice", "pet": pet_id, "content": "x"})
    assert as_bob.status_code in (403, 404)
    assert fb_client("tok-bob").get("/api/user-pets/alice").status_code == 403


NON_DEMO = [r for r in PROTECTED if not r[1].startswith("/api/demo/")]  # demo routes 404 first (above)


@pytest.mark.parametrize("method, path", NON_DEMO, ids=[f"{m} {p}" for m, p in NON_DEMO])
def test_every_protected_route_rejects_missing_and_bad_firebase_tokens(fb_client, make_pet, method, path):
    url = _fill(path, make_pet("alice"))
    assert fb_client().request(method, url, json={}).status_code == 401
    bad = fb_client("tok-expired").request(method, url, json={})
    assert bad.status_code == 401 and bad.json()["detail"] == "invalid or expired token"


@pytest.mark.parametrize("method, path", PET_ROUTES, ids=[f"{m} {p}" for m, p in PET_ROUTES])
def test_another_users_pet_is_404_with_firebase_tokens(fb_client, make_pet, method, path):
    url = _fill(path, make_pet("alice"))
    as_bob = fb_client("tok-bob").request(method, url, json={})
    assert as_bob.status_code == 404, as_bob.text
    assert as_bob.json()["detail"] == "pet not found"


def test_startup_does_not_seed_demo_users_under_firebase_sign_in(firebase_mode, monkeypatch, store):
    import api_server

    monkeypatch.setenv("SEED_ON_START", "true")
    deps.get_settings.cache_clear()
    with TestClient(api_server.app):
        pass
    assert store.query("users") == [] and store.query("pets") == []


def test_owner_reaches_their_pet_with_a_firebase_token(fb_client, make_pet):
    pet_id = make_pet("alice")
    response = fb_client("tok-alice").get(f"/api/pets/{pet_id}")
    assert response.status_code == 200 and response.json()["owners"] == ["alice"]
    created = fb_client("tok-carol").post("/api/pets", json={"name": "Mochi", "animal_type": "cat"})
    assert created.status_code == 201 and created.json()["owners"] == ["Xq3carolFirebaseUid0000000001"]
    assert fb_client("tok-alice").get(f"/api/pets/{created.json()['id']}").status_code == 404
