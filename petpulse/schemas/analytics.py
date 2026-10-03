"""Typed analytics entries, one model per tracking category (review M7, M3, H1).

Every model forbids unknown keys and bounds every field, so a write can no longer store
arbitrary client JSON (mass assignment) and readers can trust types and ranges. Field names
match the tracking forms in ``public/main.html`` (``dosage`` for medication, ``types`` for
grooming), which is what the readers use too.

Free-text fields default to ``""`` because the forms always send every field and leave unused
ones blank. Numbers reject NaN/inf (``allow_inf_nan=False``): ``parseInt`` on an empty input
becomes ``NaN`` in the browser, which ``JSON.stringify`` sends as ``null``.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

Category = Literal[
    "diet",
    "activity",
    "medication",
    "grooming",
    "exercise",
    "energy_levels",
    "bowel_movements",
    "exit_events",
    "weight",
    "temperature",
    "mood",
    "sleep",
    "water_intake",
]

ShortText = Annotated[str, Field(max_length=200)]
Notes = Annotated[str, Field(max_length=2000)]
RequiredText = Annotated[str, Field(min_length=1, max_length=200)]
# "HH:MM" from <input type="time">, or blank.
TimeOfDay = Annotated[str, Field(pattern=r"^(|([01]\d|2[0-3]):[0-5]\d)$")]
Level = Annotated[int, Field(ge=1, le=5)]
Minutes = Annotated[int, Field(ge=0, le=1440)]


class AnalyticsEntryBase(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False, str_strip_whitespace=True)


class DietEntry(AnalyticsEntryBase):
    food: RequiredText
    quantity: ShortText = ""
    time: TimeOfDay = ""
    type: Literal["breakfast", "lunch", "dinner", "treat", "other"] = "other"
    notes: Notes = ""


class ExerciseEntry(AnalyticsEntryBase):
    type: Literal["walk", "run", "play", "fetch", "swimming", "training", "other"] = "other"
    duration: Annotated[int, Field(ge=1, le=1440)]
    intensity: Literal["low", "moderate", "high", ""] = ""
    location: ShortText = ""
    notes: Notes = ""


class ActivityEntry(AnalyticsEntryBase):
    type: ShortText = ""
    duration: Optional[Minutes] = None
    notes: Notes = ""


class MedicationEntry(AnalyticsEntryBase):
    name: RequiredText
    dosage: RequiredText
    time: TimeOfDay = ""
    frequency: Literal["once", "twice", "weekly", "monthly", "as-needed", ""] = ""
    purpose: ShortText = ""


GroomingType = Literal["bath", "brushing", "nail-trim", "ear-cleaning", "teeth-brushing", "professional"]


class GroomingEntry(AnalyticsEntryBase):
    types: Annotated[list[GroomingType], Field(min_length=1, max_length=6)]
    # The form sends 0 when the duration is left blank.
    duration: Minutes = 0
    products: ShortText = ""
    notes: Notes = ""


class EnergyEntry(AnalyticsEntryBase):
    level: Level
    notes: Notes = ""


class BowelEntry(AnalyticsEntryBase):
    consistency: Literal["normal", "soft", "loose", "hard", "liquid"]
    time: TimeOfDay = ""
    notes: Notes = ""


class ExitEventEntry(AnalyticsEntryBase):
    type: Literal["walk", "potty", "play", "car-ride", "vet-visit", "other"] = "other"
    duration: Minutes = 0
    destination: ShortText = ""


class WeightEntry(AnalyticsEntryBase):
    value: Annotated[float, Field(gt=0, le=1000)]
    unit: Literal["lbs", "kg"]
    method: Literal["home-scale", "vet-visit", "groomer", ""] = ""
    time: TimeOfDay = ""
    notes: Notes = ""


class TemperatureEntry(AnalyticsEntryBase):
    value: float
    unit: Literal["F", "C"]
    method: ShortText = ""
    time: TimeOfDay = ""
    notes: Notes = ""

    @model_validator(mode="after")
    def _plausible_for_unit(self) -> "TemperatureEntry":
        low, high = (25.0, 45.0) if self.unit == "C" else (77.0, 113.0)
        if not low <= self.value <= high:
            raise ValueError(f"temperature must be between {low:g} and {high:g} {self.unit}")
        return self


MoodTrigger = Literal["food", "exercise", "visitors", "weather", "other-pets", "loud-noises", "car-ride"]
MoodBehavior = Literal["playful", "lethargic", "anxious", "aggressive", "affectionate", "withdrawn", "hyperactive"]


class MoodEntry(AnalyticsEntryBase):
    level: Level
    triggers: Annotated[list[MoodTrigger], Field(max_length=7)] = []
    behavior: Annotated[list[MoodBehavior], Field(max_length=7)] = []
    time: TimeOfDay = ""
    notes: Notes = ""


class SleepEntry(AnalyticsEntryBase):
    duration: Annotated[float, Field(ge=0, le=24)]  # hours
    quality: Literal["excellent", "good", "fair", "poor", "restless", ""] = ""
    location: ShortText = ""
    interruptions: Annotated[int, Field(ge=0, le=100)] = 0
    notes: Notes = ""


class WaterIntakeEntry(AnalyticsEntryBase):
    amount: Annotated[float, Field(gt=0, le=20000)]
    unit: Literal["ml", "l", "oz", "cups"] = "ml"
    time: TimeOfDay = ""
    notes: Notes = ""


ENTRY_MODELS: dict[str, type[AnalyticsEntryBase]] = {
    "diet": DietEntry,
    "activity": ActivityEntry,
    "medication": MedicationEntry,
    "grooming": GroomingEntry,
    "exercise": ExerciseEntry,
    "energy_levels": EnergyEntry,
    "bowel_movements": BowelEntry,
    "exit_events": ExitEventEntry,
    "weight": WeightEntry,
    "temperature": TemperatureEntry,
    "mood": MoodEntry,
    "sleep": SleepEntry,
    "water_intake": WaterIntakeEntry,
}

CATEGORIES: tuple[str, ...] = tuple(ENTRY_MODELS)


class Entry(BaseModel):
    """An analytics entry as returned by the API: the typed fields plus server metadata.

    ``timestamp`` is the server-side write time (UTC ISO 8601, the format legacy readers
    compare as strings). Rows written before validation existed may carry other keys; they are
    passed through (``extra="allow"``) so reading old data never fails.
    """

    model_config = ConfigDict(extra="allow")

    id: str
    pet_id: str
    category: str
    timestamp: str


def validate_entry(category: str, payload: Any) -> AnalyticsEntryBase:
    """Validate ``payload`` against the model for ``category``.

    Raises ``KeyError`` for an unknown category and ``pydantic.ValidationError`` for a bad body.
    """
    model = ENTRY_MODELS[category]
    return model.model_validate(payload)
