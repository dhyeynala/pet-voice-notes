"""ai_analytics after the pandas/numpy removal (review H3)."""

from __future__ import annotations

import json

import pytest

from ai_analytics import PetAnalyticsAI

HISTORY = [
    {"category": "diet", "timestamp": "2026-09-28T08:15:00"},  # Monday
    {"category": "diet", "timestamp": "2026-09-29T08:30:00"},  # Tuesday
    {"category": "diet", "timestamp": "2026-09-29T18:00:00"},  # Tuesday
    {"category": "exercise", "timestamp": "2026-09-30T07:00:00Z"},  # Wednesday, Z suffix
    {"category": "exercise", "timestamp": ""},  # bad rows count towards frequency only
    {"category": "exercise"},
]


@pytest.fixture
def ai():
    return PetAnalyticsAI()


def test_historical_patterns_are_plain_json(ai):
    patterns = ai._analyze_historical_patterns(HISTORY)
    json.dumps(patterns)  # used to raise: Object of type int32 is not JSON serializable
    assert patterns["diet"] == {
        "frequency": 3,
        "most_active_hour": 8,
        "weekday_pattern": {"most_active_day": "Tuesday", "distribution": {"Tuesday": 2, "Monday": 1}},
    }
    assert patterns["exercise"]["frequency"] == 3
    assert patterns["exercise"]["most_active_hour"] == 7
    assert type(patterns["diet"]["most_active_hour"]) is int


def test_most_active_hour_defaults_and_ties(ai):
    assert ai._find_most_active_hour([]) == 12
    assert ai._analyze_historical_patterns([]) == {}
    tie = ai._analyze_historical_patterns(
        [{"category": "c", "timestamp": "2026-10-01T15:00:00"}, {"category": "c", "timestamp": "2026-10-01T09:00:00"}]
    )
    assert tie["c"]["most_active_hour"] == 9  # earliest hour wins a tie (pandas mode() order)


def test_prepare_analytics_context_serialises(ai):
    daily = [
        {"category": "exercise", "duration": "30", "intensity": "high"},
        {"category": "exercise", "duration": 10, "intensity": "low"},
        {"category": "energy_levels", "level": 2},
        {"category": "energy_levels", "level": 4},
    ]
    context = ai._prepare_analytics_context("Max", daily, HISTORY, "2026-10-01")
    json.dumps(context)
    assert context["daily_summary"]["exercise"]["total_duration"] == 40
    assert context["daily_summary"]["exercise"]["avg_intensity"] == "moderate"
    assert context["daily_summary"]["energy"] == {"avg_level": 3.0, "recordings": 2, "trend": "increasing"}


def test_energy_trend_slope(ai):
    assert ai._calculate_energy_trend([5, 4, 3, 2]) == "decreasing"
    assert ai._calculate_energy_trend([3, 3, 3]) == "stable"
    assert ai._calculate_energy_trend([1]) == "stable"


def test_health_context_means(ai):
    ctx = ai._prepare_health_context(
        "Max", [{"category": "exercise", "duration": 20}, {"category": "exercise", "duration": 40}], 30
    )
    assert ctx["exercise_analysis"]["avg_duration"] == 30.0
    json.dumps(ctx)


def test_daily_headlines_fall_back_to_rules_with_fake(ai, app):
    headlines = ai.generate_daily_headlines("Max", [{"category": "diet"}], HISTORY, "2026-10-01")
    assert headlines == ["🍽️ Max enjoyed 1 meal today"]
