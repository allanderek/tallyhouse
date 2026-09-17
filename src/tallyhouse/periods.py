"""Period arithmetic.

A period is the ISO date of the Monday on which collection began, e.g.
"2026-09-14". ISO week notation is deliberately avoided: the ISO week-year
diverges from the calendar year at year boundaries and some years have 53
weeks, which is a reliable source of off-by-one bugs.

All datetime inputs must be timezone-aware (UTC or otherwise); naive datetimes
are rejected to prevent silent time-of-day misinterpretation.
"""

import re
from datetime import date, datetime, timedelta, timezone

COLLECTION_WINDOW_HOURS = 72


class InvalidPeriod(ValueError):
    """Raised when a period string is malformed or is not a Monday."""


def period_for(dt: datetime) -> str:
    """The period containing the given instant.

    The input datetime must be timezone-aware. Naive datetimes are rejected
    to prevent silent misinterpretation of local vs. UTC time.
    """
    if dt.tzinfo is None:
        raise InvalidPeriod("datetime must be timezone-aware")
    # Normalize to UTC before computing the date
    utc_dt = dt.astimezone(timezone.utc)
    monday = utc_dt.date() - timedelta(days=utc_dt.weekday())
    return monday.isoformat()


def parse_period(period: str) -> date:
    # Validate format explicitly: YYYY-MM-DD only. Rejects ISO week notation
    # (2026-W38) and other formats that fromisoformat might accept in newer
    # Python versions.
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", period):
        raise InvalidPeriod(f"{period!r} is not an ISO date (YYYY-MM-DD format)")
    try:
        parsed = date.fromisoformat(period)
    except ValueError as exc:
        raise InvalidPeriod(f"{period!r} is not an ISO date") from exc
    if parsed.weekday() != 0:
        raise InvalidPeriod(f"{period!r} is not a Monday")
    return parsed


def previous_period(period: str) -> str:
    return (parse_period(period) - timedelta(days=7)).isoformat()


def next_period(period: str) -> str:
    return (parse_period(period) + timedelta(days=7)).isoformat()


def window_start(period: str) -> datetime:
    """The instant the collection window opens: the period's Monday, 00:00 UTC."""
    return datetime.combine(
        parse_period(period), datetime.min.time(), tzinfo=timezone.utc
    )


def is_within_window(period: str, when: datetime) -> bool:
    """Whether an instant falls inside the period's collection window.

    The window exists so that a print labelled with a given week contains
    observations gathered during that week. Collecting outside it does not fail
    loudly on its own — it quietly mislabels evidence, which is worse.
    """
    if when.tzinfo is None:
        raise InvalidPeriod("window checks require a timezone-aware datetime")
    return window_start(period) <= when.astimezone(timezone.utc) < window_end(period)


def window_end(period: str) -> datetime:
    """The instant the collection window closes, including all retries."""
    start = datetime.combine(
        parse_period(period), datetime.min.time(), tzinfo=timezone.utc
    )
    return start + timedelta(hours=COLLECTION_WINDOW_HOURS)
