"""Voice notes: validate an upload (or a bundled sample), transcribe it, hand the text to the
note pipeline. Audio is never stored: it lives in memory for the length of the request.

Status mapping (the router turns ``VoiceError`` into HTTP errors):

- 400  bad form input (neither or both of ``audio`` / ``sample_id``, unknown sample, bad tz),
       or a transcript the note pipeline refuses (``ValueError``: e.g. over 5000 characters)
- 413  larger than ``VOICE_MAX_BYTES`` or longer than ``VOICE_MAX_SECONDS``
- 415  not WebM / Ogg / MP4 / WAV, or a format the configured provider cannot decode
- 422  no speech (nothing stored)
- 502  speech-to-text failed (nothing stored)

On ``ok`` the transcript goes to ``petpulse.services.notes.process_note(..., source="voice")``
(the shared note pipeline): the note lands at ``pets/{pet_id}/notes/{id}`` exactly like a typed
note, with ``urgent`` / ``red_flags`` decided by that pipeline. An LLM failure there still stores
an ``unprocessed`` note (it never raises), so the transcript is not lost.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from starlette.concurrency import run_in_threadpool

from petpulse.audio import GENERIC_MIMES, SUPPORTED_MIMES, is_near_silence, normalize_mime, probe_duration, sniff
from petpulse.config import Settings
from petpulse.providers.stt import UNSUPPORTED_FORMAT, STTProvider, Transcription
from petpulse.providers.llm import LLMProvider
from petpulse.samples import audio_manifest
from petpulse.services.notes import process_note
from petpulse.store.base import Store
from petpulse.timeutil import InvalidTimezone
from petpulse.timeutil import validate_tz as _canonical_tz

logger = logging.getLogger(__name__)

SUPPORTED_LIST = "audio/webm, audio/ogg, audio/mp4 or audio/wav"


class VoiceError(Exception):
    """A request the voice pipeline refuses; ``status_code`` is the HTTP status to return."""

    def __init__(self, status_code: int, detail: str, transcription: Optional[Transcription] = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail
        self.transcription = transcription


@dataclass(frozen=True)
class AudioInput:
    data: bytes
    mime: str  # canonical: audio/webm | audio/ogg | audio/mp4 | audio/wav
    hint: Optional[str] = None  # filename hint for the provider (bundled samples)
    sample_id: Optional[str] = None
    seconds: Optional[float] = None  # from the container header, when it says


# --------------------------------------------------------------------------- samples
def list_samples() -> list[dict[str, str]]:
    """``GET /api/voice/samples``: the bundled clips a user can submit instead of recording."""
    return [{"id": s.id, "label": s.label} for s in audio_manifest().listed()]


def load_sample(sample_id: str, settings: Settings, stt: STTProvider) -> AudioInput:
    sample = audio_manifest().get(sample_id.strip())
    if sample is None:
        raise VoiceError(400, f"Unknown sample_id {sample_id!r}. See GET /api/voice/samples.")
    return validate_audio(sample.read_bytes(), sample.mime, sample.file, settings, stt, sample_id=sample.id)


# ------------------------------------------------------------------------ validation
def validate_audio(
    data: bytes,
    declared_mime: Optional[str],
    filename: Optional[str],
    settings: Settings,
    stt: STTProvider,
    sample_id: Optional[str] = None,
) -> AudioInput:
    """Size cap, container sniffing, provider support and the duration cap, in that order."""
    if len(data) > settings.voice_max_bytes:
        raise VoiceError(413, f"Audio is larger than the {_mib(settings.voice_max_bytes)} limit.")
    if not data:
        raise VoiceError(422, "The recording is empty: no speech detected; nothing was saved.")
    declared = normalize_mime(declared_mime)
    if declared not in GENERIC_MIMES and declared not in SUPPORTED_MIMES:
        raise VoiceError(415, f"Unsupported audio type {declared!r}. Send {SUPPORTED_LIST}.")
    kind = sniff(data)
    if kind is None:
        raise VoiceError(415, f"Unrecognised audio data (declared {declared or 'no type'!r}). Send {SUPPORTED_LIST}.")
    if kind not in stt.supported_mimes:
        raise VoiceError(415, f"{kind} is not supported by the {stt.name} speech-to-text provider.")
    seconds = probe_duration(data, kind)
    if seconds is not None and seconds > settings.voice_max_seconds:
        raise VoiceError(413, f"Audio is longer than the {settings.voice_max_seconds:g} s limit.")
    return AudioInput(data=data, mime=kind, hint=filename, sample_id=sample_id, seconds=seconds)


def validate_tz(tz: Optional[str]) -> str:
    """Checked before any STT call, with the note pipeline's own rules (``petpulse.timeutil``)."""
    name = (tz or "").strip() or "UTC"
    try:
        return _canonical_tz(name)
    except InvalidTimezone as exc:
        raise VoiceError(400, f"Unknown time zone {name[:64]!r} (use an IANA name such as 'America/New_York').") from exc


