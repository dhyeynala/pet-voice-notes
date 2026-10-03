"""Grounded chat over one pet's records (review C4, M6, M8; replaces the 12 legacy tools).

Routing is code:
0. Requests for dosing, treatment or diagnosis advice, and questions that are not about the pet
   at all, are ``out_of_scope`` before anything else runs (no retrieval, no model call). This
   check runs first so an advice question about something the records never mention is still
   ``out_of_scope``, not ``not_in_records``.
1. Date and count questions ("when did I first mention...", "how many times...") are answered
   by the deterministic query tools. No model call, and nothing is counted from snippets.
2. Everything else: BM25 retrieval. No hit -> ``not_in_records`` with no model call.
   Otherwise one ``chat_answer.v1`` call with the hits in a ``<records>`` block.
3. Code checks every citation against the retrieved set and drops the rest; an ``answered``
   reply with no valid citation becomes ``not_in_records``. A chart is built by code from the
   enum the model picked, only for answered replies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Optional, Sequence

from pydantic import BaseModel, ConfigDict

from petpulse.llm.client import LLMClient, LLMFailure, TaskSpec, provider_mode
from petpulse.llm.schemas import ChatAnswer, ChatStatus
from petpulse.providers.llm import LLMProvider
from petpulse.services import queries
from petpulse.services.charts import build_chart
from petpulse.services.events import Event, load_events
from petpulse.services.retrieval import search, stem, tokenize
from petpulse.store.base import Store
from petpulse.timeutil import local_date, utc_now, validate_tz

CHAT_TASK: TaskSpec[ChatAnswer] = TaskSpec("chat_answer", 1, ChatAnswer)
TOP_K = 5
MAX_RECORD_CHARS = 500
SNIPPET_CHARS = 160
MAX_MESSAGE_CHARS = 1000
NOT_FOUND = "I couldn't find this in {pet}'s records."
OUT_OF_SCOPE_ANSWER = (
    "I can only answer from {pet}'s records. For medical advice, a diagnosis or dosing, please ask your veterinarian."
)
Mode = Literal["demo", "live"]


class AssistantUnavailable(RuntimeError):
    """The model call failed; the route answers 503 instead of inventing a reply."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class Citation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    date: str
    source: str
    snippet: str


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str
    status: ChatStatus
    citations: list[Citation]
    chart: Optional[dict[str, Any]]
    mode: Mode


# ------------------------------------------------------------------- intent routing
_FIRST = re.compile(r"\bwhen\b.*\b(first|start|started|begin|began)\b|\bfirst (time|mention)", re.IGNORECASE)
_LAST = re.compile(r"\bwhen\b.*\blast\b|\b(last time|most recent(ly)?)\b", re.IGNORECASE)
_COUNT = re.compile(r"\bhow (many|often)\b", re.IGNORECASE)
_INTENT_WORDS = frozenset(
    """when did was first start started begin began mention mentioned mentions notice noticed time times last most
    recent recently how many often record records note notes log logged being seem seemed seems happen happened
    week weeks month months day days past previous ago since this that ever""".split()
)
_CATEGORY_WORDS = {
    "walk": "exercise",
    "exercise": "exercise",
    "hike": "exercise",
    "meal": "diet",
    "diet": "diet",
    "groom": "grooming",
    "bath": "grooming",
    "medication": "medication",
    "pill": "medication",
    "poop": "bowel_movements",
    "weight": "weight",
    "weigh": "weight",
    "energy": "energy_levels",
}
# Question words (stemmed like the tokenizer does) that mean "count entries in a category".
CATEGORY_TERMS = {stem(word): category for word, category in _CATEGORY_WORDS.items()}

Intent = Literal["first", "last", "count", "open"]

# Asking for advice (what to give, how much, a diagnosis) is never answered from the records,
# whatever they contain. Past-tense questions about the records ("what was he diagnosed with?")
# are not advice and stay in scope.
_ADVICE = re.compile(
    r"\b(should i (give|feed|use)|(can|may) i give|is it (ok|okay|safe) to give|what (dose|dosage)|"
    r"how (much|many) \w+(\s\w+)? (should|can|could|do) i give|prescribe|what (medicine|medication|drug) (should|can)|"
    r"(can|could) you diagnose|diagnose (him|her|it|my|this|what))\b",
    re.IGNORECASE,
)
_OFF_TOPIC = re.compile(r"\b(weather|stocks?|bitcoin|capital of|recipe|president)\b", re.IGNORECASE)


def is_out_of_scope(message: str) -> bool:
    """Dosing/treatment/diagnosis advice, or a question that is not about the pet."""
    return bool(_ADVICE.search(message) or _OFF_TOPIC.search(message))


def detect_intent(message: str) -> Intent:
    if _COUNT.search(message):
        return "count"
    if _FIRST.search(message):
        return "first"
    if _LAST.search(message):
        return "last"
    return "open"


def subject_terms(message: str, pet_name: str) -> list[str]:
    """Stemmed content words of the question, without intent words, numbers or the pet's name."""
    stop = set(_INTENT_WORDS) | {w.lower() for w in pet_name.split()}
    terms = [t for t in tokenize(message, stop) if not t.isdigit()]
    return list(dict.fromkeys(terms))


def surface_words(message: str, terms: Sequence[str]) -> str:
    """The question's own words behind the stemmed ``terms`` ("tired", not "tir")."""
    words = []
    for word in re.findall(r"[A-Za-z0-9']+", message):
        if any(token in terms for token in tokenize(word)) and word.lower() not in words:
            words.append(word.lower())
    return " ".join(words) or " ".join(terms)


