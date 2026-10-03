"""Output contracts for every LLM task. These models are the single source of truth.

- Every field code branches on is an enum, including the trouble values (``UNKNOWN``,
  ``OTHER``, ``not_in_records``, ``out_of_scope``).
- Red flags are present / denied / ambiguous: three different facts, never collapsed to a bool.
- Every extracted statement carries citations (sentence numbers for notes, page numbers for
  PDFs, record labels for chat). Code checks that each citation exists.
- ``extra="forbid"``: an invented field is a validation error, not a silent drop.
- ``urgent`` and ``needs_review`` are NOT here: code decides them from these facts.

``strict_json_schema`` turns a model into the JSON schema sent to providers with strict
structured output (OpenAI ``json_schema`` with ``strict: true``).
"""

from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NoteKind = Literal["MEDICAL", "DAILY_ACTIVITY", "MIXED", "OTHER", "UNKNOWN"]
NOTE_KINDS: tuple[str, ...] = ("MEDICAL", "DAILY_ACTIVITY", "MIXED", "OTHER", "UNKNOWN")

RedFlagName = Literal[
    "blood",
    "repeated_vomiting",
    "collapse",
    "seizure",
    "breathing_difficulty",
    "pale_or_blue_gums",
    "toxin_ingestion",
]
RED_FLAGS: tuple[str, ...] = (
    "blood",
    "repeated_vomiting",
    "collapse",
    "seizure",
    "breathing_difficulty",
    "pale_or_blue_gums",
    "toxin_ingestion",
)
FlagStatus = Literal["present", "denied", "ambiguous"]

ObservationCategory = Literal[
    "diet",
    "exercise",
    "medication",
    "sleep",
    "bowel_movements",
    "mood",
    "energy_levels",
    "grooming",
    "weight",
    "symptom",
    "vet_visit",
    "other",
]
# Categories that make a note medical; the rest are daily activity.
MEDICAL_CATEGORIES: frozenset[str] = frozenset({"symptom", "vet_visit"})


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ------------------------------------------------------------------------------- notes
class Observation(_Strict):
    category: ObservationCategory
    text: str = Field(min_length=1, max_length=300, description="What the note says, close to its own words.")
    sentences: list[int] = Field(min_length=1, max_length=10, description="Sentence numbers [S#] this comes from.")


class RedFlag(_Strict):
    flag: RedFlagName
    status: FlagStatus = Field(
        description="present: the note says it happened. denied: the note says it did not. "
        "ambiguous: the note is unsure or contradicts itself."
    )
    sentences: list[int] = Field(min_length=1, max_length=10, description="Sentence numbers [S#] that say so.")


class NoteExtraction(_Strict):
    kind: NoteKind
    summary: str = Field(max_length=400, description="One or two sentences restating the note. Empty if UNKNOWN.")
    observations: list[Observation] = Field(max_length=20)
    red_flags: list[RedFlag] = Field(max_length=len(RED_FLAGS), description="Only flags the note mentions.")
    addressed_to_model: bool = Field(description="True when the note gives instructions to the assistant.")

    @model_validator(mode="after")
    def _one_entry_per_flag(self) -> "NoteExtraction":
        names = [flag.flag for flag in self.red_flags]
        if len(names) != len(set(names)):
            raise ValueError("each red flag may appear at most once")
        return self


# --------------------------------------------------------------------------------- pdf
DocumentKind = Literal["vet_visit", "lab_results", "vaccination", "prescription", "invoice", "other", "UNKNOWN"]


class PdfItem(_Strict):
    text: str = Field(min_length=1, max_length=300)
    pages: list[int] = Field(min_length=1, max_length=10, description="Page numbers [P#] this comes from.")


class PdfMedication(_Strict):
    name: str = Field(min_length=1, max_length=80)
    dose: str = Field(max_length=80, description="Dose as written, or empty if the document does not state one.")
    pages: list[int] = Field(min_length=1, max_length=10)


class PdfSummary(_Strict):
    document_kind: DocumentKind
    summary: str = Field(max_length=600)
    findings: list[PdfItem] = Field(max_length=15)
    medications: list[PdfMedication] = Field(max_length=15)
    follow_ups: list[PdfItem] = Field(max_length=10)
    addressed_to_model: bool


# -------------------------------------------------------------------------------- chat
ChatStatus = Literal["answered", "not_in_records", "out_of_scope"]
ChartKind = Literal["none", "energy_trend", "exercise_minutes", "entries_by_category", "notes_per_day"]
CHART_KINDS: tuple[str, ...] = ("none", "energy_trend", "exercise_minutes", "entries_by_category", "notes_per_day")


class ChatAnswer(_Strict):
    status: ChatStatus
    answer: str = Field(max_length=1200)
    citations: list[str] = Field(max_length=10, description="Record labels such as N3 that support the answer.")
    chart: ChartKind = Field(description="A chart that would help, or none. Code builds the chart.")


# ----------------------------------------------------------------- strict JSON schema
# Keywords providers accept in strict mode. Everything else (minLength, maxLength, title,
# default, ...) is still enforced by Pydantic after the call.
_KEEP = {
    "type",
    "properties",
    "required",
    "additionalProperties",
    "items",
    "enum",
    "const",
    "anyOf",
    "description",
    "minItems",
    "maxItems",
    "minimum",
    "maximum",
}


def _inline(node: Any, defs: dict[str, Any]) -> Any:
    if isinstance(node, list):
        return [_inline(item, defs) for item in node]
    if not isinstance(node, dict):
        return node
    if "$ref" in node:
        name = str(node["$ref"]).rsplit("/", 1)[-1]
        merged = {**copy.deepcopy(defs[name]), **{k: v for k, v in node.items() if k != "$ref"}}
        return _inline(merged, defs)
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key == "properties":
            out[key] = {name: _inline(prop, defs) for name, prop in value.items()}
        elif key in _KEEP:
            out[key] = _inline(value, defs)
    if out.get("type") == "object" or "properties" in out:
        out["type"] = "object"
        out["additionalProperties"] = False
        out["required"] = list(out.get("properties", {}))
    return out


def strict_json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The model's JSON schema in the shape strict structured output requires.

    All objects get ``additionalProperties: false`` and list every property as required;
    ``$ref``s are inlined. Deterministic, so its hash is stable per schema version.
    """
    raw = model.model_json_schema()
    defs = raw.pop("$defs", {})
    schema: dict[str, Any] = _inline(raw, defs)
    return schema
