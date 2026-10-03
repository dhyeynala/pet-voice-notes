"""Voice routes (contract: "Voice (Track D)").

- ``GET  /api/voice/samples``              -> ``[{"id", "label"}]``
- ``POST /api/pets/{pet_id}/voice-notes``  multipart ``audio=<blob>`` (or ``sample_id``) and ``tz``
  -> ``{"transcription": {"status", "text", "confidence"}, "note": Note}``

The body is parsed by hand (not with ``File``/``Form`` parameters) so the size cap is enforced
from ``Content-Length`` before the multipart parser spools anything, and so the upload is read
with a hard byte limit. The spooled upload is closed (deleted) before the response is sent.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.datastructures import UploadFile

from petpulse.auth import current_user, require_pet_access
from petpulse.config import Settings
from petpulse.deps import get_settings, get_stt
from petpulse.providers.stt import STTProvider

from petpulse.services import voice

router = APIRouter(tags=["voice"])

MULTIPART_OVERHEAD = 64 * 1024  # boundaries, headers and the small form fields


def _http(exc: voice.VoiceError) -> HTTPException:
    return HTTPException(status_code=exc.status_code, detail=exc.detail)


def _uid(user: Any) -> str:
    uid = getattr(user, "uid", None)
    if uid is None and isinstance(user, dict):
        uid = user.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="Authentication is required.")
    return str(uid)


@router.get("/api/voice/samples")
def voice_samples(user: Any = Depends(current_user)) -> list[dict[str, str]]:
    return voice.list_samples()


_OPENAPI_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "properties": {
                        "audio": {"type": "string", "format": "binary", "description": "webm/ogg/mp4/wav recording"},
                        "sample_id": {"type": "string", "description": "a bundled sample (GET /api/voice/samples)"},
                        "tz": {"type": "string", "description": "IANA time zone, e.g. America/New_York"},
                    },
                }
            }
        },
    }
}


async def _read_capped(upload: UploadFile, limit: int) -> bytes:
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise voice.VoiceError(413, f"Audio is larger than the {voice._mib(limit)} limit.")
    return data


def _field(value: Any) -> Optional[str]:
    return value.strip() if isinstance(value, str) and value.strip() else None


@router.post("/api/pets/{pet_id}/voice-notes", status_code=201, openapi_extra=_OPENAPI_BODY)
async def create_voice_note(
    pet_id: str,
    request: Request,
    user: Any = Depends(current_user),
    pet: Any = Depends(require_pet_access),
    stt: STTProvider = Depends(get_stt),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > settings.voice_max_bytes + MULTIPART_OVERHEAD:
        raise HTTPException(status_code=413, detail=f"Audio is larger than the {voice._mib(settings.voice_max_bytes)} limit.")
    content_type = request.headers.get("content-type", "")
    if not content_type.lower().startswith(("multipart/form-data", "application/x-www-form-urlencoded")):
        raise HTTPException(status_code=415, detail="Send multipart/form-data with an 'audio' file or a 'sample_id' field.")
    try:
        form = await request.form(max_files=1, max_fields=8)
    except HTTPException:
        raise
    except Exception as exc:  # malformed multipart body
        raise HTTPException(status_code=400, detail="Malformed multipart form body.") from exc
    try:
        upload = form.get("audio")
        sample_id = _field(form.get("sample_id"))
        has_audio = isinstance(upload, UploadFile)
        if has_audio == bool(sample_id):
            raise voice.VoiceError(400, "Send exactly one of an 'audio' file or a 'sample_id' field.")
        tz = voice.validate_tz(_field(form.get("tz")))
        if sample_id:
            audio = voice.load_sample(sample_id, settings, stt)
        else:
            assert isinstance(upload, UploadFile)
            data = await _read_capped(upload, settings.voice_max_bytes)
            audio = voice.validate_audio(data, upload.content_type, upload.filename, settings, stt)
            del data
        return await voice.create_voice_note(pet_id, _uid(user), audio, tz, stt, settings)
    except voice.VoiceError as exc:
        raise _http(exc) from None
    finally:
        await form.close()  # deletes the spooled upload; audio is never kept
