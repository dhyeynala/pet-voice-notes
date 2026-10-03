"""Track C services: events, time zones, retrieval, deterministic queries, notes, chat,
insights, charts and PDF summaries. Written from the requirements (review H1-H5, M2-M5, M12).
"""

from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional

import pytest

from petpulse.providers.llm import FakeLLM
from petpulse.services import queries
from petpulse.services.assistant import AssistantUnavailable, answer_question, detect_intent
from petpulse.services.charts import build_chart
from petpulse.services.events import Event, load_events
from petpulse.services.insights import compute_insights
from petpulse.services.notes import MAX_NOTE_CHARS, decide, list_notes, process_note
from petpulse.services.pdf import MIN_TEXT_CHARS, page_problems, select_pages, summarize_pdf
from petpulse.services.retrieval import BM25, search, tokenize
from petpulse.store.memory import MemoryStore
from petpulse.timeutil import InvalidTimezone, local_date, parse_timestamp, to_iso, validate_tz

UTC = timezone.utc
NOW = datetime(2026, 10, 3, 18, 0, tzinfo=UTC)  # 14:00 in New York
NY = "America/New_York"
PET = "pet-1"


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def naive(days_ago: float, hour: int = 12) -> str:
    """A legacy analytics timestamp: naive UTC ISO-8601."""
    moment = (NOW - timedelta(days=days_ago)).replace(hour=hour, minute=0, second=0, microsecond=0)
    return moment.replace(tzinfo=None).isoformat()


def add(store: MemoryStore, category: str, days_ago: float, hour: int = 12, **fields: Any) -> str:
    doc = {"category": category, "timestamp": naive(days_ago, hour), "source": "form", "schema_version": 1, **fields}
    return store.add(f"pets/{PET}/analytics", doc)


def note_doc(store: MemoryStore, text: str, days_ago: float, **fields: Any) -> str:
    note_id = f"n{len(store.query(f'pets/{PET}/notes')) + 1:03d}"
    doc = {
        "pet_id": PET,
        "source": "text",
        "text": text,
        "summary": text,
        "kind": "DAILY_ACTIVITY",
        "urgent": False,
        "needs_review": False,
        "red_flags": [],
        "observations": [],
        "status": "processed",
        "created_at": to_iso(NOW - timedelta(days=days_ago)),
        "mode": "demo",
        **fields,
    }
    store.set(f"pets/{PET}/notes/{note_id}", doc)
    return note_id


def ev(id: str, text: str, days_ago: float = 0, kind: Any = "note", category: Optional[str] = None) -> Event:
    return Event(id, kind, "text", NOW - timedelta(days=days_ago), text, category)


# ------------------------------------------------------------------ time
def test_naive_timestamps_are_utc_and_garbage_is_none():
    assert parse_timestamp("2026-10-03T23:30:00") == datetime(2026, 10, 3, 23, 30, tzinfo=UTC)
    assert parse_timestamp("2026-10-03T23:30:00Z") == parse_timestamp("2026-10-03T19:30:00-04:00")
    assert parse_timestamp("yesterday") is None and parse_timestamp(None) is None and parse_timestamp(3) is None


def test_days_are_bucketed_in_the_users_time_zone():
    late_evening_ny = parse_timestamp("2026-10-04T02:30:00")  # 22:30 on Oct 3 in New York
    assert late_evening_ny is not None
    assert local_date(late_evening_ny, "UTC") == date(2026, 10, 4)
    assert local_date(late_evening_ny, NY) == date(2026, 10, 3)


@pytest.mark.parametrize("tz", ["Mars/Olympus", "../etc/passwd", "x" * 80])
def test_invalid_time_zones_are_rejected(tz):
    with pytest.raises(InvalidTimezone):
        validate_tz(tz)


