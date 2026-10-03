"""Facts, alerts and a headline computed by code (review H2, H3; FDE: thresholds are code).

No health score: a 1-10 number from a model over aggregates is a determined computation
dressed up as judgment, and the legacy one defaulted to 7 on failure. Every threshold below
is a named constant with a unit test. Nothing here calls a model.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict, computed_field

from petpulse.services.events import Event, EventLoad
from petpulse.services.queries import energy_level, exercise_minutes
from petpulse.core.timeutil import local_date

WINDOW_DAYS = 7
LOW_ENERGY_LEVEL = 2  # at or below, on the 1-5 scale
LOW_ENERGY_STREAK = 3  # consecutive logged days
LOW_ENERGY_LOOKBACK_DAYS = 14
DIET_GAP_HOURS = 48
Severity = Literal["urgent", "warning", "info"]
Mode = Literal["demo", "live"]


class Fact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    value: Optional[float]
    unit: str
    window_days: Optional[int]
    evidence: list[str]

    # Display fields for the UI (``{text, level}``), derived from the values above.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def text(self) -> str:
        if self.value is None:
            shown = "no data"
        else:
            number = int(self.value) if float(self.value).is_integer() else self.value
            shown = f"{number} {self.unit}"
        window = f" (last {self.window_days} days)" if self.window_days else ""
        return f"{self.label}{window}: {shown}"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def level(self) -> str:
        return "info"


class Alert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    severity: Severity
    message: str
    evidence: list[str]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def text(self) -> str:
        return self.message

    @computed_field  # type: ignore[prop-decorator]
    @property
    def level(self) -> str:
        return self.severity


class Insights(BaseModel):
    model_config = ConfigDict(extra="forbid")

    facts: list[Fact]
    alerts: list[Alert]
    headline: str
    mode: Mode


@dataclass(frozen=True)
class _Window:
    start: datetime
    end: datetime

    def holds(self, event: Event) -> bool:
        return self.start <= event.at <= self.end


def low_energy_streak(events: Sequence[Event], tz: str, now: datetime) -> Optional[list[Event]]:
    """Most recent run of >= LOW_ENERGY_STREAK consecutive *logged* days with mean level <= LOW_ENERGY_LEVEL."""
    since = now - timedelta(days=LOW_ENERGY_LOOKBACK_DAYS)
    by_day: dict[Any, list[Event]] = {}
    for event in events:
        if event.category == "energy_levels" and since <= event.at <= now and energy_level(event) is not None:
            by_day.setdefault(local_date(event.at, tz), []).append(event)
    run: list[Any] = []
    best: list[Any] = []
    for day in sorted(by_day):
        levels = [energy_level(e) or 0.0 for e in by_day[day]]
        if statistics.fmean(levels) <= LOW_ENERGY_LEVEL:
            run.append(day)
            if len(run) >= LOW_ENERGY_STREAK:
                best = list(run)
        else:
            run = []
    if not best:
        return None
    return [e for day in best for e in by_day[day]]


def _ids(events: Sequence[Event], limit: int = 10) -> list[str]:
    return [e.id for e in sorted(events, key=lambda e: (e.at, e.id), reverse=True)[:limit]]


def compute_insights(load: EventLoad, *, tz: str, now: datetime, pet_name: str, mode: Mode) -> Insights:
    events = load.events
    week = _Window(now - timedelta(days=WINDOW_DAYS), now)
    prior = _Window(now - timedelta(days=2 * WINDOW_DAYS), now - timedelta(days=WINDOW_DAYS))
    recent = [e for e in events if week.holds(e)]
    notes = [e for e in recent if e.kind == "note"]
    urgent = [e for e in notes if e.fields.get("urgent") is True]
    review = [e for e in notes if e.fields.get("needs_review") is True]

    def exercise_total(window: _Window) -> tuple[Optional[float], list[Event]]:
        rows = [e for e in events if e.category == "exercise" and window.holds(e) and exercise_minutes(e) is not None]
        return (round(sum(exercise_minutes(e) or 0.0 for e in rows), 1) if rows else None), rows

    minutes, minute_rows = exercise_total(week)
    prior_minutes, prior_rows = exercise_total(prior)
    energy_rows = [e for e in recent if e.category == "energy_levels" and energy_level(e) is not None]
    energy = round(statistics.fmean(energy_level(e) or 0.0 for e in energy_rows), 2) if energy_rows else None

    facts = [
        Fact(id="entries_7d", label="Entries logged", value=len(recent), unit="entries", window_days=WINDOW_DAYS, evidence=[]),
        Fact(id="notes_7d", label="Notes", value=len(notes), unit="notes", window_days=WINDOW_DAYS, evidence=_ids(notes)),
        Fact(
            id="exercise_minutes_7d",
            label="Exercise minutes",
            value=minutes,
            unit="minutes",
            window_days=WINDOW_DAYS,
            evidence=_ids(minute_rows),
        ),
        Fact(
            id="exercise_minutes_prior_7d",
            label="Exercise minutes, the 7 days before",
            value=prior_minutes,
            unit="minutes",
            window_days=WINDOW_DAYS,
            evidence=_ids(prior_rows),
        ),
        Fact(
            id="avg_energy_7d",
            label="Average energy level (1-5)",
            value=energy,
            unit="level",
            window_days=WINDOW_DAYS,
            evidence=_ids(energy_rows),
        ),
        Fact(
            id="notes_needing_review_7d",
            label="Notes needing review",
            value=len(review),
            unit="notes",
            window_days=WINDOW_DAYS,
            evidence=_ids(review),
        ),
    ]
    if load.skipped:
        facts.append(
            Fact(
                id="unreadable_rows",
                label="Records skipped as unreadable",
                value=load.skipped,
                unit="rows",
                window_days=None,
                evidence=[],
            )
        )

    alerts: list[Alert] = []
    if urgent:
        latest = max(urgent, key=lambda e: (e.at, e.id))
        flags = sorted(
            {str(f.get("flag")) for e in urgent for f in e.fields.get("red_flags") or [] if f.get("status") == "present"}
        )
        flag_text = ", ".join(f.replace("_", " ") for f in flags) or "red flag"
        alerts.append(
            Alert(
                id="urgent_note",
                severity="urgent",
                message=f"A note on {local_date(latest.at, tz).isoformat()} mentions a possible red flag ({flag_text}). "
                "Contact your vet if you have not already.",
                evidence=_ids(urgent),
            )
        )
    streak = low_energy_streak(events, tz, now)
    if streak:
        days = sorted({local_date(e.at, tz) for e in streak})
        alerts.append(
            Alert(
                id="low_energy_streak",
                severity="warning",
                message=f"Energy was logged at {LOW_ENERGY_LEVEL} or below on {len(days)} logged days in a row "
                f"({days[0].isoformat()} to {days[-1].isoformat()}).",
                evidence=_ids(streak),
            )
        )
    diet = [e for e in events if e.has_category("diet") and e.at <= now]
    if diet:
        last_meal = max(diet, key=lambda e: (e.at, e.id))
        hours = (now - last_meal.at).total_seconds() / 3600
        if hours >= DIET_GAP_HOURS:
            alerts.append(
                Alert(
                    id="no_diet_48h",
                    severity="warning",
                    message=f"No meal has been logged for {int(hours)} hours "
                    f"(last on {local_date(last_meal.at, tz).isoformat()}).",
                    evidence=[last_meal.id],
                )
            )
    if review and not urgent:
        alerts.append(
            Alert(
                id="notes_need_review",
                severity="info",
                message=f"{len(review)} note(s) from the last {WINDOW_DAYS} days need a second look.",
                evidence=_ids(review),
            )
        )
    return Insights(facts=facts, alerts=alerts, headline=headline(alerts, len(recent), pet_name), mode=mode)


def headline(alerts: Sequence[Alert], recent_entries: int, pet_name: str) -> str:
    """Rule-based: the most severe alert wins; otherwise a plain activity line."""
    order = {"urgent": 0, "warning": 1, "info": 2}
    if alerts:
        top = min(alerts, key=lambda a: order[a.severity])
        if top.severity == "urgent":
            return f"Possible red flag noted for {pet_name}: contact your vet."
        return top.message
    if recent_entries:
        return f"{recent_entries} entries logged for {pet_name} in the last {WINDOW_DAYS} days. No alerts."
    return f"Nothing logged for {pet_name} in the last {WINDOW_DAYS} days."
