"""Speech-to-text interface, the deterministic ``FakeSTT`` and lazily imported live adapters.

The voice track adds the sample-audio manifest lookup and filename hints to ``FakeSTT``,
the browser upload route, and contract tests for the live adapters.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Literal, Optional, Protocol, runtime_checkable

Status = Literal["ok", "no_speech", "error"]


@dataclass
class Transcription:
    status: Status
    text: str = ""
    provider: str = "fake"
    error: Optional[str] = None


@runtime_checkable
class STTProvider(Protocol):
    name: str

    def transcribe(self, audio: bytes, mime: str, hint: Optional[str] = None) -> Transcription: ...


CANNED_TRANSCRIPTS: tuple[str, ...] = (
    "Max had his usual thirty minute walk and finished all of his dinner.",
    "Max seemed a bit tired this afternoon and napped for two hours.",
    "Gave Max his heartworm pill with breakfast this morning.",
    "Max played fetch at the park and drank a lot of water afterwards.",
)


@dataclass
class FakeSTT:
    """Deterministic, offline STT.

    - audio shorter than ``min_bytes`` -> ``no_speech``
    - otherwise a canned transcript chosen by ``sha256(audio) % len(CANNED_TRANSCRIPTS)``
    - ``fail=True`` -> ``error`` (simulated outage)
    """

    fail: bool = False
    min_bytes: int = 2048
    name: str = "fake"
    calls: list[dict[str, Any]] = field(default_factory=list)

    def transcribe(self, audio: bytes, mime: str, hint: Optional[str] = None) -> Transcription:
        self.calls.append({"bytes": len(audio), "mime": mime, "hint": hint})
        if self.fail:
            return Transcription(status="error", provider=self.name, error="simulated STT outage")
        if len(audio) < self.min_bytes:
            return Transcription(status="no_speech", provider=self.name)
        index = int.from_bytes(hashlib.sha256(audio).digest()[:8], "big") % len(CANNED_TRANSCRIPTS)
        return Transcription(status="ok", text=CANNED_TRANSCRIPTS[index], provider=self.name)


def _filename_for(mime: str) -> str:
    base = mime.split(";", 1)[0].strip().lower()
    ext = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/mp4": "mp4",
        "audio/mpeg": "mp3",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
    }.get(base, "webm")
    return f"audio.{ext}"


class OpenAISTT:
    """Live adapter over OpenAI transcription. ``openai`` is imported on first use."""

    name = "openai"

    def __init__(self, api_key: str, model: str = "whisper-1", timeout: float = 60.0) -> None:
        if not api_key:
            raise ValueError("OpenAISTT requires an API key")
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import openai  # lazy

            self._client = openai.OpenAI(api_key=self._api_key, timeout=self.timeout, max_retries=2)
        return self._client

    def transcribe(self, audio: bytes, mime: str, hint: Optional[str] = None) -> Transcription:
        if not audio:
            return Transcription(status="no_speech", provider=self.name)
        try:
            result = self._get_client().audio.transcriptions.create(
                model=self.model, file=(hint or _filename_for(mime), audio, mime.split(";", 1)[0])
            )
        except Exception as exc:  # provider errors are reported, never stored as transcript text
            return Transcription(status="error", provider=self.name, error=type(exc).__name__)
        text = (getattr(result, "text", "") or "").strip()
        return Transcription(status="ok" if text else "no_speech", text=text, provider=self.name)


class GoogleSTT:
    """Live adapter over Google Cloud Speech v1. Needs ``requirements-live.txt``.

    ``google.cloud.speech`` is imported on first use. All result segments are joined.
    """

    name = "google"

    def __init__(self, language_code: str = "en-US") -> None:
        self.language_code = language_code
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import speech  # lazy; optional dependency

            self._client = speech.SpeechClient()
        return self._client

    def _config(self, mime: str) -> Any:
        from google.cloud import speech  # lazy

        enc = speech.RecognitionConfig.AudioEncoding
        base = mime.split(";", 1)[0].strip().lower()
        if base == "audio/webm":
            return speech.RecognitionConfig(encoding=enc.WEBM_OPUS, sample_rate_hertz=48000, language_code=self.language_code)
        if base == "audio/ogg":
            return speech.RecognitionConfig(encoding=enc.OGG_OPUS, sample_rate_hertz=48000, language_code=self.language_code)
        # WAV / raw 16 kHz PCM (legacy server-microphone path)
        return speech.RecognitionConfig(encoding=enc.LINEAR16, sample_rate_hertz=16000, language_code=self.language_code)

    def transcribe(self, audio: bytes, mime: str, hint: Optional[str] = None) -> Transcription:
        if not audio:
            return Transcription(status="no_speech", provider=self.name)
        try:
            from google.cloud import speech  # lazy

            response = self._get_client().recognize(config=self._config(mime), audio=speech.RecognitionAudio(content=audio))
        except Exception as exc:
            return Transcription(status="error", provider=self.name, error=type(exc).__name__)
        text = " ".join(r.alternatives[0].transcript.strip() for r in response.results if r.alternatives).strip()
        return Transcription(status="ok" if text else "no_speech", text=text, provider=self.name)
