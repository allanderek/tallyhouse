import pytest

from tallyhouse.ledger import LedgerConflict, append_row, latest, read_rows

KEY = {"index_id": "agent-accessibility", "period": "2026-09-14"}


def row(value, **extra):
    base = {
        "value": value,
        "denominator": "980",
        "coverage": "98.0",
        "methodology_version": "1",
        "collector_version": "abc123",
        "computed_at": "2026-09-17T00:00:00Z",
    }
    base.update(extra)
    return base


def test_first_print_is_vintage_one(tmp_path):
    path = tmp_path / "prints.csv"
    appended = append_row(path, KEY, row("21.4"))
    assert appended["vintage"] == "1"
    assert appended["reason"] == ""


def test_identical_recomputation_is_a_no_op(tmp_path):
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    assert append_row(path, KEY, row("21.4")) is None
    assert len(read_rows(path)) == 1


def test_changed_value_without_a_reason_is_refused(tmp_path):
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    with pytest.raises(LedgerConflict):
        append_row(path, KEY, row("22.9"))
    # The published number must survive the refused write.
    assert read_rows(path)[0]["value"] == "21.4"


def test_changed_value_with_a_reason_appends_a_new_vintage(tmp_path):
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    appended = append_row(path, KEY, row("22.9"), reason="parser fix: Allow precedence")
    assert appended["vintage"] == "2"
    assert appended["reason"] == "parser fix: Allow precedence"
    rows = read_rows(path)
    assert len(rows) == 2
    assert rows[0]["value"] == "21.4"  # vintage 1 is untouched


def test_latest_returns_the_highest_vintage(tmp_path):
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    append_row(path, KEY, row("22.9"), reason="restated")
    assert latest(path, KEY)["value"] == "22.9"


def test_periods_are_independent(tmp_path):
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    other = dict(KEY, period="2026-09-21")
    assert append_row(path, other, row("21.9"))["vintage"] == "1"


def test_latest_of_an_unknown_key_is_none(tmp_path):
    assert latest(tmp_path / "prints.csv", KEY) is None
