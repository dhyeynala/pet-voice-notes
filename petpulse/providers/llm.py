"""LLM provider interface, the deterministic ``FakeLLM`` and the lazily imported ``OpenAILLM``.

The one entry point is ``complete_json`` (structured output, one call per task). The prompt
registry, schemas and the validating client in ``petpulse.llm`` are built on top of it.
"""

from __future__ import annotations

import asyncio
import json
import re
import weakref
from dataclasses import dataclass, field
from typing import Any, Callable, Literal, Optional, Protocol, runtime_checkable

from petpulse.llm.config import (
    DEFAULT_TIMEOUT_SECONDS,
    MODEL_FACTS,
    OPENAI_PINNED_MODEL,
    OPENAI_SDK_MAX_RETRIES,
)

FAKE_MODEL = "fake-llm-v1"
# The live adapter's default is the dated snapshot pinned in petpulse/llm/config.py (never an
# alias).
DEFAULT_OPENAI_MODEL = OPENAI_PINNED_MODEL

FakeMode = Literal["normal", "invalid_once", "truncate", "fail"]
FAKE_MODES: tuple[str, ...] = ("normal", "invalid_once", "truncate", "fail")
# The client marks a schema-repair attempt with this block; ``invalid_once`` keys off it.
REPAIR_MARKER = "<validation_error>"


class LLMError(RuntimeError):
    """A provider-level failure: outage, timeout, simulated failure."""


class LLMRefusal(LLMError):
    """The provider declined to answer (structured-output refusal or content filter)."""


