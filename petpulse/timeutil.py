"""Time handling: store tz-aware UTC, bucket and label days in the caller's IANA zone (review M5).

Legacy rows were written with ``datetime.utcnow().isoformat()`` (naive, no offset). Those are
read as UTC, which is what they were. Anything that does not parse is reported as ``None`` so
callers can skip and count it instead of failing the whole request (review M3).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
DEFAULT_TZ = "UTC"


class InvalidTimezone(ValueError):
    """The client sent a timezone name that is not a valid IANA zone."""


def utc_now() -> datetime:
    return datetime.now(UTC)


def to_iso(moment: datetime) -> str:
    """Serialise as ISO 8601 UTC with an explicit ``Z`` (browsers parse it unambiguously)."""
    if moment.tzinfo is None:
        raise ValueError("refusing to serialise a naive datetime")
    return moment.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_timestamp(value: Any) -> Optional[datetime]:
    """Parse a stored timestamp into an aware UTC datetime, or ``None`` if it is unusable."""
    if isinstance(value, datetime):
        moment = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith(("Z", "z")):
            text = text[:-1] + "+00:00"
        try:
            moment = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)  # legacy utcnow() rows
    return moment.astimezone(UTC)


def get_zone(tz: Optional[str]) -> ZoneInfo:
    name = (tz or DEFAULT_TZ).strip() or DEFAULT_TZ
    if len(name) > 64 or ".." in name or name.startswith("/"):
        raise InvalidTimezone(f"invalid timezone {name!r}")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidTimezone(f"invalid timezone {name!r}") from exc


def validate_tz(tz: Optional[str]) -> str:
    """Return the canonical zone name or raise ``InvalidTimezone``."""
    return str(get_zone(tz).key)


def local_date(moment: datetime, tz: str) -> date:
    """The calendar day ``moment`` falls on for someone living in ``tz``."""
    return moment.astimezone(get_zone(tz)).date()
