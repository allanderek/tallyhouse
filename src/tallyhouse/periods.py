"""Period arithmetic.

A period is the ISO date of the Monday on which collection began, e.g.
"2026-09-14". ISO week notation is deliberately avoided: the ISO week-year
diverges from the calendar year at year boundaries and some years have 53
weeks, which is a reliable source of off-by-one bugs.
"""

from datetime import date, datetime, timedelta, timezone

COLLECTION_WINDOW_HOURS = 72


class InvalidPeriod(ValueError):
    """Raised when a period string is malformed or is not a Monday."""


def period_for(dt: datetime) -> str:
    """The period containing the given instant."""
    monday = dt.date() - timedelta(days=dt.weekday())
    return monday.isoformat()


def parse_period(period: str) -> date:
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


def window_end(period: str) -> datetime:
    """The instant the collection window closes, including all retries."""
    start = datetime.combine(
        parse_period(period), datetime.min.time(), tzinfo=timezone.utc
    )
    return start + timedelta(hours=COLLECTION_WINDOW_HOURS)
