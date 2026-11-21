"""Timezone-aware timestamp parsing and strict freshness verification.

Rules implemented here:
* All internal timestamps are UTC.
* A timestamp without a verifiable timezone is rejected (never guessed).
* Publication timestamps in the future beyond clock skew are rejected.
* Crawl time is never substituted for a publication time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any

UTC = timezone.utc


class TimestampError(ValueError):
    """Raised when a timestamp cannot be verified."""


def now_utc() -> datetime:
    return datetime.now(UTC)


def parse_timestamp(value: Any, *, require_timezone: bool = True) -> datetime:
    """Parse an ISO-8601, RFC-2822, or epoch timestamp into an aware UTC datetime.

    Raises TimestampError when the value is empty, malformed, or lacks timezone
    information and ``require_timezone`` is true.
    """

    if value is None:
        raise TimestampError("missing timestamp")
    if isinstance(value, bool):
        raise TimestampError("boolean is not a timestamp")

    dt: datetime
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        seconds = float(value)
        if seconds > 1e11:  # milliseconds
            seconds /= 1000.0
        try:
            dt = datetime.fromtimestamp(seconds, tz=UTC)
        except (OverflowError, OSError, ValueError) as exc:
            raise TimestampError(f"invalid epoch timestamp: {value!r}") from exc
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise TimestampError("empty timestamp")
        dt = _parse_string(text, require_timezone=require_timezone)
    else:
        raise TimestampError(f"unsupported timestamp type: {type(value).__name__}")

    if dt.tzinfo is None or dt.utcoffset() is None:
        if require_timezone:
            raise TimestampError("timezone missing; publication time cannot be verified")
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _parse_string(text: str, *, require_timezone: bool) -> datetime:
    # Epoch encoded as a string
    if text.isdigit() and len(text) >= 9:
        return parse_timestamp(int(text))

    iso_candidate = text[:-1] + "+00:00" if text.endswith(("Z", "z")) else text
    try:
        return datetime.fromisoformat(iso_candidate)
    except ValueError:
        pass

    try:
        return parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError) as exc:
        raise TimestampError(f"unparseable timestamp: {text!r}") from exc


def iso_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimestampError("cannot serialize a naive datetime")
    return value.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def to_iso(value: Any) -> str | None:
    try:
        return iso_utc(parse_timestamp(value))
    except TimestampError:
        return None


def freshness_decision(
    published_at: Any,
    *,
    now: datetime | None = None,
    max_age_hours: int = 24,
    clock_skew_minutes: int = 5,
) -> tuple[bool, str, datetime | None]:
    """Return ``(is_fresh, reason, published_utc)`` for a strict 24h window."""

    reference = (now or now_utc()).astimezone(UTC)
    try:
        published = parse_timestamp(published_at)
    except TimestampError as exc:
        return False, str(exc), None

    if published > reference + timedelta(minutes=clock_skew_minutes):
        return False, "future_publication_timestamp", published

    cutoff = reference - timedelta(hours=max_age_hours)
    if published < cutoff:
        return False, f"older_than_{max_age_hours}h", published

    return True, "fresh", published


def parse_and_check_fresh(
    value: Any,
    *,
    now: datetime | None = None,
    max_age_hours: int = 24,
    clock_skew_minutes: int = 5,
) -> tuple[bool, str, str | None]:
    """Convenience wrapper returning an ISO string instead of a datetime."""

    fresh, reason, published = freshness_decision(
        value, now=now, max_age_hours=max_age_hours, clock_skew_minutes=clock_skew_minutes
    )
    return fresh, reason, iso_utc(published) if published else None
