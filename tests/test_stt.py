"""STT providers: FakeSTT determinism and contract tests for the live adapters.

No live calls: OpenAI is exercised through the real SDK with a mocked HTTP transport (and with
a stub client); Google through a stub ``google.cloud.speech`` module. Both check the exact
request shape the adapter sends.
"""

from __future__ import annotations

import json
import sys
import types
from typing import Any

import pytest

from petpulse.core import deps
from petpulse.providers.stt import (
    CANNED_TRANSCRIPTS,
    DEFAULT_OPENAI_STT_MODEL,
    FakeSTT,
    GoogleSTT,
    OpenAISTT,
    STTProvider,
    Transcription,
)
from petpulse.seed.samples import audio_manifest
from tests.audio_fixtures import mp4, wav, webm

FAKE_KEY = "sk-test-not-real-0000"  # pragma: allowlist secret


def _sample(sample_id: str) -> bytes:
    sample = audio_manifest().get(sample_id)
    assert sample is not None
    return sample.read_bytes()


# ------------------------------------------------------------------------------ FakeSTT
def test_providers_satisfy_the_protocol():
    for provider in (FakeSTT(), OpenAISTT(api_key=FAKE_KEY), GoogleSTT()):
        assert isinstance(provider, STTProvider)
        assert provider.supported_mimes


def test_fake_returns_the_manifest_transcript_for_bundled_clips():
    stt = FakeSTT()
    for sample in audio_manifest().samples:
        result = stt.transcribe(sample.read_bytes(), sample.mime, hint="blob")
        assert result.status == sample.status
        assert result.text == sample.transcript
        if sample.status == "ok":
            assert result.confidence == sample.confidence


def test_fake_filename_hint_matches_a_sample():
    result = FakeSTT().transcribe(b"\x1a\x45\xdf\xa3" + b"\x01" * 4000, "audio/webm", hint="uploads/vomiting_blood.webm")
    assert result.text == audio_manifest().get("vomiting_blood").transcript  # type: ignore[union-attr]
    assert FakeSTT().transcribe(b"\x01" * 4000, "audio/webm", hint="silence.wav").status == "no_speech"


def test_fake_canned_transcript_is_deterministic():
    audio = webm([0, 1000]) + bytes(range(256)) * 20
    first = FakeSTT().transcribe(audio, "audio/webm")
    assert first.status == "ok" and first.text in CANNED_TRANSCRIPTS and first.confidence == 0.9
    assert FakeSTT().transcribe(audio, "audio/webm") == first
    others = {FakeSTT().transcribe(audio + bytes([i]), "audio/webm").text for i in range(32)}
    assert len(others) > 1  # spread over the canned set


def test_fake_near_silence_and_tiny_audio_are_no_speech():
    stt = FakeSTT()
    assert stt.transcribe(wav(2.0, amplitude=5), "audio/wav").status == "no_speech"
    assert stt.transcribe(b"\x1a\x45\xdf\xa3" + b"\x00" * 100, "audio/webm").status == "no_speech"
    assert stt.transcribe(wav(2.0, amplitude=8000), "audio/wav").status == "ok"


def test_fake_failure_and_call_log_holds_no_audio():
    stt = FakeSTT(fail=True)
    result = stt.transcribe(_sample("walk_and_dinner"), "audio/webm", hint="x.webm")
    assert result.status == "error" and result.text == "" and result.error
    assert stt.calls == [{"bytes": len(_sample("walk_and_dinner")), "mime": "audio/webm", "hint": "x.webm"}]


def test_transcription_public_shape():
    assert Transcription(status="ok", text="hi", provider="openai", confidence=0.5, error=None).public() == {
        "status": "ok",
        "text": "hi",
        "confidence": 0.5,
    }


# ------------------------------------------------------------------- OpenAI (mocked HTTP)
def _mock_openai_http(handler):
    import httpx2

    return httpx2.Client(transport=httpx2.MockTransport(handler))


def _multipart_fields(request) -> tuple[dict[str, list[str]], dict[str, Any]]:
    """Parse the multipart body the SDK sent: text fields and the file part."""
    content_type = request.headers["content-type"]
    boundary = content_type.split("boundary=", 1)[1].encode()
    fields: dict[str, list[str]] = {}
    file_part: dict[str, Any] = {}
    for part in request.content.split(b"--" + boundary):
        if b"\r\n\r\n" not in part:
            continue
        head, body = part.split(b"\r\n\r\n", 1)
        body = body[:-2] if body.endswith(b"\r\n") else body
        headers = head.decode("latin-1")
        name = headers.split('name="', 1)[1].split('"', 1)[0]
        if 'filename="' in headers:
            file_part = {
                "name": name,
                "filename": headers.split('filename="', 1)[1].split('"', 1)[0],
                "content_type": headers.split("Content-Type: ", 1)[1].split("\r\n", 1)[0].strip(),
                "bytes": body,
            }
        else:
            fields.setdefault(name, []).append(body.decode())
    return fields, file_part


