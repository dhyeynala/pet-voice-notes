"""Bundled demo samples: short synthetic audio clips (with known transcripts) and a 1-page PDF.

``manifest.json`` lists every clip with its id, label, size and expected transcript (content
hashes are computed from the files at load time, so the manifest holds no hex blobs). The
deterministic ``FakeSTT`` uses it to "transcribe" a bundled clip exactly; with a live provider
the same bytes go to the real service (the live smoke test uses ``smoke_note``).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, Optional, cast

SAMPLES_DIR = Path(__file__).resolve().parent
AUDIO_DIR = SAMPLES_DIR / "audio"
PDF_DIR = SAMPLES_DIR / "pdfs"
MANIFEST_PATH = AUDIO_DIR / "manifest.json"
SMOKE_AUDIO_ID = "smoke_note"
SMOKE_PDF_PATH = PDF_DIR / "smoke_record.pdf"

SampleStatus = Literal["ok", "no_speech"]
_SAMPLE_ID = re.compile(r"^[a-z0-9_]{1,64}$")


@dataclass(frozen=True)
class AudioSample:
    id: str
    label: str
    file: str
    mime: str
    sha256: str
    status: SampleStatus
    transcript: str
    confidence: Optional[float]
    listed: bool
    seconds: Optional[float] = None

    @property
    def path(self) -> Path:
        return AUDIO_DIR / self.file

    def read_bytes(self) -> bytes:
        return self.path.read_bytes()


@dataclass(frozen=True)
class AudioManifest:
    samples: tuple[AudioSample, ...]

    def get(self, sample_id: str) -> Optional[AudioSample]:
        return next((s for s in self.samples if s.id == sample_id), None)

    def by_sha256(self, digest: str) -> Optional[AudioSample]:
        return next((s for s in self.samples if s.sha256 == digest), None)

    def by_hint(self, hint: Optional[str]) -> Optional[AudioSample]:
        """Match a filename hint (``vomiting_blood.webm``, ``uploads/silence.wav``) or a bare id."""
        if not hint:
            return None
        name = hint.replace("\\", "/").rsplit("/", 1)[-1].lower()
        stem = name.rsplit(".", 1)[0]
        return next((s for s in self.samples if name == s.file or stem == s.id), None)

    def listed(self) -> list[AudioSample]:
        return [s for s in self.samples if s.listed]


def _parse(raw: dict[str, Any]) -> AudioManifest:
    samples = []
    for item in raw.get("samples", []):
        sample_id = str(item["id"])
        if not _SAMPLE_ID.match(sample_id) or "/" in str(item["file"]) or ".." in str(item["file"]):
            raise ValueError(f"invalid sample entry in manifest: {sample_id!r}")
        status = str(item.get("status", "ok"))
        if status not in ("ok", "no_speech"):
            raise ValueError(f"invalid sample status {status!r} for {sample_id!r}")
        confidence = item.get("confidence")
        seconds = item.get("seconds")
        samples.append(
            AudioSample(
                id=sample_id,
                label=str(item["label"]),
                file=str(item["file"]),
                mime=str(item["mime"]),
                sha256=hashlib.sha256((AUDIO_DIR / str(item["file"])).read_bytes()).hexdigest(),
                status=cast(SampleStatus, status),
                transcript=str(item.get("transcript", "")),
                confidence=float(confidence) if confidence is not None else None,
                listed=bool(item.get("listed", True)),
                seconds=float(seconds) if seconds is not None else None,
            )
        )
    return AudioManifest(tuple(samples))


@lru_cache(maxsize=1)
def audio_manifest() -> AudioManifest:
    """The bundled manifest (read once)."""
    return _parse(json.loads(MANIFEST_PATH.read_text(encoding="utf-8")))