# ------------------------------------------------------------------ events
def test_events_count_unreadable_rows_and_skip_legacy_mirrors():
    store = MemoryStore()
    note_id = note_doc(store, "Walked in the park.", 1)
    store.add(f"pets/{PET}/textinput", {"input": "Walked in the park.", "timestamp": naive(1), "note_id": note_id})
    store.add(f"pets/{PET}/textinput", {"input": "An older legacy note.", "timestamp": naive(5)})
    add(store, "exercise", 2, duration=30)
    store.add(f"pets/{PET}/analytics", {"category": "diet", "timestamp": "not a date"})
    store.add(f"pets/{PET}/analytics", {"category": "diet"})
    store.add(f"pets/{PET}/analytics", {"timestamp": naive(1)})
    load = load_events(store, PET)
    assert [e.text for e in load.events if e.kind == "note"] == ["An older legacy note.", "Walked in the park."]
    assert load.skipped == 3 and load.skipped_by_reason == {"bad_timestamp": 2, "no_content": 1}
    assert [e.at for e in load.events] == sorted(e.at for e in load.events)


# ------------------------------------------------------------------ retrieval
def test_bm25_prefers_rare_terms_and_has_a_no_match_path():
    events = [ev("a", "walk walk walk in the park"), ev("b", "ate dinner"), ev("c", "walk and limping on the left leg")]
    assert search(events, "limping") and search(events, "limping")[0].event.id == "c"
    assert search(events, "seizure") == [] and search([], "walk") == []
    index = BM25([(e.id, tokenize(e.text)) for e in events])
    assert index.idf["limp"] > index.idf["walk"]


def test_bm25_ties_are_deterministic_newest_first_then_id():
    events = [ev("b", "vomited", 1), ev("a", "vomited", 1), ev("c", "vomited", 3)]
    assert [hit.event.id for hit in search(events, "vomit")] == ["a", "b", "c"]


# ------------------------------------------------------------------ queries
def test_first_mention_reaches_past_thirty_days():
    events = [ev("old", "Seemed tired after the hike.", 40), ev("new", "Tired again today.", 2), ev("x", "Ate well.", 50)]
    terms = tokenize("tired")
    assert queries.first_mention(events, terms).id == "old"
    assert queries.last_mention(events, terms).id == "new"


def test_question_windows_are_parsed_in_the_users_zone_without_a_30_day_cap():
    window = queries.window_from_question("how many walks in the last 3 months", NY, NOW)
    assert window is not None and (window.end - window.start).days == 90
    yesterday = queries.window_from_question("what did he eat yesterday", NY, NOW)
    assert yesterday is not None and yesterday.start.date() == date(2026, 10, 2)
    assert queries.window_from_question("when did he first limp", NY, NOW) is None


def test_daily_series_counts_zero_but_missing_measurements_are_unknown():
    events = [ev("e1", "x", 0, "analytics", "energy_levels")]
    energy = Event("e2", "analytics", "analytics", NOW, "energy", "energy_levels", (), {"level": 4})
    series = queries.daily_series(
        [energy, *events],
        tz="UTC",
        start=date(2026, 10, 1),
        end=date(2026, 10, 3),
        select=lambda e: True,
        value=queries.energy_level,
        aggregate="mean",
    )
    assert series == [(date(2026, 10, 1), None), (date(2026, 10, 2), None), (date(2026, 10, 3), 4.0)]
    counts = queries.daily_series(events, tz="UTC", start=date(2026, 10, 2), end=date(2026, 10, 3), select=lambda e: True)
    assert counts == [(date(2026, 10, 2), 0.0), (date(2026, 10, 3), 1.0)]


# ------------------------------------------------------------------ notes
def test_urgent_note_is_stored_with_red_flag_and_review():
    store = MemoryStore()
    note = run(process_note(PET, "alice", "He vomited blood twice tonight.", "text", NY, store=store, llm=FakeLLM()))
    assert note.urgent and note.needs_review and note.status == "processed" and note.mode == "demo"
    assert {(f.flag, f.status) for f in note.red_flags} == {("blood", "present"), ("repeated_vomiting", "present")}
    stored = store.get(f"pets/{PET}/notes/{note.id}")
    assert stored["uid"] == "alice" and stored["tz"] == NY and stored["prompt"] == "note_extract.v1"
    assert len(store.query("llm_calls")) == 1
    assert list_notes(store, PET)[0] == note


