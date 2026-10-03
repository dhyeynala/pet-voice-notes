"""Container sniffing, duration probing and near-silence detection (petpulse.audio)."""

from __future__ import annotations

import struct

import pytest

from petpulse import audio
from petpulse.samples import audio_manifest
from tests.audio_fixtures import mp4, wav, webm


@pytest.mark.parametrize(
    "declared, expected",
    [
        ("audio/webm;codecs=opus", "audio/webm"),
        ("Video/WebM", "audio/webm"),
        ("audio/ogg; codecs=opus", "audio/ogg"),
        ("audio/x-m4a", "audio/mp4"),
        ("audio/x-wav", "audio/wav"),
        ("", ""),
        (None, ""),
        ("text/plain", "text/plain"),
    ],
)
def test_normalize_mime(declared, expected):
    assert audio.normalize_mime(declared) == expected


def test_sniff_identifies_the_four_containers_and_rejects_others():
    assert audio.sniff(webm([0])) == audio.WEBM
    assert audio.sniff(b"OggS" + b"\x00" * 40) == audio.OGG
    assert audio.sniff(wav(0.1)) == audio.WAV
    assert audio.sniff(mp4(1.0)) == audio.MP4
    assert audio.sniff(b"%PDF-1.7 ...") is None
    assert audio.sniff(b"ID3\x04" + b"\x00" * 20) is None  # mp3 is not accepted
    assert audio.sniff(b"") is None


def test_bundled_sample_durations_match_the_manifest():
    for sample in audio_manifest().samples:
        data = sample.read_bytes()
        assert audio.sniff(data) == sample.mime
        seconds = audio.probe_duration(data, sample.mime)
        assert seconds is not None and seconds == pytest.approx(sample.seconds, abs=0.05), sample.id


def test_webm_duration_element_and_cluster_fallback():
    assert audio.probe_duration(webm([0, 5000], duration_ms=7250.0), "") == pytest.approx(7.25)
    # Chrome's MediaRecorder writes no Duration: the last cluster start is a lower bound.
    assert audio.probe_duration(webm([0, 30000, 61000]), "") == pytest.approx(61.0)
    assert audio.webm_sample_rate(webm([0], rate=16000.0)) == 16000
    assert audio.probe_duration(b"\x1a\x45\xdf\xa3\x81", "") is None  # truncated


def test_mp4_duration_from_mvhd_v0_and_v1_and_fragmented_is_unknown():
    assert audio.probe_duration(mp4(12.5), "") == pytest.approx(12.5)
    assert audio.probe_duration(mp4(90.0, timescale=44100, version=1), "") == pytest.approx(90.0)
    assert audio.probe_duration(mp4(0.0), "") is None  # Safari fragmented MP4 leaves it unset


def test_ogg_opus_and_vorbis_duration():
    sample = audio_manifest().get("heartworm_pill")
    assert sample is not None
    data = sample.read_bytes()
    assert audio.is_ogg_opus(data) and audio.opus_input_rate(data) == 48000
    vorbis_id = b"\x01vorbis" + struct.pack("<IBI", 0, 1, 44100) + b"\x00" * 16
    first = b"OggS" + b"\x00\x02" + struct.pack("<q", 0) + b"\x00" * 12 + vorbis_id
    last = b"OggS" + b"\x00\x04" + struct.pack("<q", 44100 * 3) + b"\x00" * 12
    assert audio.probe_duration(first + last, "audio/ogg") == pytest.approx(3.0)
    assert not audio.is_ogg_opus(first + last)


def test_wav_info_and_duration():
    info = audio.wav_info(wav(2.0, rate=8000, channels=2))
    assert info is not None and info.is_pcm16 and info.channels == 2 and info.sample_rate == 8000
    assert info.seconds == pytest.approx(2.0)
    assert audio.wav_info(b"RIFF\x00\x00\x00\x00WAVE") is None
    # Streaming writers leave the data size at 0: use what is present.
    streamed = bytearray(wav(1.0))
    streamed[40:44] = b"\x00\x00\x00\x00"
    assert audio.probe_duration(bytes(streamed), "audio/wav") == pytest.approx(1.0)


def test_near_silence_only_for_quiet_pcm():
    assert audio.is_near_silence(wav(1.0, amplitude=0), "audio/wav")
    assert audio.is_near_silence(wav(1.0, amplitude=10), "audio/wav")
    assert not audio.is_near_silence(wav(1.0, amplitude=8000), "audio/wav")
    assert not audio.is_near_silence(wav(1.0, bits=8), "audio/wav")  # cannot measure: not rejected
    assert not audio.is_near_silence(webm([0]), "audio/webm")  # compressed: cannot measure
    silence = audio_manifest().get("silence")
    assert silence is not None and audio.is_near_silence(silence.read_bytes(), "audio/wav")


def test_probe_never_raises_on_garbage():
    for blob in (b"", b"OggS", b"RIFF1234WAVEfmt ", b"\x00\x00\x00\x08ftypmvhd", b"\x1a\x45\xdf\xa3" + b"\xff" * 30):
        audio.probe_duration(blob, "")
