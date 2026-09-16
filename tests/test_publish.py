from tallyhouse.ledger import LedgerConflict, read_rows
from tallyhouse.publish import (
    PROVISIONAL_COVERAGE_THRESHOLD,
    build_print,
    record_print,
)
import pytest

META = {
    "methodology_version": "1",
    "collector_version": "test",
    "computed_at": "2026-09-17T00:00:00Z",
}


def tables(observations, verdicts, blanket):
    return {"observations": observations, "verdicts": verdicts, "blanket": blanket}


def simple(n_blocking=1, n_total=2, outcome="Fetched"):
    obs = [{"domain": f"d{i}.com", "outcome": outcome} for i in range(n_total)]
    verdicts = [
        {"domain": f"d{i}.com", "agent": "GPTBot",
         "stance": "FullBlock" if i < n_blocking else "Unmentioned"}
        for i in range(n_total)
    ]
    blanket = {f"d{i}.com": "Allowed" for i in range(n_total)}
    return tables(obs, verdicts, blanket)


def test_headline_is_the_targeted_rate():
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    assert built["headline"]["value"] == 50.0


def test_series_include_effective_blanket_coverage_and_per_agent():
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    assert "effective" in built["series"]
    assert "blanket" in built["series"]
    assert "coverage" in built["series"]
    assert "agent:GPTBot" in built["series"]


def test_print_is_provisional_below_the_coverage_threshold():
    # 2 of 100 panel domains observed.
    built = build_print(simple(1, 2), None, panel_size=100, **META)
    assert built["provisional"] is True


def test_print_is_not_provisional_at_full_coverage():
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    assert built["provisional"] is False
    assert PROVISIONAL_COVERAGE_THRESHOLD <= 100.0


def test_week_on_week_series_is_absent_without_a_previous_period():
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    assert "change_wow" not in built["series"]


def test_week_on_week_series_appears_with_a_previous_period():
    built = build_print(simple(2, 2), simple(1, 2), panel_size=2, **META)
    assert built["series"]["change_wow"]["value"] == 50.0


def test_record_print_writes_both_ledgers(tmp_path):
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built)
    prints = read_rows(tmp_path / "prints.csv")
    series = read_rows(tmp_path / "series.csv")
    assert prints[0]["value"] == "50.0"
    assert prints[0]["vintage"] == "1"
    assert {r["series_id"] for r in series} >= {"effective", "blanket", "coverage"}


def test_recording_the_same_print_twice_is_a_no_op(tmp_path):
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built)
    record_print(tmp_path, "2026-09-14", built)
    assert len(read_rows(tmp_path / "prints.csv")) == 1


def test_provisional_flag_true_in_prints_csv(tmp_path):
    # Low coverage: provisional should be "true"
    low_coverage_built = build_print(simple(1, 2), None, panel_size=100, **META)
    record_print(tmp_path, "2026-09-14", low_coverage_built)
    prints = read_rows(tmp_path / "prints.csv")
    assert prints[0]["provisional"] == "true"


def test_provisional_flag_false_in_prints_csv(tmp_path):
    # Full coverage: provisional should be "false"
    full_coverage_built = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", full_coverage_built)
    prints = read_rows(tmp_path / "prints.csv")
    assert prints[0]["provisional"] == "false"


def test_provisional_flag_true_in_series_csv(tmp_path):
    # Low coverage: provisional should be "true" in all series rows
    low_coverage_built = build_print(simple(1, 2), None, panel_size=100, **META)
    record_print(tmp_path, "2026-09-14", low_coverage_built)
    series = read_rows(tmp_path / "series.csv")
    assert all(r["provisional"] == "true" for r in series)


def test_provisional_flag_false_in_series_csv(tmp_path):
    # Full coverage: provisional should be "false"
    full_coverage_built = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", full_coverage_built)
    series = read_rows(tmp_path / "series.csv")
    assert all(r["provisional"] == "false" for r in series)


def test_rerecording_the_same_print_leaves_one_row_per_series_id(tmp_path):
    built = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built)
    record_print(tmp_path, "2026-09-14", built)
    series = read_rows(tmp_path / "series.csv")
    series_ids = [r["series_id"] for r in series]
    # Each series_id should appear exactly once
    assert len(series_ids) == len(set(series_ids))
    assert len(series) == len(built["series"])