def test_negated_note_is_not_urgent():
    note = run(
        process_note(
            PET, "alice", "No vomiting today and he ate breakfast.", "voice", "UTC", store=MemoryStore(), llm=FakeLLM()
        )
    )
    assert not note.urgent and note.source == "voice"


def test_provider_failure_stores_an_unprocessed_note_for_review():
    store = MemoryStore()
    note = run(process_note(PET, "alice", "He walked for an hour.", "text", "UTC", store=store, llm=FakeLLM(mode="fail")))
    assert note.status == "unprocessed" and note.kind == "UNKNOWN" and note.needs_review and note.summary is None
    assert store.get(f"pets/{PET}/notes/{note.id}")["failure_reason"] == "provider_error"


def test_invalid_once_is_repaired_into_a_processed_note():
    store = MemoryStore()
    note = run(
        process_note(PET, "alice", "He walked for an hour.", "text", "UTC", store=store, llm=FakeLLM(mode="invalid_once"))
    )
    assert note.status == "processed" and store.get(f"pets/{PET}/notes/{note.id}")["llm_attempts"] == 2


@pytest.mark.parametrize("text,tz", [("   ", "UTC"), ("x" * (MAX_NOTE_CHARS + 1), "UTC"), ("fine", "Nowhere/City")])
def test_bad_input_raises_value_error(text, tz):
    with pytest.raises(ValueError):
        run(process_note(PET, "alice", text, "text", tz, store=MemoryStore(), llm=FakeLLM()))


def test_decision_rules_live_in_code():
    from petpulse.llm.schemas import NoteExtraction

    base = {"summary": "s", "observations": [], "addressed_to_model": False}
    assert decide(
        NoteExtraction(kind="MEDICAL", red_flags=[{"flag": "seizure", "status": "present", "sentences": [1]}], **base)
    ) == (True, True)
    assert decide(
        NoteExtraction(kind="MEDICAL", red_flags=[{"flag": "seizure", "status": "denied", "sentences": [1]}], **base)
    ) == (False, False)
    assert decide(
        NoteExtraction(kind="MEDICAL", red_flags=[{"flag": "seizure", "status": "ambiguous", "sentences": [1]}], **base)
    ) == (False, True)
    assert decide(NoteExtraction(kind="UNKNOWN", red_flags=[], **base)) == (False, True)


# ------------------------------------------------------------------ assistant
def seeded_store() -> MemoryStore:
    store = MemoryStore()
    store.set(f"pets/{PET}", {"name": "Max", "owners": ["alice"]})
    note_doc(store, "Max seemed tired after the long hike.", 40)
    note_doc(store, "He was limping on his left leg after the walk.", 3)
    for day in range(20):
        add(store, "energy_levels", day, 23, level=2 if day < 4 else 4, notes="")
        add(store, "exercise", day, 15, duration=30, type="walk")
    return store


def ask(store: MemoryStore, message: str, llm: Optional[FakeLLM] = None) -> Any:
    return run(answer_question(PET, "alice", message, NY, store=store, llm=llm or FakeLLM(), now=NOW))


def test_first_mention_is_answered_by_code_with_a_citation():
    llm = FakeLLM()
    reply = ask(seeded_store(), "When did Max first seem tired?", llm)
    assert reply.status == "answered" and "\u201ctired\u201d" in reply.answer
    assert reply.citations[0].date == "2026-08-24" and llm.calls == []


def test_counts_are_computed_not_generated_and_not_capped_at_30_days():
    llm = FakeLLM()
    reply = ask(seeded_store(), "How many walks did he have in the last 2 weeks?", llm)
    assert reply.status == "answered" and reply.answer.startswith("14 ") and llm.calls == []


def test_nothing_retrieved_means_not_in_records_without_a_model_call():
    llm = FakeLLM()
    reply = ask(seeded_store(), "Has he ever had a seizure?", llm)
    assert reply.status == "not_in_records" and reply.citations == [] and llm.calls == []


def test_dosing_questions_are_out_of_scope():
    reply = ask(seeded_store(), "What dose of ibuprofen can I give him for the limping?")
    assert reply.status == "out_of_scope" and reply.citations == []


