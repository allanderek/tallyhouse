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


def test_bumped_methodology_with_identical_value_is_a_no_op(tmp_path):
    """Methodology version bump that reproduces the same value does not create a vintage.

    This verifies the semantic that vintage represents when the published number changed,
    not when the methodology changed. A later methodology producing the same result leaves
    a record showing the earlier methodology produced it, avoiding vintage churn.
    """
    path = tmp_path / "prints.csv"
    appended = append_row(path, KEY, row("21.4", methodology_version="1"))
    original_methodology = appended["methodology_version"]

    # Later methodology bump, identical value
    result = append_row(path, KEY, row("21.4", methodology_version="2"))
    assert result is None, "No new row written for identical value despite methodology bump"

    # Verify only one row exists and it still shows the original methodology
    rows = read_rows(path)
    assert len(rows) == 1
    assert rows[0]["methodology_version"] == original_methodology


def test_truncated_ledger_line_raises_on_latest(tmp_path):
    """A ledger file with a truncated final line causes latest() to raise, not silently misread.

    This protects against corruption from mid-write crashes. The ledger's purpose is to be
    trustworthy, so corruption must fail loudly.
    """
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))

    # Simulate a mid-write crash: the row is genuinely short, cut off before the
    # vintage column was written. csv fills the missing columns with None, so
    # this exercises the missing-vintage branch rather than the non-integer one.
    with path.open("a") as handle:
        handle.write("agent-accessibility,2026-09-14")

    # latest() should raise, not silently skip or misread the corrupted row
    with pytest.raises(LedgerConflict) as exc_info:
        latest(path, KEY)
    assert str(path) in str(exc_info.value), "Error message should name the corrupted file"
    assert "corrupted" in str(exc_info.value).lower()


def test_non_integer_vintage_raises_on_latest(tmp_path):
    """A row with non-integer vintage causes latest() to raise rather than being skipped.

    Failing loudly on corruption is better than silently tolerating it in a ledger.
    """
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))

    # Manually corrupt the vintage field
    with path.open("a") as handle:
        handle.write("agent-accessibility,2026-09-14,not_an_int,21.9,980,98.0,1,abc123,2026-09-17T00:00:00Z,\n")

    # latest() should raise, not skip the bad row
    with pytest.raises(LedgerConflict) as exc_info:
        latest(path, KEY)
    assert "non-integer vintage" in str(exc_info.value)
    assert str(path) in str(exc_info.value)


def test_header_written_exactly_once_on_new_file(tmp_path):
    """Appending to a brand-new file writes the header exactly once.

    Multiple appends should not duplicate the header.
    """
    path = tmp_path / "prints.csv"
    append_row(path, KEY, row("21.4"))
    append_row(path, KEY, row("22.9"), reason="test")

    with path.open() as handle:
        lines = handle.readlines()

    # Count header-like lines (lines starting with index_id)
    headers = [line for line in lines if line.startswith("index_id")]
    assert len(headers) == 1, "Header should appear exactly once"


def test_zero_byte_file_is_treated_as_new(tmp_path):
    """Appending to a pre-existing zero-byte file writes the header.

    A zero-byte file defeats the is_new check if not handled. This verifies
    that the header is written and subsequent read_rows returns the data,
    not misinterpreting the first row as a header.
    """
    path = tmp_path / "prints.csv"
    # Create an empty file
    path.touch()

    # Append should write header + row
    appended = append_row(path, KEY, row("21.4"))
    assert appended["vintage"] == "1"

    # read_rows should return exactly one data row, not zero
    rows = read_rows(path)
    assert len(rows) == 1
    assert rows[0]["value"] == "21.4"
    # First row should NOT be misinterpreted as header
    assert rows[0]["vintage"] == "1"


def test_three_field_key_round_trips_independently(tmp_path):
    """A multi-field key (index_id + period + series_id) round-trips correctly.

    The ledger serves both prints.csv (2-field key) and series.csv (3-field key).
    This verifies that series_id is added as a column, latest() scopes to the full key,
    and different series_id values maintain independent vintage counters.
    """
    path = tmp_path / "series.csv"

    key1 = {"index_id": "agent-accessibility", "period": "2026-09-14", "series_id": "s1"}
    key2 = {"index_id": "agent-accessibility", "period": "2026-09-14", "series_id": "s2"}

    # First series_id gets vintage 1
    appended1 = append_row(path, key1, row("21.4"))
    assert appended1["vintage"] == "1"
    assert appended1["series_id"] == "s1"

    # Second series_id under same index/period also starts at vintage 1 (independent)
    appended2 = append_row(path, key2, row("22.9"))
    assert appended2["vintage"] == "1"
    assert appended2["series_id"] == "s2"

    # Verify both rows are present
    rows = read_rows(path)
    assert len(rows) == 2

    # Verify header includes series_id
    with path.open() as handle:
        header_line = handle.readline().strip()
    assert "series_id" in header_line

    # latest() for key1 returns s1's data
    latest_s1 = latest(path, key1)
    assert latest_s1["series_id"] == "s1"
    assert latest_s1["value"] == "21.4"

    # latest() for key2 returns s2's data
    latest_s2 = latest(path, key2)
    assert latest_s2["series_id"] == "s2"
    assert latest_s2["value"] == "22.9"


def test_mismatched_key_shape_raises_on_append(tmp_path):
    """Appending a mismatched key shape to an existing file raises and writes nothing.

    Mixed key shapes would silently misalign columns with the header. The fix refuses
    the write to prevent a corrupted ledger.
    """
    path = tmp_path / "ledger.csv"

    # First append with 2-field key
    append_row(path, KEY, row("21.4"))

    # Try to append with 3-field key (mismatched shape)
    mismatched_key = dict(KEY, series_id="s1")

    with pytest.raises(LedgerConflict) as exc_info:
        append_row(path, mismatched_key, row("22.9"), reason="test")

    # Verify the error mentions the file and header mismatch
    assert str(path) in str(exc_info.value)
    assert "header mismatch" in str(exc_info.value).lower()

    # Verify nothing was written
    rows = read_rows(path)
    assert len(rows) == 1
    assert rows[0]["value"] == "21.4"
