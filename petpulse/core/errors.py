"""HTTP errors with one JSON shape, plus request ids.

Every non-2xx response from the API has the body::

    {"detail": "<human-readable message>", "request_id": "<id>"}

optionally with ``"code"`` (a short machine-readable reason, e.g. ``"no_speech"``) and, for
422s, ``"errors"`` (field-level problems, without echoing the submitted values). The same id is
sent back in the ``X-Request-ID`` header and written to the server log, so a user-visible error
can be matched to its traceback. Unhandled exceptions become a generic 500: ``str(exc)`` is
logged, never returned.

Routes raise the ``ApiError`` subclasses below (they are ``HTTPException``s, so FastAPI's own
machinery and ``raise HTTPException(...)`` keep working too). ``install(app)`` wires it up.
"""

from __future__ import annotations

import logging
import re
import uuid
from typing import Any, Mapping, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("petpulse.core.errors")

REQUEST_ID_HEADER = "X-Request-ID"
_INCOMING_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class ApiError(HTTPException):
    """Base class: ``raise NotFoundError("pet not found")``."""

    status: int = 500

    def __init__(self, detail: str, *, code: Optional[str] = None, headers: Optional[Mapping[str, str]] = None) -> None:
        super().__init__(status_code=self.status, detail=detail, headers=dict(headers) if headers else None)
        self.code = code


class BadRequestError(ApiError):
    status = 400


class UnauthorizedError(ApiError):
    status = 401

    def __init__(self, detail: str = "not authenticated", *, code: Optional[str] = None) -> None:
        super().__init__(detail, code=code, headers={"WWW-Authenticate": "Bearer"})


class ForbiddenError(ApiError):
    status = 403


class NotFoundError(ApiError):
    status = 404


class ConflictError(ApiError):
    status = 409


class PayloadTooLargeError(ApiError):
    status = 413


class UnsupportedMediaTypeError(ApiError):
    status = 415


class UnprocessableError(ApiError):
    status = 422


class BadGatewayError(ApiError):
    status = 502


class ServiceUnavailableError(ApiError):
    status = 503


# ---------------------------------------------------------------------------- request ids
class RequestIdMiddleware:
    """Assigns every HTTP request an id (``request.state.request_id``) and echoes it back.

    A well-formed incoming ``X-Request-ID`` is reused so ids can be correlated across hops;
    anything else is replaced with a fresh uuid4.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = ""
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        request_id = incoming if _INCOMING_ID.match(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = [(k, v) for k, v in message.get("headers", []) if k.lower() != b"x-request-id"]
                headers.append((b"x-request-id", request_id.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_id)


def get_request_id(request: Request) -> str:
    """The current request's id (a fresh one if the middleware did not run)."""
    request_id = getattr(request.state, "request_id", None)
    if not isinstance(request_id, str):
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
    return request_id


# ---------------------------------------------------------------------------- handlers
def error_body(request: Request, detail: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"detail": detail, "request_id": get_request_id(request)}
    body.update({key: value for key, value in extra.items() if value is not None})
    return body


def _response(
    request: Request, status_code: int, body: dict[str, Any], headers: Optional[Mapping[str, str]] = None
) -> JSONResponse:
    out = dict(headers or {})
    out[REQUEST_ID_HEADER] = body["request_id"]
    return JSONResponse(status_code=status_code, content=body, headers=out)


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    if isinstance(exc.detail, str) and exc.detail:
        body = error_body(request, exc.detail, code=getattr(exc, "code", None))
    else:
        # Non-string details (dicts/lists from older code) go under "errors"; detail stays a str.
        body = error_body(request, _reason(exc.status_code), errors=exc.detail or None)
    return _response(request, exc.status_code, body, exc.headers)


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    problems = [
        {"loc": [str(part) for part in err.get("loc", ())], "msg": str(err.get("msg", "")), "type": str(err.get("type", ""))}
        for err in exc.errors()
    ]
    summary = "; ".join(f"{'.'.join(p['loc'][1:] or p['loc'])}: {p['msg']}" for p in problems[:5])
    body = error_body(request, f"invalid request: {summary}" if summary else "invalid request", errors=problems)
    return _response(request, 422, body)


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    body = error_body(request, "internal server error")
    logger.error(
        "unhandled error request_id=%s %s %s",
        body["request_id"],
        request.method,
        request.url.path,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return _response(request, 500, body)


def _reason(status_code: int) -> str:
    from http import HTTPStatus

    try:
        return HTTPStatus(status_code).phrase.lower()
    except ValueError:
        return "error"


def install(app: FastAPI) -> None:
    """Register the request-id middleware and the JSON error handlers on ``app``."""
    app.add_middleware(RequestIdMiddleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
