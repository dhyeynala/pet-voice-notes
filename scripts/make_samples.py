#!/usr/bin/env python3
"""Regenerate the bundled demo samples (offline, no network, no keys).

    python scripts/make_samples.py            # rewrite audio clips, manifest and the smoke PDF
    python scripts/make_samples.py --check    # verify the committed manifest matches the files

Audio is synthetic TTS from ``espeak-ng`` encoded with ``ffmpeg`` (Opus in WebM/Ogg, PCM WAV).
Both tools are only needed to *regenerate* clips; the app and the tests only read the
committed files. The PDF is drawn with PyMuPDF (a base dependency).
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import struct
import subprocess  # nosec B404 - fixed argv, local tools only
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIO_DIR = ROOT / "petpulse" / "seed" / "samples" / "audio"
PDF_DIR = ROOT / "petpulse" / "seed" / "samples" / "pdfs"
MANIFEST = AUDIO_DIR / "manifest.json"

# id, label, file, transcript, espeak words-per-minute, listed in /api/voice/samples
SPEECH = [
    (
        "walk_and_dinner",
        "Routine: walk and dinner",
        "walk_and_dinner.webm",
        "Max had his usual thirty minute walk and finished all of his dinner.",
        160,
        True,
    ),
    (
        "vomiting_blood",
        "Urgent: vomiting with blood",
        "vomiting_blood.webm",
        "Max vomited twice this morning and there was some blood.",
        160,
        True,
    ),
    (
        "heartworm_pill",
        "Medication: heartworm pill",
        "heartworm_pill.ogg",
        "Gave Max his heartworm pill with breakfast this morning.",
        160,
        True,
    ),
    # ~5 s clip for the live smoke test (scripts/smoke_live.py); hidden from the sample picker.
    (
        "smoke_note",
        "Smoke test: vomiting with blood (5 s)",
        "smoke_note.webm",
        "Max vomited twice this morning and there was some blood.",
        115,
        False,
    ),
]
SILENCE = ("silence", "Silence (no speech)", "silence.wav")

CONFIDENCE = 0.97  # what FakeSTT reports for a bundled clip


def _run(argv: list[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True)  # nosec B603 - fixed argv


def _encode(text: str, wpm: int, out: Path) -> None:
    espeak = shutil.which("espeak-ng") or shutil.which("espeak")
    ffmpeg = shutil.which("ffmpeg")
    if not espeak or not ffmpeg:
        sys.exit("espeak-ng and ffmpeg are required to regenerate the audio samples")
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "tts.wav"
        _run([espeak, "-v", "en-us", "-s", str(wpm), "-w", str(raw), text])
        codec = {
            ".webm": ["-c:a", "libopus", "-b:a", "24k", "-application", "voip"],
            ".ogg": ["-c:a", "libopus", "-b:a", "24k", "-application", "voip"],
        }[out.suffix]
        _run(
            [ffmpeg, "-y", "-loglevel", "error", "-i", str(raw), "-ac", "1", "-ar", "48000", *codec]
            + ["-map_metadata", "-1", "-fflags", "+bitexact", "-flags:a", "+bitexact", str(out)]
        )


def _silence_wav(out: Path, seconds: float = 1.5, rate: int = 16000) -> None:
    """Near-silence: deterministic low-level noise (about -71 dBFS RMS), 16-bit mono PCM."""
    rng = random.Random(1234)  # nosec B311 - deterministic test data, not crypto
    frames = int(seconds * rate)
    samples = struct.pack(f"<{frames}h", *(rng.randint(-16, 16) for _ in range(frames)))
    header = b"RIFF" + struct.pack("<I", 36 + len(samples)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
    header += b"data" + struct.pack("<I", len(samples))
    out.write_bytes(header + samples)


def _smoke_pdf(out: Path) -> None:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        "Riverside Animal Clinic - Visit summary (SYNTHETIC SAMPLE)",
        "",
        "Patient: Max (dog, Labrador, 6 years)",
        "Date of visit: 2026-09-28",
        "",
        "Reason for visit: itchy skin and ears, scratching at night.",
        "Exam: mild redness on both ears, no infection seen.",
        "Diagnosis: seasonal allergic dermatitis.",
        "",
        "Medication: Apoquel 16 mg, one tablet by mouth once daily with food.",
        "Follow-up: recheck in 2 weeks.",
    ]
    y = 72.0
    for line in lines:
        page.insert_text((72, y), line, fontsize=11)
        y += 18
    doc.set_metadata({"title": "Smoke test record (synthetic)", "creationDate": "", "modDate": "", "producer": ""})
    out.write_bytes(doc.tobytes(garbage=4, deflate=True, no_new_id=True))


def _duration(path: Path) -> float:
    sys.path.insert(0, str(ROOT))
    from petpulse.services.audio import probe_duration, sniff

    data = path.read_bytes()
    seconds = probe_duration(data, sniff(data) or "")
    return round(seconds or 0.0, 2)


def build_manifest() -> dict[str, object]:
    samples = []
    for sample_id, label, file, transcript, _wpm, listed in SPEECH:
        data = (AUDIO_DIR / file).read_bytes()
        samples.append(
            {
                "id": sample_id,
                "label": label,
                "file": file,
                "mime": {"webm": "audio/webm", "ogg": "audio/ogg"}[file.rsplit(".", 1)[1]],
                "bytes": len(data),
                "seconds": _duration(AUDIO_DIR / file),
                "status": "ok",
                "transcript": transcript,
                "confidence": CONFIDENCE,
                "listed": listed,
            }
        )
    sample_id, label, file = SILENCE
    data = (AUDIO_DIR / file).read_bytes()
    samples.append(
        {
            "id": sample_id,
            "label": label,
            "file": file,
            "mime": "audio/wav",
            "bytes": len(data),
            "seconds": _duration(AUDIO_DIR / file),
            "status": "no_speech",
            "transcript": "",
            "confidence": None,
            "listed": True,
        }
    )
    # Listed samples first (picker order), the smoke clip last.
    samples.sort(key=lambda s: not s["listed"])
    return {
        "version": 1,
        "note": "Synthetic TTS clips (espeak-ng + ffmpeg). Regenerate with scripts/make_samples.py.",
        "samples": samples,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="verify the manifest matches the committed files")
    args = parser.parse_args()
    if args.check:
        expected = build_manifest()
        actual = json.loads(MANIFEST.read_text())
        if expected != actual:
            print("manifest.json is stale; run scripts/make_samples.py")
            return 1
        print("manifest.json is up to date")
        return 0
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    for _id, _label, file, transcript, wpm, _listed in SPEECH:
        _encode(transcript, wpm, AUDIO_DIR / file)
    _silence_wav(AUDIO_DIR / SILENCE[2])
    _smoke_pdf(PDF_DIR / "smoke_record.pdf")
    MANIFEST.write_text(json.dumps(build_manifest(), indent=2) + "\n")
    for path in sorted(AUDIO_DIR.iterdir()) + [PDF_DIR / "smoke_record.pdf"]:
        print(f"{path.relative_to(ROOT)}  {path.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
