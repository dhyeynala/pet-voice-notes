"""Speech-to-text: the ``STTProvider`` interface, the deterministic ``FakeSTT`` and the live
OpenAI and Google adapters (SDKs imported lazily, on first use).

Every provider returns a typed ``Transcription``; it never raises for provider trouble and
never turns an error or silence into transcript text:

- ``ok``         ``text`` holds the full transcript (all result segments joined),
- ``no_speech``  nothing intelligible was said (empty result, near-silence),
- ``error``      the provider failed (``error`` holds a short, key-free reason).

Selection (``petpulse.deps.get_stt``): ``STT_PROVIDER=auto`` uses ``OpenAISTT`` when
``OPENAI_API_KEY`` is set and ``FakeSTT`` otherwise; ``google`` must be chosen explicitly.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional, Protocol, runtime_checkable

from petpulse.audio import (
    EXTENSIONS,
    MP4,
    OGG,
    SUPPORTED_MIMES,
    WAV,
    WEBM,
    is_near_silence,
    is_ogg_opus,
    normalize_mime,
    opus_input_rate,
    sniff,
    wav_info,
    webm_sample_rate,
)
from petpulse.samples import AudioManifest, audio_manifest

Status = Literal["ok", "no_speech", "error"]

FAKE_STT_MODEL = "fake-stt-v1"
# Pinned dated snapshot (see Settings.stt_openai_model to change it).
DEFAULT_OPENAI_STT_MODEL = "gpt-4o-mini-transcribe-2025-12-15"
DEFAULT_GOOGLE_STT_MODEL = "default"
UNSUPPORTED_FORMAT = "unsupported_format"

# Context for the OpenAI transcription models (improves spelling of pet/medical words).
OPENAI_PROMPT = "A pet owner's short voice note about their pet's health, food, walks, sleep and medication."


@dataclass
class Transcription:
    status: Status
    text: str = ""
    provider: str = "fake"
    error: Optional[str] = None
    confidence: Optional[float] = None

    def public(self) -> dict[str, Any]:
        """The API shape: ``{"status", "text", "confidence"}``."""
        return {"status": self.status, "text": self.text, "confidence": self.confidence}


@runtime_checkable
class STTProvider(Protocol):
    name: str
    model: str
    supported_mimes: frozenset[str]

    def transcribe(self, audio: bytes, mime: str, hint: Optional[str] = None) -> Transcription: ...


def _describe_error(exc: BaseException) -> str:
    """A short reason without the exception message (SDK messages can echo request data)."""
    status = getattr(exc, "status_code", None)
    if not isinstance(status, int):
        code = getattr(exc, "code", None)  # google.api_core exceptions carry the HTTP status here
        status = code if isinstance(code, int) else None
    return f"{type(exc).__name__} ({status})" if status else type(exc).__name__


def _kind(audio: bytes, mime: str) -> str:
    """Canonical container type: the magic bytes win, the declared type is the fallback."""
    return sniff(audio) or normalize_mime(mime)


def _round(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 3)


# ------------------------------------------------------------------------------- FakeSTT
CANNED_TRANSCRIPTS: tuple[str, ...] = (
    "Max had his usual thirty minute walk and finished all of his dinner.",
    "Max seemed a bit tired this afternoon and napped for two hours.",
    "Gave Max his heartworm pill with breakfast this morning.",
    "Max played fetch at the park and drank a lot of water afterwards.",
)
CANNED_CONFIDENCE = 0.9


@dataclass
class FakeSTT:
    """Deterministic, offline STT. Same audio, same transcript. Never touches the network.

    Lookup order:

    1. ``fail=True`` -> ``error`` (simulated outage),
    2. ``sha256(audio)`` matches a bundled sample in ``samples/audio/manifest.json`` -> that
       sample's transcript (or ``no_speech`` for the silence clip),
    3. the filename ``hint`` matches a bundled sample (``vomiting_blood.webm``) -> that sample,
    4. near-silence (PCM WAV below -50 dBFS) or fewer than ``min_bytes`` bytes -> ``no_speech``,
    5. otherwise a canned transcript chosen by ``sha256(audio) % len(CANNED_TRANSCRIPTS)``.
    """

    fail: bool = False
    min_bytes: int = 2048
    manifest: Optional[AudioManifest] = None
    name: str = "fake"
    model: str = FAKE_STT_MODEL
    supported_mimes: frozenset[str] = SUPPORTED_MIMES
    calls: list[dict[str, Any]] = field(default_factory=list)

    def transcribe(self, audio: bytes, mime: str, hint: Optional[str] = None) -> Transcription:
        # Only metadata is recorded: audio is never kept.
        self.calls.append({"bytes": len(audio), "mime": mime, "hint": hint})
        if self.fail:
            return Transcription(status="error", provider=self.name, error="simulated STT outage")
        manifest = self.manifest or audio_manifest()
        digest = hashlib.sha256(audio).hexdigest()
        sample = manifest.by_sha256(digest) or manifest.by_hint(hint)
        if sample is not None:
            if sample.status == "no_speech":
                return Transcription(status="no_speech", provider=self.name)
            return Transcription(status="ok", text=sample.transcript, provider=self.name, confidence=sample.confidence)
        if len(audio) < self.min_bytes or is_near_silence(audio, mime):
            return Transcription(status="no_speech", provider=self.name)
        index = int(digest[:16], 16) % len(CANNED_TRANSCRIPTS)
        return Transcription(status="ok", text=CANNED_TRANSCRIPTS[index], provider=self.name, confidence=CANNED_CONFIDENCE)


# ----------------------------------------------------------------------------- OpenAISTT
class OpenAISTT:
    """Live adapter over ``POST /v1/audio/transcriptions``. ``openai`` is imported on first use.

    - Accepts WebM, Ogg, MP4 and WAV; the upload is named ``audio.<ext>`` from its sniffed type
      (the API picks the decoder from the extension).
    - ``gpt-4o*-transcribe`` models: ``response_format=json`` with token ``logprobs`` ->
      ``confidence = exp(mean logprob)``.
    - ``whisper-1``: ``verbose_json``; segments Whisper itself marks as silent
      (``no_speech_prob > 0.6`` and ``avg_logprob < -1``) count as no speech.
    - Client-level ``timeout`` and bounded ``max_retries``; any SDK error -> ``error``.
    """

    name = "openai"
    supported_mimes: frozenset[str] = SUPPORTED_MIMES

    def __init__(
        self,
        api_key: str,
        model: str = DEFAULT_OPENAI_STT_MODEL,
        timeout: float = 30.0,
        language: Optional[str] = "en",
        max_retries: int = 2,
        client: Any = None,
        http_client: Any = None,
    ) -> None:
        if not api_key:
            raise ValueError("OpenAISTT requires an API key")
        self._http_client = http_client  # tests inject a mock transport here
        self._api_key = api_key
        self.model = model
        self.timeout = timeout
        self.language = (language or "").split("-", 1)[0].lower() or None  # ISO-639-1 ("en-US" -> "en")
        self.max_retries = max_retries
        self._client: Any = client

    def __repr__(self) -> str:  # never render the key
        return f"OpenAISTT(model={self.model!r}, timeout={self.timeout!r})"

    def _get_client(self) -> Any:
        if self._client is None:
            import openai  # lazy: demo mode never imports the SDK

            kwargs: dict[str, Any] = {"api_key": self._api_key, "timeout": self.timeout, "max_retries": self.max_retries}
            if self._http_client is not None:
                kwargs["http_client"] = self._http_client
            self._client = openai.OpenAI(**kwargs)
        return self._client

    @property
    def _is_whisper(self) -> bool:
        return self.model.startswith("whisper")

    def request(self, audio: bytes, mime: str) -> dict[str, Any]:
        """The keyword arguments sent to ``client.audio.transcriptions.create``."""
        kind = _kind(audio, mime)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "file": (f"audio.{EXTENSIONS[kind]}", audio, kind),
            "temperature": 0,
            "prompt": OPENAI_PROMPT,
        }
        if self.language:
            kwargs["language"] = self.language
        if self._is_whisper:
            kwargs["response_format"] = "verbose_json"
        else:
            kwargs["response_format"] = "json"
            kwargs["include"] = ["logprobs"]
        return kwargs

    def transcribe(self, audio: bytes, mime: str, hint: Optional[str] = None) -> Transcription:
        if not audio:
            return Transcription(status="no_speech", provider=self.name)
        if _kind(audio, mime) not in self.supported_mimes:
            return Transcription(status="error", provider=self.name, error=f"{UNSUPPORTED_FORMAT}: {normalize_mime(mime)}")
        try:
            result = self._get_client().audio.transcriptions.create(**self.request(audio, mime))
        except Exception as exc:  # provider errors are reported, never stored as transcript text
            return Transcription(status="error", provider=self.name, error=_describe_error(exc))
        text = " ".join(str(getattr(result, "text", "") or "").split())
        confidence: Optional[float] = None
        segments = list(getattr(result, "segments", None) or [])
        if segments:
            silent = [
                (getattr(s, "no_speech_prob", 0.0) or 0.0) > 0.6 and (getattr(s, "avg_logprob", 0.0) or 0.0) < -1.0
                for s in segments
            ]
            if all(silent):
                return Transcription(status="no_speech", provider=self.name)
            logprobs = [float(getattr(s, "avg_logprob", 0.0) or 0.0) for s in segments]
            confidence = _round(math.exp(sum(logprobs) / len(logprobs)))
        tokens = [t for t in (getattr(result, "logprobs", None) or []) if getattr(t, "logprob", None) is not None]
        if tokens:
            confidence = _round(math.exp(sum(float(t.logprob) for t in tokens) / len(tokens)))
        if not text:
            return Transcription(status="no_speech", provider=self.name)
        return Transcription(status="ok", text=text, provider=self.name, confidence=confidence)


# ----------------------------------------------------------------------------- GoogleSTT
class _Unsupported(Exception):
    pass


_OPUS_RATES = frozenset({8000, 12000, 16000, 24000, 48000})  # rates Google accepts for Opus


class GoogleSTT:
    """Live adapter over Google Cloud Speech-to-Text v1 (``google-cloud-speech``, live extras).

    - WebM/Opus -> ``WEBM_OPUS`` and Ogg/Opus -> ``OGG_OPUS``, with the sample rate from the
      container header (48 kHz, MediaRecorder's rate, when the header does not say).
    - PCM16 WAV -> ``LINEAR16`` with the header's sample rate and channel count.
    - MP4/AAC (Safari) and Ogg/Vorbis are not accepted by v1 -> ``error: unsupported_format``.
    - Synchronous ``recognize`` (clips are capped at ``VOICE_MAX_SECONDS``, 60 s by default)
      with a request timeout. **All** result segments are joined (fixes review L3).
    """

    name = "google"
    supported_mimes: frozenset[str] = frozenset({WEBM, OGG, WAV})

    def __init__(
        self,
        credentials_path: Optional[str] = None,
        language_code: str = "en-US",
        timeout: float = 30.0,
        model: str = DEFAULT_GOOGLE_STT_MODEL,
        client: Any = None,
    ) -> None:
        self.credentials_path = credentials_path
        self.language_code = language_code
        self.timeout = timeout
        self.model = model
        self._client: Any = client

    def _get_client(self) -> Any:
        if self._client is None:
            from google.cloud import speech  # lazy; optional dependency (requirements-live.txt)

            if self.credentials_path:
                self._client = speech.SpeechClient.from_service_account_file(str(Path(self.credentials_path)))
            else:
                self._client = speech.SpeechClient()  # application default credentials
        return self._client

    def config_fields(self, audio: bytes, mime: str) -> dict[str, Any]:
        """``RecognitionConfig`` fields for this audio (encoding given by name)."""
        kind = _kind(audio, mime)
        fields: dict[str, Any] = {
            "language_code": self.language_code,
            "enable_automatic_punctuation": True,
            "model": self.model,
        }
        if kind == WEBM:
            rate = webm_sample_rate(audio)
            fields.update(encoding="WEBM_OPUS", sample_rate_hertz=rate if rate in _OPUS_RATES else 48000)
        elif kind == OGG:
            if audio.startswith(b"OggS") and not is_ogg_opus(audio):
                raise _Unsupported("ogg/vorbis")
            rate = opus_input_rate(audio)
            fields.update(encoding="OGG_OPUS", sample_rate_hertz=rate if rate in _OPUS_RATES else 48000)
        elif kind == WAV:
            info = wav_info(audio)
            if info is None or not info.is_pcm16:
                raise _Unsupported("wav (only 16-bit PCM)")
            fields.update(encoding="LINEAR16", sample_rate_hertz=info.sample_rate, audio_channel_count=info.channels)
        elif kind == MP4:
            raise _Unsupported("audio/mp4 (Google STT v1 has no AAC/MP4 decoder)")
        else:
            raise _Unsupported(kind or "unknown")
        return fields

    def transcribe(self, audio: bytes, mime: str, hint: Optional[str] = None) -> Transcription:
        if not audio:
            return Transcription(status="no_speech", provider=self.name)
        try:
            fields = self.config_fields(audio, mime)
        except _Unsupported as exc:
            return Transcription(status="error", provider=self.name, error=f"{UNSUPPORTED_FORMAT}: {exc}")
        try:
            from google.cloud import speech  # lazy

            fields["encoding"] = getattr(speech.RecognitionConfig.AudioEncoding, fields["encoding"])
            response = self._get_client().recognize(
                config=speech.RecognitionConfig(**fields),
                audio=speech.RecognitionAudio(content=audio),
                timeout=self.timeout,
            )
        except Exception as exc:
            return Transcription(status="error", provider=self.name, error=_describe_error(exc))
        best = [r.alternatives[0] for r in getattr(response, "results", []) if getattr(r, "alternatives", None)]
        text = " ".join(" ".join(str(a.transcript).split()) for a in best if str(a.transcript).strip())
        if not text:
            return Transcription(status="no_speech", provider=self.name)
        scores = [float(getattr(a, "confidence", 0.0) or 0.0) for a in best if str(a.transcript).strip()]
        scores = [s for s in scores if s > 0]
        confidence = _round(sum(scores) / len(scores)) if scores else None
        return Transcription(status="ok", text=text, provider=self.name, confidence=confidence)
