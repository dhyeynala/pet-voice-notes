"""Regression tests for the bug-fix track: C4, H2, M1, M2, M3, M4, M10 (legacy bodies)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta

import pytest


def ts(days_ago: float = 0.0, now: datetime | None = None) -> str:
    return ((now or datetime.utcnow()) - timedelta(days=days_ago)).isoformat()


@pytest.fixture
def viz():
    from visualization_service import PetVisualizationService

    return PetVisualizationService()


# ------------------------------------------------------------------------------------- M2
NOW = datetime(2026, 10, 3, 12, 0, 0)


@pytest.mark.parametrize(
    "early, late, expected",
    [
        (6, 1, "decreasing"),
        (1, 6, "increasing"),
        (3, 3, "stable"),
        (6, 5, "stable"),  # 1.25 ratio not reached
        (4, 5, "increasing"),  # exactly 1.25x
        (0, 4, "increasing"),
        (4, 0, "decreasing"),
        (2, 1, "insufficient_data"),
        (0, 0, "insufficient_data"),
    ],
)
def test_trend_compares_halves_of_the_time_window(viz, early, late, expected):
    entries = [{"timestamp": ts(25 - i * 0.1, NOW)} for i in range(early)]
    entries += [{"timestamp": ts(5 - i * 0.1, NOW)} for i in range(late)]
    assert viz._calculate_trend(entries, 30, now=NOW) == expected


def test_trend_ignores_bad_and_out_of_window_timestamps(viz):
    entries = [{"timestamp": ts(25, NOW)}] * 4 + [{"timestamp": ""}, {}, {"timestamp": "garbage"}, {"timestamp": ts(90, NOW)}]
    entries += [{"timestamp": ts(-3, NOW)}]  # in the future
    assert viz._calculate_trend(entries, 30, now=NOW) == "decreasing"


def test_trend_order_of_entries_does_not_matter(viz):
    entries = [{"timestamp": ts(2, NOW)}, {"timestamp": ts(28, NOW)}, {"timestamp": ts(1, NOW)}, {"timestamp": ts(3, NOW)}]
    assert viz._calculate_trend(entries, 30, now=NOW) == viz._calculate_trend(entries[::-1], 30, now=NOW) == "increasing"


# ------------------------------------------------------------------------------------- M3
BAD_ROWS = [
    {"category": "exercise", "timestamp": "", "duration": 30},
    {"category": "exercise", "duration": "30 min", "timestamp": ts()},
    {"category": "energy_levels", "timestamp": "not-a-date", "level": 4},
    {"category": "energy_levels", "timestamp": ts(), "level": "high"},
    {"category": "medication", "timestamp": None},
    {"category": "exercise", "timestamp": ts(), "duration": None},
]


def test_charts_skip_bad_rows_instead_of_raising(viz):
    good = [
        {"category": "exercise", "timestamp": ts(), "duration": 20},
        {"category": "energy_levels", "timestamp": ts(), "level": 2},
        {"category": "medication", "timestamp": ts(), "name": "x"},
    ]
    data = BAD_ROWS + good
    assert viz.generate_weekly_activity_chart(data)["data"]["datasets"][0]["data"][-1] == 6  # 6 rows dated today
    assert viz.generate_energy_distribution_chart(data)["data"]["datasets"][0]["data"] == [0, 1, 0, 1, 0]  # "high" skipped
    assert viz.generate_exercise_duration_histogram(data)["type"] == "bar"
    assert viz.generate_medication_adherence_chart(data)["data"]["datasets"][0]["data"][-1] == 100.0
    assert sum(viz.generate_activity_heatmap_data(data)["activities"]) == 6
    metrics = viz.generate_summary_metrics(data, 30)
    assert metrics["exercise"]["total_sessions"] == 4
    assert metrics["exercise"]["total_duration"] == 50  # 30 + 20; "30 min" and None are skipped
    assert metrics["energy"]["total_recordings"] == 2  # the "high" level is skipped, not counted as 3
    assert viz.generate_medical_records_timeline(data)["type"] == "line"
    assert viz.generate_dynamic_chart(data, "bar", "hour", "count", None, "count", 30, None) is not None


def test_energy_without_a_level_is_not_counted_as_normal(viz):
    data = [{"category": "energy_levels", "timestamp": ts()}]
    assert viz.generate_energy_distribution_chart(data) is None
    assert "energy" not in viz.generate_summary_metrics(data, 30)


def test_histogram_handles_identical_durations(viz):
    data = [{"category": "exercise", "timestamp": ts(), "duration": 30}] * 3
    chart = viz.generate_exercise_duration_histogram(data)
    assert chart["data"]["labels"] and sum(chart["data"]["datasets"][0]["data"]) == 3


def test_summary_endpoint_skips_and_counts_bad_rows(client, store, make_pet):
    pet_id = make_pet()
    store.add(f"pets/{pet_id}/analytics", {"category": "diet"})
    store.add(f"pets/{pet_id}/analytics", {"category": "diet", "timestamp": ts()})
    store.add(f"pets/{pet_id}/voice-notes", {"transcript": "x", "timestamp": ""})
    store.add(f"pets/{pet_id}/textinput", {"input": "x", "timestamp": "nope"})
    body = client.get(f"/api/pets/{pet_id}/analytics/summary").json()
    assert body["summary"]["diet"]["total"] == 1
    assert body["skipped_rows"] == 3


def test_daily_headline_fallback_tolerates_bad_values():
    import api_server

    rows = [
        {"category": "exercise", "duration": "30 min"},
        {"category": "exercise", "duration": 70},
        {"category": "energy_levels", "level": None},
    ]
    headlines = api_server.generate_routine_headlines("Max", rows, "2026-10-03")
    assert any("70 minutes" in h for h in headlines)
    assert not any("energy" in h.lower() for h in headlines)  # no level recorded: no energy headline


def test_ai_analytics_context_tolerates_bad_values():
    from ai_analytics import PetAnalyticsAI

    rows = [
        {"category": "exercise", "duration": "abc", "timestamp": ts()},
        {"category": "exercise", "duration": 15, "timestamp": ts()},
        {"category": "energy_levels", "level": "x", "timestamp": ts()},
    ]
    ai = PetAnalyticsAI()
    context = ai._prepare_analytics_context("Max", rows, rows)
    assert context["daily_summary"]["exercise"]["total_duration"] == 15
    assert context["daily_summary"]["energy"]["avg_level"] is None
    json.dumps(context)  # still JSON-serialisable
    health = ai._prepare_health_context("Max", rows, 30)
    assert health["exercise_analysis"]["total_duration"] == 15


# ------------------------------------------------------------------------------------- M4
def test_dynamic_chart_missing_values_are_none_not_zero(viz):
    data = [
        {"category": "energy_levels", "level": 4, "timestamp": ts()},
        {"category": "mood", "level": 2, "timestamp": ts(1)},
        {"category": "diet", "timestamp": ts()},
    ]
    assert viz._extract_y_value({"category": "diet"}, "level") is None
    assert viz._extract_y_value({"duration": "x"}, "duration") is None
    cfg = viz.generate_dynamic_chart(data, "line", "date", "level", None, "average", 30, "category")
    series = {d["label"]: d["data"] for d in cfg["data"]["datasets"]}
    assert set(series) == {"Energy_Levels", "Mood"}
    assert None in series["Energy_Levels"] and 0 not in series["Energy_Levels"]
    counted = viz.generate_dynamic_chart(data, "bar", "date", "count", None, "count", 30, "category")
    assert all(v is not None for d in counted["data"]["datasets"] for v in d["data"])  # counts stay 0


def test_histogram_does_not_impute_15_minutes(viz):
    data = [
        {"category": "daily_activity", "summary": "A 30 minute walk", "timestamp": ts()},
        {"category": "daily_activity", "summary": "Ate breakfast", "timestamp": ts()},
    ]
    chart = viz.generate_exercise_duration_histogram(data)
    assert sum(chart["data"]["datasets"][0]["data"]) == 1
    assert not any(label.startswith("15-") for label in chart["data"]["labels"])


# ------------------------------------------------------------------------------------- M1
@pytest.mark.parametrize(
    "raw",
    [
        {"classification": "Emergency!!", "confidence": 0.9},
        {"classification": "MEDICAL", "confidence": 7},
        {"classification": "MEDICAL", "confidence": -0.1},
        {"classification": "MEDICAL", "confidence": "0.9"},
        {"classification": "MEDICAL", "confidence": True},
        {"classification": "MEDICAL", "confidence": float("nan")},
        {"classification": "MEDICAL"},
        {"confidence": 0.5},
        ["MEDICAL", 0.9],
        "MEDICAL",
    ],
)
def test_invalid_model_classification_becomes_unknown(raw):
    from summarize_openai import validate_classification

    result = validate_classification(raw)
    assert result["classification"] == "UNKNOWN" and result["confidence"] == 0.0 and result["needs_review"] is True


def test_valid_model_classification_is_kept_and_cleaned():
    from summarize_openai import validate_classification

    result = validate_classification(
        {"classification": "MEDICAL", "confidence": 1, "keywords": ["vomit", 3, ""], "reasoning": "x", "extra": 1}
    )
    assert result == {
        "classification": "MEDICAL",
        "confidence": 1.0,
        "keywords": ["vomit"],
        "reasoning": "x",
        "primary_activities": [],
        "needs_review": False,
    }


class _StubLLM:
    def __init__(self, content, finish_reason="stop"):
        self.content, self.finish_reason = content, finish_reason

    def legacy_chat(self, task, **kwargs):
        from types import SimpleNamespace

        message = SimpleNamespace(content=self.content, tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=self.finish_reason)])


@pytest.mark.parametrize(
    "content, finish_reason",
    [
        ('{"classification": "Emergency!!", "confidence": 7}', "stop"),
        ("MEDICAL, probably", "stop"),
        ('{"classification": "MEDICAL", "confid', "length"),
        ('{"classification": "MEDICAL", "confidence": 0.9}', "length"),
    ],
)
def test_classifier_rejects_off_schema_or_truncated_output(monkeypatch, content, finish_reason):
    from petpulse import deps
    import summarize_openai

    deps.override(llm=_StubLLM(content, finish_reason))
    result = summarize_openai.classify_pet_content("Max vomited twice")
    assert result["classification"] == "UNKNOWN" and result["needs_review"] is True


# ------------------------------------------------------------------------------------- H2
def test_classifier_outage_is_unknown_not_daily_activity(fake_llm, no_retry_sleep):
    from petpulse import deps
    import summarize_openai

    fake_llm.fail = True
    deps.override(llm=fake_llm)
    result = summarize_openai.classify_pet_content("Max collapsed and is vomiting blood")
    assert result["classification"] == "UNKNOWN" and result["confidence"] == 0.0 and result["needs_review"] is True
    assert summarize_openai.summarize_text("Max collapsed") is None


def test_textinput_outage_stores_note_flagged_for_review_without_fake_summary(
    client, store, fake_llm, make_pet, no_retry_sleep
):
    pet_id = make_pet()
    fake_llm.fail = True
    body = client.post(f"/api/pets/{pet_id}/textinput", json={"input": "Went for a walk in the park"}).json()
    assert body["content_type"] == "UNKNOWN" and body["needs_review"] is True and body["summary"] is None
    [(_, note)] = store.query(f"pets/{pet_id}/textinput")
    assert note["summary"] is None and note["needs_review"] is True and note["confidence"] == 0.0
    assert store.query(f"pets/{pet_id}/analytics") == []  # not routed to the happy-path dashboard


def test_health_insights_have_no_invented_score(client, store, make_pet):
    pet_id = make_pet()
    store.add(f"pets/{pet_id}/analytics", {"category": "exercise", "duration": 20, "timestamp": ts()})
    body = client.get(f"/api/pets/{pet_id}/health_insights").json()
    assert body["insights"]["overall_health_score"] is None
    assert "Consistent data collection" not in body["insights"]["positive_trends"]


def test_health_insights_failure_is_503(client_noraise, make_pet, monkeypatch):
    import api_server

    pet_id = make_pet()

    def broken():
        raise RuntimeError("analytics down")

    monkeypatch.setattr(api_server, "get_pet_ai", broken)
    response = client_noraise.get(f"/api/pets/{pet_id}/health_insights")
    assert response.status_code == 503
    assert "insights" not in response.json() and "overall_health_score" not in response.text


def test_model_health_insights_are_validated():
    from ai_analytics import _validated_insights

    assert _validated_insights({"overall_health_score": 42, "alerts": []})["overall_health_score"] is None
    assert _validated_insights({"overall_health_score": 8, "alerts": ["x"]})["overall_health_score"] == 8
    assert _validated_insights({"alerts": "not a list"}) is None
    assert _validated_insights(["x"]) is None


# The server-microphone routes (/api/stop_recording) and main.py are deleted (review C5). The
# "no speech / STT error is never stored" guarantee now lives on POST /api/pets/{id}/voice-notes
# (422 / 502 with nothing stored): see tests/test_voice.py.


# ------------------------------------------------------------------------------------- C4
def test_cached_chat_path_also_sends_the_retrieved_note(client, store, fake_llm, make_pet):
    from petpulse.providers.llm import LegacyTask

    pet_id = make_pet()
    store.add(
        f"pets/{pet_id}/voice-notes", {"transcript": "Max ate grass and threw up", "summary": "Vomit", "timestamp": ts()}
    )
    assert client.post(f"/api/pets/{pet_id}/preload", json={"days": 30}).status_code == 200
    assert client.post(f"/api/pets/{pet_id}/chat", json={"query": "Did Max throw up?"}).status_code == 200
    [final] = [c for c in fake_llm.calls if c["task"] == LegacyTask.CHAT_ASSISTANT]
    system = final["messages"][0]["content"]
    assert "Max ate grass and threw up" in system and not system.rstrip().endswith("True")


def test_chat_without_records_says_so(client, fake_llm, make_pet):
    from petpulse.providers.llm import LegacyTask

    pet_id = make_pet()
    client.post(f"/api/pets/{pet_id}/chat", json={"query": "How is Max?"})
    [final] = [c for c in fake_llm.calls if c["task"] == LegacyTask.CHAT_ASSISTANT]
    assert "do not guess" in final["messages"][0]["content"]


async def _rag_documents(pet_id):
    from simple_rag_service import SimplePetHealthRAGService

    return await SimplePetHealthRAGService().get_pet_data_for_rag(pet_id)


def test_rag_reads_dosage_and_grooming_types(app, store, make_pet):
    import asyncio

    pet_id = make_pet()
    store.add(f"pets/{pet_id}/analytics", {"category": "medication", "name": "Apoquel", "dosage": "16 mg", "timestamp": ts()})
    store.add(
        f"pets/{pet_id}/analytics", {"category": "grooming", "types": ["bath", "brushing"], "duration": 20, "timestamp": ts()}
    )
    store.add(f"pets/{pet_id}/records", {"summary": None, "file_name": "scan.pdf", "timestamp": ts()})
    contents = [d["content"] for d in asyncio.run(_rag_documents(pet_id))]
    assert any("Dosage: 16 mg" in c for c in contents)
    assert any("Types: bath, brushing" in c for c in contents)
    assert not any(c.startswith("Medical record: None") for c in contents)


# ------------------------------------------------------------------------------------- M10
def test_legacy_errors_are_http_errors_not_200(client_noraise, make_pet, fake_llm, no_retry_sleep):
    pet_id = make_pet()
    assert client_noraise.post(f"/api/pets/{pet_id}/textinput", json={"input": ""}).status_code == 422
    assert client_noraise.post(f"/api/pets/{pet_id}/chat", json={"query": ""}).status_code == 422
    assert client_noraise.post(f"/api/pets/{pet_id}/knowledge_search", json={"query": ""}).status_code == 422
    fake_llm.fail = True
    response = client_noraise.post(f"/api/pets/{pet_id}/chat", json={"query": "How is Max?"})
    assert response.status_code == 503 and "simulated provider outage" not in response.text
