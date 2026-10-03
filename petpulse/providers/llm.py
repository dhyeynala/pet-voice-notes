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
from typing import Any, Callable, Optional, Protocol, runtime_checkable

FAKE_MODEL = "fake-llm-v1"
# Model used by the live adapter's ``complete_json`` until the LLM track pins dated snapshots
# in petpulse/llm/config.py. Legacy call sites still pass their own ``model=`` to legacy_chat.
DEFAULT_OPENAI_MODEL = "gpt-4o-mini"


class LLMError(RuntimeError):
    """A provider-level failure: outage, timeout, simulated failure."""


class UnsupportedTask(LLMError):
    """The fake has no deterministic behaviour for this task; callers take their fallback path."""


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


@dataclass
class FakeLLM:
    """Deterministic, offline LLM. Same input, same output. Never touches the network.

    ``fail=True`` simulates an outage on every call (used by tests and, later, ``FAKE_FAIL``).
    Every call is appended to ``calls`` so tests can assert on the exact prompt sent.
    The LLM track registers rule-based handlers per task with ``register``.
    """

    fail: bool = False
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
        self.calls.append({"api": "complete_json", "task": task, "system": system, "user": user, "schema": schema})
        if self.fail:
            raise LLMError(f"simulated provider outage (task={task})")
        handler = self._json_handlers.get(task)
        payload = handler(system, user, schema) if handler else skeleton_from_schema(schema)
        text = json.dumps(payload, sort_keys=True)
        return RawCompletion(
            text=text,
            model=self.model,
            input_tokens=_estimate_tokens(system + user),
            output_tokens=_estimate_tokens(text),
            finish_reason="stop",
        )

    def legacy_chat(self, task: str, **kwargs: Any) -> ChatCompletionLike:
        messages = list(kwargs.get("messages") or [])
        self.calls.append({"api": "legacy_chat", "task": task, "kwargs": kwargs, "messages": messages})
        if self.fail:
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


class OpenAILLM:
    """Live adapter. ``openai`` is imported on first use, never at module import.

    Hardening (pinned dated models, strict-schema validation and repair, call records, cost)
    is the LLM track's job; this is the wiring skeleton that auto-selection builds.
    """

    name = "openai"

    def __init__(self, api_key: str, model: str = DEFAULT_OPENAI_MODEL, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("OpenAILLM requires an API key")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self._sync: Any = None
        self._async: Any = None

    def _sync_client(self) -> Any:
        if self._sync is None:
            import openai  # lazy: demo mode never imports the SDK

            self._sync = openai.OpenAI(api_key=self._api_key, timeout=self.timeout, max_retries=2)
        return self._sync

    def _async_client(self) -> Any:
        if self._async is None:
            import openai  # lazy

            self._async = openai.AsyncOpenAI(api_key=self._api_key, timeout=self.timeout, max_retries=2)
        return self._async

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
        response = await self._async_client().chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": re.sub(r"[^A-Za-z0-9_-]", "_", task)[:64], "schema": schema, "strict": True},
            },
        )
        choice = response.choices[0]
        usage = getattr(response, "usage", None)
        return RawCompletion(
            text=choice.message.content or "",
            model=getattr(response, "model", self.model),
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
            finish_reason=choice.finish_reason or "",
        )

    def legacy_chat(self, task: str, **kwargs: Any) -> Any:
        return self._sync_client().chat.completions.create(**kwargs)
