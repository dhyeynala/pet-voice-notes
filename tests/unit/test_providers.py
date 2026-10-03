"""FakeLLM / FakeSTT determinism and the live adapters' lazy wiring (no network)."""

from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

from petpulse.providers import FakeLLM, FakeSTT, LLMError, LLMProvider, OpenAILLM, OpenAISTT, STTProvider
from petpulse.providers.llm import skeleton_from_schema

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"enum": ["MEDICAL", "DAILY_ACTIVITY", "UNKNOWN"]},
        "summary": {"type": "string"},
        "urgent": {"type": "boolean"},
        "observations": {"type": "array", "items": {"type": "string"}},
        "score": {"type": ["number", "null"]},
    },
    "required": ["kind", "summary", "urgent", "observations", "score"],
}

FAKE_KEY = "sk-test-not-real"  # pragma: allowlist secret


def test_fakes_satisfy_protocols():
    assert isinstance(FakeLLM(), LLMProvider)
    assert isinstance(FakeSTT(), STTProvider)


def test_complete_json_is_deterministic_and_schema_shaped():
    llm = FakeLLM()
    kwargs = dict(task="note_extract", system="sys", user="Max ate dinner", schema=SCHEMA)
    a = asyncio.run(llm.complete_json(**kwargs))
    b = asyncio.run(llm.complete_json(**kwargs))
    assert a == b
    assert a.model == "fake-llm-v1" and a.finish_reason == "stop"
    assert json.loads(a.text) == {"kind": "UNKNOWN", "summary": "", "urgent": False, "observations": [], "score": None}
    assert llm.calls[-1]["task"] == "note_extract"


def test_complete_json_uses_registered_handler():
    llm = FakeLLM()
    llm.register("note_extract", lambda system, user, schema: {"echo": user})
    out = asyncio.run(llm.complete_json(task="note_extract", system="s", user="hi", schema=SCHEMA))
    assert json.loads(out.text) == {"echo": "hi"}


def test_fail_mode_raises():
    llm = FakeLLM(fail=True)
    with pytest.raises(LLMError):
        asyncio.run(llm.complete_json(task="t", system="s", user="u", schema={}))


def test_skeleton_prefers_unknown_and_handles_const():
    assert skeleton_from_schema({"enum": ["A", "UNKNOWN"]}) == "UNKNOWN"
    assert skeleton_from_schema({"enum": ["A", "B"]}) == "A"
    assert skeleton_from_schema({"const": 3}) == 3
    assert skeleton_from_schema({"type": "integer"}) == 0


def test_fake_stt_contract():
    stt = FakeSTT()
    assert stt.transcribe(b"", "audio/webm").status == "no_speech"
    assert stt.transcribe(b"x" * 100, "audio/webm").status == "no_speech"
    audio = bytes(range(256)) * 20
    first = stt.transcribe(audio, "audio/webm")
    assert first.status == "ok" and first.text and first.provider == "fake"
    assert stt.transcribe(audio, "audio/webm") == first
    assert FakeSTT(fail=True).transcribe(audio, "audio/webm").status == "error"


def test_live_adapters_do_not_import_sdk_until_used(monkeypatch):
    monkeypatch.delitem(sys.modules, "openai", raising=False)
    OpenAILLM(api_key=FAKE_KEY)
    OpenAISTT(api_key=FAKE_KEY)
    assert "openai" not in sys.modules


def test_live_adapters_require_a_key():
    with pytest.raises(ValueError):
        OpenAILLM(api_key="")
    with pytest.raises(ValueError):
        OpenAISTT(api_key="")


class _FakeOpenAIModule(types.ModuleType):
    """Stands in for the ``openai`` SDK so the adapters' wiring is exercised offline."""

    def __init__(self):
        super().__init__("openai")
        self.created: list[dict] = []
        outer = self

        class _Completions:
            def create(self, **kwargs):
                outer.created.append(kwargs)
                msg = types.SimpleNamespace(content='{"ok": true}', tool_calls=None)
                return types.SimpleNamespace(
                    choices=[types.SimpleNamespace(message=msg, finish_reason="stop")],
                    model="gpt-test",
                    usage=types.SimpleNamespace(prompt_tokens=11, completion_tokens=3),
                )

        class _AsyncCompletions:
            async def create(self, **kwargs):
                return _Completions().create(**kwargs)

        class _Transcriptions:
            def create(self, **kwargs):
                outer.created.append(kwargs)
                return types.SimpleNamespace(text=" hello max ")

        class OpenAI:
            def __init__(self, **kwargs):
                outer.created.append({"client": kwargs})
                self.chat = types.SimpleNamespace(completions=_Completions())
                self.audio = types.SimpleNamespace(transcriptions=_Transcriptions())

        class AsyncOpenAI:
            def __init__(self, **kwargs):
                self.chat = types.SimpleNamespace(completions=_AsyncCompletions())

        self.OpenAI = OpenAI
        self.AsyncOpenAI = AsyncOpenAI


def test_openai_adapters_wire_through_sdk(monkeypatch):
    fake_sdk = _FakeOpenAIModule()
    monkeypatch.setitem(sys.modules, "openai", fake_sdk)

    llm = OpenAILLM(api_key=FAKE_KEY, model="gpt-test")
    raw = asyncio.run(llm.complete_json(task="note.extract v1", system="s", user="u", schema={"type": "object"}))
    assert (raw.text, raw.input_tokens, raw.output_tokens, raw.finish_reason) == ('{"ok": true}', 11, 3, "stop")
    sent = fake_sdk.created[-1]
    assert sent["response_format"]["json_schema"]["name"] == "note_extract_v1"
    assert sent["response_format"]["json_schema"]["strict"] is True

    assert not hasattr(llm, "legacy_chat")  # the transitional passthrough is gone

    stt = OpenAISTT(api_key=FAKE_KEY)
    result = stt.transcribe(b"audio-bytes", "audio/webm;codecs=opus")
    assert result.status == "ok" and result.text == "hello max" and result.provider == "openai"
    assert fake_sdk.created[-1]["file"][0] == "audio.webm"


# STT adapter contract tests (OpenAI request shape, Google segments/encodings) live in test_stt.py.