def _mib(size: int) -> str:
    return f"{size / (1024 * 1024):g} MiB"


# --------------------------------------------------------------------- transcription
async def transcribe_audio(audio: AudioInput, stt: STTProvider) -> Transcription:
    """Transcribe without storing anything. Never raises for provider trouble.

    Near-silent PCM is answered with ``no_speech`` before any provider call (saves a billed
    request and avoids hallucinated text from live models).
    """
    if is_near_silence(audio.data, audio.mime):
        return Transcription(status="no_speech", provider=stt.name)
    try:
        result = await run_in_threadpool(stt.transcribe, audio.data, audio.mime, audio.hint)
    except Exception as exc:  # a provider must not raise, but never let it leak a 500
        logger.warning("stt provider %s raised %s", stt.name, type(exc).__name__)
        return Transcription(status="error", provider=stt.name, error=type(exc).__name__)
    if result.status == "ok" and not result.text.strip():
        return Transcription(status="no_speech", provider=result.provider)
    return result


def raise_for_status(result: Transcription) -> None:
    if result.status == "no_speech":
        raise VoiceError(422, "No speech detected in the recording; nothing was saved.", result)
    if result.status == "error":
        reason = result.error or "unknown error"
        if reason.startswith(UNSUPPORTED_FORMAT):
            raise VoiceError(415, f"The {result.provider} speech-to-text provider cannot decode this audio ({reason}).")
        raise VoiceError(502, f"Speech-to-text failed ({result.provider}: {reason}); nothing was saved.", result)


# ---------------------------------------------------------------------- note storage
async def store_voice_note(
    pet_id: str,
    uid: str,
    text: str,
    tz: str,
    *,
    store: Optional[Store] = None,
    llm: Optional[LLMProvider] = None,
) -> dict[str, Any]:
    """Hand the transcript to the shared note pipeline; its ``ValueError`` (bad input) is a 400."""
    try:
        note = await process_note(pet_id, uid, text, "voice", tz, store=store, llm=llm)
    except ValueError as exc:
        raise VoiceError(400, f"The transcript could not be saved as a note: {exc}.") from exc
    return note.model_dump(mode="json")


# ---------------------------------------------------------------------------- facade
async def create_voice_note(
    pet_id: str,
    uid: str,
    audio: AudioInput,
    tz: str,
    stt: STTProvider,
    *,
    store: Optional[Store] = None,
    llm: Optional[LLMProvider] = None,
) -> dict[str, Any]:
    """Transcribe ``audio`` and store the transcript as a voice note.

    Returns ``{"transcription": {...}, "note": Note}``; raises ``VoiceError`` (nothing stored)
    for no speech, STT errors and formats the provider cannot decode.
    """
    result = await transcribe_audio(audio, stt)
    logger.info(
        "voice note pet=%s provider=%s status=%s bytes=%d sample=%s",
        pet_id,
        result.provider,
        result.status,
        len(audio.data),
        audio.sample_id or "-",
    )
    raise_for_status(result)
    note = await store_voice_note(pet_id, uid, result.text, tz, store=store, llm=llm)
    return {"transcription": result.public(), "note": note}
