"""The demo dataset, generated relative to "now" so the charts always look current.

Pure functions: ``build(now)`` returns plain documents and never touches a store, so the data
is easy to test and deterministic for a given ``now`` (no randomness; variation comes from the
day number).

Who and what:

- Alice owns **Max** (6-year-old Golden Retriever) and **Luna** (3-year-old cat).
- Bob owns his own **Max** (2-year-old French Bulldog), a different pet with the same name.
- Alice's Max has ~30 days of entries in all ten tracking categories with an energy dip over
  the last week, plus 8 notes; the most recent one ("vomited twice ... some blood") is urgent.
  One older note (day -40) mentions him being tired, for "when did I first mention ..." demos.
- Luna and Bob's Max have fewer entries.

Analytics entries use the field names of the tracking forms in ``public/main.html`` and the
legacy timestamp format (naive UTC ISO-8601), so the legacy dashboard reads them unchanged.
Notes are stored in the contract ``Note`` shape (``pets/{id}/notes``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

SEED_VERSION = 1
DEMO_TZ = "America/New_York"

# Fixed uuid4 values: reset restores the same ids, so a pet selected in the UI survives a reset.
ALICE_MAX_ID = "638452ec-3d34-4f2c-8d6b-5765533e2287"
ALICE_LUNA_ID = "72949cb3-b5b3-4ac1-aa47-8a9e4dc8c268"
BOB_MAX_ID = "ade67093-1441-48e3-802f-5dcd551135b0"

DEMO_USERS: tuple[dict[str, str], ...] = (
    {"uid": "alice", "name": "Alice", "email": "alice@demo.local"},
    {"uid": "bob", "name": "Bob", "email": "bob@demo.local"},
)

CATEGORIES = (
    "diet",
    "exercise",
    "medication",
    "grooming",
    "energy_levels",
    "bowel_movements",
    "exit_events",
    "weight",
    "sleep",
    "mood",
)


@dataclass
class SeedPet:
    id: str
    owner: str
    fields: dict[str, Any]
    created_days_ago: int
    analytics: list[dict[str, Any]] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class DemoData:
    users: tuple[dict[str, str], ...]
    pets: list[SeedPet]


class _Clock:
    """Turns (days ago, "HH:MM" UTC) into legacy timestamps, skipping times still in the future."""

    def __init__(self, now: datetime) -> None:
        self.now = now.astimezone(timezone.utc).replace(microsecond=0)

    def at(self, days_ago: int, hhmm: str) -> Optional[str]:
        hour, minute = (int(part) for part in hhmm.split(":"))
        moment = (self.now - timedelta(days=days_ago)).replace(hour=hour, minute=minute, second=0)
        if moment > self.now:
            return None
        return moment.replace(tzinfo=None).isoformat()

    def aware(self, days_ago: int, hhmm: str) -> Optional[str]:
        naive = self.at(days_ago, hhmm)
        return f"{naive}+00:00" if naive else None


def _entry(clock: _Clock, days_ago: int, hhmm: str, category: str, **fields: Any) -> Optional[dict[str, Any]]:
    timestamp = clock.at(days_ago, hhmm)
    if timestamp is None:
        return None
    return {**fields, "category": category, "timestamp": timestamp}


# ---------------------------------------------------------------------------- Alice's Max
def _alice_max_analytics(clock: _Clock) -> list[dict[str, Any]]:  # noqa: C901 - a flat data script
    out: list[Optional[dict[str, Any]]] = []
    for d in range(29, -1, -1):
        dip = d <= 6  # the last week: lower energy, shorter walks, picky eating
        # Times are UTC; the demo owner is in New York (UTC-4), so 11:30Z is 7:30 am.
        breakfast_note = "Only ate about half" if d in (5, 1) else ""
        out.append(
            _entry(
                clock,
                d,
                "11:30",
                "diet",
                food="Chicken & rice kibble",
                quantity="1.5 cups",
                time="07:30",
                type="breakfast",
                notes=breakfast_note,
            )
        )
        if d != 1:
            out.append(
                _entry(
                    clock,
                    d,
                    "22:00",
                    "diet",
                    food="Chicken & rice kibble with pumpkin" if dip else "Chicken & rice kibble",
                    quantity="1 cup" if dip else "1.5 cups",
                    time="18:00",
                    type="dinner",
                    notes="Picky, left some" if dip and d % 2 == 0 else "",
                )
            )
        if d % 3 == 0 and not dip:
            out.append(
                _entry(clock, d, "19:00", "diet", food="Peanut butter biscuit", quantity="1", time="15:00", type="treat")
            )

        walk_minutes = 15 + (d % 3) * 5 if dip else 35 + (d % 4) * 5
        out.append(
            _entry(
                clock,
                d,
                "12:15",
                "exercise",
                type="walk",
                duration=walk_minutes,
                intensity="low" if dip else "moderate",
                location="Neighborhood loop",
                notes="Slow, stopped to lie down" if d == 5 else "",
            )
        )
        if not dip and d % 2 == 0:
            out.append(
                _entry(
                    clock,
                    d,
                    "21:30",
                    "exercise",
                    type="fetch",
                    duration=20 + (d % 3) * 10,
                    intensity="high",
                    location="Riverside dog park",
                    notes="",
                )
            )

        out.append(
            _entry(
                clock,
                d,
                "12:00",
                "medication",
                name="Apoquel",
                dosage="16 mg",
                time="08:00",
                frequency="once",
                purpose="Seasonal allergies (itching)",
            )
        )
        if d == 20:
            out.append(
                _entry(
                    clock,
                    d,
                    "12:05",
                    "medication",
                    name="Heartgard Plus",
                    dosage="1 chewable",
                    time="08:05",
                    frequency="monthly",
                    purpose="Heartworm prevention",
                )
            )

        if d % 4 == 2:
            out.append(
                _entry(clock, d, "23:00", "grooming", types=["brushing"], duration=10, products="Slicker brush", notes="")
            )
        if d == 15:
            out.append(
                _entry(
                    clock,
                    d,
                    "20:00",
                    "grooming",
                    types=["bath", "teeth-brushing"],
                    duration=40,
                    products="Oatmeal shampoo, enzymatic toothpaste",
                    notes="Good boy in the tub",
                )
            )
        if d == 21:
            out.append(
                _entry(clock, d, "20:30", "grooming", types=["nail-trim"], duration=15, products="Nail grinder", notes="")
            )

        level = (2 if d % 2 else 3) if dip else (4 if d % 3 else 5)
        energy_note = "Tired, napping a lot" if dip else ("Zoomies after dinner" if level == 5 else "")
        out.append(_entry(clock, d, "23:30", "energy_levels", level=level, notes=energy_note))

        out.append(
            _entry(
                clock,
                d,
                "12:30",
                "bowel_movements",
                consistency="soft" if d == 2 else "normal",
                time="08:30",
                notes="",
            )
        )
        if d % 2 == 0:
            out.append(_entry(clock, d, "21:45", "bowel_movements", consistency="normal", time="17:45", notes=""))

        out.append(_entry(clock, d, "16:30", "exit_events", type="potty", duration=5, destination="Backyard"))
        out.append(_entry(clock, d, "02:30", "exit_events", type="potty", duration=5, destination="Backyard"))
        if d == 12:
            out.append(_entry(clock, d, "14:00", "exit_events", type="vet-visit", duration=60, destination="Maple Street Vet"))

        if d % 7 == 3:
            weights = {24: 68.4, 17: 68.2, 10: 68.0, 3: 67.1}
            out.append(
                _entry(
                    clock,
                    d,
                    "12:40",
                    "weight",
                    value=weights[d],
                    unit="lbs",
                    method="vet-visit" if d == 10 else "home-scale",
                    time="08:40",
                    notes="Down a bit, eating less" if d == 3 else "",
                )
            )

        out.append(
            _entry(
                clock,
                d,
                "11:00",
                "sleep",
                duration=11.5 if dip else 9.5 + (d % 2) * 0.5,
                quality=("restless" if d % 2 else "fair") if dip else "good",
                location="Dog bed",
                interruptions=2 if dip else 0,
                notes="Woke up panting twice" if d == 1 else "",
            )
        )

        if d % 2 == 0 or dip:
            out.append(
                _entry(
                    clock,
                    d,
                    "23:45",
                    "mood",
                    level=3 if dip else 5,
                    triggers=["food"] if dip else ["exercise", "visitors"],
                    behavior=["lethargic", "withdrawn"] if dip else ["playful", "affectionate"],
                    time="19:45",
                    notes="Not interested in his toys" if dip else "",
                )
            )
    return [entry for entry in out if entry is not None]


def _note(
    clock: _Clock,
    days_ago: int,
    hhmm: str,
    *,
    source: str,
    text: str,
    summary: str,
    kind: str,
    observations: list[dict[str, Any]],
    red_flags: Optional[list[dict[str, Any]]] = None,
) -> Optional[dict[str, Any]]:
    created_at = clock.aware(days_ago, hhmm)
    if created_at is None:
        return None
    flags = red_flags or []
    urgent = any(flag["status"] == "present" for flag in flags)
    # Same "code decides" rule the note pipeline uses (demo plan D4-1).
    needs_review = urgent or kind in ("UNKNOWN", "MIXED") or any(flag["status"] == "ambiguous" for flag in flags)
    return {
        "source": source,
        "text": text,
        "summary": summary,
        "kind": kind,
        "urgent": urgent,
        "needs_review": needs_review,
        "red_flags": flags,
        "observations": observations,
        "status": "processed",
        "created_at": created_at,
        "tz": DEMO_TZ,
        "mode": "demo",
    }


def _obs(category: str, text: str, *sentences: int) -> dict[str, Any]:
    return {"category": category, "text": text, "sentences": list(sentences) or [1]}


def _alice_max_notes(clock: _Clock) -> list[dict[str, Any]]:
    notes = [
        _note(
            clock,
            40,
            "22:30",
            source="voice",
            text="Max seemed a little tired after the long hike on Saturday. He still ate all of his dinner.",
            summary="A little tired after a long hike; ate all of his dinner.",
            kind="DAILY_ACTIVITY",
            observations=[_obs("mood", "a little tired after a long hike", 1), _obs("diet", "ate all of his dinner", 2)],
        ),
        _note(
            clock,
            27,
            "22:15",
            source="text",
            text="Max had his usual 30 minute walk and finished dinner.",
            summary="Usual 30 minute walk; finished dinner.",
            kind="DAILY_ACTIVITY",
            observations=[_obs("exercise", "30 minute walk"), _obs("diet", "finished dinner")],
        ),
        _note(
            clock,
            20,
            "12:10",
            source="text",
            text="Gave Max his monthly Heartgard chewable with breakfast. No issues.",
            summary="Monthly Heartgard given with breakfast.",
            kind="DAILY_ACTIVITY",
            observations=[_obs("medication", "monthly Heartgard chewable", 1)],
        ),
        _note(
            clock,
            15,
            "20:45",
            source="voice",
            text="Bath day. Max was a good boy and his coat looks great. We started brushing his teeth too.",
            summary="Bath and first tooth brushing; coat looks great.",
            kind="DAILY_ACTIVITY",
            observations=[_obs("grooming", "bath", 1, 2), _obs("grooming", "started brushing his teeth", 3)],
        ),
        _note(
            clock,
            9,
            "23:00",
            source="text",
            text="Max scratched his ears a lot today and kept shaking his head. He is eating normally.",
            summary="Scratching ears and head shaking; eating normally.",
            kind="MEDICAL",
            observations=[_obs("symptom", "scratching ears and shaking head", 1), _obs("diet", "eating normally", 2)],
        ),
        _note(
            clock,
            5,
            "13:00",
            source="voice",
            text="Max was slow on his walk this morning and lay down halfway. He only ate half his breakfast.",
            summary="Slow on the morning walk, lay down halfway; ate half his breakfast.",
            kind="MIXED",
            observations=[
                _obs("exercise", "slow on his walk, lay down halfway", 1),
                _obs("diet", "ate half his breakfast", 2),
            ],
        ),
        _note(
            clock,
            3,
            "21:00",
            source="text",
            text="Max seems lethargic. He slept most of the afternoon and skipped fetch.",
            summary="Lethargic; slept most of the afternoon and skipped fetch.",
            kind="MIXED",
            observations=[_obs("mood", "lethargic", 1), _obs("sleep", "slept most of the afternoon", 2)],
        ),
        _note(
            clock,
            1,
            "12:45",
            source="voice",
            text="Max vomited twice this morning and there was some blood. He is drinking water but won't eat.",
            summary="Vomited twice with some blood; drinking water but not eating.",
            kind="MEDICAL",
            observations=[_obs("symptom", "vomited twice with some blood", 1), _obs("diet", "won't eat", 2)],
            red_flags=[
                {"flag": "blood", "status": "present", "sentences": [1]},
                {"flag": "repeated_vomiting", "status": "present", "sentences": [1]},
            ],
        ),
    ]
    return [note for note in notes if note is not None]


# ---------------------------------------------------------------------------- Luna
def _luna_analytics(clock: _Clock) -> list[dict[str, Any]]:
    out: list[Optional[dict[str, Any]]] = []
    for d in range(27, -1, -1):
        out.append(
            _entry(clock, d, "12:00", "diet", food="Salmon pate (wet)", quantity="1 can", time="08:00", type="breakfast")
        )
        if d % 2 == 0:
            out.append(_entry(clock, d, "23:00", "energy_levels", level=4 if d % 4 else 3, notes=""))
            out.append(_entry(clock, d, "13:00", "bowel_movements", consistency="normal", time="09:00", notes="Litter box"))
        if d % 3 == 0:
            out.append(
                _entry(
                    clock, d, "00:30", "exercise", type="play", duration=10, intensity="high", location="Living room", notes=""
                )
            )
            out.append(
                _entry(
                    clock,
                    d,
                    "12:30",
                    "sleep",
                    duration=14.0,
                    quality="excellent",
                    location="Sunny windowsill",
                    interruptions=0,
                    notes="",
                )
            )
            out.append(
                _entry(
                    clock,
                    d,
                    "23:30",
                    "mood",
                    level=4,
                    triggers=["food"],
                    behavior=["playful"],
                    time="19:30",
                    notes="",
                )
            )
        if d % 7 == 0:
            out.append(
                _entry(
                    clock, d, "22:00", "grooming", types=["brushing"], duration=5, products="Rubber grooming mitt", notes=""
                )
            )
        if d in (21, 7):
            out.append(
                _entry(
                    clock, d, "12:15", "weight", value=9.5 if d == 21 else 9.6, unit="lbs", method="home-scale", time="08:15"
                )
            )
    return [entry for entry in out if entry is not None]


def _luna_notes(clock: _Clock) -> list[dict[str, Any]]:
    notes = [
        _note(
            clock,
            12,
            "00:15",
            source="text",
            text="Luna knocked her water glass over again and played with the feather wand for 15 minutes.",
            summary="Played with the feather wand for 15 minutes.",
            kind="DAILY_ACTIVITY",
            observations=[_obs("exercise", "feather wand play, 15 minutes", 1)],
        ),
        _note(
            clock,
            4,
            "13:30",
            source="voice",
            text="Luna threw up a hairball after breakfast. Otherwise she is normal and playful.",
            summary="One hairball after breakfast; otherwise normal and playful.",
            kind="MEDICAL",
            observations=[_obs("symptom", "hairball after breakfast", 1), _obs("mood", "normal and playful", 2)],
        ),
    ]
    return [note for note in notes if note is not None]


# ---------------------------------------------------------------------------- Bob's Max
def _bob_max_analytics(clock: _Clock) -> list[dict[str, Any]]:
    out: list[Optional[dict[str, Any]]] = []
    for d in range(13, -1, -1):
        out.append(
            _entry(clock, d, "13:00", "diet", food="Grain-free puppy kibble", quantity="1 cup", time="09:00", type="breakfast")
        )
        out.append(
            _entry(
                clock,
                d,
                "14:00",
                "exercise",
                type="walk",
                duration=20,
                intensity="moderate",
                location="Block loop",
                notes="Short walks, flat-faced breed",
            )
        )
        out.append(_entry(clock, d, "02:00", "energy_levels", level=5 if d % 2 else 4, notes=""))
        if d % 3 == 0:
            out.append(
                _entry(
                    clock,
                    d,
                    "13:30",
                    "sleep",
                    duration=12.0,
                    quality="good",
                    location="Crate",
                    interruptions=1,
                    notes="Snores",
                )
            )
        if d == 6:
            out.append(_entry(clock, d, "15:00", "weight", value=24.2, unit="lbs", method="home-scale", time="11:00"))
    return [entry for entry in out if entry is not None]


def _bob_max_notes(clock: _Clock) -> list[dict[str, Any]]:
    notes = [
        _note(
            clock,
            2,
            "23:30",
            source="voice",
            text="Max loved the dog park today. He ran for an hour and slept the whole way home.",
            summary="An hour at the dog park; slept on the way home.",
            kind="DAILY_ACTIVITY",
            observations=[_obs("exercise", "an hour at the dog park", 1, 2), _obs("sleep", "slept the whole way home", 2)],
        ),
    ]
    return [note for note in notes if note is not None]


# ---------------------------------------------------------------------------- entry point
def build(now: Optional[datetime] = None) -> DemoData:
    clock = _Clock(now or datetime.now(timezone.utc))
    pets = [
        SeedPet(
            id=ALICE_MAX_ID,
            owner="alice",
            fields={
                "name": "Max",
                "animal_type": "dog",
                "breed": "Golden Retriever",
                "age": 6,
                "weight": 67.1,
                "gender": "male-neutered",
            },
            created_days_ago=45,
            analytics=_alice_max_analytics(clock),
            notes=_alice_max_notes(clock),
        ),
        SeedPet(
            id=ALICE_LUNA_ID,
            owner="alice",
            fields={
                "name": "Luna",
                "animal_type": "cat",
                "breed": "Domestic Shorthair",
                "age": 3,
                "weight": 9.6,
                "gender": "female-spayed",
            },
            created_days_ago=44,
            analytics=_luna_analytics(clock),
            notes=_luna_notes(clock),
        ),
        SeedPet(
            id=BOB_MAX_ID,
            owner="bob",
            fields={
                "name": "Max",
                "animal_type": "dog",
                "breed": "French Bulldog",
                "age": 2,
                "weight": 24.2,
                "gender": "male",
            },
            created_days_ago=20,
            analytics=_bob_max_analytics(clock),
            notes=_bob_max_notes(clock),
        ),
    ]
    return DemoData(users=DEMO_USERS, pets=pets)
