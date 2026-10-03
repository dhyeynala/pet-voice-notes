"""LLM provider interface, the deterministic ``FakeLLM`` and the lazily imported ``OpenAILLM``.

Two entry points exist on purpose:

- ``complete_json`` is the target interface (structured output, one call per task). The
  LLM track builds the prompt registry, schemas and validating adapter on top of it.
- ``legacy_chat`` is a *transitional* OpenAI-shaped ``chat.completions.create`` passthrough
  so the legacy modules keep working on either provider with minimal change. It is removed
  once ``summarize_openai``, ``pdf_parser``, ``ai_analytics``, ``simple_rag_service`` and
  ``intelligent_chatbot_service`` are replaced (LLM track).
"""

from __future__ import annotations

import json
import re
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
# alias). Legacy call sites still pass their own ``model=`` to legacy_chat.
DEFAULT_OPENAI_MODEL = OPENAI_PINNED_MODEL

FakeMode = Literal["normal", "invalid_once", "truncate", "fail"]
FAKE_MODES: tuple[str, ...] = ("normal", "invalid_once", "truncate", "fail")
# The client marks a schema-repair attempt with this block; ``invalid_once`` keys off it.
REPAIR_MARKER = "<validation_error>"


class LLMError(RuntimeError):
    """A provider-level failure: outage, timeout, simulated failure."""


class UnsupportedTask(LLMError):
    """The fake has no deterministic behaviour for this task; callers take their fallback path."""


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

    def legacy_chat(self, task: str, **kwargs: Any) -> Any: ...


class LegacyTask:
    """Task names used by the legacy call sites (one per prompt)."""

    NOTE_SUMMARY = "legacy.note_summary"
    NOTE_CLASSIFY = "legacy.note_classify"
    PDF_SUMMARY = "legacy.pdf_summary"
    DAILY_HEADLINES = "legacy.daily_headlines"
    HEALTH_INSIGHTS = "legacy.health_insights"
    RAG_ANSWER = "legacy.rag_answer"
    CHAT_ASSISTANT = "legacy.chat_assistant"


# ---------------------------------------------------------------------------- OpenAI-shaped
@dataclass
class _Message:
    content: Optional[str]
    role: str = "assistant"
    tool_calls: Optional[list[Any]] = None


@dataclass
class _Choice:
    message: _Message
    finish_reason: str = "stop"
    index: int = 0


@dataclass
class _Usage:
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ChatCompletionLike:
    """The subset of ``openai.types.chat.ChatCompletion`` the legacy code reads."""

    choices: list[_Choice]
    model: str
    usage: _Usage


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def _messages_text(messages: list[dict[str, Any]], role: str) -> str:
    return "\n".join(str(m.get("content") or "") for m in messages if m.get("role") == role)


def _after_marker(text: str, marker: str) -> str:
    idx = text.find(marker)
    return text[idx + len(marker) :] if idx >= 0 else ""


def _note_body(messages: list[dict[str, Any]]) -> str:
    """Legacy user prompts are ``"<instruction>:\\n\\n<note text>"``."""
    user = _messages_text(messages, "user")
    return user.split("\n\n", 1)[1] if "\n\n" in user else user


def _first_sentence(text: str, limit: int = 200) -> str:
    text = " ".join(text.split())
    match = re.match(r"(.+?[.!?])(\s|$)", text)
    sentence = match.group(1) if match else text
    return sentence[:limit]


_MEDICAL_WORDS = re.compile(
    r"\b(vomit\w*|blood\w*|diarrh\w*|limp\w*|vet|medication|pill|sick|pain\w*|injur\w*|collaps\w*|seizure\w*|"
    r"letharg\w*|cough\w*|fever|swollen|bleed\w*)\b",
    re.IGNORECASE,
)
_DAILY_WORDS = re.compile(
    r"\b(walk\w*|play\w*|ate|eat\w*|meal|dinner|breakfast|slept|sleep\w*|nap\w*|groom\w*|bath|park|fetch|"
    r"train\w*|treat\w*|happy|energetic)\b",
    re.IGNORECASE,
)


def _fake_note_summary(messages: list[dict[str, Any]]) -> str:
    body = _note_body(messages).strip()
    if not body:
        return "[Simulated summary] (empty note)"
    return f"[Simulated summary] {_first_sentence(body)}"


