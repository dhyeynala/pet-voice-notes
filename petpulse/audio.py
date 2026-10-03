"""Audio container helpers for the voice upload path. Pure stdlib, no decoding.

- ``sniff`` identifies the container from its magic bytes (the upload's declared type is
  only a hint; browsers send ``audio/webm;codecs=opus``, ``audio/mp4``, ``video/webm`` ...).
- ``probe_duration`` reads the duration from container headers where that is possible
  (WAV header, Ogg granule position, MP4 ``mvhd``, WebM ``Duration`` or the last cluster
  timecode). It returns ``None`` when the container does not say; callers then rely on the
  byte-size cap alone.
- ``wav_info`` / ``is_near_silence`` parse PCM WAV and measure its level, so near-silent
  recordings are rejected before any provider call.
"""

from __future__ import annotations

import math
import struct
import sys
from array import array
from dataclasses import dataclass
from typing import Optional

WEBM = "audio/webm"
OGG = "audio/ogg"
MP4 = "audio/mp4"
WAV = "audio/wav"

SUPPORTED_MIMES: frozenset[str] = frozenset({WEBM, OGG, MP4, WAV})
EXTENSIONS: dict[str, str] = {WEBM: "webm", OGG: "ogg", MP4: "mp4", WAV: "wav"}

_ALIASES: dict[str, str] = {
    "video/webm": WEBM,
    "audio/opus": OGG,
    "application/ogg": OGG,
    "video/ogg": OGG,
    "audio/x-m4a": MP4,
    "audio/m4a": MP4,
    "audio/aac": MP4,
    "video/mp4": MP4,
    "audio/x-wav": WAV,
    "audio/wave": WAV,
    "audio/vnd.wave": WAV,
}
# Declared types that carry no information; the sniffed type decides.
GENERIC_MIMES: frozenset[str] = frozenset({"", "application/octet-stream", "binary/octet-stream"})

# Near-silence threshold for PCM: RMS below this many dBFS counts as "no speech".
SILENCE_DBFS = -50.0


def normalize_mime(mime: Optional[str]) -> str:
    """``'Audio/WebM; codecs=opus'`` -> ``'audio/webm'``; aliases mapped to the four canonical types."""
    base = (mime or "").split(";", 1)[0].strip().lower()
    return _ALIASES.get(base, base)


def sniff(data: bytes) -> Optional[str]:
    """Container type from magic bytes, or ``None`` if it is not one of the supported four."""
    if data.startswith(b"\x1a\x45\xdf\xa3"):
        return WEBM  # EBML header (WebM / Matroska)
    if data.startswith(b"OggS"):
        return OGG
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return WAV
    if len(data) >= 12 and data[4:8] == b"ftyp":
        return MP4
    return None


