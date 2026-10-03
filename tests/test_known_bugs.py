"""Red proofs for the review's known bugs (ported from the review harness).

Each test asserts the *correct* behaviour and is marked ``xfail(strict=True,
raises=AssertionError)``:

- while the bug exists, the assertion fails -> reported as xfailed (expected);
- when a fix lands, the test passes -> strict xfail turns that into a FAILURE, so the fixer
  must delete the marker in the same PR (the test then guards against regressions);
- any other exception (e.g. a route was renamed) is a real failure, not a silent xfail:
  update the test to the new API in the PR that changes it.

Finding IDs refer to the review (pet-voice-notes-review.md).
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import pytest


def known_bug(finding: str, owner: str):
    return pytest.mark.xfail(strict=True, raises=AssertionError, reason=f"{finding} (fix owner: {owner})")


@known_bug("C1: no server-side auth, anyone can list any user's pets", "auth/data track")
def test_c1_anonymous_request_cannot_read_another_users_pets(client, make_pet):
    make_pet("alice", "Max")
    response = client.get("/api/user-pets/alice")  # no credentials at all
    assert response.status_code in (401, 403, 404)


@known_bug("C2: pet ids derive from the name, so two users' 'Max' collide", "auth/data track")
def test_c2_two_users_with_same_pet_name_get_distinct_pets(client, store):
    a = client.post("/api/pets/userA", json={"name": "Max", "animal_type": "dog"}).json()
    b = client.post("/api/pets/userB", json={"name": "Max", "animal_type": "cat"}).json()
    assert a["pet"]["id"] != b["pet"]["id"]
    assert store.get(f"pets/{a['pet']['id']}")["animal_type"] == "dog"


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
        data={"uid": "victim", "pet": pet_id},
        files={"file": (filename, doc.tobytes(), "application/pdf")},
    )
    assert response.status_code == 200
    assert seen == {"existed_during_processing": False}
    assert not target.exists()
    [(_, record)] = store.query(f"pets/{pet_id}/records")
    assert record["filename"] == "TRAVERSAL_PROOF.pdf"
    assert record["blob_key"].startswith(f"pets/{pet_id}/records/") and "TRAVERSAL" not in record["blob_key"]


def test_c4_chat_prompt_contains_the_retrieved_note(client, store, fake_llm, make_pet):
    from petpulse.providers.llm import LegacyTask

    pet_id = make_pet("alice", "Max")
    store.add(
        f"pets/{pet_id}/voice-notes",
        {
            "transcript": "Max started limping on his left hind leg on Tuesday",
            "summary": "Limping",
            "timestamp": datetime.utcnow().isoformat(),
        },
    )
    response = client.post(f"/api/pets/{pet_id}/chat", json={"query": "When did Max start limping?"})
    assert response.status_code == 200

    final_calls = [c for c in fake_llm.calls if c["task"] == LegacyTask.CHAT_ASSISTANT]
    assert final_calls, "the chat route made no final assistant call"
    prompt = "\n".join(str(m.get("content")) for m in final_calls[-1]["messages"])
    assert "limping on his left hind leg" in prompt


def test_h2_outage_does_not_classify_emergency_as_daily_activity(client, fake_llm, make_pet, no_retry_sleep):
    pet_id = make_pet("alice", "Max")
    fake_llm.fail = True
    response = client.post(
        f"/api/pets/{pet_id}/textinput", json={"input": "Max collapsed and is vomiting blood, gums are pale"}
    )
    assert response.json().get("content_type") != "DAILY_ACTIVITY"


def test_h2_health_insights_never_invent_a_score(client, make_pet):
    pet_id = make_pet("alice", "Max")
    response = client.get(f"/api/pets/{pet_id}/health_insights")
    insights = response.json().get("insights") or {}
    assert insights.get("overall_health_score") is None


def test_m2_trend_reports_decreasing_activity():
    from visualization_service import PetVisualizationService

    now = datetime.utcnow()
    early = [{"timestamp": (now - timedelta(days=25, hours=i)).isoformat()} for i in range(6)]
    late = [{"timestamp": now.isoformat()}]
    assert PetVisualizationService()._calculate_trend(early + late, 30) == "decreasing"


def test_m3_missing_timestamp_does_not_break_summary(client_noraise, store, make_pet):
    pet_id = make_pet("alice", "Max")
    store.add(f"pets/{pet_id}/analytics", {"category": "diet"})
    response = client_noraise.get(f"/api/pets/{pet_id}/analytics/summary")
    assert response.status_code == 200


def test_m4_dynamic_chart_average_ignores_entries_without_the_metric():
    from visualization_service import PetVisualizationService

    ts = datetime.now().replace(microsecond=0).isoformat()
    data = [
        {"category": "energy_levels", "level": 4, "timestamp": ts},
        {"category": "diet", "timestamp": ts},
        {"category": "diet", "timestamp": ts},
    ]
    cfg = PetVisualizationService().generate_dynamic_chart(data, "line", "date", "level", None, "average", 30, None)
    assert cfg["data"]["datasets"][0]["data"] == [4.0]


@known_bug("CORS: any origin is reflected with credentials allowed", "auth/data track")
def test_cors_does_not_reflect_an_arbitrary_origin(client):
    response = client.options(
        "/api/user-pets/x", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"}
    )
    assert response.headers.get("access-control-allow-origin") not in ("https://evil.example", "*")