@pytest.mark.parametrize(
    "message",
    [
        "What dose of ibuprofen should I give Max?",  # nothing in the records mentions ibuprofen
        "Can I give him chocolate as a treat?",
        "How much Benadryl should I give Max?",
        "Can you diagnose what's wrong with him?",
        "What's the weather tomorrow?",
    ],
)
def test_out_of_scope_runs_before_the_not_found_branch(message):
    """Regression: with no matching records the not-found branch used to answer first."""
    llm = FakeLLM()
    reply = ask(seeded_store(), message, llm)
    assert reply.status == "out_of_scope" and reply.citations == [] and reply.chart is None
    assert "veterinarian" in reply.answer and llm.calls == []  # decided by code, no model call


@pytest.mark.parametrize(
    "message",
    ["What was Max diagnosed with at the vet?", "When did Max first seem tired?", "Has he ever had a seizure?"],
)
def test_record_questions_are_not_out_of_scope(message):
    assert ask(seeded_store(), message).status != "out_of_scope"


def test_open_question_cites_only_retrieved_records():
    reply = ask(seeded_store(), "Why was he limping?")
    assert reply.status == "answered" and reply.citations and reply.citations[0].snippet.startswith("He was limping")


def test_citations_outside_the_retrieved_set_are_dropped():
    llm = FakeLLM()
    llm.register(
        "chat_answer.v1",
        lambda system, user, schema: {"status": "answered", "answer": "Invented [N9].", "citations": ["N9"], "chart": "none"},
    )
    reply = ask(seeded_store(), "Why was he limping?", llm)
    assert reply.status == "not_in_records" and reply.citations == []


def test_chart_request_returns_a_valid_chart_config():
    reply = ask(seeded_store(), "Show me a chart of his energy trend")
    assert reply.status == "answered" and reply.chart is not None
    assert reply.chart["type"] == "line" and len(reply.chart["data"]["labels"]) == 30
    assert len(reply.chart["data"]["datasets"][0]["data"]) == 30


def test_provider_outage_is_reported_as_unavailable():
    with pytest.raises(AssistantUnavailable):
        ask(seeded_store(), "Why was he limping?", FakeLLM(mode="fail"))


def test_intents():
    assert detect_intent("When did he first limp?") == "first"
    assert detect_intent("how many times did he vomit") == "count"
    assert detect_intent("when was the last time he limped") == "last"
    assert detect_intent("is he ok?") == "open"


# ------------------------------------------------------------------ charts
def test_no_data_means_no_chart():
    assert build_chart("energy_trend", [], tz="UTC", now=NOW) is None
    assert build_chart("none", [ev("a", "x")], tz="UTC", now=NOW) is None


# ------------------------------------------------------------------ insights
def insights(store: MemoryStore, now: datetime = NOW) -> Any:
    return compute_insights(load_events(store, PET), tz=NY, now=now, pet_name="Max", mode="demo")


def test_low_energy_streak_needs_three_consecutive_logged_days():
    store = MemoryStore()
    for day, level in [(1, 2), (2, 1), (3, 2), (4, 5)]:
        add(store, "energy_levels", day, level=level)
    assert "low_energy_streak" in [a.id for a in insights(store).alerts]
    store2 = MemoryStore()
    for day, level in [(1, 2), (2, 4), (3, 2), (4, 2)]:
        add(store2, "energy_levels", day, level=level)
    assert "low_energy_streak" not in [a.id for a in insights(store2).alerts]


def test_urgent_note_in_the_last_week_is_an_urgent_alert_and_the_headline():
    store = MemoryStore()
    flag = [{"flag": "blood", "status": "present", "sentences": [1]}]
    note_doc(store, "Vomited blood.", 1, urgent=True, needs_review=True, red_flags=flag, kind="MEDICAL")
    result = insights(store)
    assert result.alerts[0].severity == "urgent" and "blood" in result.alerts[0].message
    assert result.headline.startswith("Possible red flag")
    note_doc_old = MemoryStore()
    note_doc(note_doc_old, "Vomited blood.", 9, urgent=True, red_flags=flag)
    assert not [a for a in insights(note_doc_old).alerts if a.severity == "urgent"]