@pytest.mark.parametrize(
    "audio_bytes, declared, filename, mime",
    [
        (_sample("vomiting_blood"), "audio/webm;codecs=opus", "audio.webm", "audio/webm"),
        (_sample("heartworm_pill"), "audio/ogg", "audio.ogg", "audio/ogg"),
        (mp4(3.0), "audio/mp4", "audio.mp4", "audio/mp4"),
        (wav(1.0), "audio/x-wav", "audio.wav", "audio/wav"),
        (_sample("walk_and_dinner"), "application/octet-stream", "audio.webm", "audio/webm"),  # sniffed
    ],
)
def test_openai_http_request_shape(audio_bytes, declared, filename, mime):
    sent: list[Any] = []

    def handler(request):
        sent.append(request)
        body = {
            "text": " Max vomited twice. ",
            "logprobs": [{"token": "Max", "logprob": -0.1}, {"token": "v", "logprob": -0.3}],
        }
        return __import__("httpx2").Response(200, json=body)

    stt = OpenAISTT(api_key=FAKE_KEY, timeout=12.5, http_client=_mock_openai_http(handler))
    result = stt.transcribe(audio_bytes, declared, hint="ignored-name.bin")

    assert result.status == "ok" and result.text == "Max vomited twice." and result.provider == "openai"
    assert result.confidence == pytest.approx(0.819, abs=0.001)  # exp(mean(-0.1, -0.3))
    [request] = sent
    assert request.method == "POST" and request.url.path == "/v1/audio/transcriptions"
    assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
    fields, file_part = _multipart_fields(request)
    assert fields["model"] == [DEFAULT_OPENAI_STT_MODEL]
    assert fields["response_format"] == ["json"]
    assert fields["include[]"] == ["logprobs"]
    assert fields["language"] == ["en"] and fields["temperature"] == ["0"]
    assert fields["prompt"] and "pet" in fields["prompt"][0]
    assert file_part["name"] == "file" and file_part["filename"] == filename
    assert file_part["content_type"] == mime and file_part["bytes"] == audio_bytes


def test_openai_http_errors_become_typed_errors_without_leaking(monkeypatch):
    def handler(request):
        return __import__("httpx2").Response(401, json={"error": {"message": f"Incorrect API key {FAKE_KEY}"}})

    stt = OpenAISTT(api_key=FAKE_KEY, max_retries=0, http_client=_mock_openai_http(handler))
    result = stt.transcribe(_sample("vomiting_blood"), "audio/webm")
    assert result.status == "error" and result.text == ""
    assert result.error == "AuthenticationError (401)"
    assert FAKE_KEY not in repr(stt) and FAKE_KEY not in str(result)


def test_openai_http_timeout_is_an_error():
    import httpx2

    def handler(request):
        raise httpx2.ReadTimeout("slow", request=request)

    stt = OpenAISTT(api_key=FAKE_KEY, max_retries=0, timeout=0.5, http_client=_mock_openai_http(handler))
    result = stt.transcribe(_sample("vomiting_blood"), "audio/webm")
    assert result.status == "error" and result.error == "APITimeoutError"


def test_openai_empty_text_is_no_speech():
    def handler(request):
        return __import__("httpx2").Response(200, json={"text": "  "})

    stt = OpenAISTT(api_key=FAKE_KEY, http_client=_mock_openai_http(handler))
    assert stt.transcribe(_sample("vomiting_blood"), "audio/webm").status == "no_speech"


