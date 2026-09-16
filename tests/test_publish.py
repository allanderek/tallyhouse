from tallyhouse.ledger import read_rows
from tallyhouse.publish import (
    PROVISIONAL_COVERAGE_THRESHOLD,
    build_print,
    record_print,
)

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
