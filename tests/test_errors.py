"""Error responses: real status codes, ``{"detail": str, "request_id": str}``, no leaks (M10)."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel

from petpulse.core import errors


class Body(BaseModel):
    n: int


@pytest.fixture
def toy():
    app = FastAPI()
    errors.install(app)

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("db password is hunter2")  # pragma: allowlist secret

    @app.get("/missing")
    def missing() -> None:
        raise errors.NotFoundError("pet not found")

    @app.get("/coded")
    def coded() -> None:
        raise errors.UnprocessableError("no speech detected", code="no_speech")

    @app.get("/plain")
    def plain() -> None:
        raise HTTPException(409, detail={"why": "legacy dict detail"})

    @app.post("/typed")
    def typed(body: Body) -> int:
        return body.n

    return app


def test_unhandled_exception_is_a_generic_500_with_request_id(toy, caplog):
    with TestClient(toy, raise_server_exceptions=False) as c, caplog.at_level(logging.ERROR, "petpulse.core.errors"):
        response = c.get("/boom")
    assert response.status_code == 500
    body = response.json()
    assert body == {"detail": "internal server error", "request_id": body["request_id"]}
    assert "hunter2" not in response.text
    assert response.headers["x-request-id"] == body["request_id"]
    # ...but the server log has the id and the real error, for debugging.
    assert body["request_id"] in caplog.text and "hunter2" in caplog.text


def test_api_errors_keep_their_status_and_code(toy):
    with TestClient(toy) as c:
        missing = c.get("/missing")
        coded = c.get("/coded")
        plain = c.get("/plain")
    assert missing.status_code == 404 and missing.json()["detail"] == "pet not found"
    assert coded.status_code == 422 and coded.json()["code"] == "no_speech"
    assert plain.status_code == 409
    assert plain.json()["detail"] == "conflict" and plain.json()["errors"] == {"why": "legacy dict detail"}


def test_validation_errors_do_not_echo_input(toy):
    with TestClient(toy) as c:
        response = c.post("/typed", json={"n": "<script>secret-input</script>"})
    assert response.status_code == 422
    assert "secret-input" not in response.text
    assert response.json()["detail"].startswith("invalid request: n:")


def test_request_id_is_echoed_when_well_formed(toy):
    with TestClient(toy) as c:
        assert c.get("/missing", headers={"X-Request-ID": "abc-123"}).json()["request_id"] == "abc-123"
        forged = c.get("/missing", headers={"X-Request-ID": "bad id\nwith newline"})
    assert forged.json()["request_id"] != "bad id\nwith newline"
    assert len(forged.json()["request_id"]) == 32


def test_app_wide_404_and_success_carry_request_ids(client, anon_client):
    unknown = anon_client.get("/api/nope")
    assert unknown.status_code == 404 and unknown.json()["request_id"]
    ok = client.get("/api/health")
    assert ok.status_code == 200 and ok.headers["x-request-id"]


def test_cors_allows_configured_origin_without_credentials(client):
    response = client.options(
        "/api/me",
        headers={
            "Origin": "http://localhost:8000",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8000"
    assert "access-control-allow-credentials" not in response.headers


def test_wildcard_origin_is_rejected_by_config():
    from petpulse.core.config import ConfigError, Settings

    with pytest.raises(ConfigError, match="ALLOWED_ORIGINS"):
        Settings(_env_file=None, allowed_origins=["*"]).check()  # type: ignore[call-arg]
