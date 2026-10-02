"""The published CSV downloads.

The property worth most attention is that a download of the ledger *is* the
ledger: the exact bytes committed, not a re-serialisation. The first
implementation failed this invisibly — reading with universal newlines rewrote
the csv module's CRLF endings to LF, so the published file differed from the
committed one by 20 bytes and no diff that ignores line endings would show it.
"""

import csv
import io
import json
from pathlib import Path

from tallyhouse.downloads import catalogue, files, manifest
from tallyhouse.site import write_site


def seed(root: Path, *, period="2026-09-14", crlf=True):
    terminator = "\r\n" if crlf else "\n"
    (root / "prints.csv").write_text(
        f"index_id,period,value{terminator}"
        f'agent-accessibility,{period},23.4{terminator}'
    )
    (root / "series.csv").write_text(
        f"index_id,period,series_id,value{terminator}"
        f"agent-accessibility,{period},coverage,99.7{terminator}"
    )
    (root / "panel").mkdir(parents=True, exist_ok=True)
    (root / "panel" / "2026.json").write_text(json.dumps({
        "year": 2026, "domains": ["b.com", "a.com"],
        "ranks": {"a.com": 1, "b.com": 2},
    }))
    return {
        "index": {"id": "agent-accessibility"},
        "prints": [{"period": period, "value": "23.4"}],
        "verdicts": [
            {"domain": "a.com", "period": period, "agent": "GPTBot", "stance": "FullBlock"},
            {"domain": "a.com", "period": period, "agent": "CCBot", "stance": "Unmentioned"},
        ],
    }


def by_path(entries):
    return {e["path"]: e for e in entries}


def test_the_ledger_download_is_the_committed_bytes(tmp_path):
    data = seed(tmp_path)
    entry = by_path(catalogue(tmp_path, data))["data/prints.csv"]
    with (tmp_path / "prints.csv").open(newline="") as handle:
        assert entry["content"] == handle.read()
    # Specifically including the line endings, which is where this went wrong.
    assert "\r\n" in entry["content"]


def test_writing_the_site_does_not_translate_line_endings(tmp_path):
    data = seed(tmp_path)
    out = tmp_path / "site"
    write_site(files(catalogue(tmp_path, data)), out)
    assert (out / "data" / "prints.csv").read_bytes() == (tmp_path / "prints.csv").read_bytes()


def test_a_panel_download_carries_the_rank_that_is_the_denominator(tmp_path):
    data = seed(tmp_path)
    entry = by_path(catalogue(tmp_path, data))["data/panel-2026-09-14.csv"]
    rows = list(csv.DictReader(io.StringIO(entry["content"])))
    # Ordered by rank rather than by the panel file's order, since rank is what
    # a reader will look something up by.
    assert rows == [{"rank": "1", "domain": "a.com"}, {"rank": "2", "domain": "b.com"}]


def test_a_verdicts_download_has_one_row_per_domain_per_agent(tmp_path):
    data = seed(tmp_path)
    entry = by_path(catalogue(tmp_path, data))["data/verdicts-2026-09-14.csv"]
    rows = list(csv.DictReader(io.StringIO(entry["content"])))
    assert rows == [
        {"domain": "a.com", "period": "2026-09-14", "agent": "CCBot", "stance": "Unmentioned"},
        {"domain": "a.com", "period": "2026-09-14", "agent": "GPTBot", "stance": "FullBlock"},
    ]


def test_per_period_downloads_name_the_latest_published_period(tmp_path):
    data = seed(tmp_path, period="2026-09-28")
    paths = set(by_path(catalogue(tmp_path, data)))
    assert "data/panel-2026-09-28.csv" in paths
    assert "data/verdicts-2026-09-28.csv" in paths


def test_nothing_published_yields_only_what_exists(tmp_path):
    # A checkout with no prints still publishes the ledgers it has, and no
    # per-period file naming a period that does not exist.
    seed(tmp_path)
    entries = catalogue(tmp_path, {"prints": [], "verdicts": []})
    assert set(by_path(entries)) == {"data/prints.csv", "data/series.csv"}


def test_a_missing_ledger_is_omitted_rather_than_published_empty(tmp_path):
    data = seed(tmp_path)
    (tmp_path / "series.csv").unlink()
    assert "data/series.csv" not in by_path(catalogue(tmp_path, data))


def test_the_manifest_describes_each_file_without_carrying_it(tmp_path):
    """The generator renders links and sizes; Python writes the bytes.

    verdicts-<period>.csv is tens of thousands of rows, and pushing it through
    the generator to be handed straight back would cost a megabyte of string for
    nothing.
    """
    data = seed(tmp_path)
    entries = catalogue(tmp_path, data)
    described = by_path(manifest(entries))["data/verdicts-2026-09-14.csv"]
    assert "content" not in described
    assert described["rows"] == 2
    assert described["bytes"] > 0
    assert described["label"] and described["description"]


def test_each_index_owns_its_own_per_period_files(tmp_path):
    """A download must not be offered on the wrong index's page.

    The live panel is 1000 Tranco-qualified domains over a week; the historical
    panel is 611 balanced-panel domains over a quarter. Offering one on the
    other's page hands the reader the wrong population, which is the exact
    conflation this project is built to avoid -- and is what the first version
    of this section did.
    """
    data = seed(tmp_path)
    (tmp_path / "panel" / "historical.json").write_text(json.dumps({
        "domains": ["a.com"], "ranks": {"a.com": {"early": 5, "late": 9}},
    }))
    data["index"] = {"id": "agent-accessibility"}
    data["history"] = {"id": "agent-accessibility-history"}
    owners = {e["path"]: e["index_id"] for e in catalogue(tmp_path, data)}
    # The ledgers carry both indices' rows, filtered by index_id inside the file.
    assert owners["data/prints.csv"] == ""
    assert owners["data/series.csv"] == ""
    assert owners["data/panel-2026-09-14.csv"] == "agent-accessibility"
    assert owners["data/verdicts-2026-09-14.csv"] == "agent-accessibility"
    assert owners["data/panel-historical.csv"] == "agent-accessibility-history"


def test_the_balanced_panel_download_carries_both_endpoint_ranks(tmp_path):
    # Both ranks, because membership resting on two endpoints is the whole
    # construction of that panel.
    data = seed(tmp_path)
    (tmp_path / "panel" / "historical.json").write_text(json.dumps({
        "domains": ["a.com"], "ranks": {"a.com": {"early": 5, "late": 9}},
    }))
    data["index"] = {"id": "agent-accessibility"}
    data["history"] = {"id": "agent-accessibility-history"}
    entry = by_path(catalogue(tmp_path, data))["data/panel-historical.csv"]
    rows = list(csv.DictReader(io.StringIO(entry["content"])))
    assert rows == [{"rank_late": "9", "rank_early": "5", "domain": "a.com"}]


def test_no_balanced_panel_file_without_a_historical_index(tmp_path):
    data = seed(tmp_path)
    data["index"] = {"id": "agent-accessibility"}
    assert "data/panel-historical.csv" not in by_path(catalogue(tmp_path, data))
