"""Deterministic answers to date and count questions (FDE: never the model's job).

"When did I first mention Max being tired?" and "how many times did he vomit this month?"
are lookups and counts over the events, not retrieval plus generation. There is no 30-day
cap (review M8): the whole history is searched unless the question names a window.
Days are bucketed in the caller's timezone (review M5).
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable, Iterable, Literal, Optional, Sequence

from petpulse.services.events import Event, numeric_field
from petpulse.services.retrieval import tokenize
from petpulse.core.timeutil import get_zone, local_date

Aggregate = Literal["count", "sum", "mean"]
MAX_WINDOW_DAYS = 365


@dataclass(frozen=True)
class Window:
    """A half-open UTC interval [start, end) plus how it was described."""

    start: datetime
    end: datetime
    label: str


def matches_terms(event: Event, terms: Sequence[str]) -> bool:
    """Every query term (already stemmed) appears in the event text."""
    if not terms:
        return False
    tokens = set(tokenize(event.text))
    return all(term in tokens for term in terms)


def in_window(event: Event, window: Optional[Window]) -> bool:
    return window is None or window.start <= event.at < window.end


def mentions(events: Iterable[Event], terms: Sequence[str], window: Optional[Window] = None) -> list[Event]:
    """Events (notes, records, and analytics rows with their free-text notes) mentioning all ``terms``.

    Oldest first, ties by id.
    """
    found = [e for e in events if in_window(e, window) and matches_terms(e, terms)]
    return sorted(found, key=lambda e: (e.at, e.id))


def first_mention(events: Iterable[Event], terms: Sequence[str]) -> Optional[Event]:
    found = mentions(events, terms)
    return found[0] if found else None


def last_mention(events: Iterable[Event], terms: Sequence[str]) -> Optional[Event]:
    found = mentions(events, terms)
    return max(found, key=lambda e: (e.at, e.id)) if found else None


def count(
    events: Iterable[Event],
    *,
    terms: Sequence[str] = (),
    category: Optional[str] = None,
    window: Optional[Window] = None,
) -> list[Event]:
    """Events matching a category and/or terms in the window. ``len()`` of this is the count."""
    out = []
    for event in events:
        if not in_window(event, window):
            continue
        if category is not None and not event.has_category(category):
            continue
        if terms and not matches_terms(event, terms):
            continue
        if category is None and not terms:
            continue
        out.append(event)
    return sorted(out, key=lambda e: (e.at, e.id))


def days_between(start: date, end: date) -> list[date]:
    if end < start:
        return []
    return [start + timedelta(days=offset) for offset in range((end - start).days + 1)]


def daily_series(
    events: Iterable[Event],
    *,
    tz: str,
    start: date,
    end: date,
    select: Callable[[Event], bool],
    value: Optional[Callable[[Event], Optional[float]]] = None,
    aggregate: Aggregate = "count",
) -> list[tuple[date, Optional[float]]]:
    """One value per local calendar day from ``start`` to ``end`` inclusive.

    ``count`` gives 0 on empty days. ``sum``/``mean`` give ``None`` on days with no value:
    a missing measurement is unknown, not zero (review M4).
    """
    buckets: dict[date, list[float]] = {}
    counts: dict[date, int] = {}
    for event in events:
        if not select(event):
            continue
        day = local_date(event.at, tz)
        if day < start or day > end:
            continue
        counts[day] = counts.get(day, 0) + 1
        if value is not None:
            number = value(event)
            if number is not None:
                buckets.setdefault(day, []).append(number)
    series: list[tuple[date, Optional[float]]] = []
    for day in days_between(start, end):
        if aggregate == "count":
            series.append((day, float(counts.get(day, 0))))
        elif day not in buckets:
            series.append((day, None))
        elif aggregate == "sum":
            series.append((day, round(sum(buckets[day]), 2)))
        else:
            series.append((day, round(statistics.fmean(buckets[day]), 2)))
    return series


def list_medications(events: Iterable[Event]) -> list[Event]:
    return [e for e in events if e.has_category("medication")]


def energy_level(event: Event) -> Optional[float]:
    level = numeric_field(event, "level", "energy_level")
    return level if level is not None and 1 <= level <= 5 else None


def exercise_minutes(event: Event) -> Optional[float]:
    minutes = numeric_field(event, "duration", "duration_min", "minutes")
    return minutes if minutes is not None and 0 <= minutes <= 1440 else None


# ------------------------------------------------------------------ question windows
_LAST_N = re.compile(r"\b(?:last|past|previous)\s+(\d{1,3})\s+(day|week|month)s?\b", re.IGNORECASE)
_THIS = re.compile(r"\b(today|yesterday|this week|this month|last week|last month)\b", re.IGNORECASE)


def window_from_question(question: str, tz: str, now: datetime) -> Optional[Window]:
    """Parse "last 2 weeks", "this month", "yesterday"...; ``None`` means all history."""
    zone = get_zone(tz)
    local_now = now.astimezone(zone)
    today = local_now.date()

    def span(first: date, last_exclusive: date, label: str) -> Window:
        start = datetime.combine(first, datetime.min.time(), zone)
        end = datetime.combine(last_exclusive, datetime.min.time(), zone)
        return Window(start, end, label)

    match = _LAST_N.search(question)
    if match:
        n, unit = int(match.group(1)), match.group(2).lower()
        days = min(max(n * {"day": 1, "week": 7, "month": 30}[unit], 1), MAX_WINDOW_DAYS)
        return span(today - timedelta(days=days - 1), today + timedelta(days=1), f"in the last {days} days")
    match = _THIS.search(question)
    if not match:
        return None
    phrase = match.group(1).lower()
    if phrase == "today":
        return span(today, today + timedelta(days=1), "today")
    if phrase == "yesterday":
        return span(today - timedelta(days=1), today, "yesterday")
    if phrase == "this week":
        monday = today - timedelta(days=today.weekday())
        return span(monday, today + timedelta(days=1), "this week")
    if phrase == "last week":
        monday = today - timedelta(days=today.weekday())
        return span(monday - timedelta(days=7), monday, "last week")
    first_of_month = today.replace(day=1)
    if phrase == "this month":
        return span(first_of_month, today + timedelta(days=1), "this month")
    previous_first = (first_of_month - timedelta(days=1)).replace(day=1)
    return span(previous_first, first_of_month, "last month")
