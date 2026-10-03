"""Charts are built by code from a fixed enum (review M6: replaces the 12 overlapping tools).

The model may only name a chart kind; the data always comes from the events, bucketed by
local day. Missing measurements are ``None`` (a gap), never 0 (review M4).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional, Sequence

from petpulse.services.events import Event
from petpulse.services.queries import daily_series, energy_level, exercise_minutes
from petpulse.timeutil import local_date

CHART_DAYS = 30


def _labels(series: Sequence[tuple[Any, Optional[float]]]) -> list[str]:
    return [day.isoformat() for day, _ in series]


def build_chart(
    kind: str, events: Sequence[Event], *, tz: str, now: datetime, days: int = CHART_DAYS
) -> Optional[dict[str, Any]]:
    """``{type, title, data}`` (Chart.js-shaped) or ``None`` for ``none`` / no data."""
    end = local_date(now, tz)
    start = end - timedelta(days=days - 1)
    if kind == "energy_trend":
        series = daily_series(
            events,
            tz=tz,
            start=start,
            end=end,
            select=lambda e: e.category == "energy_levels",
            value=energy_level,
            aggregate="mean",
        )
        title, chart_type, label = f"Energy level (1-5), last {days} days", "line", "Average energy level"
    elif kind == "exercise_minutes":
        series = daily_series(
            events,
            tz=tz,
            start=start,
            end=end,
            select=lambda e: e.category == "exercise",
            value=exercise_minutes,
            aggregate="sum",
        )
        title, chart_type, label = f"Exercise minutes per day, last {days} days", "bar", "Minutes"
    elif kind == "notes_per_day":
        series = daily_series(events, tz=tz, start=start, end=end, select=lambda e: e.kind == "note", aggregate="count")
        title, chart_type, label = f"Notes per day, last {days} days", "bar", "Notes"
    elif kind == "entries_by_category":
        counts: dict[str, int] = {}
        for event in events:
            if not start <= local_date(event.at, tz) <= end:
                continue
            for category in ([event.category] if event.category else list(event.categories)):
                counts[category] = counts.get(category, 0) + 1
        if not counts:
            return None
        ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
        return {
            "type": "bar",
            "title": f"Entries by category, last {days} days",
            "data": {
                "labels": [name for name, _ in ordered],
                "datasets": [{"label": "Entries", "data": [n for _, n in ordered]}],
            },
        }
    else:
        return None
    if all(value in (None, 0.0) for _, value in series):
        return None
    return {
        "type": chart_type,
        "title": title,
        "data": {"labels": _labels(series), "datasets": [{"label": label, "data": [value for _, value in series]}]},
    }