# ------------------------------------------------------------------ OpenAI (stub client)
class _StubTranscriptions:
    def __init__(self, response: Any = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.response = response
        self.error = error

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def _stub_client(transcriptions: _StubTranscriptions) -> Any:
    return types.SimpleNamespace(audio=types.SimpleNamespace(transcriptions=transcriptions))


def test_openai_whisper_uses_verbose_json_and_detects_silent_segments():
    segment = types.SimpleNamespace
    speech = _StubTranscriptions(
        types.SimpleNamespace(text="Max ate.", segments=[segment(avg_logprob=-0.2, no_speech_prob=0.01)])
    )
    stt = OpenAISTT(api_key=FAKE_KEY, model="whisper-1", client=_stub_client(speech))
    result = stt.transcribe(_sample("walk_and_dinner"), "audio/webm")
    assert result.status == "ok" and result.confidence == pytest.approx(0.819, abs=0.001)
    assert speech.calls[0]["response_format"] == "verbose_json" and "include" not in speech.calls[0]

    hallucination = _StubTranscriptions(
        types.SimpleNamespace(text="Thank you.", segments=[segment(avg_logprob=-1.4, no_speech_prob=0.93)])
    )
    stt = OpenAISTT(api_key=FAKE_KEY, model="whisper-1", client=_stub_client(hallucination))
    assert stt.transcribe(_sample("walk_and_dinner"), "audio/webm").status == "no_speech"


def test_openai_unsupported_container_never_calls_the_api():
    calls = _StubTranscriptions(types.SimpleNamespace(text="x"))
    stt = OpenAISTT(api_key=FAKE_KEY, client=_stub_client(calls))
    result = stt.transcribe(b"ID3\x04" + b"\x00" * 3000, "audio/mpeg")
    assert result.status == "error" and result.error and result.error.startswith("unsupported_format")
    assert calls.calls == []


def test_openai_client_is_built_lazily_with_timeout_and_retries(monkeypatch):
    built: list[dict[str, Any]] = []
    speech = _StubTranscriptions(types.SimpleNamespace(text="hello max"))

    class FakeOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            built.append(kwargs)
            self.audio = types.SimpleNamespace(transcriptions=speech)

    fake_sdk = types.ModuleType("openai")
    fake_sdk.OpenAI = FakeOpenAI  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", fake_sdk)
    stt = OpenAISTT(api_key=FAKE_KEY, timeout=7.0, max_retries=1, language="en-GB")
    assert built == []
    stt.transcribe(_sample("walk_and_dinner"), "audio/webm")
    stt.transcribe(_sample("walk_and_dinner"), "audio/webm")
    assert built == [{"api_key": FAKE_KEY, "timeout": 7.0, "max_retries": 1}]
    assert speech.calls[0]["language"] == "en"


def test_settings_pin_the_openai_model_timeout_and_language(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", FAKE_KEY)
    monkeypatch.setenv("STT_TIMEOUT_SECONDS", "9")
    monkeypatch.setenv("STT_LANGUAGE", "es-MX")
    deps.reset()
    stt = deps.get_stt()
    assert isinstance(stt, OpenAISTT)
    assert (stt.model, stt.timeout, stt.language) == (DEFAULT_OPENAI_STT_MODEL, 9.0, "es")
    monkeypatch.setenv("STT_OPENAI_MODEL", "whisper-1")
    deps.reset()
    assert deps.get_stt().model == "whisper-1"


def test_settings_build_google_with_credentials(monkeypatch):
    monkeypatch.setenv("STT_PROVIDER", "google")
    monkeypatch.setenv("GOOGLE_APPLICATION_CREDENTIALS", "/secrets/sa.json")
    deps.reset()
    stt = deps.get_stt()
    assert isinstance(stt, GoogleSTT)
    assert (stt.credentials_path, stt.language_code, stt.timeout) == ("/secrets/sa.json", "en-US", 30.0)


# ---------------------------------------------------------------------- Google (stub SDK)
class _GoogleStub:
    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.results: list[Any] = []
        self.error: Exception | None = None
        self.from_file: list[str] = []


def _install_google(monkeypatch, stub: _GoogleStub) -> None:
    google = types.ModuleType("google")
    cloud = types.ModuleType("google.cloud")
    speech = types.ModuleType("google.cloud.speech")

    class AudioEncoding:
        LINEAR16, OGG_OPUS, WEBM_OPUS = 1, 6, 9

    class RecognitionConfig:
        def __init__(self, **kwargs: Any) -> None:
            self.kwargs = kwargs

    RecognitionConfig.AudioEncoding = AudioEncoding  # type: ignore[attr-defined]

    class RecognitionAudio:
        def __init__(self, content: bytes) -> None:
            self.content = content

    class SpeechClient:
        @classmethod
        def from_service_account_file(cls, path: str) -> "SpeechClient":
            stub.from_file.append(path)
            return cls()

        def recognize(self, *, config: Any, audio: Any, timeout: float) -> Any:
            stub.requests.append({"config": config.kwargs, "content": audio.content, "timeout": timeout})
            if stub.error:
                raise stub.error
            return types.SimpleNamespace(results=stub.results)

    speech.RecognitionConfig = RecognitionConfig  # type: ignore[attr-defined]
    speech.RecognitionAudio = RecognitionAudio  # type: ignore[attr-defined]
    speech.SpeechClient = SpeechClient  # type: ignore[attr-defined]
    cloud.speech = speech  # type: ignore[attr-defined]
    google.cloud = cloud  # type: ignore[attr-defined]
    for name, module in {"google": google, "google.cloud": cloud, "google.cloud.speech": speech}.items():
        monkeypatch.setitem(sys.modules, name, module)


def _segment(text: str, confidence: float = 0.0) -> Any:
    return types.SimpleNamespace(alternatives=[types.SimpleNamespace(transcript=text, confidence=confidence)])


@pytest.fixture
def google_stub(monkeypatch) -> _GoogleStub:
    stub = _GoogleStub()
    _install_google(monkeypatch, stub)
    return stub


def test_google_joins_all_result_segments(google_stub):
    """Review L3: the legacy code kept only results[0]."""
    google_stub.results = [
        _segment("Max vomited twice ", 0.9),
        _segment("this morning", 0.7),
        types.SimpleNamespace(alternatives=[]),
        _segment("and there was some blood.", 0.8),
    ]
    result = GoogleSTT(timeout=11.0).transcribe(_sample("vomiting_blood"), "audio/webm;codecs=opus")
    assert result.status == "ok" and result.provider == "google"
    assert result.text == "Max vomited twice this morning and there was some blood."
    assert result.confidence == pytest.approx(0.8)
    [request] = google_stub.requests
    assert request["timeout"] == 11.0 and request["content"] == _sample("vomiting_blood")
    assert request["config"] == {
        "language_code": "en-US",
        "enable_automatic_punctuation": True,
        "model": "default",
        "encoding": 9,  # WEBM_OPUS
        "sample_rate_hertz": 48000,
    }


def test_google_ogg_opus_and_wav_mapping(google_stub):
    google_stub.results = [_segment("ok")]
    stt = GoogleSTT(language_code="en-GB")
    stt.transcribe(_sample("heartworm_pill"), "audio/ogg")
    stt.transcribe(wav(1.0, rate=22050, channels=2), "audio/wav")
    stt.transcribe(webm([0], rate=16000.0), "audio/webm")
    ogg, pcm, webm16 = (r["config"] for r in google_stub.requests)
    assert (ogg["encoding"], ogg["sample_rate_hertz"], ogg["language_code"]) == (6, 48000, "en-GB")
    assert (pcm["encoding"], pcm["sample_rate_hertz"], pcm["audio_channel_count"]) == (1, 22050, 2)
    assert (webm16["encoding"], webm16["sample_rate_hertz"]) == (9, 16000)


def test_google_rejects_formats_v1_cannot_decode_without_calling(google_stub):
    stt = GoogleSTT()
    assert "audio/mp4" not in stt.supported_mimes
    for audio_bytes, mime in ((mp4(2.0), "audio/mp4"), (wav(0.5, bits=8), "audio/wav")):
        result = stt.transcribe(audio_bytes, mime)
        assert result.status == "error" and result.error and result.error.startswith("unsupported_format")
    vorbis = b"OggS" + b"\x00" * 22 + b"\x01vorbis" + b"\x00" * 30
    assert GoogleSTT().transcribe(vorbis, "audio/ogg").error.startswith("unsupported_format")  # type: ignore[union-attr]
    assert google_stub.requests == []


def test_google_no_speech_error_and_credentials(google_stub):
    stt = GoogleSTT(credentials_path="/secrets/sa.json")
    assert stt.transcribe(_sample("vomiting_blood"), "audio/webm").status == "no_speech"
    assert google_stub.from_file == ["/secrets/sa.json"]
    assert stt.transcribe(b"", "audio/webm").status == "no_speech"

    class DeadlineExceeded(Exception):
        status_code = 504

    google_stub.error = DeadlineExceeded("deadline")
    failed = stt.transcribe(_sample("vomiting_blood"), "audio/webm")
    assert failed.status == "error" and failed.text == "" and failed.error == "DeadlineExceeded (504)"


def test_google_missing_sdk_is_an_error_not_a_crash(monkeypatch):
    monkeypatch.setitem(sys.modules, "google.cloud.speech", None)
    result = GoogleSTT().transcribe(_sample("vomiting_blood"), "audio/webm")
    assert result.status == "error" and result.error in ("ImportError", "ModuleNotFoundError")


def test_google_config_is_valid_for_the_real_sdk_when_installed():
    """Runs only where ``requirements-live.txt`` is installed; builds the real proto offline."""
    speech = pytest.importorskip("google.cloud.speech")
    stt = GoogleSTT()
    for audio_bytes, mime in (
        (_sample("vomiting_blood"), "audio/webm"),
        (_sample("heartworm_pill"), "audio/ogg"),
        (wav(1.0), "audio/wav"),
    ):
        fields = stt.config_fields(audio_bytes, mime)
        fields["encoding"] = getattr(speech.RecognitionConfig.AudioEncoding, fields["encoding"])
        config = speech.RecognitionConfig(**fields)
        assert json.loads(type(config).to_json(config))["languageCode"] == "en-US"