def test_changed_headline_value_with_no_reason_raises_and_writes_nothing(tmp_path):
    # Record initial print
    built1 = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built1)

    # Get file contents before attempting conflicting write
    prints_content_before = (tmp_path / "prints.csv").read_bytes()
    series_content_before = (tmp_path / "series.csv").read_bytes()

    # Try to record with different value, no reason
    built2 = build_print(simple(2, 2), None, panel_size=2, **META)
    with pytest.raises(LedgerConflict):
        record_print(tmp_path, "2026-09-14", built2)

    # Verify nothing was written
    assert (tmp_path / "prints.csv").read_bytes() == prints_content_before
    assert (tmp_path / "series.csv").read_bytes() == series_content_before


def test_changed_value_with_reason_appends_new_vintage(tmp_path):
    # Record initial print
    built1 = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built1)

    # Record different value with reason
    built2 = build_print(simple(2, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built2, reason="test update")

    prints = read_rows(tmp_path / "prints.csv")
    assert len(prints) == 2
    assert prints[0]["vintage"] == "1"
    assert prints[1]["vintage"] == "2"
    assert prints[1]["reason"] == "test update"


def test_changed_series_value_with_no_reason_raises_before_prints_touched(tmp_path):
    # Record initial print
    built1 = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built1)

    prints_content_before = (tmp_path / "prints.csv").read_bytes()
    series_content_before = (tmp_path / "series.csv").read_bytes()

    # Create a modified print with different coverage series value
    built2 = build_print(simple(1, 2), None, panel_size=1, **META)
    with pytest.raises(LedgerConflict):
        record_print(tmp_path, "2026-09-14", built2)

    # Verify both files were not touched (validation happened before any write)
    assert (tmp_path / "prints.csv").read_bytes() == prints_content_before
    assert (tmp_path / "series.csv").read_bytes() == series_content_before


def test_denominator_only_change_detected_in_phase_1(tmp_path):
    """Test Finding A: would_conflict catches denominator-only changes (not just value).

    A row with unchanged value and coverage but different denominator should still
    be caught as a conflict if no reason is supplied. This verifies that the
    would_conflict helper uses all of _COMPARED_FIELDS, not just value.
    """
    # Record initial print with 2 conclusive domains
    built1 = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built1)

    prints_content_before = (tmp_path / "prints.csv").read_bytes()
    series_content_before = (tmp_path / "series.csv").read_bytes()

    # Create a print with different denominator but same value (50% stays 50%)
    # This requires different observation counts but same proportions
    built2 = build_print(simple(2, 4), None, panel_size=4, **META)
    # Verify the value is unchanged (both 50%) but denominator differs
    assert float(built2["headline"]["value"]) == float(built1["headline"]["value"])
    assert int(built2["headline"]["denominator"]) != int(built1["headline"]["denominator"])

    # Should raise even without reason, and write nothing
    with pytest.raises(LedgerConflict):
        record_print(tmp_path, "2026-09-14", built2)

    assert (tmp_path / "prints.csv").read_bytes() == prints_content_before
    assert (tmp_path / "series.csv").read_bytes() == series_content_before


def test_both_headline_and_series_conflicts_mentioned_in_error(tmp_path):
    """Test Finding B: conflict error message names all conflicting keys (headline + series).

    When both the headline and at least one series conflict, the raised LedgerConflict
    should mention both so the operator sees the full scope of the restatement.
    """
    # Record initial print
    built1 = build_print(simple(1, 2), None, panel_size=2, **META)
    record_print(tmp_path, "2026-09-14", built1)

    # Try to record with a different value (both headline and coverage series will differ)
    built2 = build_print(simple(2, 2), None, panel_size=2, **META)

    with pytest.raises(LedgerConflict) as exc_info:
        record_print(tmp_path, "2026-09-14", built2)

    error_msg = str(exc_info.value)
    # The error message should reference both prints and series conflicts
    assert "prints" in error_msg or "prints.csv" in error_msg or "index_id" in error_msg
    assert "series" in error_msg or "coverage" in error_msg