# ------------------------------------------------------------------------------------- WAV
@dataclass(frozen=True)
class WavInfo:
    audio_format: int  # 1 = PCM, 3 = float, 0xFFFE = extensible
    channels: int
    sample_rate: int
    bits_per_sample: int
    data_offset: int
    data_size: int

    @property
    def is_pcm16(self) -> bool:
        return self.audio_format in (1, 0xFFFE) and self.bits_per_sample == 16

    @property
    def seconds(self) -> float:
        block = max(1, self.channels * self.bits_per_sample // 8)
        return self.data_size / block / self.sample_rate if self.sample_rate else 0.0


def wav_info(data: bytes) -> Optional[WavInfo]:
    """Parse the RIFF chunks of a WAV file. ``None`` if it is not a readable WAV."""
    if sniff(data) != WAV:
        return None
    pos = 12
    fmt: Optional[tuple[int, int, int, int]] = None
    while pos + 8 <= len(data):
        chunk_id = data[pos : pos + 4]
        (size,) = struct.unpack_from("<I", data, pos + 4)
        body = pos + 8
        if chunk_id == b"fmt " and size >= 16 and body + 16 <= len(data):
            audio_format, channels, rate, _byte_rate, _align, bits = struct.unpack_from("<HHIIHH", data, body)
            fmt = (audio_format, channels, rate, bits)
        elif chunk_id == b"data" and fmt is not None:
            # Streaming writers put 0 or 0xFFFFFFFF here; use what is actually present.
            available = len(data) - body
            data_size = available if size in (0, 0xFFFFFFFF) else min(size, available)
            return WavInfo(fmt[0], fmt[1], fmt[2], fmt[3], body, data_size)
        pos = body + size + (size & 1)
    return None


def pcm16_rms_dbfs(info: WavInfo, data: bytes) -> float:
    """RMS level of 16-bit PCM in dBFS (``-inf`` for digital silence)."""
    raw = data[info.data_offset : info.data_offset + info.data_size]
    samples = array("h")
    samples.frombytes(raw[: len(raw) - (len(raw) % 2)])
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return float("-inf")
    mean_square = sum(s * s for s in samples) / len(samples)
    return 20 * math.log10(math.sqrt(mean_square) / 32768) if mean_square else float("-inf")


def is_near_silence(data: bytes, mime: str, threshold_dbfs: float = SILENCE_DBFS) -> bool:
    """True for PCM16 WAV whose RMS level is below ``threshold_dbfs`` (or that has no samples).

    Compressed formats (Opus, AAC) cannot be measured without decoding, so they return False.
    """
    if normalize_mime(mime) != WAV and sniff(data) != WAV:
        return False
    info = wav_info(data)
    if info is None or not info.is_pcm16:
        return False
    return info.data_size < 2 or pcm16_rms_dbfs(info, data) < threshold_dbfs


# ---------------------------------------------------------------------------------- Ogg
def _ogg_duration(data: bytes) -> Optional[float]:
    head = data.find(b"OpusHead", 0, 512)
    if head >= 0 and head + 12 <= len(data):
        (pre_skip,) = struct.unpack_from("<H", data, head + 10)
        rate, skip = 48000, pre_skip  # Opus granule positions always count 48 kHz samples
    else:
        vorbis = data.find(b"\x01vorbis", 0, 512)
        if vorbis < 0 or vorbis + 16 > len(data):
            return None
        (rate,) = struct.unpack_from("<I", data, vorbis + 12)
        skip = 0
    last = data.rfind(b"OggS")
    if last < 0 or last + 14 > len(data) or not rate:
        return None
    granule = int(struct.unpack_from("<q", data, last + 6)[0])
    if granule <= 0:
        return None
    return max(0.0, float(granule - skip) / float(rate))


def opus_input_rate(data: bytes) -> Optional[int]:
    """The ``input sample rate`` field of an Ogg ``OpusHead`` (informational, may be 0)."""
    head = data.find(b"OpusHead", 0, 512)
    if head < 0 or head + 16 > len(data):
        return None
    (rate,) = struct.unpack_from("<I", data, head + 12)
    return int(rate) or None


def is_ogg_opus(data: bytes) -> bool:
    return data.startswith(b"OggS") and data.find(b"OpusHead", 0, 512) >= 0


# ---------------------------------------------------------------------------------- MP4
def _mp4_duration(data: bytes) -> Optional[float]:
    pos = data.find(b"mvhd")
    if pos < 4 or pos + 32 > len(data):
        return None
    version = data[pos + 4]
    if version == 1:
        if pos + 40 > len(data):
            return None
        timescale, duration = struct.unpack_from(">IQ", data, pos + 4 + 4 + 16)
    else:
        timescale, duration = struct.unpack_from(">II", data, pos + 4 + 4 + 8)
    if not timescale or not duration or duration in (0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF):
        return None  # fragmented MP4 (Safari MediaRecorder) leaves this unset
    return float(duration) / float(timescale)


# --------------------------------------------------------------------------------- WebM
_EBML_SEGMENT = 0x18538067
_EBML_INFO = 0x1549A966
_EBML_TIMECODE_SCALE = 0x2AD7B1
_EBML_DURATION = 0x4489
_EBML_CLUSTER = 0x1F43B675
_EBML_CLUSTER_TIMECODE = 0xE7
_EBML_TRACKS = 0x1654AE6B
_EBML_SAMPLING_FREQUENCY = 0xB5


def _vint(data: bytes, pos: int, keep_marker: bool) -> Optional[tuple[int, int, bool]]:
    """Read an EBML variable-length integer. Returns (value, length, all_ones)."""
    if pos >= len(data):
        return None
    first = data[pos]
    length = 1
    mask = 0x80
    while length <= 8 and not first & mask:
        mask >>= 1
        length += 1
    if length > 8 or pos + length > len(data):
        return None
    value = first if keep_marker else first & (mask - 1)
    all_ones = (first & (mask - 1)) == mask - 1
    for byte in data[pos + 1 : pos + length]:
        value = (value << 8) | byte
        all_ones = all_ones and byte == 0xFF
    return value, length, all_ones


def _ebml_children(data: bytes, start: int, end: int) -> list[tuple[int, int, int]]:
    """(id, payload_start, payload_end) for the elements in ``data[start:end]``."""
    out = []
    pos = start
    while pos < end:
        ident = _vint(data, pos, keep_marker=True)
        if ident is None:
            break
        size = _vint(data, pos + ident[1], keep_marker=False)
        if size is None:
            break
        payload = pos + ident[1] + size[1]
        payload_end = end if size[2] else min(end, payload + size[0])  # unknown size -> to the end
        out.append((ident[0], payload, payload_end))
        if size[2]:
            break
        pos = payload_end
    return out


def _uint(data: bytes, start: int, end: int) -> int:
    return int.from_bytes(data[start:end], "big") if end > start else 0


def _float(data: bytes, start: int, end: int) -> Optional[float]:
    if end - start == 4:
        return float(struct.unpack(">f", data[start:end])[0])
    if end - start == 8:
        return float(struct.unpack(">d", data[start:end])[0])
    return None


def _webm_segment(data: bytes) -> Optional[tuple[int, int]]:
    for ident, start, end in _ebml_children(data, 0, len(data)):
        if ident == _EBML_SEGMENT:
            return start, end
    return None


def _webm_info(data: bytes, segment: tuple[int, int]) -> tuple[int, Optional[float]]:
    """(TimecodeScale in ns, declared Duration in ticks or None) from the Segment's Info."""
    scale = 1_000_000  # default: 1 ms per tick
    declared: Optional[float] = None
    for ident, start, end in _ebml_children(data, *segment):
        if ident != _EBML_INFO:
            continue
        for child, c_start, c_end in _ebml_children(data, start, end):
            if child == _EBML_TIMECODE_SCALE:
                scale = _uint(data, c_start, c_end) or scale
            elif child == _EBML_DURATION:
                declared = _float(data, c_start, c_end)
        break
    return scale, declared


def _webm_last_cluster_ticks(data: bytes) -> Optional[int]:
    last = data.rfind(_EBML_CLUSTER.to_bytes(4, "big"))
    if last < 0:
        return None
    clusters = _ebml_children(data, last, len(data))
    if not clusters or clusters[0][0] != _EBML_CLUSTER:
        return None
    _ident, c_start, c_end = clusters[0]
    for child, t_start, t_end in _ebml_children(data, c_start, c_end):
        if child == _EBML_CLUSTER_TIMECODE:
            return _uint(data, t_start, t_end)
    return None


def _webm_duration(data: bytes) -> Optional[float]:
    segment = _webm_segment(data)
    if segment is None:
        return None
    scale, declared = _webm_info(data, segment)
    if declared and declared > 0:
        return declared * scale / 1e9
    # Chrome's MediaRecorder writes no Duration: use the last cluster's timecode as a lower bound.
    ticks = _webm_last_cluster_ticks(data)
    return ticks * scale / 1e9 if ticks is not None else None


def webm_sample_rate(data: bytes) -> Optional[int]:
    """``SamplingFrequency`` of the first audio track, if the header carries it."""
    segment = _webm_segment(data)
    if segment is None:
        return None
    pos = data.find(_EBML_SAMPLING_FREQUENCY.to_bytes(1, "big") + b"\x88", segment[0])
    while pos >= 0:
        value = _float(data, pos + 2, pos + 10)
        if value and 7000 < value < 200000:
            return int(value)
        pos = data.find(b"\xb5\x88", pos + 1)
    pos = data.find(b"\xb5\x84", segment[0])
    if pos >= 0:
        value = _float(data, pos + 2, pos + 6)
        if value and 7000 < value < 200000:
            return int(value)
    return None


def probe_duration(data: bytes, mime: str) -> Optional[float]:
    """Duration in seconds from container headers, or ``None`` if the container does not say.

    For WebM without a ``Duration`` element this is a lower bound (last cluster start), which
    is what a maximum-length check needs.
    """
    kind = sniff(data) or normalize_mime(mime)
    try:
        if kind == WAV:
            info = wav_info(data)
            return info.seconds if info else None
        if kind == OGG:
            return _ogg_duration(data)
        if kind == MP4:
            return _mp4_duration(data)
        if kind == WEBM:
            return _webm_duration(data)
    except (struct.error, IndexError, ValueError, OverflowError):
        return None
    return None