@dataclass
class RawCompletion:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    finish_reason: str


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    async def complete_json(
        self,
        *,
        task: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> RawCompletion: ...


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def skeleton_from_schema(schema: dict[str, Any]) -> Any:
    """A deterministic, schema-shaped placeholder. Prefers ``UNKNOWN`` for enums."""
    if "enum" in schema:
        values = list(schema["enum"])
        return "UNKNOWN" if "UNKNOWN" in values else values[0]
    if "const" in schema:
        return schema["const"]
    kind = schema.get("type")
    if isinstance(kind, list):
        kind = "null" if "null" in kind else kind[0]
    if kind == "object":
        props = schema.get("properties", {})
        required = schema.get("required", list(props))
        return {name: skeleton_from_schema(props[name]) for name in required if name in props}
    if kind == "array":
        return []
    if kind == "string":
        return ""
    if kind in ("number", "integer"):
        return 0
    if kind == "boolean":
        return False
    return None


JsonHandler = Callable[[str, str, dict[str, Any]], Any]


def default_json_handler(task: str) -> Optional[JsonHandler]:
    """Rule-based handler for a versioned task (``note_extract.v1``...), imported lazily."""
    from petpulse.llm.fake_rules import HANDLERS  # lazy: avoids an import cycle

    return HANDLERS.get(task)


@dataclass
class FakeLLM:
    """Deterministic, offline LLM. Same input, same output. Never touches the network.

    ``fail=True`` simulates an outage on every call. Every call is appended to ``calls`` so
    tests can assert on the exact prompt sent. Versioned tasks (``note_extract.v1`` ...) are
    answered by the keyword rules in ``petpulse.llm.fake_rules``; ``register`` overrides them.

    ``mode`` (``FAKE_LLM_MODE``) exercises the client's unhappy paths:
    ``invalid_once`` returns schema-invalid JSON unless the request is a repair attempt,
    ``truncate`` returns cut-off JSON with ``finish_reason="length"``, ``fail`` raises.
    """

    fail: bool = False
    mode: FakeMode = "normal"
    name: str = "fake"
    model: str = FAKE_MODEL
    calls: list[dict[str, Any]] = field(default_factory=list)
    _json_handlers: dict[str, JsonHandler] = field(default_factory=dict)

    def register(self, task: str, handler: JsonHandler) -> None:
        self._json_handlers[task] = handler

    async def complete_json(
        self,
        *,
        task: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> RawCompletion:
        self.calls.append(
            {
                "api": "complete_json",
                "task": task,
                "system": system,
                "user": user,
                "schema": schema,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        if self.fail or self.mode == "fail":
            raise LLMError(f"simulated provider outage (task={task})")
        handler = self._json_handlers.get(task) or default_json_handler(task)
        payload = handler(system, user, schema) if handler else skeleton_from_schema(schema)
        finish_reason = "stop"
        if self.mode == "invalid_once" and REPAIR_MARKER not in user and isinstance(payload, dict):
            # The classic M1 failure: an off-enum label plus an invented field.
            payload = {**payload, "kind": "Emergency!!", "confidence": 7}
        text = json.dumps(payload, sort_keys=True)
        if self.mode == "truncate":
            text, finish_reason = text[: max(1, len(text) // 2)], "length"
        return RawCompletion(
            text=text,
            model=self.model,
            input_tokens=_estimate_tokens(system + user),
            output_tokens=_estimate_tokens(text),
            finish_reason=finish_reason,
        )


def schema_name(task: str) -> str:
    """OpenAI ``json_schema.name``: letters, digits, ``_`` and ``-`` only, at most 64 chars."""
    return re.sub(r"[^A-Za-z0-9_-]", "_", task)[:64]


class OpenAILLM:
    """Live adapter over the OpenAI Chat Completions API. ``openai`` is imported on first use.

    - strict structured output: ``response_format={"type": "json_schema", "strict": true}``
      with the schema the client derived from the Pydantic model;
    - a pinned, dated model id (``petpulse.llm.config.OPENAI_PINNED_MODEL`` / ``OPENAI_MODEL``);
    - a request timeout and a bounded number of SDK transport retries;
    - ``finish_reason`` is passed through (``length`` = truncated) and a structured-output
      refusal or content filter raises ``LLMRefusal``; transport/API errors raise ``LLMError``.

    The client (``petpulse.llm.client``) validates, repairs once, and records every attempt.
    ``http_client`` lets contract tests inject a mocked transport; production passes nothing.
    """

    name = "openai"

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_OPENAI_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        *,
        max_retries: int = OPENAI_SDK_MAX_RETRIES,
        base_url: Optional[str] = None,
        http_client: Any = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAILLM requires an API key")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = base_url
        self._http_client = http_client
        # One AsyncOpenAI client per event loop: its httpx pool holds connections bound to the
        # loop that opened them, so a client must never outlive (or cross into) another loop.
        # Weak keys, so a closed loop and its client are dropped together.
        self._clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Any] = weakref.WeakKeyDictionary()

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"api_key": self._api_key, "timeout": self.timeout, "max_retries": self.max_retries}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return kwargs

    def _async_client(self) -> Any:
        """The client for the running loop (``asyncio.run`` per call, a TestClient portal, uvicorn)."""
        loop = asyncio.get_running_loop()
        client = self._clients.get(loop)
        if client is None:
            import openai  # lazy

            kwargs = self._client_kwargs()
            if self._http_client is not None:  # tests only: a mocked, loop-independent transport
                kwargs["http_client"] = self._http_client
            client = openai.AsyncOpenAI(**kwargs)
            self._clients[loop] = client
        return client

    def build_request(
        self, *, task: str, system: str, user: str, schema: dict[str, Any], temperature: float, max_tokens: int
    ) -> dict[str, Any]:
        """The exact ``chat.completions.create`` arguments (asserted by the contract tests)."""
        request: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_completion_tokens": max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name(task), "schema": schema, "strict": True},
            },
        }
        facts = MODEL_FACTS.get(self.model)
        if facts is not None and facts.reasoning_effort is not None:
            request["reasoning_effort"] = facts.reasoning_effort
        return request

    async def complete_json(
        self,
        *,
        task: str,
        system: str,
        user: str,
        schema: dict[str, Any],
        temperature: float = 0.0,
        max_tokens: int = 800,
    ) -> RawCompletion:
        request = self.build_request(
            task=task, system=system, user=user, schema=schema, temperature=temperature, max_tokens=max_tokens
        )
        client = self._async_client()
        try:
            response = await client.chat.completions.create(**request)
        except Exception as exc:
            api_error = _openai_error_types()
            if api_error and isinstance(exc, api_error):
                status = getattr(exc, "status_code", None)
                raise LLMError(f"openai {type(exc).__name__}" + (f" (HTTP {status})" if status else "")) from exc
            raise
        if not response.choices:
            raise LLMError("openai returned no choices")
        choice = response.choices[0]
        message = choice.message
        finish_reason = choice.finish_reason or ""
        if getattr(message, "refusal", None):
            raise LLMRefusal("openai refused the request (structured-output refusal)")
        if finish_reason == "content_filter":
            raise LLMRefusal("openai stopped the response (content_filter)")
        usage = getattr(response, "usage", None)
        return RawCompletion(
            text=message.content or "",
            model=getattr(response, "model", None) or self.model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            finish_reason=finish_reason,
        )


def _openai_error_types() -> Optional[type[BaseException]]:
    """``openai.APIError`` (base of timeout, connection and HTTP status errors), if loaded."""
    import sys

    module = sys.modules.get("openai")
    error = getattr(module, "APIError", None) if module is not None else None
    return error if isinstance(error, type) and issubclass(error, BaseException) else None