def test_diet_gap_alert_only_with_diet_history():
    store = MemoryStore()
    add(store, "exercise", 0, duration=20)
    assert "no_diet_48h" not in [a.id for a in insights(store).alerts]
    add(store, "diet", 3, food="kibble")
    assert "no_diet_48h" in [a.id for a in insights(store).alerts]
    add(store, "diet", 1, food="kibble")
    assert "no_diet_48h" not in [a.id for a in insights(store).alerts]


def test_facts_are_computed_and_unreadable_rows_are_reported():
    store = MemoryStore()
    for day in range(14):
        add(store, "exercise", day, duration=10 if day < 7 else 20)
    store.add(f"pets/{PET}/analytics", {"category": "diet", "timestamp": "??"})
    facts = {f.id: f.value for f in insights(store).facts}
    assert facts["exercise_minutes_7d"] == 70 and facts["exercise_minutes_prior_7d"] == 140
    assert facts["avg_energy_7d"] is None and facts["unreadable_rows"] == 1
    assert insights(store).headline.endswith("in the last 7 days. No alerts.")


def test_empty_pet_has_no_alerts():
    result = insights(MemoryStore())
    assert result.alerts == [] and result.headline == "Nothing logged for Max in the last 7 days."


# ------------------------------------------------------------------ pdf
PAGE1 = "Visit summary for Max.\nDiagnosis: otitis externa.\nPrescribed Apoquel 16 mg once daily."
PAGE2 = "Recheck in 2 weeks.\nWeight 30 kg."


def test_pdf_summary_cites_real_pages():
    store = MemoryStore()
    result = run(summarize_pdf([PAGE1, PAGE2], pet_id=PET, uid="alice", store=store, llm=FakeLLM()))
    assert result.status == "summarized" and result.pages_included == 2
    assert result.summary.medications[0].name == "Apoquel" and result.summary.medications[0].pages == [1]
    assert result.summary.follow_ups[0].pages == [2]
    assert store.query("llm_calls")[0][1]["feature"] == "pdf_summary"


def test_pdf_without_text_is_no_text_and_makes_no_call():
    llm = FakeLLM()
    result = run(summarize_pdf(["  ", " 1 "], pet_id=PET, uid="alice", store=None, llm=llm))
    assert result.status == "no_text" and llm.calls == [] and MIN_TEXT_CHARS > 3


def test_pdf_failure_is_summary_failed_without_placeholder_text():
    result = run(summarize_pdf([PAGE1], pet_id=PET, uid="alice", store=None, llm=FakeLLM(mode="fail")))
    assert result.status == "summary_failed" and result.summary is None and result.failure_reason == "provider_error"


def test_pages_are_included_whole_within_the_budget():
    assert select_pages(["a" * 60, "b" * 50, "c" * 10], budget=100) == ["a" * 60]
    assert select_pages(["a" * 150], budget=100) == ["a" * 100]


def test_page_citations_outside_the_document_are_rejected():
    from petpulse.llm.schemas import PdfSummary

    summary = PdfSummary(
        document_kind="other",
        summary="s",
        findings=[{"text": "x", "pages": [3]}],
        medications=[],
        follow_ups=[],
        addressed_to_model=False,
    )
    assert page_problems(summary, 2) == ["findings.0.pages: [3] not in 1..2"]


@pytest.mark.parametrize(
    "transcript,urgent",
    [
        ("Max vomited twice this morning and there was some blood.", True),  # voice sample vomiting_blood
        ("Max had his usual thirty minute walk and finished all of his dinner.", False),  # walk_and_dinner
        ("Gave Max his heartworm pill with breakfast this morning.", False),  # heartworm_pill
    ],
)
def test_voice_sample_transcripts_drive_the_urgent_banner(transcript, urgent):
    note = run(process_note(PET, "alice", transcript, "voice", "UTC", store=MemoryStore(), llm=FakeLLM()))
    assert note.urgent is urgent and note.status == "processed"
