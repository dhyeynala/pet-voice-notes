"""Chat dates (live-test regression): the dates the model is given as evidence, the citation
dates the API returns, and the dates the UI shows for those cited notes are one calendar day,
computed in the request's tz.

Live, the user (America/New_York, ~4:35 PM ET) saw chat Sources one day early: the backend
was right (evidence and citations use the note's local date in ``tz``), but the UI parsed the
date-only citation ``"2026-10-03"`` with ``new Date()`` (UTC midnight) and showed Oct 2. The
notes here are recorded in the ET evening, when the UTC date is already the next day, so a
UTC slip on either side would show.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

ROOT = Path(__file__).resolve().parents[2]
TZ = "America/New_York"
EVIDENCE = re.compile(r"^\[(N\d+)\] (\d{4}-\d{2}-\d{2}) \((\w+)\): (.*)$", re.M)


def _at(days_ago: int, hh: int, mm: int) -> datetime:
    local_day = datetime.now(ZoneInfo(TZ)).date() - timedelta(days=days_ago)
    return datetime.combine(local_day, time(hh, mm), tzinfo=ZoneInfo(TZ))


def _note(store, pet_id: str, text: str, when: datetime) -> str:
    return str(
        store.add(
            f"pets/{pet_id}/notes",
            {
                "pet_id": pet_id,
                "uid": "alice",
                "tz": TZ,
                "source": "voice",
                "text": text,
                "summary": text,
                "kind": "MEDICAL",
                "urgent": True,
                "needs_review": False,
                "red_flags": [],
                "observations": [],
                "status": "processed",
                "created_at": when.astimezone(ZoneInfo("UTC")).isoformat(),
                "mode": "demo",
            },
        )
    )


def _ui_dates(values: list[str]) -> list[str]:
    """public/js/dom.js formatDate(value, en-US) in a browser set to America/New_York."""
    script = (
        "import(process.argv[1]).then((m) => console.log(JSON.stringify("
        "JSON.parse(process.argv[2]).map((v) => m.formatDate(v, { locale: 'en-US' })))))"
    )
    out = subprocess.run(
        ["node", "-e", script, (ROOT / "public" / "js" / "dom.js").as_uri(), json.dumps(values)],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
        env={"TZ": TZ, "PATH": "/usr/bin:/bin:/usr/local/bin"},
    )
    return list(json.loads(out.stdout))


@pytest.fixture
def evening_notes(store, make_pet):
    pet_id = make_pet("alice", name="Max")
    recorded = {
        # 9:30 PM ET yesterday = 01:30 UTC today; 4:32 PM ET two days ago (both always in the past).
        _note(store, pet_id, "Max vomited twice and there was some blood.", _at(1, 21, 30)): _at(1, 21, 30),
        _note(store, pet_id, "Max vomited again after his walk.", _at(2, 16, 32)): _at(2, 16, 32),
    }
    return pet_id, recorded


def test_evidence_citation_and_ui_dates_are_the_same_local_day(client, fake_llm, store, evening_notes):
    pet_id, recorded = evening_notes
    response = client.post(f"/api/pets/{pet_id}/chat", json={"message": "When did Max vomit?", "tz": TZ})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "answered", body

    (call,) = [c for c in fake_llm.calls if c["task"].startswith("chat_answer")]
    evidence = {text: day for _label, day, _source, text in EVIDENCE.findall(call["user"])}
    assert len(evidence) == 2, call["user"]
    expected = {store.get(f"pets/{pet_id}/notes/{nid}")["text"]: when.date().isoformat() for nid, when in recorded.items()}
    assert evidence == expected  # the model sees each note's ET date, not its UTC date

    cited = {c["id"]: c["date"] for c in body["citations"]}
    assert cited and set(cited) <= set(recorded)
    for note_id, day in cited.items():
        assert day == recorded[note_id].date().isoformat()
        assert day == evidence[store.get(f"pets/{pet_id}/notes/{note_id}")["text"]]
    # Dates the model writes in its answer come from that same evidence.
    assert set(re.findall(r"\d{4}-\d{2}-\d{2}", body["answer"])) <= set(evidence.values())

    if shutil.which("node") is None:
        pytest.skip("node is not installed (the UI half runs in tests/js too)")
    ids = list(cited)
    created = [store.get(f"pets/{pet_id}/notes/{nid}")["created_at"] for nid in ids]
    sources = _ui_dates([cited[nid] for nid in ids])  # chat "Sources"
    notes_list = _ui_dates(created)  # the notes list (from created_at)
    shown = [f"{recorded[nid]:%b} {recorded[nid].day}, {recorded[nid].year}" for nid in ids]
    assert sources == shown and notes_list == shown
