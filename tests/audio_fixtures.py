"""Tiny synthetic audio containers for tests (no codecs needed)."""

from __future__ import annotations

import math
import struct


def wav(seconds: float = 1.0, rate: int = 16000, amplitude: int = 8000, channels: int = 1, bits: int = 16) -> bytes:
    """A PCM WAV with a 440 Hz tone (``amplitude=0`` gives digital silence)."""
    frames = int(seconds * rate)
    if bits == 16:
        body = struct.pack(
            f"<{frames * channels}h",
            *(int(amplitude * math.sin(2 * math.pi * 440 * (i // channels) / rate)) for i in range(frames * channels)),
        )
    else:
        body = bytes(128 for _ in range(frames * channels))
    block = channels * bits // 8
    header = b"RIFF" + struct.pack("<I", 36 + len(body)) + b"WAVE"
    header += b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, rate, rate * block, block, bits)
    return header + b"data" + struct.pack("<I", len(body)) + body


def ebml(ident: int, payload: bytes) -> bytes:
    raw_id = ident.to_bytes((ident.bit_length() + 7) // 8, "big")
    size = len(payload)
    encoded = bytes([0x80 | size]) if size < 0x7F else (0x10000000 | size).to_bytes(4, "big")
    return raw_id + encoded + payload


def webm(cluster_timecodes_ms: list[int], duration_ms: float | None = None, rate: float = 48000.0) -> bytes:
    """A minimal WebM: EBML header, Segment{Info, Tracks{SamplingFrequency}, Clusters}."""
    header = ebml(0x1A45DFA3, ebml(0x4282, b"webm"))
    info_children = ebml(0x2AD7B1, (1_000_000).to_bytes(3, "big"))
    if duration_ms is not None:
        info_children += ebml(0x4489, struct.pack(">d", duration_ms))
    info = ebml(0x1549A966, info_children)
    tracks = ebml(0x1654AE6B, ebml(0xAE, ebml(0xE1, ebml(0xB5, struct.pack(">d", rate)))))
    clusters = b"".join(
        ebml(0x1F43B675, ebml(0xE7, t.to_bytes(4, "big")) + ebml(0xA3, b"\x81\x00\x00\x80" + b"\x00" * 40))
        for t in cluster_timecodes_ms
    )
    return header + ebml(0x18538067, info + tracks + clusters)


def mp4(seconds: float, timescale: int = 1000, version: int = 0) -> bytes:
    ftyp = struct.pack(">I", 20) + b"ftypM4A " + b"\x00\x00\x00\x00" + b"M4A "
    if version == 0:
        body = b"\x00\x00\x00\x00" + struct.pack(">IIII", 0, 0, timescale, int(seconds * timescale))
    else:
        body = b"\x01\x00\x00\x00" + struct.pack(">QQIQ", 0, 0, timescale, int(seconds * timescale))
    mvhd = struct.pack(">I", 8 + len(body) + 80) + b"mvhd" + body + b"\x00" * 80
    moov = struct.pack(">I", 8 + len(mvhd)) + b"moov" + mvhd
    return ftyp + moov + b"\x00" * 4096
