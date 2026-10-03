"""Contract tests for the live OpenAI adapter, against a mocked HTTP transport (no network).

They pin what is sent (endpoint, pinned model, strict json_schema, temperature 0,
``max_completion_tokens``, ``reasoning_effort``, auth header) and how every unhappy response
maps: ``length`` -> truncated failure, refusal -> ``LLMRefusal``, HTTP 5xx / timeout ->
``LLMError``. A model or SDK upgrade that changes any of this fails here, not in the demo.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Callable

import httpx2
import pytest

from petpulse.llm.client import LLMClient, LLMFailure
from petpulse.llm.config import OPENAI_PINNED_MODEL, TASK_SETTINGS
from petpulse.llm.schemas import NoteExtraction, strict_json_schema
from petpulse.providers.llm import LLMError, LLMRefusal, OpenAILLM
from petpulse.services.notes import NOTE_TASK, numbered

FAKE_KEY = "sk-test-not-a-real-key"  # pragma: allowlist secret
GOOD = {"kind": "DAILY_ACTIVITY", "summary": "Walked.", "observations": [], "red_flags": [], "addressed_to_model": False}


def completion(content: Any = GOOD, *, finish_reason: str = "stop", refusal: Any = None) -> dict[str, Any]:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1_790_000_000,
        "model": OPENAI_PINNED_MODEL,
        "choices": [
            {
                "index": 0,
                "finish_reason": finish_reason,
                "message": {
                    "role": "assistant",
                    "content": None if refusal else (content if isinstance(content, str) else json.dumps(content)),
                    "refusal": refusal,
                },
            }
        ],
        "usage": {"prompt_tokens": 321, "completion_tokens": 45, "total_tokens": 366},
    }


def adapter(handler: Callable[[httpx2.Request], httpx2.Response], **kwargs: Any) -> OpenAILLM:
    client = httpx2.AsyncClient(transport=httpx2.MockTransport(handler))
    return OpenAILLM(api_key=FAKE_KEY, max_retries=0, http_client=client, **kwargs)


def run_note(llm: OpenAILLM) -> Any:
    variables = {"note": numbered(["He walked for an hour."]), "sentence_count": "1"}
    return asyncio.run(LLMClient(llm).run(NOTE_TASK, variables))


def test_request_matches_the_contract_and_usage_is_parsed():
    seen: list[httpx2.Request] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        return httpx2.Response(200, json=completion())

    result = run_note(adapter(handler))
    assert result.value.kind == "DAILY_ACTIVITY" and result.mode == "live" and result.attempts == 1
    (request,) = seen
    assert request.method == "POST" and request.url.path.endswith("/v1/chat/completions")
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    body = json.loads(request.content)
    assert body["model"] == OPENAI_PINNED_MODEL
    assert body["temperature"] == 0
    assert body["max_completion_tokens"] == TASK_SETTINGS["note_extract"].max_tokens and "max_tokens" not in body
    assert body["reasoning_effort"] == "none"
    fmt = body["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["name"] == "note_extract_v1"
    assert fmt["json_schema"]["schema"] == strict_json_schema(NoteExtraction)
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert "<note>" in body["messages"][1]["content"]


def test_usage_is_returned_on_the_raw_completion():
    llm = adapter(lambda request: httpx2.Response(200, json=completion()))
    raw = asyncio.run(llm.complete_json(task="note_extract.v1", system="s", user="u", schema={"type": "object"}))
    assert (raw.input_tokens, raw.output_tokens, raw.finish_reason) == (321, 45, "stop")
    assert raw.model == OPENAI_PINNED_MODEL


def test_length_finish_is_a_truncation_failure_not_a_repair():
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(request)
        return httpx2.Response(200, json=completion('{"kind": "DAILY_ACT', finish_reason="length"))

    with pytest.raises(LLMFailure) as info:
        run_note(adapter(handler))
    assert info.value.reason == "truncated" and len(calls) == 1


def test_schema_invalid_output_gets_exactly_one_repair():
    replies = [completion({**GOOD, "kind": "Emergency!!"}), completion()]
    calls = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        calls.append(json.loads(request.content))
        return httpx2.Response(200, json=replies[len(calls) - 1])

    result = run_note(adapter(handler))
    assert result.attempts == 2 and "<validation_error>" in calls[1]["messages"][1]["content"]


def test_refusal_raises_llm_refusal():
    llm = adapter(lambda request: httpx2.Response(200, json=completion(refusal="I can't help with that.")))
    with pytest.raises(LLMRefusal):
        asyncio.run(llm.complete_json(task="t", system="s", user="u", schema={"type": "object"}))
    with pytest.raises(LLMFailure) as info:
        run_note(llm)
    assert info.value.reason == "refused"


def test_content_filter_raises_llm_refusal():
    llm = adapter(lambda request: httpx2.Response(200, json=completion(finish_reason="content_filter")))
    with pytest.raises(LLMRefusal):
        asyncio.run(llm.complete_json(task="t", system="s", user="u", schema={"type": "object"}))


def test_http_500_is_an_llm_error():
    llm = adapter(lambda request: httpx2.Response(500, json={"error": {"message": "boom", "type": "server_error"}}))
    with pytest.raises(LLMError):
        asyncio.run(llm.complete_json(task="t", system="s", user="u", schema={"type": "object"}))
    with pytest.raises(LLMFailure) as info:
        run_note(llm)
    assert info.value.reason == "provider_error"


def test_timeout_is_an_llm_error():
    def handler(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ReadTimeout("timed out", request=request)

    with pytest.raises(LLMError):
        asyncio.run(adapter(handler).complete_json(task="t", system="s", user="u", schema={"type": "object"}))


def test_undated_model_is_rejected_by_settings():
    from petpulse.core.config import ConfigError, Settings

    with pytest.raises(ConfigError, match="dated snapshot"):
        Settings(llm_provider="openai", openai_api_key=FAKE_KEY, openai_model="gpt-5.4-mini").check()
    Settings(llm_provider="openai", openai_api_key=FAKE_KEY).check()