@dataclass
class _Context:
    pet_name: str
    tz: str
    now: datetime
    mode: Mode


def _citation(event: Event, tz: str) -> Citation:
    snippet = event.text if len(event.text) <= SNIPPET_CHARS else event.text[: SNIPPET_CHARS - 3].rstrip() + "..."
    return Citation(id=event.id, date=local_date(event.at, tz).isoformat(), source=event.source, snippet=snippet)


def _not_found(ctx: _Context, answer: Optional[str] = None) -> ChatResponse:
    return ChatResponse(
        answer=answer or NOT_FOUND.format(pet=ctx.pet_name), status="not_in_records", citations=[], chart=None, mode=ctx.mode
    )


def _out_of_scope(ctx: _Context) -> ChatResponse:
    return ChatResponse(
        answer=OUT_OF_SCOPE_ANSWER.format(pet=ctx.pet_name), status="out_of_scope", citations=[], chart=None, mode=ctx.mode
    )


def _answer_query(intent: Intent, message: str, terms: list[str], events: Sequence[Event], ctx: _Context) -> ChatResponse:
    shown = surface_words(message, terms)
    if intent in ("first", "last"):
        event = queries.first_mention(events, terms) if intent == "first" else queries.last_mention(events, terms)
        if event is None:
            return _not_found(ctx, f"I found no record mentioning \u201c{shown}\u201d for {ctx.pet_name}.")
        cite = _citation(event, ctx.tz)
        word = "first" if intent == "first" else "most recent"
        answer = (
            f"The {word} record mentioning \u201c{shown}\u201d is from {cite.date} ({event.source}): "
            f"\u201c{cite.snippet}\u201d"
        )
        return ChatResponse(answer=answer, status="answered", citations=[cite], chart=None, mode=ctx.mode)

    window = queries.window_from_question(message, ctx.tz, ctx.now)
    category = next((CATEGORY_TERMS[t] for t in terms if t in CATEGORY_TERMS), None)
    if category is not None:
        found = queries.count(events, category=category, window=window)
        what = f"{category.replace('_', ' ')} entries"
    else:
        found = queries.count(events, terms=terms, window=window)
        what = f"records mentioning \u201c{shown}\u201d"
    when = f" {window.label}" if window else ""
    if not found:
        return _not_found(ctx, f"I found no {what} for {ctx.pet_name}{when}.")
    latest = found[-1]
    answer = f"{len(found)} {what}{when}. The most recent is from {local_date(latest.at, ctx.tz).isoformat()}."
    citations = [_citation(e, ctx.tz) for e in reversed(found[-5:])]
    return ChatResponse(answer=answer, status="answered", citations=citations, chart=None, mode=ctx.mode)


def _records_block(hits: Sequence[Event], tz: str) -> tuple[str, dict[str, Event]]:
    labels: dict[str, Event] = {}
    lines = []
    for index, event in enumerate(hits, start=1):
        label = f"N{index}"
        labels[label] = event
        text = event.text if len(event.text) <= MAX_RECORD_CHARS else event.text[:MAX_RECORD_CHARS] + "..."
        lines.append(f"[{label}] {local_date(event.at, tz).isoformat()} ({event.source}): {text}")
    return "\n".join(lines), labels


def pet_name_for(store: Store, pet_id: str) -> str:
    pet = store.get(f"pets/{pet_id}") or {}
    name = pet.get("name")
    return str(name) if isinstance(name, str) and name.strip() else "your pet"


async def answer_question(
    pet_id: str,
    uid: str,
    message: str,
    tz: str,
    *,
    store: Store,
    llm: LLMProvider,
    pet_name: Optional[str] = None,
    now: Optional[datetime] = None,
) -> ChatResponse:
    question = message.strip()
    if not question:
        raise ValueError("message is empty")
    if len(question) > MAX_MESSAGE_CHARS:
        raise ValueError(f"message is longer than {MAX_MESSAGE_CHARS} characters")
    ctx = _Context(pet_name or pet_name_for(store, pet_id), validate_tz(tz), now or utc_now(), provider_mode(llm))
    if is_out_of_scope(question):
        return _out_of_scope(ctx)
    events = load_events(store, pet_id).events

    intent = detect_intent(question)
    terms = subject_terms(question, ctx.pet_name)
    if intent != "open" and terms:
        return _answer_query(intent, question, terms, events, ctx)

    hits = [hit.event for hit in search(events, question, k=TOP_K, extra_stopwords=ctx.pet_name.split())]
    if not hits:
        return _not_found(ctx)
    records, labels = _records_block(hits, ctx.tz)
    client = LLMClient(llm, store, meta={"pet_id": pet_id, "uid": uid, "feature": "chat"})
    try:
        result = await client.run(
            CHAT_TASK,
            {
                "today": local_date(ctx.now, ctx.tz).isoformat(),
                "tz": ctx.tz,
                "pet_name": ctx.pet_name,
                "records": records,
                "question": question,
            },
        )
    except LLMFailure as failure:
        raise AssistantUnavailable(failure.reason) from failure
    reply = result.value
    if reply.status != "answered":
        return ChatResponse(answer=reply.answer, status=reply.status, citations=[], chart=None, mode=ctx.mode)
    valid = [labels[label] for label in dict.fromkeys(c.strip() for c in reply.citations) if label in labels]
    if not valid:
        return _not_found(ctx)
    chart = build_chart(reply.chart, events, tz=ctx.tz, now=ctx.now) if reply.chart != "none" else None
    return ChatResponse(
        answer=reply.answer,
        status="answered",
        citations=[_citation(e, ctx.tz) for e in valid],
        chart=chart,
        mode=ctx.mode,
    )
