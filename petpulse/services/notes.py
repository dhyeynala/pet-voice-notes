"""The note pipeline: one ``note_extract.v1`` call per note; the model reads, code decides.

``process_note`` is the single entry point for typed notes (``POST /api/pets/{id}/notes``),
voice notes (Track D, after transcription) and anything else that produces owner text.

- The note is split into numbered sentences ``[S1]...`` by code; citations refer to them and
  code rejects any citation to a sentence that does not exist (then one repair attempt).
- ``urgent`` and ``needs_review`` are computed here from the extracted facts, never by the model.
- On any LLM failure the note is still stored, honestly: ``status="unprocessed"``,
  ``kind="UNKNOWN"``, ``needs_review=True``, no summary, no flags (review H2).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from petpulse.llm.client import LLMClient, LLMFailure, TaskSpec, provider_mode
from petpulse.llm.schemas import NoteExtraction, NoteKind, Observation, RedFlag
from petpulse.providers.llm import LLMProvider
from petpulse.store.base import Store
from petpulse.timeutil import parse_timestamp, to_iso, utc_now, validate_tz

NoteSource = Literal["text", "voice", "pdf"]
NoteStatus = Literal["processed", "unprocessed"]
Mode = Literal["demo", "live"]

NOTE_TASK: TaskSpec[NoteExtraction] = TaskSpec("note_extract", 1, NoteExtraction)
MAX_NOTE_CHARS = 5000
SCHEMA_VERSION = 1


class Note(BaseModel):
    """The API shape of a note (shared contract)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    pet_id: str
    source: NoteSource
    text: str
    summary: Optional[str]
    kind: NoteKind
    urgent: bool
    needs_review: bool
    red_flags: list[RedFlag]
    observations: list[Observation]
    status: NoteStatus
    created_at: str
    mode: Mode


def notes_collection(pet_id: str) -> str:
    return f"pets/{pet_id}/notes"


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    """Deterministic sentence split; these numbers are what citations point at."""
    return [" ".join(part.split()) for part in _SENTENCE_END.split(text) if part and part.strip()]


def numbered(sentences: list[str]) -> str:
    return "\n".join(f"[S{i}] {sentence}" for i, sentence in enumerate(sentences, start=1))


def citation_problems(extraction: NoteExtraction, sentence_count: int) -> list[str]:
    problems = []
    groups: tuple[tuple[str, Sequence[Observation | RedFlag]], ...] = (
        ("observations", extraction.observations),
        ("red_flags", extraction.red_flags),
    )
    for where, items in groups:
        for index, item in enumerate(items):
            bad = [n for n in item.sentences if not 1 <= n <= sentence_count]
            if bad:
                problems.append(f"{where}.{index}.sentences: {bad} not in 1..{sentence_count}")
    return problems


def decide(extraction: NoteExtraction) -> tuple[bool, bool]:
    """Code decides: ``(urgent, needs_review)`` from the extracted, cited facts."""
    urgent = any(flag.status == "present" for flag in extraction.red_flags)
    needs_review = (
        urgent
        or extraction.kind in ("UNKNOWN", "MIXED")
        or any(flag.status == "ambiguous" for flag in extraction.red_flags)
        or extraction.addressed_to_model
    )
    return urgent, needs_review


def _default_deps(store: Optional[Store], llm: Optional[LLMProvider]) -> tuple[Store, LLMProvider]:
    from petpulse import deps  # late import: deps builds providers from settings

    return (store if store is not None else deps.get_store()), (llm if llm is not None else deps.get_llm())


async def process_note(
    pet_id: str,
    uid: str,
    text: str,
    source: NoteSource,
    tz: str,
    *,
    store: Optional[Store] = None,
    llm: Optional[LLMProvider] = None,
) -> Note:
    """Extract, decide, store and return one note. Raises ``ValueError`` on empty/oversized text
    or an invalid timezone (map to 422); never raises on an LLM failure."""
    clean = text.strip()
    if not clean:
        raise ValueError("note text is empty")
    if len(clean) > MAX_NOTE_CHARS:
        raise ValueError(f"note text is longer than {MAX_NOTE_CHARS} characters")
    if source not in ("text", "voice", "pdf"):
        raise ValueError(f"unknown note source {source!r}")
    zone = validate_tz(tz)
    store, llm = _default_deps(store, llm)

    sentences = split_sentences(clean)
    note_id = uuid.uuid4().hex
    client = LLMClient(llm, store, meta={"pet_id": pet_id, "uid": uid, "feature": "notes", "note_id": note_id})
    extra: dict[str, Any] = {}
    try:
        result = await client.run(
            NOTE_TASK,
            {"note": numbered(sentences), "sentence_count": str(len(sentences))},
            check=lambda value: citation_problems(value, len(sentences)),
        )
    except LLMFailure as failure:
        note = Note(
            id=note_id,
            pet_id=pet_id,
            source=source,
            text=clean,
            summary=None,
            kind="UNKNOWN",
            urgent=False,
            needs_review=True,
            red_flags=[],
            observations=[],
            status="unprocessed",
            created_at=to_iso(utc_now()),
            mode=provider_mode(llm),
        )
        extra = {"failure_reason": failure.reason, "llm_call_ids": failure.call_ids, "llm_attempts": failure.attempts}
    else:
        extraction = result.value
        urgent, needs_review = decide(extraction)
        note = Note(
            id=note_id,
            pet_id=pet_id,
            source=source,
            text=clean,
            summary=extraction.summary.strip() or None,
            kind=extraction.kind,
            urgent=urgent,
            needs_review=needs_review,
            red_flags=extraction.red_flags,
            observations=extraction.observations,
            status="processed",
            created_at=to_iso(utc_now()),
            mode=result.mode,
        )
        extra = {
            "addressed_to_model": extraction.addressed_to_model,
            "prompt": result.prompt_key,
            "prompt_sha256": result.prompt_sha256,
            "provider": result.provider,
            "model": result.model,
            "llm_call_ids": result.call_ids,
            "llm_attempts": result.attempts,
        }
    document = {
        **note.model_dump(),
        **extra,
        "uid": uid,
        "tz": zone,
        "sentences": sentences,
        "schema_version": SCHEMA_VERSION,
    }
    store.set(f"{notes_collection(pet_id)}/{note_id}", document)
    return note


_NOTE_FIELDS = tuple(Note.model_fields)


def note_from_document(doc_id: str, doc: dict[str, Any]) -> Optional[Note]:
    """Rebuild the API shape from a stored document; ``None`` if the row is not readable."""
    try:
        return Note.model_validate({**{k: doc.get(k) for k in _NOTE_FIELDS}, "id": doc.get("id") or doc_id})
    except ValueError:
        return None


def list_notes(store: Store, pet_id: str, limit: int = 50) -> list[Note]:
    """Newest first; unreadable rows are skipped."""
    rows = store.query(notes_collection(pet_id))
    notes = [note for doc_id, doc in rows if (note := note_from_document(doc_id, doc)) is not None]
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    notes.sort(key=lambda n: (parse_timestamp(n.created_at) or epoch, n.id), reverse=True)
    return notes[: max(limit, 0)]
