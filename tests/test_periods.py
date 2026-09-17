from datetime import datetime, date, timezone, timedelta

import pytest

from tallyhouse.periods import (
    InvalidPeriod,
    next_period,
    parse_period,
    period_for,
    previous_period,
    window_end,
)


def test_period_for_returns_monday_of_that_week():
    # 2026-09-16 is a Wednesday; its Monday is 2026-09-14.
    assert period_for(datetime(2026, 9, 16, 13, 0, tzinfo=timezone.utc)) == "2026-09-14"


def test_period_for_on_a_monday_returns_that_monday():
    assert period_for(datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)) == "2026-09-14"


def test_period_for_on_a_sunday_returns_the_preceding_monday():
    assert period_for(datetime(2026, 9, 20, 23, 59, tzinfo=timezone.utc)) == "2026-09-14"


def test_periods_step_by_seven_days():
    assert previous_period("2026-09-14") == "2026-09-07"
    assert next_period("2026-09-14") == "2026-09-21"


def test_periods_cross_year_boundaries_without_iso_week_confusion():
    # The trap ISO week notation would create: this Monday sits in calendar 2026
    # but ISO week-year 2027. A Monday date has no such ambiguity.
    assert next_period("2026-12-28") == "2027-01-04"
    assert previous_period("2027-01-04") == "2026-12-28"


def test_parse_period_returns_a_date():
    assert parse_period("2026-09-14") == date(2026, 9, 14)


def test_non_monday_period_is_rejected():
    with pytest.raises(InvalidPeriod):
        parse_period("2026-09-16")


def test_malformed_period_is_rejected():
    with pytest.raises(InvalidPeriod):
        parse_period("2026-W38")


def test_window_closes_72_hours_after_monday_midnight_utc():
    assert window_end("2026-09-14") == datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc)


def test_period_for_non_utc_aware_datetime_normalizes_to_utc():
    # 2026-09-20 22:00-05:00 is 2026-09-21 03:00 UTC (a Monday)
    dt = datetime(2026, 9, 20, 22, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert period_for(dt) == "2026-09-21"


def test_period_for_rejects_naive_datetime():
    with pytest.raises(InvalidPeriod):
        period_for(datetime(2026, 9, 16, 13, 0))


def test_parse_period_rejects_iso_week_notation():
    with pytest.raises(InvalidPeriod):
        parse_period("2026-W38")


def test_parse_period_rejects_non_hyphenated_iso_format():
    with pytest.raises(InvalidPeriod):
        parse_period("20260914")


def test_window_opens_at_the_periods_monday_midnight_utc():
    from tallyhouse.periods import window_start
    assert window_start("2026-09-14") == datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc)


def test_an_instant_inside_the_window_is_within():
    from tallyhouse.periods import is_within_window
    assert is_within_window("2026-09-14", datetime(2026, 9, 16, 23, 59, tzinfo=timezone.utc))


def test_the_window_opens_inclusively_and_closes_exclusively():
    from tallyhouse.periods import is_within_window
    assert is_within_window("2026-09-14", datetime(2026, 9, 14, 0, 0, tzinfo=timezone.utc))
    # 72 hours exactly is the close, and is outside.
    assert not is_within_window("2026-09-14", datetime(2026, 9, 17, 0, 0, tzinfo=timezone.utc))


def test_collecting_before_the_period_opens_is_outside():
    from tallyhouse.periods import is_within_window
    assert not is_within_window("2026-09-14", datetime(2026, 9, 13, 23, 59, tzinfo=timezone.utc))


def test_window_check_normalises_other_timezones():
    from tallyhouse.periods import is_within_window
    # 2026-09-16T20:00-05:00 is 2026-09-17T01:00Z — past the close.
    late = datetime(2026, 9, 16, 20, 0, tzinfo=timezone(timedelta(hours=-5)))
    assert not is_within_window("2026-09-14", late)


def test_window_check_rejects_a_naive_datetime():
    from tallyhouse.periods import is_within_window
    with pytest.raises(InvalidPeriod):
        is_within_window("2026-09-14", datetime(2026, 9, 15, 12, 0))
