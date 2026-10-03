"""Red proofs for the review's known bugs (ported from the review harness).

Each test asserts the *correct* behaviour and is marked ``xfail(strict=True,
raises=AssertionError)``:

- while the bug exists, the assertion fails -> reported as xfailed (expected);
- when a fix lands, the test passes -> strict xfail turns that into a FAILURE, so the fixer
  must delete the marker in the same PR (the test then guards against regressions);
- any other exception (e.g. a route was renamed) is a real failure, not a silent xfail:
  update the test to the new API in the PR that changes it.

Finding IDs refer to the review (pet-voice-notes-review.md). Every proof below is fixed now
(C1, C2, CORS by the auth/data track; C3, C4, H2, M2-M4 by the bug-fix and LLM tracks), so none
carries the marker; they stay as regression tests. C4, H2 and M2-M4 originally drove the legacy
modules; since those are deleted they now prove the same property through the contract routes
and services that replaced them. ``known_bug`` is kept for the next finding.

The ``client`` fixture is signed in as alice, who owns the pets ``make_pet()`` creates.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import pytest


def known_bug(finding: str, owner: str):
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"{finding} (fix owner: {owner})")


def test_c1_anonymous_request_cannot_read_another_users_pets(anon_client, client_as, make_pet):
    """Fixed (C1): no token -> 401; another user's token -> no access to alice's data."""
    pet_id = make_pet("alice", "Max")
    assert anon_client.get("/api/user-pets/alice").status_code == 401
    assert anon_client.get(f"/api/pets/{pet_id}/analytics").status_code == 401
    bob = client_as("bob")
    assert bob.get("/api/user-pets/alice").status_code == 403
    assert bob.get(f"/api/pets/{pet_id}/analytics").status_code == 404


def test_c2_two_users_with_same_pet_name_get_distinct_pets(client_as, store):
    """Fixed (C2): pet ids are uuid4s and ownership is per pet, so two "Max"es never collide."""
    a = client_as("userA").post("/api/pets", json={"name": "Max", "animal_type": "dog"}).json()
    b = client_as("userB").post("/api/pets", json={"name": "Max", "animal_type": "cat"}).json()
    assert a["id"] != b["id"]
    assert store.get(f"pets/{a['id']}")["animal_type"] == "dog"
    assert store.get(f"pets/{b['id']}")["owners"] == ["userB"]


def test_cors_does_not_reflect_an_arbitrary_origin(client):
    """Fixed (CORS): only ALLOWED_ORIGINS are echoed, and never with credentials."""
    response = client.options(
        "/api/user-pets/x", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert response.headers.get("access-control-allow-origin") not in ("https://evil.example", "*")
    assert response.headers.get("access-control-allow-credentials") != "true"


def test_c3_upload_filename_cannot_choose_write_location(client_as, store, make_pet, monkeypatch, tmp_path):
    """Fixed: uploads are parsed from memory and stored under a server-generated blob key."""
    import pymupdf

    from petpulse.routers import records

    target = tmp_path / "TRAVERSAL_PROOF.pdf"
    # "/tmp/" + "../<absolute path without leading slash>" resolved to ``target`` in the old code.
    filename = "../" + os.path.relpath(target, "/")
    seen: dict[str, bool] = {}
    real_extract = records.extract_pdf_text

    def spy_extract(data, *args, **kwargs):
        seen["existed_during_processing"] = target.exists()
        return real_extract(data, *args, **kwargs)

    monkeypatch.setattr(records, "extract_pdf_text", spy_extract)
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Recheck in 2 weeks.")
    pet_id = make_pet("alice", "Max")
    response = client_as("alice").post(
        "/api/upload_pdf",
        data={"uid": "alice", "pet": pet_id},  # the owner uploading (a foreign uid is a 403 now)
        files={"file": (filename, doc.tobytes(), "application/pdf")},
    )
    assert response.status_code == 200
    assert seen == {"existed_during_processing": False}
    assert not target.exists()
    [(_, record)] = store.query(f"pets/{pet_id}/records")
    assert record["filename"] == "TRAVERSAL_PROOF.pdf"
    assert record["blob_key"].startswith(f"pets/{pet_id}/records/") and "TRAVERSAL" not in record["blob_key"]


def test_c4_chat_prompt_contains_the_retrieved_note(client, store, fake_llm, make_pet):
    """Fixed (C4): the retrieved note reaches the model, and the answer cites it."""
    pet_id = make_pet("alice", "Max")
    note = client.post(
        f"/api/pets/{pet_id}/notes", json={"text": "Max started limping on his left hind leg on Tuesday"}
    ).json()
    fake_llm.calls.clear()
    response = client.post(f"/api/pets/{pet_id}/chat", json={"message": "Why is Max limping?"})
    assert response.status_code == 200
    [call] = [c for c in fake_llm.calls if c["task"] == "chat_answer.v1"]
    assert "limping on his left hind leg" in call["user"]
    assert [c["id"] for c in response.json()["citations"]] == [note["id"]]


def test_h2_outage_does_not_classify_emergency_as_daily_activity(client, fake_llm, make_pet):
    """Fixed (H2): a provider outage stores an unprocessed note for review, never DAILY_ACTIVITY."""
    pet_id = make_pet("alice", "Max")
    fake_llm.fail = True
    response = client.post(f"/api/pets/{pet_id}/notes", json={"text": "Max collapsed and is vomiting blood, gums are pale"})
    assert response.status_code == 201
    note = response.json()
    assert note["kind"] != "DAILY_ACTIVITY" and note["needs_review"] is True and note["summary"] is None


def test_h2_health_insights_never_invent_a_score(client, store, make_pet):
    """Fixed (H2): insights are facts with evidence; no score, nothing filled in without data."""
    pet_id = make_pet("alice", "Max")
    body = client.get(f"/api/pets/{pet_id}/insights").json()
    assert "overall_health_score" not in body and body["alerts"] == []
    facts = {f["id"]: f for f in body["facts"]}
    assert facts["avg_energy_7d"]["value"] is None and facts["exercise_minutes_7d"]["value"] is None


def _analytics(store, pet_id, category, at, **fields):
    store.add(f"pets/{pet_id}/analytics", {"category": category, "timestamp": at.replace(tzinfo=None).isoformat(), **fields})


def test_m2_trend_reports_decreasing_activity(client, store, make_pet):
    """Fixed (M2): the week-over-week exercise facts show the drop (old trend said 'increasing')."""
    pet_id = make_pet("alice", "Max")
    now = datetime.now(timezone.utc)
    for i in range(6):
        _analytics(store, pet_id, "exercise", now - timedelta(days=9, hours=i), duration=30)
    _analytics(store, pet_id, "exercise", now - timedelta(hours=1), duration=30)
    facts = {f["id"]: f["value"] for f in client.get(f"/api/pets/{pet_id}/insights").json()["facts"]}
    assert facts["exercise_minutes_prior_7d"] == 180 and facts["exercise_minutes_7d"] == 30


def test_m3_missing_timestamp_does_not_break_summary(client_noraise, store, make_pet):
    """Fixed (M3): a row without a timestamp is skipped and counted, not a 500."""
    pet_id = make_pet("alice", "Max")
    store.add(f"pets/{pet_id}/analytics", {"category": "diet"})
    response = client_noraise.get(f"/api/pets/{pet_id}/insights")
    assert response.status_code == 200
    facts = {f["id"]: f["value"] for f in response.json()["facts"]}
    assert facts["unreadable_rows"] == 1


def test_m4_dynamic_chart_average_ignores_entries_without_the_metric():
    """Fixed (M4): days without an energy level are gaps (None), not 0, in the chart average."""
    from petpulse.services.charts import build_chart
    from petpulse.services.events import Event

    now = datetime(2026, 10, 3, 12, tzinfo=timezone.utc)
    events = [
        Event("e1", "analytics", "analytics", now, "energy", "energy_levels", (), {"level": 4}),
        Event("e2", "analytics", "analytics", now - timedelta(days=1), "diet", "diet", (), {}),
        Event("e3", "analytics", "analytics", now - timedelta(days=1), "energy", "energy_levels", (), {}),
    ]
    chart = build_chart("energy_trend", events, tz="UTC", now=now, days=2)
    assert chart is not None and chart["data"]["datasets"][0]["data"] == [None, 4.0]
