"""FakeLLM / FakeSTT determinism and the live adapters' lazy wiring (no network)."""

from __future__ import annotations

import asyncio
import json
import sys
import types

import pytest

from petpulse.providers import FakeLLM, FakeSTT, LLMError, LLMProvider, OpenAILLM, OpenAISTT, STTProvider, UnsupportedTask
from petpulse.providers.llm import LegacyTask, skeleton_from_schema

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
    with pytest.raises(LLMError):
        llm.legacy_chat(LegacyTask.NOTE_SUMMARY, messages=[])


def test_skeleton_prefers_unknown_and_handles_const():
    assert skeleton_from_schema({"enum": ["A", "UNKNOWN"]}) == "UNKNOWN"
    assert skeleton_from_schema({"enum": ["A", "B"]}) == "A"
    assert skeleton_from_schema({"const": 3}) == 3
    assert skeleton_from_schema({"type": "integer"}) == 0


def _chat(llm, task, system, user):
    resp = llm.legacy_chat(
        task, model="gpt-4o", messages=[{"role": "system", "content": system}, {"role": "user", "content": user}]
    )
    return resp.choices[0].message.content


def test_legacy_classify_is_keyword_based_json():
    llm = FakeLLM()
    out = json.loads(
        _chat(llm, LegacyTask.NOTE_CLASSIFY, "classify", "Classify this pet content:\n\nMax vomited after his walk")
    )
    assert out["classification"] == "MIXED"
    assert (
        json.loads(_chat(llm, LegacyTask.NOTE_CLASSIFY, "c", "x:\n\nMax had a long walk"))["classification"]
        == "DAILY_ACTIVITY"
    )
    assert json.loads(_chat(llm, LegacyTask.NOTE_CLASSIFY, "c", "x:\n\nMax is limping"))["classification"] == "MEDICAL"
    assert json.loads(_chat(llm, LegacyTask.NOTE_CLASSIFY, "c", "x:\n\nthe weather is nice"))["classification"] == "OTHER"


def test_legacy_summary_and_pdf_are_labelled_simulated():
    llm = FakeLLM()
    summary = _chat(llm, LegacyTask.NOTE_SUMMARY, "s", "Summarize:\n\nMax walked 30 minutes. Then he slept.")
    assert summary == "[Simulated summary] Max walked 30 minutes."
    pdf = _chat(llm, LegacyTask.PDF_SUMMARY, "s", "Exam notes\nApoquel 16 mg daily\nRecheck in 2 weeks\nWeight 30kg")
    assert pdf.startswith("[Simulated summary]")
    assert "Apoquel 16 mg daily" in pdf and "Recheck in 2 weeks" in pdf and "Weight" not in pdf


def test_legacy_chat_answers_only_from_given_context():
    llm = FakeLLM()
    with_ctx = _chat(llm, LegacyTask.CHAT_ASSISTANT, "Prompt\nContext from Pet's Health Data:\nMax limped on Tuesday", "When?")
    assert "Max limped on Tuesday" in with_ctx
    without = _chat(llm, LegacyTask.CHAT_ASSISTANT, "Prompt with no context block", "When did Max limp?")
    assert "no records" in without


def test_legacy_unsupported_task_raises_so_callers_fall_back():
    with pytest.raises(UnsupportedTask):
        FakeLLM().legacy_chat(LegacyTask.HEALTH_INSIGHTS, messages=[])


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

    legacy = llm.legacy_chat(LegacyTask.NOTE_SUMMARY, model="gpt-4o", messages=[{"role": "user", "content": "x"}])
    assert legacy.choices[0].message.content == '{"ok": true}'
    assert fake_sdk.created[-1]["model"] == "gpt-4o"

    stt = OpenAISTT(api_key=FAKE_KEY)
    result = stt.transcribe(b"audio-bytes", "audio/webm;codecs=opus")
    assert result.status == "ok" and result.text == "hello max" and result.provider == "openai"
    assert fake_sdk.created[-1]["file"][0] == "audio.webm"


def _fake_google_speech(monkeypatch, results):
    google = types.ModuleType("google")
    cloud = types.ModuleType("google.cloud")
    speech = types.ModuleType("google.cloud.speech")
    sent: dict = {}

    class _Encoding:
        WEBM_OPUS, OGG_OPUS, LINEAR16 = "WEBM_OPUS", "OGG_OPUS", "LINEAR16"

    class RecognitionConfig:
        AudioEncoding = _Encoding

        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class SpeechClient:
        def recognize(self, config, audio):
            sent["config"] = config.kwargs
            return types.SimpleNamespace(results=results)

    speech.RecognitionConfig = RecognitionConfig
    speech.RecognitionAudio = lambda content: content
    speech.SpeechClient = SpeechClient
    cloud.speech = speech
    google.cloud = cloud
    for name, module in {"google": google, "google.cloud": cloud, "google.cloud.speech": speech}.items():
        monkeypatch.setitem(sys.modules, name, module)
    return sent


def _segment(text):
    return types.SimpleNamespace(alternatives=[types.SimpleNamespace(transcript=text)])


def test_google_stt_joins_all_segments(monkeypatch):
    from petpulse.providers import GoogleSTT

    sent = _fake_google_speech(monkeypatch, [_segment("Max vomited twice "), _segment("and there was some blood")])
    result = GoogleSTT().transcribe(b"opus-bytes", "audio/webm;codecs=opus")
    assert result.status == "ok" and result.text == "Max vomited twice and there was some blood"
    assert sent["config"]["encoding"] == "WEBM_OPUS" and sent["config"]["sample_rate_hertz"] == 48000


def test_google_stt_no_speech_and_error(monkeypatch):
    from petpulse.providers import GoogleSTT

    _fake_google_speech(monkeypatch, [])
    assert GoogleSTT().transcribe(b"pcm", "audio/wav").status == "no_speech"
    assert GoogleSTT().transcribe(b"", "audio/wav").status == "no_speech"
    monkeypatch.setitem(sys.modules, "google.cloud.speech", None)
    monkeypatch.delattr(sys.modules["google.cloud"], "speech")
    failed = GoogleSTT().transcribe(b"pcm", "audio/ogg")
    assert failed.status == "error" and failed.text == ""
