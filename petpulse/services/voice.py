"""Voice notes: validate an upload (or a bundled sample), transcribe it, hand the text to the
note pipeline. Audio is never stored: it lives in memory for the length of the request.

Status mapping (the router turns ``VoiceError`` into HTTP errors):

- 400  bad form input (neither or both of ``audio`` / ``sample_id``, unknown sample, bad tz)
- 413  larger than ``VOICE_MAX_BYTES`` or longer than ``VOICE_MAX_SECONDS``
- 415  not WebM / Ogg / MP4 / WAV, or a format the configured provider cannot decode
- 422  no speech (nothing stored)
- 502  speech-to-text failed (nothing stored)

On ``ok`` the transcript goes to ``petpulse.services.notes.process_note(..., source="voice")``
(LLM track). Until that module exists on the branch, the legacy classify-and-store path is used
so voice notes keep working; the switch is automatic once the module is importable.
"""

from __future__ import annotations

import dataclasses
import importlib
import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from starlette.concurrency import run_in_threadpool

from petpulse import deps
from petpulse.audio import GENERIC_MIMES, SUPPORTED_MIMES, is_near_silence, normalize_mime, probe_duration, sniff
from petpulse.config import Settings
from petpulse.providers.stt import UNSUPPORTED_FORMAT, STTProvider, Transcription
from petpulse.samples import audio_manifest

logger = logging.getLogger(__name__)

NOTES_MODULE = "petpulse.services.notes"
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
    name = (tz or "").strip() or "UTC"
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise VoiceError(400, f"Unknown time zone {name!r} (use an IANA name such as 'America/New_York').") from exc
    return name


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
def resolve_process_note() -> Optional[Callable[..., Any]]:
    """``petpulse.services.notes.process_note`` if the LLM track's module is on this branch."""
    try:
        module = importlib.import_module(NOTES_MODULE)
    except ModuleNotFoundError as exc:
        if exc.name != NOTES_MODULE:
            raise  # the module exists but one of its imports is broken: surface it
        return None
    fn = getattr(module, "process_note", None)
    return fn if callable(fn) else None


def note_to_dict(note: Any) -> dict[str, Any]:
    if hasattr(note, "model_dump"):
        return dict(note.model_dump(mode="json"))
    if dataclasses.is_dataclass(note) and not isinstance(note, type):
        return dataclasses.asdict(note)
    if isinstance(note, Mapping):
        return dict(note)
    raise TypeError(f"process_note returned {type(note).__name__}, expected a Note")


async def store_voice_note(pet_id: str, uid: str, text: str, tz: str, settings: Settings) -> dict[str, Any]:
    process_note = resolve_process_note()
    if process_note is None:
        return await run_in_threadpool(_legacy_store_note, pet_id, uid, text, tz, settings)
    if inspect.iscoroutinefunction(process_note):
        note = await process_note(pet_id, uid, text, "voice", tz)
    else:
        note = await run_in_threadpool(process_note, pet_id, uid, text, "voice", tz)
        if inspect.isawaitable(note):
            note = await note
    return note_to_dict(note)


def _legacy_store_note(pet_id: str, uid: str, text: str, tz: str, settings: Settings) -> dict[str, Any]:
    """Transitional: the legacy classify + summarise path, shaped like the contract's Note.

    Used only while ``petpulse.services.notes`` is absent. The legacy modules are untyped and
    imported lazily.
    """
    legacy = importlib.import_module("summarize_openai")
    classification = legacy.classify_pet_content(text)
    summary = legacy.summarize_text(text)
    kind = str(classification.get("classification", "MIXED"))
    created_at = datetime.now(timezone.utc).isoformat()
    entry = {
        "transcript": text,
        "summary": summary,
        "content_type": kind,
        "confidence": classification.get("confidence", 0.5),
        "keywords": classification.get("keywords", []),
        "timestamp": created_at,
        "source": "voice",
        "uid": uid,
        "tz": tz,
    }
    note_id = deps.get_store().add(f"pets/{pet_id}/voice-notes", entry)
    if kind == "DAILY_ACTIVITY":
        importlib.import_module("firestore_store").store_analytics_from_voice(pet_id, text, summary, classification)
    return {
        "id": note_id,
        "pet_id": pet_id,
        "source": "voice",
        "text": text,
        "summary": summary,
        "kind": kind,
        "urgent": False,
        "needs_review": kind in ("MEDICAL", "MIXED", "UNKNOWN"),
        "red_flags": [],
        "observations": [],
        "status": "processed",
        "created_at": created_at,
        "mode": settings.feature_modes()["notes"]["mode"],
    }


# ---------------------------------------------------------------------------- facade
async def create_voice_note(
    pet_id: str, uid: str, audio: AudioInput, tz: str, stt: STTProvider, settings: Settings
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
    note = await store_voice_note(pet_id, uid, result.text, tz, settings)
    return {"transcription": result.public(), "note": note}