def _fake_note_classify(messages: list[dict[str, Any]]) -> str:
    body = _note_body(messages)
    medical = sorted({m.lower() for m in _MEDICAL_WORDS.findall(body)})
    daily = sorted({m.lower() for m in _DAILY_WORDS.findall(body)})
    if medical and daily:
        label = "MIXED"
    elif medical:
        label = "MEDICAL"
    elif daily:
        label = "DAILY_ACTIVITY"
    else:
        label = "OTHER"
    result = {
        "classification": label,
        "confidence": 0.5,
        "keywords": (medical + daily)[:5],
        "reasoning": "Simulated keyword classification (fake provider)",
        "primary_activities": daily[:3],
    }
    return json.dumps(result, sort_keys=True)


_PDF_LINE = re.compile(r"mg\b|diagnos|vaccin|follow.?up|recheck", re.IGNORECASE)


def _fake_pdf_summary(messages: list[dict[str, Any]]) -> str:
    body = _messages_text(messages, "user")
    lines = [" ".join(line.split()) for line in body.splitlines()]
    hits = [line for line in lines if line and _PDF_LINE.search(line)][:8]
    if not hits:
        return "[Simulated summary] No medications, diagnoses or follow-ups found in the document text."
    return "[Simulated summary] Key lines from the document:\n" + "\n".join(f"- {line}" for line in hits)


def _context_answer(messages: list[dict[str, Any]], marker: str) -> str:
    context = _after_marker(_messages_text(messages, "system"), marker).strip()
    question = _messages_text(messages, "user").strip()
    lines = [line.strip() for line in context.splitlines() if line.strip()][:3]
    if not lines:
        return f"[Simulated answer] I found no records to answer: {question[:120]}"
    return "[Simulated answer] From the provided context:\n" + "\n".join(f"- {line[:200]}" for line in lines)


def _fake_rag_answer(messages: list[dict[str, Any]]) -> str:
    return _context_answer(messages, "Context from Pet's Health Data, Veterinary Knowledge, and Breed Information:")


def _fake_chat_assistant(messages: list[dict[str, Any]]) -> str:
    return _context_answer(messages, "Context from Pet's Health Data:")


_LEGACY_HANDLERS: dict[str, Callable[[list[dict[str, Any]]], str]] = {
    LegacyTask.NOTE_SUMMARY: _fake_note_summary,
    LegacyTask.NOTE_CLASSIFY: _fake_note_classify,
    LegacyTask.PDF_SUMMARY: _fake_pdf_summary,
    LegacyTask.RAG_ANSWER: _fake_rag_answer,
    LegacyTask.CHAT_ASSISTANT: _fake_chat_assistant,
    # DAILY_HEADLINES and HEALTH_INSIGHTS are deliberately absent: the legacy code then takes
    # its rule-based fallback. The LLM track replaces both with code-computed insights.
}


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

    def legacy_chat(self, task: str, **kwargs: Any) -> ChatCompletionLike:
        messages = list(kwargs.get("messages") or [])
        self.calls.append({"api": "legacy_chat", "task": task, "kwargs": kwargs, "messages": messages})
        if self.fail or self.mode == "fail":
            raise LLMError(f"simulated provider outage (task={task})")
        handler = _LEGACY_HANDLERS.get(task)
        if handler is None:
            raise UnsupportedTask(f"FakeLLM has no deterministic behaviour for {task!r}")
        content = handler(messages)
        prompt = "\n".join(str(m.get("content") or "") for m in messages)
        return ChatCompletionLike(
            choices=[_Choice(message=_Message(content=content))],
            model=self.model,
            usage=_Usage(prompt_tokens=_estimate_tokens(prompt), completion_tokens=_estimate_tokens(content)),
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
        self._sync: Any = None
        self._async: Any = None

    def _client_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"api_key": self._api_key, "timeout": self.timeout, "max_retries": self.max_retries}
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return kwargs

    def _sync_client(self) -> Any:
        if self._sync is None:
            import openai  # lazy: demo mode never imports the SDK

            self._sync = openai.OpenAI(**self._client_kwargs())
        return self._sync

    def _async_client(self) -> Any:
        if self._async is None:
            import openai  # lazy

            kwargs = self._client_kwargs()
            if self._http_client is not None:
                kwargs["http_client"] = self._http_client
            self._async = openai.AsyncOpenAI(**kwargs)
        return self._async

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

    def legacy_chat(self, task: str, **kwargs: Any) -> Any:
        return self._sync_client().chat.completions.create(**kwargs)


def _openai_error_types() -> Optional[type[BaseException]]:
    """``openai.APIError`` (base of timeout, connection and HTTP status errors), if loaded."""
    import sys

    module = sys.modules.get("openai")
    error = getattr(module, "APIError", None) if module is not None else None
    return error if isinstance(error, type) and issubclass(error, BaseException) else None
