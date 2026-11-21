from __future__ import annotations

from datetime import datetime, timezone

import pytest

from frontieratlas.common.timeutil import (
    TimestampError,
    freshness_decision,
    iso_utc,
    parse_timestamp,
    parse_and_check_fresh,
)

NOW = datetime(2026, 11, 21, 12, 0, 0, tzinfo=timezone.utc)


def test_parse_iso_with_z():
    parsed = parse_timestamp("2026-11-21T06:00:00Z")
    assert parsed == datetime(2026, 11, 21, 6, 0, tzinfo=timezone.utc)
    assert iso_utc(parsed) == "2026-11-21T06:00:00Z"


def test_parse_rfc2822():
    parsed = parse_timestamp("Fri, 21 Nov 2026 06:00:00 +0000")
    assert parsed.hour == 6
    assert parsed.tzinfo is not None


def test_parse_epoch_and_offset_conversion():
    assert parse_timestamp(1795244623).year == 2026
    parsed = parse_timestamp("2026-11-21T08:00:00+02:00")
    assert parsed.hour == 6
    assert parsed.utcoffset().total_seconds() == 0


def test_naive_timestamp_is_rejected():
    with pytest.raises(TimestampError):
        parse_timestamp("2026-11-21T06:00:00")


def test_missing_timestamp_is_rejected():
    with pytest.raises(TimestampError):
        parse_timestamp(None)


def test_freshness_accepts_recent_and_rejects_stale():
    fresh, reason, published = freshness_decision("2026-11-21T06:00:00Z", now=NOW, max_age_hours=24)
    assert fresh is True and reason == "fresh" and published is not None

    stale, reason, _ = freshness_decision("2026-11-19T06:00:00Z", now=NOW, max_age_hours=24)
    assert stale is False and "older_than_24h" in reason


def test_freshness_rejects_future_beyond_skew():
    future, reason, _ = freshness_decision("2026-11-21T12:30:00Z", now=NOW, clock_skew_minutes=5)
    assert future is False and reason == "future_publication_timestamp"


def test_freshness_allows_small_clock_skew():
    fresh, reason, _ = freshness_decision("2026-11-21T12:03:00Z", now=NOW, clock_skew_minutes=5)
    assert fresh is True and reason == "fresh"


def test_missing_date_is_not_treated_as_fresh():
    fresh, reason, iso = parse_and_check_fresh(None, now=NOW)
    assert fresh is False
    assert "missing" in reason
    assert iso is None
