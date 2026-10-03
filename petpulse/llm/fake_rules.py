"""Deterministic keyword rules that stand in for the model when no API key is set.

The fake receives exactly the rendered prompt a real model would get and answers from the
text inside the data markers only. Its output is built from the same Pydantic schemas and
goes through the same validation, so the whole pipeline is exercised in demo mode.

These rules were written from the requirement (what each red flag means), not tuned on the
eval cases; the offline eval keeps cases the fake is expected to get wrong.

Magic phrase: a note containing ``#fail`` simulates a provider outage, so the demo can show
the honest failure path (unprocessed note, needs review, no invented summary).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from petpulse.llm.schemas import (
    MEDICAL_CATEGORIES,
    ChatAnswer,
    NoteExtraction,
    Observation,
    PdfItem,
    PdfMedication,
    PdfSummary,
    RedFlag,
)
from petpulse.providers.llm import LLMError

FailPhrase = "#fail"
_FLAGS = re.IGNORECASE


def block(user: str, tag: str) -> str:
    """Text between ``<tag>`` and ``</tag>`` in a rendered user message ("" if absent)."""
    match = re.search(rf"<{tag}>\n?(.*?)\n?</{tag}>", user, re.DOTALL)
    return match.group(1).strip() if match else ""


def numbered_lines(text: str, prefix: str) -> list[tuple[str, str]]:
    """Parse ``[S1] text`` / ``[N2] text`` lines into ``(label, text)`` pairs."""
    out = []
    for line in text.splitlines():
        match = re.match(rf"\[({prefix}\d+)\]\s?(.*)$", line.strip())
        if match:
            out.append((match.group(1), match.group(2).strip()))
    return out


# ---------------------------------------------------------------------- note rules
NEGATION = re.compile(
    r"\b(no|not|never|without|none|nor|didn'?t|did not|hasn'?t|has not|haven'?t|have not|isn'?t|wasn'?t|"
    r"won'?t|doesn'?t|does not|don'?t|do not|zero)\b",
    _FLAGS,
)
HEDGE = re.compile(
    r"\b(maybe|might|possibly|perhaps|not sure|unsure|i think|looked like|looks like|seemed like|could have|"
    r"may have|probably|i guess)\b",
    _FLAGS,
)
CLAUSE_BREAK = re.compile(r"[,;:]|\b(but|though|however|and|then)\b", _FLAGS)
ADDRESSED_TO_MODEL = re.compile(
    r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|prompts?)|\byou are now\b|"
    r"system prompt|disregard (all|the|any|previous)|as an ai\b|new instructions:",
    _FLAGS,
)

_VOMIT = r"vomit\w*|threw up|throw(?:ing)? up|puk\w*"
_TOXINS = r"chocolate|grapes?|raisins?|xylitol|rat poison|antifreeze|ibuprofen|advil|tylenol|acetaminophen"


@dataclass(frozen=True)
class FlagRule:
    flag: str
    trigger: re.Pattern[str]  # the flag happened (sentence level)
    topic: re.Pattern[str]  # the flag's subject is mentioned (used for denials)


FLAG_RULES: tuple[FlagRule, ...] = (
    FlagRule(
        "blood",
        re.compile(
            rf"\bblood\w*\b.*\b({_VOMIT}|stool|poop\w*|diarrh\w*|urine|pee\w*|nose|mouth)|"
            rf"\b({_VOMIT}|stool|poop\w*|diarrh\w*|urine|pee\w*)\b.*\bblood\w*|\bbloody\b|\bbleeding\b",
            _FLAGS,
        ),
        re.compile(r"\bblood\w*|\bbleed\w*", _FLAGS),
    ),
    FlagRule(
        "repeated_vomiting",
        re.compile(
            rf"\b({_VOMIT})\b.*\b(twice|again|three times|\d+ times|several times|multiple times|repeatedly|"
            rf"all (day|night|morning))\b|\b(keeps?|kept) ({_VOMIT})",
            _FLAGS,
        ),
        re.compile(rf"\b({_VOMIT})", _FLAGS),
    ),
    FlagRule(
        "collapse",
        re.compile(r"\b(collaps\w*|fainted|passed out|couldn'?t stand|could not stand|can'?t stand)", _FLAGS),
        re.compile(r"\b(collaps\w*|fainted|passed out)", _FLAGS),
    ),
    FlagRule(
        "seizure",
        re.compile(r"\b(seizure\w*|seizing|convuls\w*|fitting)\b", _FLAGS),
        re.compile(r"\b(seizure\w*|seizing|convuls\w*)", _FLAGS),
    ),
    FlagRule(
        "breathing_difficulty",
        re.compile(
            r"\b(can'?t|cannot|struggl\w* to|trouble|difficulty|hard time)\s+breath\w*|\blabou?red breath\w*|"
            r"\bgasping\b|\bbreathing (hard|heavily|fast|strangely|noisily)",
            _FLAGS,
        ),
        re.compile(r"\bbreath\w*|\bgasping\b", _FLAGS),
    ),
    FlagRule(
        "pale_or_blue_gums",
        re.compile(
            r"\bgums\b[^.]{0,25}\b(pale|white|blue|grey|gray)\b|\b(pale|white|blue|grey|gray)\b[^.]{0,10}\bgums\b", _FLAGS
        ),
        re.compile(r"\bgums\b", _FLAGS),
    ),
    FlagRule(
        "toxin_ingestion",
        re.compile(
            rf"\b(ate|eaten|eat|eating|got into|chewed|swallowed|licked|stole|snuck)\b[^.]{{0,40}}\b({_TOXINS})\b", _FLAGS
        ),
        re.compile(rf"\b({_TOXINS})\b", _FLAGS),
    ),
)

CATEGORY_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "diet",
        re.compile(
            r"\b(ate|eat|eats|eating|food|dinner|breakfast|lunch|kibble|meal|treats?|fed|feeding|appetite|drank)\b", _FLAGS
        ),
    ),
    ("exercise", re.compile(r"\b(walk\w*|ran|run|running|fetch|park|hike\w*|swim\w*|jog\w*)\b", _FLAGS)),
    (
        "medication",
        re.compile(
            r"\b(pills?|dose|dosage|\d+\s?mg|medication|meds|apoquel|heartworm|flea|tablets?|antibiotics?|"
            r"carprofen|insulin)\b",
            _FLAGS,
        ),
    ),
    ("sleep", re.compile(r"\b(slept|sleep\w*|nap\w*)\b", _FLAGS)),
    ("bowel_movements", re.compile(r"\b(poop\w*|stool|diarrh\w*|bowel|constipat\w*)\b", _FLAGS)),
    ("mood", re.compile(r"\b(happy|anxious|playful|grumpy|calm|nervous|excited|clingy|restless|cheerful)\b", _FLAGS)),
    ("energy_levels", re.compile(r"\b(energy|energetic|lethargic|tired|sluggish|lazy|hyper)\b", _FLAGS)),
    ("grooming", re.compile(r"\b(bath|brush\w*|groom\w*|nails?|trim\w*)\b", _FLAGS)),
    ("weight", re.compile(r"\b(weigh\w*|\d+(\.\d+)?\s?(kg|lbs?|pounds))\b", _FLAGS)),
    (
        "symptom",
        re.compile(
            rf"\b({_VOMIT}|diarrh\w*|limp\w*|cough\w*|sneez\w*|itch\w*|scratch\w*|letharg\w*|sick|pain\w*|swollen|"
            r"swelling|bleed\w*|blood\w*|lump|rash|wheez\w*|seizure\w*|collaps\w*|fainted|gasping|pale)\b",
            _FLAGS,
        ),
    ),
    ("vet_visit", re.compile(r"\b(vet|vets|veterinarian|clinic|check-?up|vaccin\w*)\b", _FLAGS)),
)
# Symptoms that are phrased as a negation ("not eating") and so skip the negation check.
APPETITE_LOSS = re.compile(
    r"\b(not eating|won'?t eat|refus\w* (to eat|food|dinner|breakfast)|off (his|her) food|no appetite)\b", _FLAGS
)
_PRECEDENCE = {"present": 3, "ambiguous": 2, "denied": 1}


def _clause_start(sentence: str, position: int) -> int:
    starts = [m.end() for m in CLAUSE_BREAK.finditer(sentence) if m.end() <= position]
    return max(starts) if starts else 0


def _negated_before(sentence: str, end: int) -> bool:
    """Is there a negation in the clause that ends at ``end``, before ``end``?"""
    return bool(NEGATION.search(sentence[_clause_start(sentence, end) : end]))


def flag_status(rule: FlagRule, sentence: str) -> Optional[str]:
    """present / ambiguous / denied for one sentence, or ``None`` if the flag is not mentioned."""
    trigger = rule.trigger.search(sentence)
    if trigger and not _negated_before(sentence, trigger.end()):
        return "ambiguous" if HEDGE.search(sentence) else "present"
    for topic in rule.topic.finditer(sentence):
        if _negated_before(sentence, topic.end()):
            return "denied"
    return None


def _all_negated(pattern: re.Pattern[str], sentence: str) -> bool:
    matches = list(pattern.finditer(sentence))
    return bool(matches) and all(_negated_before(sentence, m.end()) for m in matches)


def _sentence_observations(number: int, text: str) -> list[Observation]:
    found = [
        Observation(category=category, text=text[:300], sentences=[number])  # type: ignore[arg-type]
        for category, pattern in CATEGORY_RULES
        if pattern.search(text) and not _all_negated(pattern, text)
    ]
    if APPETITE_LOSS.search(text) and not any(o.category == "symptom" for o in found):
        found.append(Observation(category="symptom", text=text[:300], sentences=[number]))
    return found


def _resolve_flags(statuses: dict[str, dict[str, list[int]]]) -> list[RedFlag]:
    red_flags: list[RedFlag] = []
    for rule in FLAG_RULES:  # fixed order
        found = statuses.get(rule.flag)
        if not found:
            continue
        if "present" in found and "denied" in found:  # the note contradicts itself
            status, cited = "ambiguous", sorted({n for nums in found.values() for n in nums})
        else:
            status = max(found, key=lambda s: _PRECEDENCE[s])
            cited = found[status]
        red_flags.append(RedFlag(flag=rule.flag, status=status, sentences=cited))  # type: ignore[arg-type]
    return red_flags


def extract_note(sentences: list[tuple[int, str]]) -> NoteExtraction:
    """Apply the keyword rules to numbered sentences."""
    words = sum(len(text.split()) for _, text in sentences)
    full_text = " ".join(text for _, text in sentences)
    if words < 3:
        return NoteExtraction(kind="UNKNOWN", summary="", observations=[], red_flags=[], addressed_to_model=False)

    observations: list[Observation] = []
    statuses: dict[str, dict[str, list[int]]] = {}
    for number, text in sentences:
        observations.extend(_sentence_observations(number, text))
        for rule in FLAG_RULES:
            status = flag_status(rule, text)
            if status:
                statuses.setdefault(rule.flag, {}).setdefault(status, []).append(number)
    red_flags = _resolve_flags(statuses)

    medical = any(f.status != "denied" for f in red_flags) or any(o.category in MEDICAL_CATEGORIES for o in observations)
    activity = any(o.category not in MEDICAL_CATEGORIES for o in observations)
    kind = "MIXED" if medical and activity else "MEDICAL" if medical else "DAILY_ACTIVITY" if activity else "OTHER"

    cited_numbers = sorted({n for o in observations for n in o.sentences} | {n for f in red_flags for n in f.sentences})
    by_number = dict(sentences)
    picked = [by_number[n] for n in cited_numbers[:2]] or [sentences[0][1]]
    summary = " ".join(picked)
    if len(summary) > 400:
        summary = summary[:397].rstrip() + "..."
    return NoteExtraction(
        kind=kind,  # type: ignore[arg-type]
        summary=summary,
        observations=observations[:20],
        red_flags=red_flags,
        addressed_to_model=bool(ADDRESSED_TO_MODEL.search(full_text)),
    )


def note_extract_handler(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
    note = block(user, "note")
    if FailPhrase in note.lower():
        raise LLMError("simulated provider outage (#fail in note)")
    note = note.replace("\u2019", "'")  # curly apostrophes from speech-to-text
    sentences = [(int(label[1:]), text) for label, text in numbered_lines(note, "S")]
    return extract_note(sentences).model_dump()


# ---------------------------------------------------------------------- chat rules
OUT_OF_SCOPE = re.compile(
    r"\b(should i (give|feed|take|use)|what dose|how much \w+ (should|can) i give|diagnos\w*|is it safe to give|"
    r"can i give|prescribe|what medicine)\b|\b(weather|stock|bitcoin|capital of|recipe|president)\b",
    _FLAGS,
)
_STOP = frozenset(
    "a an and are as at be did do does for from had has have he her his how i in is it its me my of on or our "
    "she so that the their them they this to was we were what when where which who why will with you your "
    "max luna".split()
)
CHART_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("energy_trend", re.compile(r"\benerg\w*|\btired\w*|\bletharg\w*", _FLAGS)),
    ("exercise_minutes", re.compile(r"\bexercis\w*|\bwalk\w*|\bactivity minutes\b", _FLAGS)),
    ("notes_per_day", re.compile(r"\bnotes?\b", _FLAGS)),
    ("entries_by_category", re.compile(r"\bcategor\w*|\bentries\b|\bbreakdown\b", _FLAGS)),
)
_WANTS_CHART = re.compile(r"\b(chart|graph|plot|trend|visuali[sz]e)\b", _FLAGS)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOP and len(w) > 2}


def _stem(word: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 3:
            return word[: -len(suffix)]
    return word


def chat_answer_handler(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
    question = block(user, "question")
    records = numbered_lines(block(user, "records"), "N")
    chart = "none"
    if _WANTS_CHART.search(question):
        chart = next((kind for kind, pattern in CHART_RULES if pattern.search(question)), "entries_by_category")
    if OUT_OF_SCOPE.search(question):
        answer = ChatAnswer(
            status="out_of_scope",
            answer="I can only answer from your pet's records. For medical advice or dosing, please ask your veterinarian.",
            citations=[],
            chart="none",
        )
        return answer.model_dump()
    wanted = {_stem(w) for w in _tokens(question)}
    used = [(label, text) for label, text in records if wanted & {_stem(w) for w in _tokens(text)}][:2]
    if not used:
        answer = ChatAnswer(
            status="not_in_records",
            answer="I couldn't find this in the records.",
            citations=[],
            chart=chart,  # type: ignore[arg-type]
        )
        return answer.model_dump()
    lines = "; ".join(f"{text[:180]} [{label}]" for label, text in used)
    answer = ChatAnswer(
        status="answered",
        answer=f"From the records: {lines}",
        citations=[label for label, _ in used],
        chart=chart,  # type: ignore[arg-type]
    )
    return answer.model_dump()


# ----------------------------------------------------------------------- pdf rules
_MED = re.compile(r"\b([A-Z][A-Za-z-]{2,})\s+(\d+(?:\.\d+)?\s?(?:mg|mcg|ml|g)\b(?:[^.;\n]{0,40})?)")
_FOLLOW_UP = re.compile(r"recheck|follow.?up|return in|revisit|next appointment|booster due", _FLAGS)
_FINDING = re.compile(r"diagnos\w*|assessment|finding|result|positive|negative|vaccin\w*|otitis|dermatitis|exam", _FLAGS)
_KIND_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("invoice", re.compile(r"\binvoice\b|amount due|\btotal due\b", _FLAGS)),
    ("vaccination", re.compile(r"vaccination record|vaccine certificate|rabies certificate", _FLAGS)),
    ("lab_results", re.compile(r"\b(cbc|chemistry panel|bloodwork|urinalysis|lab results?)\b", _FLAGS)),
    ("prescription", re.compile(r"\bprescription\b|\brx\b", _FLAGS)),
    ("vet_visit", re.compile(r"\b(exam|visit|assessment|diagnos\w*|patient|veterinar\w*)\b", _FLAGS)),
)


def _pages(document: str) -> list[tuple[int, str]]:
    pages: list[tuple[int, str]] = []
    for match in re.finditer(r"\[P(\d+)\]\n?(.*?)(?=\n\[P\d+\]|\Z)", document, re.DOTALL):
        pages.append((int(match.group(1)), match.group(2)))
    return pages


def _scan_pages(pages: list[tuple[int, str]]) -> tuple[list[PdfItem], list[PdfMedication], list[PdfItem]]:
    findings: list[PdfItem] = []
    follow_ups: list[PdfItem] = []
    medications: list[PdfMedication] = []
    for number, text in pages:
        for raw in text.splitlines():
            line = " ".join(raw.split())
            if not line:
                continue
            for med in _MED.finditer(line):
                medications.append(PdfMedication(name=med.group(1), dose=med.group(2).strip()[:80], pages=[number]))
            if _FOLLOW_UP.search(line):
                follow_ups.append(PdfItem(text=line[:300], pages=[number]))
            elif _FINDING.search(line) and not _MED.search(line):
                findings.append(PdfItem(text=line[:300], pages=[number]))
    return findings, medications, follow_ups


def _pdf_text(findings: list[PdfItem], medications: list[PdfMedication], follow_ups: list[PdfItem]) -> str:
    parts = []
    if medications:
        parts.append("Medications: " + ", ".join(f"{m.name} {m.dose}".strip() for m in medications[:5]) + ".")
    if follow_ups:
        parts.append("Follow-up: " + follow_ups[0].text)
    if findings and len(parts) < 2:
        parts.append("Noted: " + findings[0].text)
    return " ".join(parts) or "No medications, findings or follow-ups were found in the document text."


def pdf_summary_handler(system: str, user: str, schema: dict[str, Any]) -> dict[str, Any]:
    document = block(user, "document")
    pages = _pages(document)
    if not any(text.strip() for _, text in pages):
        empty = PdfSummary(
            document_kind="UNKNOWN", summary="", findings=[], medications=[], follow_ups=[], addressed_to_model=False
        )
        return empty.model_dump()
    findings, medications, follow_ups = _scan_pages(pages)
    whole = document
    kind = next((name for name, pattern in _KIND_RULES if pattern.search(whole)), "other")
    summary = _pdf_text(findings, medications, follow_ups)
    result = PdfSummary(
        document_kind=kind,  # type: ignore[arg-type]
        summary=summary[:600],
        findings=findings[:15],
        medications=medications[:15],
        follow_ups=follow_ups[:10],
        addressed_to_model=bool(ADDRESSED_TO_MODEL.search(whole)),
    )
    return result.model_dump()


Handler = Callable[[str, str, dict[str, Any]], Any]

# Keyed by ``<prompt_id>.v<version>``: a new prompt version needs an explicit fake mapping.
HANDLERS: dict[str, Handler] = {
    "note_extract.v1": note_extract_handler,
    "chat_answer.v1": chat_answer_handler,
    "pdf_summary.v1": pdf_summary_handler,
}

# Schema fields the fake must emit; used by tests to keep handlers and schemas in step.
SCHEMAS = {"note_extract.v1": NoteExtraction, "chat_answer.v1": ChatAnswer, "pdf_summary.v1": PdfSummary}
