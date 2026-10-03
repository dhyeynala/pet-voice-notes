"""One read model over everything recorded about a pet (review M3, M5).

Notes, analytics entries and PDF records all become ``Event``s with an aware UTC timestamp. Rows that cannot
be read (missing or bad timestamp, no text, not a dict) are skipped and counted, never a 500.
Retrieval, the query tools, charts and insights all read this one model.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Literal, Optional

from petpulse.store.base import Store
from petpulse.core.timeutil import parse_timestamp

EventKind = Literal["note", "analytics", "record"]
EventSource = Literal["text", "voice", "pdf", "analytics"]

NOTES = "notes"
ANALYTICS = "analytics"
RECORDS = "records"

_META_FIELDS = frozenset(
    {"category", "timestamp", "created_at", "at", "pet_id", "uid", "user_id", "source", "id", "schema_version", "tz", "notes"}
)


@dataclass(frozen=True)
class Event:
    id: str
    kind: EventKind
    source: EventSource
    at: datetime
    text: str
    category: Optional[str] = None
    categories: tuple[str, ...] = ()
    fields: dict[str, Any] = field(default_factory=dict, compare=False, hash=False)
    source_ref: str = ""

    def has_category(self, category: str) -> bool:
        return self.category == category or category in self.categories


@dataclass
class EventLoad:
    events: list[Event]
    skipped: int = 0
    skipped_by_reason: dict[str, int] = field(default_factory=dict)


def _timestamp(doc: dict[str, Any]) -> Optional[datetime]:
    for key in ("created_at", "timestamp", "at"):
        if key in doc:
            return parse_timestamp(doc.get(key))
    return None


def _clean(text: Any) -> str:
    return " ".join(str(text).split()) if isinstance(text, (str, int, float)) else ""


def _note_event(doc_id: str, doc: dict[str, Any], at: datetime, ref: str) -> Optional[Event]:
    text = _clean(doc.get("text"))
    if not text:
        return None
    categories = tuple(
        sorted({str(o.get("category")) for o in doc.get("observations") or [] if isinstance(o, dict) and o.get("category")})
    )
    raw_source = doc.get("source")
    source: EventSource = raw_source if raw_source in ("text", "voice", "pdf") else "text"
    fields = {k: doc.get(k) for k in ("kind", "urgent", "needs_review", "status", "red_flags", "summary")}
    return Event(doc_id, "note", source, at, text, None, categories, fields, ref)


def _analytics_text(category: str, doc: dict[str, Any]) -> str:
    parts = [f"{key} {value}" for key, value in sorted(doc.items()) if key not in _META_FIELDS and _clean(value)]
    note = _clean(doc.get("notes"))
    text = f"{category.replace('_', ' ')}: " + ", ".join(parts)
    return f"{text}. {note}" if note else text


def _analytics_event(doc_id: str, doc: dict[str, Any], at: datetime, ref: str) -> Optional[Event]:
    category = _clean(doc.get("category"))
    if not category:
        return None
    fields = {k: v for k, v in doc.items() if k not in _META_FIELDS}
    return Event(doc_id, "analytics", "analytics", at, _analytics_text(category, doc), category, (), fields, ref)


def _record_event(doc_id: str, doc: dict[str, Any], at: datetime, ref: str) -> Optional[Event]:
    summary = doc.get("summary")
    if isinstance(summary, dict):  # structured PdfSummary
        summary = summary.get("summary")
    name = _clean(doc.get("filename") or doc.get("file_name"))
    text = _clean(summary)
    if not text and not name:
        return None
    fields = {"filename": name, "status": doc.get("status"), "pages": doc.get("pages")}
    return Event(doc_id, "record", "pdf", at, f"{name}: {text}" if name and text else text or name, None, (), fields, ref)


_Builder = Callable[[str, dict[str, Any], datetime, str], Optional[Event]]
_BUILDERS: dict[str, _Builder] = {
    NOTES: _note_event,
    ANALYTICS: _analytics_event,
    RECORDS: _record_event,
}


def load_events(store: Store, pet_id: str) -> EventLoad:
    """All readable events for ``pet_id``, sorted by time then id; unreadable rows counted."""
    events: list[Event] = []
    skipped: Counter[str] = Counter()
    for collection in (NOTES, ANALYTICS, RECORDS):
        path = f"pets/{pet_id}/{collection}"
        for doc_id, doc in store.query(path):
            if not isinstance(doc, dict):
                skipped["not_a_document"] += 1
                continue
            at = _timestamp(doc)
            if at is None:
                skipped["bad_timestamp"] += 1
                continue
            event = _BUILDERS[collection](doc_id, doc, at, f"{path}/{doc_id}")
            if event is None:
                skipped["no_content"] += 1
                continue
            events.append(event)
    events.sort(key=lambda e: (e.at, e.id))
    return EventLoad(events=events, skipped=sum(skipped.values()), skipped_by_reason=dict(skipped))


def numeric_field(event: Event, *names: str) -> Optional[float]:
    """A numeric field such as ``level`` or ``duration``; ``None`` if absent or not a number."""
    for name in names:
        value = event.fields.get(name)
        if isinstance(value, bool):
            continue
        number: Optional[float] = None
        if isinstance(value, (int, float)):
            number = float(value)
        elif isinstance(value, str):
            try:
                number = float(value.strip())
            except ValueError:
                number = None
        if number is not None and math.isfinite(number):
            return number
    return None
