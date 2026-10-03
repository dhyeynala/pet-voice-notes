"""Demo tokens, the auth dependency on every /api route, and ownership checks (review C1)."""

from __future__ import annotations

import re
from typing import Any

import pytest
from fastapi.routing import APIRoute

from petpulse.core import deps
from petpulse.core.auth import InvalidToken, issue_token, verify_token
from petpulse.core.config import Settings

PUBLIC_ROUTES = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/config"),
    ("GET", "/api/demo/users"),
    ("POST", "/api/demo/login"),
}


def settings(**env: Any) -> Settings:
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------- tokens
def test_token_round_trip():
    s = settings(auth_secret="unit-test-secret")  # pragma: allowlist secret
    token = issue_token("alice", settings=s, now=1_000)
    assert verify_token(token, settings=s, now=1_001) == "alice"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda t: t[:-2] + ("AA" if not t.endswith("AA") else "BB"),  # signature
        lambda t: "v2" + t[2:],  # version
        lambda t: t.split(".", 1)[1],  # missing part
        lambda t: "",
        lambda t: "Bearer " + t,
    ],
)
def test_tampered_tokens_are_rejected(mutate):
    s = settings(auth_secret="unit-test-secret")  # pragma: allowlist secret
    with pytest.raises(InvalidToken):
        verify_token(mutate(issue_token("alice", settings=s, now=1_000)), settings=s, now=1_001)


def test_payload_cannot_be_swapped_without_the_secret():
    s = settings(auth_secret="unit-test-secret")  # pragma: allowlist secret
    alice = issue_token("alice", settings=s, now=1_000).split(".")
    bob = issue_token("bob", settings=s, now=1_000).split(".")
    with pytest.raises(InvalidToken):
        verify_token(".".join([alice[0], bob[1], alice[2]]), settings=s, now=1_001)


def test_tokens_expire():
    s = settings(auth_secret="unit-test-secret", auth_token_ttl_minutes=1)  # pragma: allowlist secret
    token = issue_token("alice", settings=s, now=1_000)
    assert verify_token(token, settings=s, now=1_059) == "alice"
    with pytest.raises(InvalidToken, match="expired"):
        verify_token(token, settings=s, now=1_060)


def test_a_different_secret_rejects_the_token():
    token = issue_token("alice", settings=settings(auth_secret="one"), now=1_000)  # pragma: allowlist secret
    with pytest.raises(InvalidToken):
        verify_token(token, settings=settings(auth_secret="two"), now=1_001)  # pragma: allowlist secret


def test_generated_secret_is_stable_within_the_process():
    s = settings()
    assert s.auth_secret is None
    assert verify_token(issue_token("alice", settings=s), settings=settings()) == "alice"


def test_token_ttl_must_be_positive():
    from petpulse.core.config import ConfigError

    with pytest.raises(ConfigError, match="AUTH_TOKEN_TTL_MINUTES"):
        settings(auth_token_ttl_minutes=0).check()


# ---------------------------------------------------------------------------- route inventory
def _api_routes() -> list[tuple[str, str]]:
    """Every (method, path) under /api, from the OpenAPI schema (covers included routers too)."""
    import petpulse.app as app_module

    app_module.app.openapi_schema = None  # rebuild: routes may have been added since import
    out = []
    for path, operations in app_module.app.openapi()["paths"].items():
        if path.startswith("/api"):
            out.extend((method.upper(), path) for method in operations if method in {"get", "post", "put", "patch", "delete"})
    hidden = [
        r.path
        for r in app_module.app.routes
        if isinstance(r, APIRoute) and r.path.startswith("/api") and not r.include_in_schema
    ]
    assert not hidden, f"routes hidden from OpenAPI escape the auth inventory: {hidden}"
    return sorted(out)


def _fill(path: str, pet_id: str) -> str:
    path = path.replace("{pet_id}", pet_id).replace("{user_id}", "alice").replace("{category}", "diet")
    return re.sub(r"\{[^}]+\}", "x", path)


PROTECTED = [r for r in _api_routes() if r not in PUBLIC_ROUTES]


def test_inventory_is_not_empty_and_public_routes_exist():
    routes = set(_api_routes())
    assert PUBLIC_ROUTES <= routes
    assert len(PROTECTED) >= 20
    assert ("GET", "/api/test") not in routes
    assert not any(path.startswith("/api/pages") for _, path in routes)
    assert not routes & REMOVED_ROUTES


# Removed with the legacy modules (Track F); the contract routes in docs/api-contract.md replace them.
REMOVED_ROUTES = {
    ("POST", "/api/pets/{pet_id}/textinput"),
    ("POST", "/api/pets/{pet_id}/knowledge_search"),
    ("GET", "/api/pets/{pet_id}/assistant_summary"),
    ("GET", "/api/pets/{pet_id}/health_insights"),
    ("POST", "/api/pets/{pet_id}/daily_routine"),
    ("POST", "/api/pets/{pet_id}/preload"),
    ("POST", "/api/pets/{pet_id}/cache/clear"),
    ("GET", "/api/pets/{pet_id}/cache/status"),
    ("GET", "/api/pets/{pet_id}/analytics/summary"),
    ("GET", "/api/pets/{pet_id}/visualizations"),
}


@pytest.mark.parametrize("method, path", sorted(REMOVED_ROUTES), ids=[f"{m} {p}" for m, p in sorted(REMOVED_ROUTES)])
def test_removed_legacy_routes_are_gone(client, make_pet, method, path):
    response = client.request(method, _fill(path, make_pet("alice")), json={"query": "x", "input": "x"})
    assert response.status_code in (404, 405), response.text
    assert response.json().get("detail") != "pet not found"


