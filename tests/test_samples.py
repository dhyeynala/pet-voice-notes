"""The bundled samples match their manifest and stay small."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from petpulse.seed.samples import AUDIO_DIR, MANIFEST_PATH, SMOKE_AUDIO_ID, SMOKE_PDF_PATH, audio_manifest

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_matches_files():
    manifest = audio_manifest()
    ids = [s.id for s in manifest.samples]
    assert len(ids) == len(set(ids))
    for sample in manifest.samples:
        data = sample.read_bytes()
        assert hashlib.sha256(data).hexdigest() == sample.sha256, sample.id
        assert len(data) == json.loads(MANIFEST_PATH.read_text())["samples"][ids.index(sample.id)]["bytes"]
        assert len(data) < 64 * 1024, f"{sample.id} is too big for the repo"
        assert sample.label
        assert (sample.status == "ok") == bool(sample.transcript)
    on_disk = {p.name for p in AUDIO_DIR.iterdir() if p.name != "manifest.json"}
    assert on_disk == {s.file for s in manifest.samples}


def test_listed_samples_cover_routine_urgent_and_silence():
    listed = {s.id: s for s in audio_manifest().listed()}
    assert 3 <= len(listed) <= 4
    assert SMOKE_AUDIO_ID not in listed
    assert "blood" in listed["vomiting_blood"].transcript and "Urgent" in listed["vomiting_blood"].label
    assert listed["silence"].status == "no_speech"


def test_smoke_clip_is_about_five_seconds_and_mentions_the_red_flag():
    smoke = audio_manifest().get(SMOKE_AUDIO_ID)
    assert smoke is not None and smoke.mime == "audio/webm"
    assert smoke.seconds is not None and 4.0 <= smoke.seconds <= 6.5
    assert len(smoke.read_bytes()) < 100 * 1024
    words = smoke.transcript.lower()
    assert sum(w in words for w in ("vomit", "blood", "twice")) >= 2


def test_smoke_pdf_is_one_page_with_the_key_facts():
    import pymupdf

    with pymupdf.open(SMOKE_PDF_PATH) as doc:
        assert doc.page_count == 1
        text = doc[0].get_text()
    assert "Apoquel 16 mg" in text and "recheck in 2 weeks" in text
    assert SMOKE_PDF_PATH.stat().st_size < 20 * 1024


def test_make_samples_check_mode_agrees_with_committed_manifest():
    result = subprocess.run(
        [sys.executable, "scripts/make_samples.py", "--check"], cwd=ROOT, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stdout + result.stderr