@pytest.mark.parametrize("method, path", PROTECTED, ids=[f"{m} {p}" for m, p in PROTECTED])
def test_every_protected_route_requires_a_token(anon_client, client_as, make_pet, method, path):
    url = _fill(path, make_pet("alice"))
    no_token = anon_client.request(method, url, json={})
    assert no_token.status_code == 401, no_token.text
    assert no_token.headers.get("www-authenticate") == "Bearer"
    body = no_token.json()
    assert body["detail"] == "not authenticated" and body["request_id"]

    bad = anon_client.request(method, url, json={}, headers={"Authorization": "Bearer v1.bogus.token"})
    assert bad.status_code == 401
    assert bad.json()["detail"] == "invalid or expired token"

    wrong_scheme = anon_client.request(method, url, json={}, headers={"Authorization": "Basic YWxpY2U6eA=="})
    assert wrong_scheme.status_code == 401


PET_ROUTES = [(m, p) for m, p in PROTECTED if "{pet_id}" in p]


@pytest.mark.parametrize("method, path", PET_ROUTES, ids=[f"{m} {p}" for m, p in PET_ROUTES])
def test_another_users_pet_is_404_and_the_owner_gets_through(client, client_as, make_pet, method, path):
    url = _fill(path, make_pet("alice"))
    as_bob = client_as("bob").request(method, url, json={})
    assert as_bob.status_code == 404, as_bob.text
    assert as_bob.json()["detail"] == "pet not found"
    # The owner passes the auth/ownership layer (some bodies still 4xx on a generic body).
    # Other placeholders (e.g. {record_id}) don't exist, so a 404 for *that* is fine; "pet not found" is not.
    as_alice = client.request(method, url, json={"message": "How is Max?", "text": "Max ate"})
    assert as_alice.status_code not in (401, 403), as_alice.text
    assert not (as_alice.status_code == 404 and as_alice.json()["detail"] == "pet not found"), as_alice.text


def test_unknown_pet_is_404_like_someone_elses(client):
    assert client.get("/api/pets/does-not-exist/analytics").status_code == 404
    assert client.get("/api/pets/does-not-exist").status_code == 404


@pytest.mark.parametrize(
    "method, path, body",
    [
        ("GET", "/api/pets/{pet}/analytics", None),
        ("GET", "/api/pets/{pet}/records", None),
        ("GET", "/api/pets/{pet}/insights", None),
        ("GET", "/api/pets/{pet}/notes", None),
        ("POST", "/api/pets/{pet}/analytics/diet", {"food": "kibble"}),
        ("POST", "/api/pets/{pet}/notes", {"text": "Max had a walk"}),
        ("POST", "/api/pets/{pet}/chat", {"message": "Did Max walk?"}),
        ("GET", "/api/pets/{pet}", None),
    ],
)
def test_owner_gets_2xx(client, make_pet, method, path, body):
    response = client.request(method, path.format(pet=make_pet("alice")), json=body)
    assert 200 <= response.status_code < 300, response.text


# ---------------------------------------------------------------------------- legacy uid/pet in path/body
def test_uid_in_path_must_be_the_caller(client):
    assert client.get("/api/user-pets/bob").status_code == 403
    response = client.post("/api/pets/bob", json={"name": "Rex", "animal_type": "dog"})
    assert response.status_code == 403
    assert response.json()["detail"] == "user id does not match the signed-in user"


def test_pet_in_body_must_be_owned(client, client_as, make_pet):
    alice_pet = make_pet("alice")
    bob = client_as("bob")
    # POST /api/markdown names the pet in the JSON body (not a voice route: Track D removes those).
    assert bob.post("/api/markdown", json={"uid": "bob", "pet": alice_pet, "markdown": "x"}).status_code == 404
    assert client.post("/api/markdown", json={"uid": "bob", "pet": alice_pet, "markdown": "x"}).status_code == 403
    assert client.post("/api/markdown", json={"uid": "alice", "markdown": "x"}).status_code == 422
    upload = bob.post(
        "/api/upload_pdf",
        data={"uid": "bob", "pet": alice_pet},
        files={"file": ("x.pdf", b"%PDF-1.4", "application/pdf")},
    )
    assert upload.status_code == 404


def test_markdown_is_per_owned_pet_with_no_shared_page(client, client_as, make_pet, store):
    alice_pet = make_pet("alice")
    bob = client_as("bob")
    bob_pet = make_pet("bob")
    write = client.post("/api/markdown", json={"page": "default-page", "pet": alice_pet, "markdown": "alice secret"})
    assert write.status_code == 200
    assert store.get("pages/default-page") is None
    assert bob.get("/api/markdown", params={"page": "default-page", "pet": bob_pet}).json() == {"markdown": ""}
    assert bob.get("/api/markdown", params={"page": "default-page", "pet": alice_pet}).status_code == 404
    assert client.get("/api/markdown", params={"pet": alice_pet}).json() == {"markdown": "alice secret"}


def test_current_user_name_comes_from_the_store(client_as, store):
    store.set("users/carol", {"name": "Carol"})
    assert client_as("carol").get("/api/me").json() == {"uid": "carol", "name": "Carol"}
    assert client_as("dave").get("/api/me").json() == {"uid": "dave", "name": "dave"}


def test_auth_secret_from_settings_survives_a_restart(monkeypatch, app):
    from fastapi.testclient import TestClient

    monkeypatch.setenv("AUTH_SECRET", "persisted-demo-secret")  # pragma: allowlist secret
    deps.get_settings.cache_clear()
    token = issue_token("alice")
    deps.get_settings.cache_clear()  # "restart": settings re-read, same secret
    with TestClient(app, headers={"Authorization": f"Bearer {token}"}) as c:
        assert c.get("/api/me").status_code == 200
